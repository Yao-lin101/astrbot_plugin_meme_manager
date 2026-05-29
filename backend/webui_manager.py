import logging
from astrbot.api.event import AstrMessageEvent

logger = logging.getLogger(__name__)

class WebuiManager:
    @staticmethod
    async def start_webui(sender, event: AstrMessageEvent):
        """提示管理后台已迁移"""
        yield event.plain_result(
            "✨ 表情包管理后台已直接集成到 AstrBot 系统面板中！\n"
            "━━━━━━━━━━━━━━\n"
            "无需再单独启动或关闭进程。\n"
            "➜ 请直接打开 AstrBot Dashboard (WebUI)\n"
            "➜ 点击侧边栏的「插件管理」\n"
            "➜ 在 meme_manager 插件下，点击「表情包管理」页面即可访问！"
        )

    @staticmethod
    async def stop_server(sender, event: AstrMessageEvent):
        """提示管理后台已迁移"""
        yield event.plain_result(
            "✨ 表情包管理后台已直接集成到 AstrBot 系统面板中，没有单独的后台进程需要关闭。"
        )

    @staticmethod
    async def _shutdown(sender):
        pass

    @staticmethod
    async def _cleanup_resources(sender):
        pass
