import asyncio
import os
import time

from astrbot.api import logger
from astrbot.api.all import *  # noqa: F403
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import *  # noqa: F403
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star

from .backend import (
    CategoryManager,
    CommandsHandler,
    EventHandlers,
    MemeConfigMixin,
    migrate_old_persona_tags_if_needed,
    patch_onebot_serializer,
    register_apis,
    reload_personas,
    sync_similarity_features,
    sync_tag_embeddings,
)
from .config import MEMES_DATA_PATH, MEMES_DIR
from .image_host.img_sync import ImageSync
from .init import init_plugin

_meme_sender_instance = None


class MemeSender(Star, MemeConfigMixin):
    context: Context

    def __init__(self, context: Context, config: dict | None = None):
        global _meme_sender_instance
        _meme_sender_instance = self
        super().__init__(context)
        self.config = config or {}
        migrate_old_persona_tags_if_needed(self.config)

        # Patch OneBot event serializer for sticker support
        patch_onebot_serializer()

        # Initialize plugin directories and default files
        if not init_plugin():
            raise RuntimeError("插件初始化失败")

        # Initialize category manager
        self.category_manager = CategoryManager()
        try:
            self._last_mtime = os.path.getmtime(MEMES_DATA_PATH)
        except Exception:
            self._last_mtime = 0

        # Initialize image host sync client
        self.img_sync = None
        image_host_type = self.config.get("image_host", "stardots")

        if image_host_type == "stardots":
            stardots_config = self.config.get("image_host_config", {}).get(
                "stardots", {}
            )
            if stardots_config.get("key") and stardots_config.get("secret"):
                stardots_config["provider"] = "stardots"
                self.img_sync = ImageSync(
                    config={
                        "key": stardots_config["key"],
                        "secret": stardots_config["secret"],
                        "space": stardots_config.get("space", "memes"),
                        "provider": "stardots",
                    },
                    local_dir=MEMES_DIR,
                    provider_type="stardots",
                )
        elif image_host_type == "cloudflare_r2":
            r2_config = self.config.get("image_host_config", {}).get(
                "cloudflare_r2", {}
            )
            required_fields = [
                "account_id",
                "access_key_id",
                "secret_access_key",
                "bucket_name",
            ]
            if all(r2_config.get(field) for field in required_fields):
                if r2_config.get("public_url"):
                    r2_config["public_url"] = r2_config["public_url"].rstrip("/")
                r2_config["provider"] = "cloudflare_r2"
                self.img_sync = ImageSync(
                    config=r2_config, local_dir=MEMES_DIR, provider_type="cloudflare_r2"
                )
                self._r2_bucket_name = r2_config.get("bucket_name")

        # Initialize state properties
        self.found_emotions = []
        self.upload_states = {}
        self.pending_images = {}
        self.auto_steal_semaphore = asyncio.Semaphore(2)

        # Register all Web APIs and serve static endpoint
        register_apis(self)

        if hasattr(self, "_r2_bucket_name"):
            logger.info(f"Cloudflare R2 图床已初始化: {self._r2_bucket_name}")
            delattr(self, "_r2_bucket_name")

        # Setup and inject persona prompt instructions
        self.persona_prompts_backup = {}
        self._reload_personas()

        # Activate or deactivate LLM tool based on settings
        try:
            if self.enable_llm_tool in ("tool", "hybrid"):
                self.context.activate_llm_tool("send_meme")
            else:
                self.context.deactivate_llm_tool("send_meme")
        except Exception as e:
            logger.warning(f"[meme_manager] 无法激活/停用 LLM 发图工具: {e}")

        # Start background tag embedding and similarity feature synchronization
        asyncio.create_task(sync_tag_embeddings(self))
        asyncio.create_task(sync_similarity_features(self))

    @property
    def category_mapping(self) -> dict[str, str]:
        """Backward compatibility property: returns all categories with empty string values."""
        return dict.fromkeys(self.category_manager.get_categories(), "")

    def _reload_personas(self):
        """Reload meme settings and inject prompt instructions into registered personas."""
        reload_personas(self)

    async def reload_emotions(self):
        """Dynamically reload meme configuration settings."""
        try:
            self.category_manager.sync_with_filesystem()
            self._reload_personas()
            asyncio.create_task(sync_tag_embeddings(self))
            try:
                self._last_mtime = os.path.getmtime(MEMES_DATA_PATH)
            except Exception:
                self._last_mtime = 0
        except Exception as e:
            logger.error(f"重新加载表情配置失败: {str(e)}")

    async def check_and_reload_if_changed(self):
        """Check configuration file modification time and reload if changed."""
        try:
            current_mtime = os.path.getmtime(MEMES_DATA_PATH)
            if current_mtime != self._last_mtime:
                logger.info(
                    "[meme_manager] 检测到分类配置文件有变动，正在自动重新加载..."
                )
                self._last_mtime = current_mtime
                self.category_manager.categories = (
                    self.category_manager._load_categories()
                )
                self._reload_personas()
        except Exception as e:
            logger.error(f"[meme_manager] 检查自动重载失败: {e}")

    @filter.command_group("表情管理")
    def meme_manager(self):
        pass

    @meme_manager.command("查看图库")
    async def list_emotions(self, event: AstrMessageEvent):
        """查看所有可用表情包标签"""
        await self.check_and_reload_if_changed()
        async for res in CommandsHandler.list_emotions(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("添加表情")
    async def upload_meme(self, event: AstrMessageEvent, tags: str | None = None):
        """上传表情包并标记指定标签"""
        async for res in CommandsHandler.upload_meme(self, event, tags):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("清空全部")
    async def clear_all_emojis_command(self, event: AstrMessageEvent):
        """清空所有表情包与所有标签配置，以及标签向量缓存。"""
        async for res in CommandsHandler.clear_all_emojis_command(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("删除标签")
    async def delete_tag_command(self, event: AstrMessageEvent, tag: str | None = None):
        """删除指定标签，移除标签配置及其下表情包的此标签归属（无标签表情将被彻底删除）"""
        async for res in CommandsHandler.delete_tag_command(self, event, tag):
            yield res

    @meme_manager.command("同步状态")
    async def check_sync_status(
        self, event: AstrMessageEvent, detail: str | None = None
    ):
        """检查表情包与图床的同步状态"""
        async for res in CommandsHandler.check_sync_status(self, event, detail):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("同步到云端")
    async def sync_to_remote(self, event: AstrMessageEvent):
        """将本地表情包同步到云端"""
        async for res in CommandsHandler.sync_to_remote(self, event):
            yield res

    @meme_manager.command("图库统计")
    async def show_library_stats(self, event: AstrMessageEvent):
        """显示图库详细统计信息"""
        async for res in CommandsHandler.show_library_stats(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("从云端同步")
    async def sync_from_remote(self, event: AstrMessageEvent):
        """从云端同步表情包到本地"""
        async for res in CommandsHandler.sync_from_remote(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("覆盖到云端")
    async def overwrite_to_remote(self, event: AstrMessageEvent):
        """让云端完全和本地一致（会删除云端多出的图）"""
        async for res in CommandsHandler.overwrite_to_remote(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("从云端覆盖")
    async def overwrite_from_remote(self, event: AstrMessageEvent):
        """让本地完全和云端一致（会删除本地多出的图）"""
        async for res in CommandsHandler.overwrite_from_remote(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("压缩现有表情")
    async def compress_existing_memes(self, event: AstrMessageEvent):
        """手动压缩所有已存在的表情包文件"""
        async for res in CommandsHandler.compress_existing_memes(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("重构向量缓存")
    async def rebuild_tag_embeddings(self, event: AstrMessageEvent):
        """清空缓存的标签向量并重新计算"""
        async for res in CommandsHandler.rebuild_tag_embeddings(self, event):
            yield res

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_upload_image(self, event: AstrMessageEvent):
        """处理用户上传 of 图片"""
        await self.check_and_reload_if_changed()
        async for res in EventHandlers.handle_upload_image(self, event):
            yield res

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_direct_meme_trigger(self, event: AstrMessageEvent):
        """监听 <emotions>标签</emotions> 直接触发表情包发送，绕过 LLM"""
        await self.check_and_reload_if_changed()
        async for res in EventHandlers.handle_direct_meme_trigger(self, event):
            yield res

    @filter.event_message_type(EventMessageType.ALL)
    async def cache_last_image(self, event: AstrMessageEvent):
        """缓存各会话最近收到的图片，供 steal_meme 在当前消息/引用均无图时回退取图。"""
        images = [c for c in event.message_obj.message if isinstance(c, Image)]
        if not images:
            return
        if not hasattr(self, "_session_last_image"):
            self._session_last_image = {}

        # Clean up expired caches (TTL = 300s) to prevent memory accumulation
        now = time.time()
        expired_keys = [
            k
            for k, v in self._session_last_image.items()
            if (now - v.get("ts", 0)) > 300
        ]
        for k in expired_keys:
            self._session_last_image.pop(k, None)

        img_bytes = None
        try:
            img_bytes = await images[-1].convert_to_base64()
        except Exception as e:
            logger.warning(f"[meme_manager] 缓存图片数据失败: {e}")

        self._session_last_image[event.unified_msg_origin] = {
            "url": images[-1].url,
            "bytes": img_bytes,
            "ts": now,
        }

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_group_message(self, event: AstrMessageEvent):
        """处理群聊消息以实现暗中自动偷表情包"""
        if not self.auto_steal_enabled:
            return

        # 1. 检查是否为图片消息
        images = [c for c in event.message_obj.message if isinstance(c, Image)]
        if not images:
            return

        # 2. 概率判定
        import random

        probability = self.auto_steal_probability
        if random.randint(1, 100) > probability:
            logger.debug(f"[meme_manager] 自动偷图概率未命中: {probability}%")
            return

        # 3. 检查多模态模型是否启用
        if not self.multimodal_llm_enabled:
            logger.debug(
                "[meme_manager] 未开启多模态大模型分类表情包，跳过自动偷表情。"
            )
            return

        # 4. 执行暗中自动偷表情包（带并发限制）
        await self.check_and_reload_if_changed()

        async def run_steal_task():
            async with self.auto_steal_semaphore:
                await EventHandlers.auto_steal_meme(self, event)

        asyncio.create_task(run_steal_task())

    @filter.on_llm_response(priority=99999)
    async def resp(self, event: AstrMessageEvent, response: LLMResponse):
        """处理 LLM 响应，识别表情"""
        await self.check_and_reload_if_changed()
        await EventHandlers.resp(self, event, response)

    @filter.on_decorating_result(priority=99999)
    async def on_decorating_result(self, event: AstrMessageEvent):
        """在消息发送前清理文本中的表情标签，并添加表情图片"""
        await self.check_and_reload_if_changed()
        await EventHandlers.on_decorating_result(self, event)

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        """消息发送后处理。用于发送未混合的表情图片。"""
        await EventHandlers.after_message_sent(self, event)

    @llm_tool(name="steal_meme")
    async def steal_meme(
        self,
        event: AstrMessageEvent,
        categories: list[str] | None = None,
        category: str | None = None,
        description: str | None = None,
    ):
        """保存并收录聊天中的表情包到表情包库中。

        Args:
            categories(list): 表情分类列表（如 ['开心']）。仅在用户明确指定了分类时传入，否则不传。
            category(string): 表情分类。单标签兼容，仅在用户明确指定了分类时传入，否则不传。
            description(string): 表情包画面的简洁描述。仅在用户明确指定了描述时传入，否则不传。
        """
        await self.check_and_reload_if_changed()
        if not categories and category:
            categories = [category]
        return await EventHandlers.steal_meme(
            self, event, categories, description=description
        )

    @llm_tool(name="send_meme")
    async def send_meme(
        self,
        event: AstrMessageEvent,
        query: str | None = None,
        index: int | None = None,
    ):
        """搜索并发送表情包。

        Args:
            query(string): 检索关键词/表情标签。支持逗号分隔多个标签（如 '猫猫, 得意'），标签顺序会影响匹配权重，越靠前的标签权重越高、对结果影响越大。
            index(number): 选中的候选表情包序号（从 1 开始）。确定发送特定表情时传入。
        """
        await self.check_and_reload_if_changed()
        from .backend import send_meme

        return await send_meme(self, event, query, index)

    async def terminate(self):
        """清理资源"""
        personas = self.context.provider_manager.personas
        if hasattr(self, "persona_prompts_backup"):
            for persona in personas:
                name = persona.get("name") or ""
                if name in self.persona_prompts_backup:
                    persona["prompt"] = self.persona_prompts_backup[name]

        if self.img_sync:
            self.img_sync.stop_sync()
