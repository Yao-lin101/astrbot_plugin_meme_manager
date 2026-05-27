import os

from astrbot.api import logger
from astrbot.api.all import *  # noqa: F403
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import *  # noqa: F403
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register

from .backend.category_manager import CategoryManager
from .backend.commands_handler import CommandsHandler
from .backend.event_handlers import EventHandlers
from .backend.webui_manager import WebuiManager
from .config import MEMES_DATA_PATH, MEMES_DIR
from .image_host.img_sync import ImageSync
from .init import init_plugin


@register(
    "meme_manager", "anka", "anka - 表情包管理器 - 支持表情包发送及表情包上传", "3.20"
)
class MemeSender(Star):
    context: Context

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}

        # 初始化插件
        if not init_plugin():
            raise RuntimeError("插件初始化失败")

        # 初始化类别管理器
        self.category_manager = CategoryManager()
        try:
            self._last_mtime = os.path.getmtime(MEMES_DATA_PATH)
        except Exception:
            self._last_mtime = 0

        # 初始化图床同步客户端
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

        # 用于管理服务器
        self.webui_process = None

        self.server_key = None
        self.server_port = self.config.get("webui_port", 5000)

        # 初始化表情状态
        self.found_emotions = []
        self.upload_states = {}
        self.pending_images = {}

        # 所有的配置属性现在通过下方的 @property 动态获取，以便在 WebUI 修改设置后实时生效
        pass

        if hasattr(self, "_r2_bucket_name"):
            logger.info(f"Cloudflare R2 图床已初始化: {self._r2_bucket_name}")
            delattr(self, "_r2_bucket_name")

        # 构建表情包提示词
        self.persona_prompts_backup = {}
        self._reload_personas()

    @property
    def category_mapping(self) -> dict[str, str]:
        """向后兼容属性：返回所有分类，值为空字符串（模拟字典结构）"""
        return dict.fromkeys(self.category_manager.get_categories(), "")

    def _reload_personas(self):
        """重新加载表情配置并构建提示词并注入全局人格"""
        personas = self.context.provider_manager.personas

        if not hasattr(self, "persona_prompts_backup"):
            self.persona_prompts_backup = {}

        for persona in personas:
            name = persona.get("name") or ""
            if name not in self.persona_prompts_backup:
                self.persona_prompts_backup[name] = persona.get("prompt") or ""

        if self.emotion_llm_enabled:
            for persona in personas:
                name = persona.get("name") or ""
                persona["prompt"] = self.persona_prompts_backup.get(name, "")
            return

        from .backend.database import get_db_conn

        for persona in personas:
            name = persona.get("name") or ""
            original_prompt = self.persona_prompts_backup.get(name, "")
            persona_id = persona.get("id") or name or ""

            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT emotions FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
                (f"%,{persona_id},%",),
            )
            rows = cursor.fetchall()
            conn.close()

            allowed_categories = set()
            for row in rows:
                if row["emotions"]:
                    for emo in row["emotions"].split(","):
                        emo = emo.strip()
                        if emo:
                            allowed_categories.add(emo)

            if not allowed_categories:
                persona["prompt"] = original_prompt
                continue

            allowed_categories_string = ", ".join(sorted(allowed_categories))
            sys_prompt_add = (
                self.prompt_head
                + allowed_categories_string
                + self.prompt_tail_1
                + str(self.max_emotions_per_message)
                + self.prompt_tail_2
            )
            persona["prompt"] = original_prompt + sys_prompt_add

    async def reload_emotions(self):
        """动态重新加载表情配置"""
        try:
            self.category_manager.sync_with_filesystem()
            self._reload_personas()
            try:
                self._last_mtime = os.path.getmtime(MEMES_DATA_PATH)
            except Exception:
                self._last_mtime = 0
        except Exception as e:
            logger.error(f"重新加载表情配置失败: {str(e)}")

    async def check_and_reload_if_changed(self):
        """检查配置文件修改时间，如果有变动则自动重载分类和系统提示词"""
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("开启管理后台")
    async def start_webui(self, event: AstrMessageEvent):
        """启动表情包管理服务器"""
        async for res in WebuiManager.start_webui(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("关闭管理后台")
    async def stop_server(self, event: AstrMessageEvent):
        """关闭表情包管理服务器的指令"""
        async for res in WebuiManager.stop_server(self, event):
            yield res

    @meme_manager.command("查看图库")
    async def list_emotions(self, event: AstrMessageEvent):
        """查看所有可用表情包类别"""
        await self.check_and_reload_if_changed()
        async for res in CommandsHandler.list_emotions(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("添加表情")
    async def upload_meme(self, event: AstrMessageEvent, category: str | None = None):
        """上传表情包到指定类别"""
        async for res in CommandsHandler.upload_meme(self, event, category):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("恢复默认表情包")
    async def restore_default_memes_command(
        self, event: AstrMessageEvent, category: str | None = None
    ):
        """恢复内置默认表情包，可指定类别或恢复全部。"""
        async for res in CommandsHandler.restore_default_memes_command(
            self, event, category
        ):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("清空指定类型")
    async def clear_category_command(
        self, event: AstrMessageEvent, category: str | None = None
    ):
        """清空指定类型下的所有表情包，但保留类型本身。"""
        async for res in CommandsHandler.clear_category_command(self, event, category):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("清空全部")
    async def clear_all_emojis_command(self, event: AstrMessageEvent):
        """清空所有类型下的表情包，但保留类型和描述配置。"""
        async for res in CommandsHandler.clear_all_emojis_command(self, event):
            yield res

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("删除类型本身")
    async def delete_category_command(
        self, event: AstrMessageEvent, category: str | None = None
    ):
        """删除指定类型本身，同时移除其描述配置和本地文件夹。"""
        async for res in CommandsHandler.delete_category_command(self, event, category):
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

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_upload_image(self, event: AstrMessageEvent):
        """处理用户上传 of 图片"""
        await self.check_and_reload_if_changed()
        async for res in EventHandlers.handle_upload_image(self, event):
            yield res

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
    ):
        """保存并收录上一条聊天记录中发送的表情包到当前人格的表情包库中。

        Args:
            categories(list): 表情包所属的类别列表，如 ["happy", "sad"] 等。注意：只有当用户在指令中明确指定了具体分类名称（例如“收录到 happy 分类中”）时才传入此参数；如果用户只是说“偷图/收录”或未明确指定，请保持此参数为 None，严禁自行推测或生成分类。
            category(string): 同上，表情包所属的类别（单标签兼容，仅在用户明确指定时传入，否则不传）
        """
        await self.check_and_reload_if_changed()
        if not categories and category:
            categories = [category]
        return await EventHandlers.steal_meme(self, event, categories)

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

        await WebuiManager._shutdown(self)
        await WebuiManager._cleanup_resources(self)

    @property
    def fault_tolerant_symbols(self) -> list[str]:
        return self.config.get("fault_tolerant_symbols", ["⬡"])

    @property
    def prompt_head(self) -> str:
        return self.config.get("prompt", {}).get("prompt_head", "")

    @property
    def prompt_tail_1(self) -> str:
        return self.config.get("prompt", {}).get("prompt_tail_1", "")

    @property
    def prompt_tail_2(self) -> str:
        return self.config.get("prompt", {}).get("prompt_tail_2", "")

    @property
    def max_emotions_per_message(self) -> int:
        return self.config.get("max_emotions_per_message", 2)

    @property
    def emotions_probability(self) -> int:
        return self.config.get("emotions_probability", 50)

    @property
    def strict_max_emotions_per_message(self) -> bool:
        return self.config.get("strict_max_emotions_per_message", True)

    @property
    def emotion_llm_enabled(self) -> bool:
        return self.config.get("emotion_llm_enabled", False)

    @property
    def emotion_llm_provider_id(self) -> str:
        return self.config.get("emotion_llm_provider_id", "")

    @property
    def multimodal_llm_enabled(self) -> bool:
        return self.config.get("multimodal_llm_enabled", False)

    @property
    def multimodal_llm_provider_id(self) -> str:
        return self.config.get("multimodal_llm_provider_id", "")

    @property
    def enable_mixed_message(self) -> bool:
        return self.config.get("enable_mixed_message", True)

    @property
    def mixed_message_probability(self) -> int:
        return self.config.get("mixed_message_probability", 80)

    @property
    def remove_invalid_alternative_markup(self) -> bool:
        return self.config.get("remove_invalid_alternative_markup", False)

    @property
    def convert_static_to_gif(self) -> bool:
        return self.config.get("convert_static_to_gif", False)

    @property
    def streaming_compatibility(self) -> bool:
        return self.config.get("streaming_compatibility", False)

    @property
    def content_cleanup_rule(self) -> str:
        return self.config.get("content_cleanup_rule", "&&[a-zA-Z]*&&")
