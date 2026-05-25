import asyncio
import logging
from multiprocessing import Process

from astrbot.api.event import AstrMessageEvent
from astrbot.core import astrbot_config
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.io import get_local_ip_addresses

from ..utils import generate_secret_key
from ..webui import ServerState, run_server

logger = logging.getLogger(__name__)


class WebuiManager:
    @staticmethod
    async def start_webui(sender, event: AstrMessageEvent):
        """启动表情包管理服务器"""
        if event.get_message_type() != MessageType.FRIEND_MESSAGE:
            yield event.plain_result(
                "⚠️ 该指令仅限私聊使用。\n请私聊发送“表情管理 开启管理后台”。"
            )
            return

        try:
            sender.server_port = sender.config.get("webui_port", 5000)
            is_running = bool(sender.webui_process and sender.webui_process.is_alive())
            if (
                is_running
                and sender.server_key
                and await WebuiManager._check_port_active(sender)
            ):
                yield event.plain_result(
                    "ℹ️ 管理后台已在运行，以下是当前访问信息：\n\n"
                    + WebuiManager._build_webui_access_message(sender)
                )
                return

            state = ServerState()
            state.ready.clear()

            # 生成秘钥
            sender.server_key = generate_secret_key(8)

            # 检查端口占用情况
            if await WebuiManager._check_port_active(sender):
                await WebuiManager._shutdown(sender)
                await asyncio.sleep(1)  # 等待系统释放端口
                if await WebuiManager._check_port_active(sender):
                    raise RuntimeError(f"端口 {sender.server_port} 仍被占用")

            # 序列化人格列表，避免多进程间传递未定义对象导致的 Pickle 错误
            personas_list = []
            if hasattr(sender.context, "provider_manager") and hasattr(
                sender.context.provider_manager, "personas"
            ):
                for p in sender.context.provider_manager.personas:
                    personas_list.append(
                        {
                            "id": p.get("id") or p.get("name") or "",
                            "name": p.get("name") or "",
                            "prompt": p.get("prompt") or "",
                        }
                    )

            config_for_server = {
                "img_sync": sender.img_sync,
                "category_manager": sender.category_manager,
                "webui_port": sender.server_port,
                "server_key": sender.server_key,
                "plugin_config": sender.config,
                "personas": personas_list,
            }
            sender.webui_process = Process(target=run_server, args=(config_for_server,))
            sender.webui_process.start()

            # 等待服务器就绪（轮询检测端口激活）
            for i in range(10):
                if await WebuiManager._check_port_active(sender):
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("⌛ 启动超时，请检查防火墙设置")

            access_message = WebuiManager._build_webui_access_message(sender)
            yield event.plain_result(access_message)

        except Exception as e:
            logger.error(f"启动失败: {str(e)}")
            yield event.plain_result(
                f"⚠️ 后台启动失败，请稍后重试\n（错误代码：{str(e)}）"
            )
            await WebuiManager._cleanup_resources(sender)

    @staticmethod
    async def _check_port_active(sender):
        """验证端口是否实际已激活"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", sender.server_port), timeout=1
            )
            writer.close()
            return True
        except Exception:
            return False

    @staticmethod
    def _build_webui_access_urls(sender) -> list[str]:
        """参考 AstrBot 本体生成可访问地址列表。"""
        access_urls = [f"http://localhost:{sender.server_port}"]
        seen_hosts = {"localhost", "127.0.0.1"}

        try:
            for ip_addr in get_local_ip_addresses():
                if not ip_addr or ip_addr in seen_hosts or ip_addr.startswith("127."):
                    continue
                seen_hosts.add(ip_addr)
                access_urls.append(f"http://{ip_addr}:{sender.server_port}")
        except Exception as exc:
            logger.warning(f"获取本地网络地址失败: {exc}")

        return access_urls

    @staticmethod
    def _build_webui_access_message(sender) -> str:
        access_urls = WebuiManager._build_webui_access_urls(sender)
        parts = [
            "✨ 管理后台已就绪！",
            "━━━━━━━━━━━━━━",
            "表情包管理服务器已启动！",
            "🔗 可访问地址：",
            f"   ➜ 本地: {access_urls[0]}",
        ]

        for url in access_urls[1:]:
            parts.append(f"   ➜ 网络: {url}")

        parts.extend(
            [
                f"🔑 临时密钥：{sender.server_key} （本次有效）",
                "⚠️ 请勿分享给未授权用户",
            ]
        )

        if len(access_urls) == 1:
            parts.append(
                "⚠️ 当前仅检测到本地地址，如需远程访问，请确认端口映射、防火墙 and 宿主机网络已放行。"
            )

        callback_api_base = str(
            astrbot_config.get("callback_api_base", "") or ""
        ).strip()
        if callback_api_base:
            parts.append(
                f"ℹ️ 如你通过反代对外暴露服务，请优先使用你自己的外部地址访问。当前 callback_api_base: {callback_api_base}"
            )

        return "\n".join(parts)

    @staticmethod
    async def stop_server(sender, event: AstrMessageEvent):
        """关闭表情包管理服务器的指令"""
        try:
            is_running = bool(sender.webui_process and sender.webui_process.is_alive())
            if not is_running:
                yield event.plain_result("ℹ️ 管理后台当前未运行。")
                return

            await WebuiManager._shutdown(sender)
            yield event.plain_result("✅ 管理后台已关闭。")
        except Exception as e:
            yield event.plain_result(f"❌ 管理后台关闭失败：{str(e)}")
        finally:
            await WebuiManager._cleanup_resources(sender)

    @staticmethod
    async def _shutdown(sender):
        if sender.webui_process:
            sender.webui_process.terminate()
            sender.webui_process.join()

    @staticmethod
    async def _cleanup_resources(sender):
        if sender.img_sync:
            sender.img_sync.stop_sync()
        sender.server_key = None
        sender.server_port = None
        if sender.webui_process:
            if sender.webui_process.is_alive():
                sender.webui_process.terminate()
                sender.webui_process.join()
        sender.webui_process = None
        logger.info("资源清理完成")
