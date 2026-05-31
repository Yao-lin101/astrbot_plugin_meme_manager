import asyncio
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
from .backend.helpers import get_persona_setting, migrate_old_persona_tags_if_needed
from .config import MEMES_DATA_PATH, MEMES_DIR
from .image_host.img_sync import ImageSync
from .init import init_plugin
from .utils import get_config_value


@register(
    "meme_manager", "anka", "anka - 表情包管理器 - 支持表情包发送及表情包上传", "3.20"
)
class MemeSender(Star):
    context: Context

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        migrate_old_persona_tags_if_needed(self.config)

        # Monkeypatch OneBot image serializer to support sticker (subType=1) format
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            original_from_segment_to_dict = AiocqhttpMessageEvent._from_segment_to_dict

            async def patched_from_segment_to_dict(segment) -> dict:
                res = await original_from_segment_to_dict(segment)
                if res.get("type") == "image":
                    sub_type = getattr(segment, "sub_type", None)
                    if sub_type is None:
                        sub_type = getattr(segment, "subType", None)
                    if sub_type is None:
                        sub_type = getattr(segment, "subtype", None)
                    if sub_type is not None:
                        # Compatible with go-cqhttp (subType) and NapCat/Lagrange (sub_type, subtype)
                        data = res.setdefault("data", {})
                        data["subType"] = sub_type
                        data["sub_type"] = sub_type
                        data["subtype"] = sub_type
                return res

            AiocqhttpMessageEvent._from_segment_to_dict = patched_from_segment_to_dict
            logger.info(
                "Meme Manager: Successfully patched AiocqhttpMessageEvent._from_segment_to_dict for sticker support"
            )
        except Exception as e:
            logger.warning(
                f"Meme Manager: Failed to patch OneBot image serializer: {e}"
            )

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

        # 初始化表情状态
        self.found_emotions = []
        self.upload_states = {}
        self.pending_images = {}
        self.auto_steal_semaphore = asyncio.Semaphore(
            2
        )  # 限制并发自动偷图的协程数量为 2

        # 所有的配置属性现在通过下方的 @property 动态获取，以便在 WebUI 修改设置后实时生效
        pass

        # 注册 Web APIs
        from .backend.api import (
            add_emoji,
            batch_convert_emoji_gif,
            batch_copy_emoji,
            batch_delete_emoji,
            batch_edit_personas,
            batch_import_emojis,
            batch_move_emoji,
            check_duplicates,
            check_sync_process,
            clear_all_emoji,
            clear_category,
            delete_category,
            delete_emoji,
            edit_emoji,
            get_all_emojis,
            get_emoji_file_base64,
            get_emoji_info,
            get_emojis_by_category,
            get_emotions,
            get_img_host_sync_status,
            get_persona_tags,
            get_personas,
            get_sync_status,
            move_emoji,
            rename_category,
            resolve_duplicates,
            restore_category,
            save_persona_tag,
            sync_config,
            sync_from_remote,
            sync_to_remote,
        )

        PLUGIN_NAME = "astrbot_plugin_meme_manager"

        apis = [
            ("emoji", get_all_emojis, ["GET"]),
            ("emoji/add", add_emoji, ["POST"]),
            ("emoji/delete", delete_emoji, ["POST"]),
            ("emoji/batch_delete", batch_delete_emoji, ["POST"]),
            ("emoji/batch_convert_gif", batch_convert_emoji_gif, ["POST"]),
            ("emoji/move", move_emoji, ["POST"]),
            ("emoji/batch_move", batch_move_emoji, ["POST"]),
            ("emoji/batch_copy", batch_copy_emoji, ["POST"]),
            ("category/clear", clear_category, ["POST"]),
            ("emoji/clear_all", clear_all_emoji, ["POST"]),
            ("emotions", get_emotions, ["GET"]),
            ("category/delete", delete_category, ["POST"]),
            ("sync/status", get_sync_status, ["GET"]),
            ("sync/config", sync_config, ["POST"]),
            ("category/restore", restore_category, ["POST"]),
            ("category/rename", rename_category, ["POST"]),
            ("img_host/sync/status", get_img_host_sync_status, ["GET"]),
            ("img_host/sync/upload", sync_to_remote, ["POST"]),
            ("img_host/sync/download", sync_from_remote, ["POST"]),
            ("img_host/sync/check_process", check_sync_process, ["GET"]),
            ("personas", get_personas, ["GET"]),
            ("emoji/edit", edit_emoji, ["POST"]),
            ("emoji/info/<filename>", get_emoji_info, ["GET"]),
            ("emoji/batch_edit_personas", batch_edit_personas, ["POST"]),
            ("persona_tags", get_persona_tags, ["GET"]),
            ("persona_tags", save_persona_tag, ["POST"]),
            ("emoji/batch_import", batch_import_emojis, ["POST"]),
            ("emoji/file_base64", get_emoji_file_base64, ["GET"]),
            ("emoji/dup/check", check_duplicates, ["GET"]),
            ("emoji/dup/resolve", resolve_duplicates, ["POST"]),
            ("emoji/<category>", get_emojis_by_category, ["GET"]),
        ]

        for route, handler, methods in apis:
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/{route}",
                self.wrap_api_handler(handler),
                methods,
                f"Meme Manager API: {route}",
            )

        # 注册表情文件服务接口
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/memes/<category>/<filename>",
            self.serve_emoji,
            ["GET"],
            "Serve emoji files",
        )

        if hasattr(self, "_r2_bucket_name"):
            logger.info(f"Cloudflare R2 图床已初始化: {self._r2_bucket_name}")
            delattr(self, "_r2_bucket_name")

        # 构建表情包提示词
        self.persona_prompts_backup = {}
        self._reload_personas()

        # 根据配置激活或停用 LLM 工具
        try:
            if self.enable_llm_tool:
                self.context.activate_llm_tool("send_meme")
            else:
                self.context.deactivate_llm_tool("send_meme")
        except Exception as e:
            logger.warning(f"[meme_manager] 无法激活/停用 LLM 发图工具: {e}")

        # 初始化标签向量与表情相似度特征
        from .backend.emotion_handler import sync_tag_embeddings
        from .backend.similarity import sync_similarity_features

        asyncio.create_task(sync_tag_embeddings(self))
        asyncio.create_task(sync_similarity_features(self))

    def wrap_api_handler(self, handler):
        async def wrapper(*args, **kwargs):
            from quart import current_app

            # Register the dynamic unauthenticated serve_emoji route on app startup/first request
            app = current_app._get_current_object()
            route_name = "meme_manager_serve_emoji"
            if route_name not in app.view_functions:
                app.add_url_rule(
                    "/api/file/meme_manager/memes/<category>/<filename>",
                    endpoint=route_name,
                    view_func=self.serve_emoji,
                    methods=["GET"],
                )

            current_app.config["PLUGIN_CONFIG"] = {
                "sender": self,
                "img_sync": self.img_sync,
                "category_manager": self.category_manager,
                "plugin_config": self.config,
                "personas": [
                    {
                        "id": p.get("id") or p.get("name") or "",
                        "name": p.get("name") or "",
                        "prompt": p.get("prompt") or "",
                    }
                    for p in self.context.provider_manager.personas
                ]
                if hasattr(self.context, "provider_manager")
                else [],
                "context": self.context,
            }
            return await handler(*args, **kwargs)

        return wrapper

    async def serve_emoji(self, category, filename):
        import os

        from quart import send_from_directory

        from .config import MEMES_DIR

        # Check absolute location directly under MEMES_DIR
        target_path = os.path.join(MEMES_DIR, filename)
        if os.path.exists(target_path):
            return await send_from_directory(MEMES_DIR, filename)

        # Check category path
        if category != "file" and category != "all":
            category_path = os.path.join(MEMES_DIR, category)
            if os.path.exists(os.path.join(category_path, filename)):
                return await send_from_directory(category_path, filename)

        # Search all subdirectories inside MEMES_DIR
        for item in os.listdir(MEMES_DIR):
            item_path = os.path.join(MEMES_DIR, item)
            if os.path.isdir(item_path):
                file_path = os.path.join(item_path, filename)
                if os.path.exists(file_path):
                    return await send_from_directory(item_path, filename)

        return "File not found: " + filename, 404

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

        format_instruction = (
            "\n\n<meme_formatting_instructions>\n"
            "【输出格式要求（极其重要）】:\n"
            "你必须在回复的【最末尾】且【单独一行】输出一个固定格式的表情标记块：<emotions>标签1, 标签2, ...</emotions>（例如 <emotions>得意, 摸头, 猫猫</emotions>，用英文逗号 `,` 分隔）。不要分散在正文多处。若当前回复不需要表情包，则不要输出此标签块。\n"
            "</meme_formatting_instructions>"
        )

        tool_instruction = (
            "\n\n<meme_tool_instructions>\n"
            "【表情包工具发送指引（极其重要）】:\n"
            "你拥有发送本地表情包的专属工具 `send_meme`。在对话过程中，为了活跃气氛或展现你的个性，你应该根据当前的聊天氛围、你的人格设定以及表情包使用偏好（供参考），积极、自然地使用此工具发送表情包。\n"
            "工具调用必须遵循以下两步工作流：\n"
            "1. 检索候选：先调用 `send_meme(query='检索词')`（不传 `index` 参数）来搜索候选表情包列表。强烈建议并鼓励你使用多个由英文逗号分隔的检索词（例如 '猫猫, 开心, 撒娇'）以进行多标签精准检索，这更有助于精准且切合语境地匹配表情包。\n"
            "2. 选择并发送：阅读检索返回的表情包候选列表，选择其中最符合当前语境的一个，然后再次调用 `send_meme(query='检索词', index=选择的序号)`（如 index=1）正式发送表情包。\n"
            "注意：在单次回复中，你可以多次调用本工具进行检索或发送，但严禁使用其他任何外部网络搜索或画图工具发图。\n"
            "</meme_tool_instructions>"
        )

        for persona in personas:
            name = persona.get("name") or ""
            persona_id = persona.get("id") or ""
            blacklist = self.config.get("persona_blacklist", [])
            if name in blacklist or persona_id in blacklist:
                if name in self.persona_prompts_backup:
                    persona["prompt"] = self.persona_prompts_backup[name]
                continue

            original_prompt = self.persona_prompts_backup.get(name, "")

            # 从配置中获取该人格的偏好
            pref = get_persona_setting(
                self.config, persona_id, "meme_preference"
            ) or get_persona_setting(self.config, name, "meme_preference")
            use_pref = get_persona_setting(
                self.config, persona_id, "meme_use_preference"
            ) or get_persona_setting(self.config, name, "meme_use_preference")

            pref_prompt = ""
            if pref:
                pref_prompt += f"<meme_preference>{pref}</meme_preference>"
            if use_pref:
                if pref_prompt:
                    pref_prompt += "\n"
                pref_prompt += f"<meme_use_preference>{use_pref}</meme_use_preference>"

            injected_prompt = original_prompt
            if pref_prompt:
                injected_prompt += "\n\n" + pref_prompt

            if self.enable_llm_tool:
                persona["prompt"] = injected_prompt + tool_instruction
            else:
                behavior_prompt = f"\n\n<meme_behavior_instructions>\n{self.meme_prompt}\n</meme_behavior_instructions>"
                persona["prompt"] = (
                    injected_prompt + behavior_prompt + format_instruction
                )

    async def reload_emotions(self):
        """动态重新加载表情配置"""
        try:
            self.category_manager.sync_with_filesystem()
            self._reload_personas()
            from .backend.emotion_handler import sync_tag_embeddings

            asyncio.create_task(sync_tag_embeddings(self))
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
        """保存并收录上一条聊天记录中发送的表情包到当前人格的表情包库中。

        Args:
            categories(list): 表情包所属的类别列表，如 ["happy", "sad"] 等。注意：只有当用户在指令中明确指定了具体分类名称（例如“收录到 happy 分类中”）时才传入此参数；如果用户只是说“偷图/收录”或未明确指定，请保持此参数为 None，严禁自行推测或生成分类。
            category(string): 同上，表情包所属的类别（单标签兼容，仅在用户明确指定时传入，否则不传）
            description(string): 对这张表情包画面的简洁描述，请用简短的一句话描述该图内容（如 "一只摊在地上表情无语的猫猫" 或 "熊猫头双手抱头表示痛苦"）。此参数对于表情包的后续精准检索和描述匹配至关重要！
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
        query: str,
        index: int | None = None,
    ):
        """搜索并发送表情包。

        Args:
            query(string): 检索表情包的标签。支持并鼓励传入多个由英文逗号分隔的标签（如 '猫猫, 开心, 撒娇'）以进行多标签精准检索，这也更容易精准匹配图库中的表情包。
            index(number): 选中的表情包序号（从 1 开始）。如果首次调用或需要展示候选列表供选择，请不要进行传值；如果已获得候选列表，请传入选中的序号进行发送。
        """
        await self.check_and_reload_if_changed()

        from .backend.helpers import get_persona_id

        persona_id = await get_persona_id(self, event)

        from .backend.emotion_handler import search_memes_for_llm

        candidates = await search_memes_for_llm(self, query, persona_id)

        if not candidates:
            return f"未找到与标签 '{query}' 相关的表情包，请尝试其他的关键词检索。"

        # Group candidates to avoid duplicates and implement selection logic.
        display_groups = []
        desc_lookup = {}
        tags_lookup = {}

        for c in candidates:
            desc = c.get("description")
            if desc and desc.strip():
                desc_text = desc.strip()
                if desc_text in desc_lookup:
                    desc_lookup[desc_text]["memes"].append(c)
                else:
                    group = {
                        "type": "description",
                        "display_text": f"描述：{desc_text}",
                        "memes": [c],
                    }
                    display_groups.append(group)
                    desc_lookup[desc_text] = group
            else:
                key = tuple(sorted(e.strip().lower() for e in c["emotions"]))
                if key in tags_lookup:
                    tags_lookup[key]["memes"].append(c)
                else:
                    tags_str = ", ".join(c["emotions"])
                    group = {
                        "type": "tags",
                        "display_text": f"标签：[{tags_str}]",
                        "memes": [c],
                    }
                    display_groups.append(group)
                    tags_lookup[key] = group

        if index is None:
            response_text = f"已找到与标签 '{query}' 相关的表情包候选列表：\n"
            for i, group in enumerate(display_groups, start=1):
                response_text += f"{i}. {group['display_text']}\n"
            response_text += "请在上述候选中选择最合适的一个序号，并再次调用本工具传入 `index` 参数（如 index=1）来发送对应的表情包。"
            return response_text

        idx = int(index) - 1
        if idx < 0 or idx >= len(display_groups):
            return (
                f"无效的序号 {index}。当前可选的序号范围是 1 到 {len(display_groups)}。"
            )

        selected_group = display_groups[idx]
        import random

        selected_meme = random.choice(selected_group["memes"])
        filename = selected_meme["filename"]
        meme_file = os.path.join(MEMES_DIR, filename)

        if not os.path.exists(meme_file):
            return "所选表情包文件不存在或已被删除。"

        from .backend.helpers import convert_to_gif

        final_meme_file = convert_to_gif(meme_file, self)

        try:
            img = Image.fromFileSystem(final_meme_file)
            object.__setattr__(img, "sub_type", 1)  # 发送为表情包格式

            if event.get_platform_name() == "gewechat":
                await event.send(MessageChain([img]))
            else:
                await self.context.send_message(
                    event.unified_msg_origin,
                    MessageChain([img]),
                )

            if final_meme_file != meme_file and os.path.exists(final_meme_file):
                try:
                    os.remove(final_meme_file)
                except Exception:
                    pass

            desc_info = (
                f"描述为 '{selected_meme['description']}'"
                if selected_meme.get("description")
                else f"标签为 [{', '.join(selected_meme['emotions'])}]"
            )
            return f"表情包已成功发送！已选择{desc_info}的表情包。"
        except Exception as e:
            logger.error(f"[meme_manager] LLM发图工具发送失败: {e}")
            return f"表情包发送失败：{e}"

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

        pass

    @property
    def fault_tolerant_symbols(self) -> list[str]:
        return get_config_value(self.config, "fault_tolerant_symbols", ["⬡"])

    @property
    def auto_steal_enabled(self) -> bool:
        return get_config_value(self.config, "auto_steal_enabled", False)

    @property
    def auto_steal_probability(self) -> int:
        return get_config_value(self.config, "auto_steal_probability", 30)

    @property
    def meme_prompt(self) -> str:
        default_prompt = (
            "【表情包发送行为指引】：你在每次回复中都应该自然地根据当前的聊天内容和情绪选择表情标签。"
            "\n规则："
            "\n1. 标签越丰富、越明确，越能精准匹配到图库中的表情。建议根据当前的聊天内容和情绪提炼并输出多个简短标签（用英文逗号 `,` 分隔），可从以下几个社交维度去发想："
            "\n   - 意图与功能（如：敷衍、赞同、摸头、贴贴、递茶、抱抱）"
            "\n   - 情绪与心理（如：得意、害羞、尴尬、开摆、委屈、暴躁、吃惊）"
            "\n   - 画面主体与行为（如：猫猫、睡觉、吃瓜、熊猫头）"
            "\n   - 风格与态度（如：阴阳怪气、沙雕、二次元、职场发疯、治愈）"
            "\n   （若当前回复不需要表情包，则不输出表情标签）"
            "\n\n【关于搜索与发图工具的限制】："
            "\n除非用户十分明确要求你使用网络搜索，否则对于普通的聊天回复和表情包发送需求，严禁使用任何外部搜索工具（如 web_search、tavily 等）去网络搜索图片，也严禁调用任何第三方发图或消息发送工具。你只需输出表情标签，系统会自动在后台拦截并从本地匹配发送表情包。"
        )
        return get_config_value(self.config, "meme_prompt", default_prompt)

    @property
    def multimodal_tag_prompt(self) -> str:
        default_tag_prompt = (
            "你是一个专业的表情包内容分析师，需要全面分析表情包的各个维度，重点识别角色来源、作品归属和物品特征，为用户提供详细、准确、实用的信息。\n"
            "标签策略（重点优化）：\n"
            "- 标签数量：4-6个精选标签，避免冗余\n"
            "- 标签优先级（从高到低）：\n"
            '  * 角色/作品标签（最高优先级）：如果能识别角色或作品，必须包含。如"派蒙"、"原神"、"海绵宝宝"、"柴犬"\n'
            '  * 物品/主体标签（高优先级）：描述表情包的主体是什么。如"猫"、"狗"、"食物"、"机器人"\n'
            '  * 情感/表情标签（中优先级）：描述表情包表达的情感。如"开心"、"无语"、"生气"、"摆烂"、"震惊"\n'
            '  * 动作/状态标签（中优先级）：描述角色或物品的动作。如"奔跑"、"吃东西"、"睡觉"、"跳舞"\n'
            '  * 风格/形式标签（低优先级）：如"二次元"、"像素风"、"真人"、"手绘"\n'
            "- 标签质量：\n"
            "  * 使用通俗易懂的词汇\n"
            "  * 考虑用户搜索习惯与词汇偏好\n"
            "  * 平衡具体性和通用性\n"
            "  * 避免过于专业或生僻的术语\n\n"
            "描述：\n"
            "根据画面和标签结果进行简洁描述。"
        )
        return get_config_value(
            self.config, "multimodal_tag_prompt", default_tag_prompt
        )

    @property
    def max_emotions_per_message(self) -> int:
        return get_config_value(self.config, "max_emotions_per_message", 2)

    @property
    def emotions_probability(self) -> int:
        return get_config_value(self.config, "emotions_probability", 50)

    @property
    def multimodal_llm_enabled(self) -> bool:
        return get_config_value(self.config, "multimodal_llm_enabled", False)

    @property
    def multimodal_llm_provider_id(self) -> str:
        return get_config_value(self.config, "multimodal_llm_provider_id", "")

    @property
    def enable_mixed_message(self) -> bool:
        return get_config_value(self.config, "enable_mixed_message", True)

    @property
    def mixed_message_probability(self) -> int:
        return get_config_value(self.config, "mixed_message_probability", 80)

    @property
    def convert_static_to_gif(self) -> bool:
        return get_config_value(self.config, "convert_static_to_gif", False)

    @property
    def streaming_compatibility(self) -> bool:
        return get_config_value(self.config, "streaming_compatibility", False)

    @property
    def enable_similarity_dedup(self) -> bool:
        return get_config_value(self.config, "enable_similarity_dedup", True)

    @property
    def similarity_dedup_threshold(self) -> float:
        return get_config_value(self.config, "similarity_dedup_threshold", 0.85)

    @property
    def enable_llm_tool(self) -> bool:
        return get_config_value(self.config, "enable_llm_tool", False)
