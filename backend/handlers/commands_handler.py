import logging
import os
import time

from astrbot.api.event import AstrMessageEvent
from astrbot.core.utils.session_waiter import (
    SessionController,
    SessionFilter,
    session_waiter,
)

from ...config import MEMES_DIR
from ...utils import (
    compress_image,
)
from ..db.database import get_db_conn, migrate_filesystem_to_db
from ..db.models import (
    clear_all_emojis,
    get_emoji_by_category,
)

logger = logging.getLogger(__name__)


class ConfirmationCancelled(Exception):
    """Raised when a dangerous command is cancelled by the user."""


class SenderScopedSessionFilter(SessionFilter):
    """Bind confirmation replies to the same sender within the same session."""

    def filter(self, event: AstrMessageEvent) -> str:
        sender_id = str(event.get_sender_id() or "").strip()
        return f"{event.unified_msg_origin}:{sender_id}"


class CommandsHandler:
    @staticmethod
    def _get_manageable_categories(sender) -> set[str]:
        """Return the union of configured and local categories."""
        return (
            set(sender.category_manager.get_categories())
            | sender.category_manager.get_local_categories()
        )

    @staticmethod
    async def _wait_for_command_confirmation(
        sender, event: AstrMessageEvent, timeout: int = 30
    ) -> bool:
        """Wait for the same sender to reply with confirmation text."""

        @session_waiter(timeout=timeout, record_history_chains=False)
        async def confirmation_waiter(
            controller: SessionController, confirm_event: AstrMessageEvent
        ) -> None:
            reply = (confirm_event.message_str or "").strip()

            if reply in {"确认", "确定"}:
                controller.stop()
                return

            if reply in {"取消", "退出"}:
                await confirm_event.send(confirm_event.plain_result("已取消本次操作。"))
                controller.stop(ConfirmationCancelled())
                return

            await confirm_event.send(
                confirm_event.plain_result(
                    "请回复“确认”继续执行，或回复“取消”终止本次操作。"
                )
            )
            controller.keep(timeout=timeout, reset_timeout=True)

        try:
            await confirmation_waiter(event, SenderScopedSessionFilter())
            return True
        except TimeoutError:
            await event.send(event.plain_result("⌛ 等待确认超时，操作已取消。"))
            return False
        except ConfirmationCancelled:
            return False

    @staticmethod
    def _format_category_counts(category_counts: dict[str, int], limit: int = 8) -> str:
        """Render a compact category count summary for confirmation prompts."""
        non_empty_items = [
            (category, count)
            for category, count in sorted(category_counts.items())
            if count > 0
        ]
        if not non_empty_items:
            return "无可删除的表情包文件。"

        lines = [
            f"- {category}: {count} 个" for category, count in non_empty_items[:limit]
        ]
        if len(non_empty_items) > limit:
            lines.append(f"- 其余 {len(non_empty_items) - limit} 个标签已省略")
        return "\n".join(lines)

    @staticmethod
    async def list_emotions(sender, event: AstrMessageEvent):
        """查看所有可用表情包标签"""
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT emotions FROM memes")
            rows = cursor.fetchall()
            conn.close()

            local_stats = {}
            for row in rows:
                if row["emotions"]:
                    for emo in row["emotions"].split(","):
                        emo = emo.strip()
                        if emo:
                            local_stats[emo] = local_stats.get(emo, 0) + 1

            categories = sorted(sender.category_manager.get_categories())
            categories_str = ",".join(
                f"[{tag}:{local_stats.get(tag, 0)}]" for tag in categories
            )
            yield event.plain_result(f"🖼️ 当前图库标签：{categories_str}")
        except Exception as e:
            logger.error(f"查看图库失败: {e}")
            yield event.plain_result(f"❌ 查看图库失败: {e}")

    @staticmethod
    async def upload_meme(sender, event: AstrMessageEvent, tags: str = None):
        """上传表情包并标记指定标签"""
        if not tags:
            yield event.plain_result(
                "📌 若要添加表情，请按照此格式操作：\n/表情管理 添加表情 [标签1,标签2...]\n（输入/表情管理 查看图库 可获取标签列表）"
            )
            return

        import re

        raw_tags = [t.strip() for t in re.split(r"[,，\s]+", tags) if t.strip()]
        if not raw_tags:
            yield event.plain_result(
                "📌 若要添加表情，请按照此格式操作：\n/表情管理 添加表情 [标签1,标签2...]"
            )
            return

        valid_categories = set(sender.category_manager.get_categories())
        resolved_tags = []
        invalid_tags = []

        for t in raw_tags:
            if t in valid_categories:
                resolved_tags.append(t)
            else:
                clean_t = t.strip()
                if 0 < len(clean_t) <= 20:
                    resolved_tags.append(clean_t)
                else:
                    invalid_tags.append(t)

        if not resolved_tags:
            yield event.plain_result(
                f"❌ 指定的标签名称不合法（标签长度需限制在 20 字符内）。无效的标签：{', '.join(invalid_tags)}"
            )
            return

        user_key = f"{event.session_id}_{event.get_sender_id()}"
        sender.upload_states[user_key] = {
            "categories": resolved_tags,
            "expire_time": time.time() + 30,
        }

        tags_display = "、".join(resolved_tags)
        invalid_tip = (
            f"（已忽略无效标签: {', '.join(invalid_tags)}）" if invalid_tags else ""
        )
        yield event.plain_result(
            f"请在30秒内发送要添加到【{tags_display}】标签的图片（可发送多张图片）。{invalid_tip}"
        )

    @staticmethod
    async def clear_all_emojis_command(sender, event: AstrMessageEvent):
        """清空所有标签下的表情包，但保留标签配置。"""
        available_categories = sorted(
            CommandsHandler._get_manageable_categories(sender)
        )
        category_counts = {
            category: len(get_emoji_by_category(category))
            for category in available_categories
        }
        total_count = sum(category_counts.values())

        if total_count == 0:
            yield event.plain_result("📭 当前没有可清空的表情包文件。")
            return

        category_count = sum(1 for count in category_counts.values() if count > 0)
        summary = CommandsHandler._format_category_counts(category_counts)
        yield event.plain_result(
            f"⚠️ 【安全警告：第一次确认】\n"
            f"即将清空全部表情包和标签，共 {total_count} 个文件，涉及 {category_count} 个标签。\n"
            "该操作不可逆，将同时删除所有标签配置和向量缓存。\n"
            f"{summary}\n"
            "请在 30 秒内回复“确认”继续，或回复“取消”放弃。"
        )
        if not await CommandsHandler._wait_for_command_confirmation(sender, event):
            return

        yield event.plain_result(
            "🔴 【安全警告：第二次确认】\n"
            "请进行最终确认！该操作会彻底删除本地所有表情文件并清空数据库中所有表情标签配置和向量缓存。\n"
            "确定要彻底清空吗？\n"
            "请在 30 秒内回复“确认清空全部表情与标签”以最终执行，或回复“取消”放弃。"
        )

        @session_waiter(timeout=30, record_history_chains=False)
        async def second_confirmation_waiter(
            controller: SessionController, confirm_event: AstrMessageEvent
        ) -> None:
            reply = (confirm_event.message_str or "").strip()
            if reply == "确认清空全部表情与标签":
                controller.stop()
                return
            if reply in {"取消", "退出"}:
                await confirm_event.send(confirm_event.plain_result("已取消本次操作。"))
                controller.stop(ConfirmationCancelled())
                return
            await confirm_event.send(
                confirm_event.plain_result(
                    "⚠️ 输入不正确！请回复“确认清空全部表情与标签”以最终确认执行，或回复“取消”放弃。"
                )
            )
            controller.keep(timeout=30, reset_timeout=True)

        try:
            await second_confirmation_waiter(event, SenderScopedSessionFilter())
        except TimeoutError:
            await event.send(event.plain_result("⌛ 等待确认超时，操作已取消。"))
            return
        except ConfirmationCancelled:
            return

        clear_all_emojis()
        sender.category_manager.clear_all_categories()
        from ..db.database import clear_all_tag_embeddings

        clear_all_tag_embeddings()
        sender._reload_personas()

        # 重新统计真正删除了多少
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memes")
        rem_count = cursor.fetchone()[0]
        conn.close()

        deleted_total = total_count - rem_count
        yield event.plain_result(
            f"✅ 已成功清空全部表情包和标签，共删除 {deleted_total} 个文件，标签配置与向量缓存已清空。"
        )

    @staticmethod
    async def delete_tag_command(sender, event: AstrMessageEvent, tag: str = None):
        """删除指定标签，移除标签配置及其下表情包的此标签归属（无标签表情将被彻底删除）"""
        if not tag:
            yield event.plain_result(
                "📌 若要删除标签，请按照此格式操作：\n/表情管理 删除标签 [标签名称]"
            )
            return

        tag = tag.strip()
        available_categories = CommandsHandler._get_manageable_categories(sender)
        if tag not in available_categories:
            yield event.plain_result(
                f"⚠️ 未找到标签「{tag}」。\n可先使用 /表情管理 查看图库 查看当前标签。"
            )
            return

        emoji_count = len(get_emoji_by_category(tag))
        yield event.plain_result(
            f"⚠️ 即将删除标签「{tag}」并从配置中移除，同时移去该标签下全部表情包的「{tag}」标签属性"
            f"{f'（其中有 {emoji_count} 个表情包如果不再属于其他任何标签，将会被物理删除）' if emoji_count > 0 else ''}。\n"
            "该操作不可恢复。\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await CommandsHandler._wait_for_command_confirmation(sender, event):
            return

        if not sender.category_manager.delete_category(tag):
            yield event.plain_result(f"❌ 删除标签「{tag}」失败，请稍后重试。")
            return

        sender._reload_personas()
        yield event.plain_result(
            f"✅ 已成功删除标签「{tag}」"
            f"{f'，并处理了 {emoji_count} 个相关表情包的归属。' if emoji_count > 0 else '。'}"
        )

    @staticmethod
    async def check_sync_status(sender, event: AstrMessageEvent, detail: str = None):
        """检查同步状态"""
        if not sender.img_sync:
            yield event.plain_result("❌ 未配置图床同步服务。")
            return

        yield event.plain_result("正在检查云端同步状态，请稍后...")
        try:
            status = sender.img_sync.check_status()

            # 使用数据库统计替代文件夹扫描
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT emotions FROM memes")
            rows = cursor.fetchall()
            conn.close()

            local_stats = {}
            for row in rows:
                if row["emotions"]:
                    for emo in row["emotions"].split(","):
                        emo = emo.strip()
                        if emo:
                            local_stats[emo] = local_stats.get(emo, 0) + 1
            local_total = len(rows)

            tags_str = ",".join(
                f"[{cat}:{count}]" for cat, count in sorted(local_stats.items())
            )
            result = [
                f"🔄 表情包同步状态报告 | 📁 本地总计: {local_total} 个文件",
                f"📂 标签详情: {tags_str}" if tags_str else "",
            ]

            result.extend(
                [
                    "",
                    f"☁️ 待同步到云端: {len(status.get('to_upload', []))} 个文件",
                    f"⬇️ 待从云端下载: {len(status.get('to_download', []))} 个文件",
                ]
            )

            if detail == "详细" and "remote_details" in status:
                remote_images = status["remote_details"]
                if remote_images:
                    result.append(f"📊 云端总计: {len(remote_images)} 个文件")
                else:
                    result.append("📂 云端无文件")

            yield event.plain_result("\n".join(result))
        except Exception as e:
            logger.error(f"检查同步状态失败: {str(e)}")
            yield event.plain_result(f"❌ 检查同步状态失败: {str(e)}")

    @staticmethod
    async def sync_to_remote(sender, event: AstrMessageEvent):
        """同步到云端"""
        if not sender.img_sync:
            yield event.plain_result("❌ 未配置图床同步服务。")
            return

        yield event.plain_result("正在启动同步流程，同步至云端...")
        try:
            success = sender.img_sync.sync_to_remote()
            if success:
                yield event.plain_result("云端同步已完成！")
            else:
                yield event.plain_result("云端同步失败，请查看日志哦。")
        except Exception as e:
            logger.error(f"同步到云端失败: {str(e)}")
            yield event.plain_result(f"同步到云端失败: {str(e)}")

    @staticmethod
    async def show_library_stats(sender, event: AstrMessageEvent):
        """显示图库详细统计信息"""
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT emotions FROM memes")
            rows = cursor.fetchall()
            conn.close()

            local_stats = {}
            for row in rows:
                if row["emotions"]:
                    for emo in row["emotions"].split(","):
                        emo = emo.strip()
                        if emo:
                            local_stats[emo] = local_stats.get(emo, 0) + 1
            local_total = len(rows)

            tags_str = ",".join(
                f"[{cat}:{count}]" for cat, count in sorted(local_stats.items())
            )
            result = (
                f"📊 图库统计 | 总表情包: {local_total} 个 | {tags_str}"
                if tags_str
                else f"📊 图库统计 | 总表情包: {local_total} 个"
            )

            yield event.plain_result(result)
        except Exception as e:
            logger.error(f"展示统计信息失败: {e}")
            yield event.plain_result(f"展示统计信息失败: {e}")

    @staticmethod
    async def sync_from_remote(sender, event: AstrMessageEvent):
        """从云端同步"""
        if not sender.img_sync:
            yield event.plain_result("❌ 未配置图床同步服务。")
            return

        yield event.plain_result("正在启动同步流程，从云端拉取...")
        try:
            success = sender.img_sync.sync_from_remote()
            if success:
                # 重新运行迁移，以防下载的图片有子文件夹结构
                migrate_filesystem_to_db()
                yield event.plain_result("从云端同步已完成！")
                await sender.reload_emotions()
            else:
                yield event.plain_result("从云端同步失败，请查看日志。")
        except Exception as e:
            logger.error(f"从云端同步失败: {str(e)}")
            yield event.plain_result(f"从云端同步失败: {str(e)}")

    @staticmethod
    async def overwrite_to_remote(sender, event: AstrMessageEvent):
        """覆盖到云端"""
        if not sender.img_sync:
            yield event.plain_result("❌ 未配置图床同步服务。")
            return

        yield event.plain_result(
            "⚠️ 警告：覆盖到云端会让云端表情与本地完全一致，云端多出的文件将被删除。\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await CommandsHandler._wait_for_command_confirmation(sender, event):
            return

        try:
            success = sender.img_sync.overwrite_to_remote()
            if success:
                yield event.plain_result("覆盖到云端已完成！")
            else:
                yield event.plain_result("覆盖到云端失败，请查看日志。")
        except Exception as e:
            logger.error(f"覆盖到云端失败: {str(e)}")
            yield event.plain_result(f"覆盖到云端失败: {str(e)}")

    @staticmethod
    async def overwrite_from_remote(sender, event: AstrMessageEvent):
        """从云端覆盖"""
        if not sender.img_sync:
            yield event.plain_result("❌ 未配置图床同步服务。")
            return

        yield event.plain_result(
            "⚠️ 警告：从云端覆盖会让本地表情与云端完全一致，本地多出的文件将被删除，且数据库中未标记的也会丢失。\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await CommandsHandler._wait_for_command_confirmation(sender, event):
            return

        try:
            success = sender.img_sync.overwrite_from_remote()
            if success:
                # 重新迁移
                migrate_filesystem_to_db()
                yield event.plain_result("从云端覆盖已完成！")
                await sender.reload_emotions()
            else:
                yield event.plain_result("从云端覆盖失败，请查看日志。")
        except Exception as e:
            logger.error(f"从云端覆盖失败: {str(e)}")
            yield event.plain_result(f"从云端覆盖失败: {str(e)}")

    @staticmethod
    async def compress_existing_memes(sender, event: AstrMessageEvent):
        """手动压缩所有已存在的表情包文件"""
        cfg = sender.config
        if not cfg.get("enable_compression", True):
            yield event.plain_result(
                "⚠️ 插件配置中未启用压缩功能，请先在配置中开启自动压缩。"
            )
            return

        max_size_kb = cfg.get("compression_max_size_kb", 1024)
        max_width = cfg.get("compression_max_width", 1024)
        quality = cfg.get("compression_quality", 80)
        compress_gif = cfg.get("compress_gif", False)
        compression_format = cfg.get("compression_format", "original")

        from ..db.database import get_db_conn

        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM memes")
        rows = cursor.fetchall()

        if not rows:
            conn.close()
            yield event.plain_result("📭 数据库中没有注册的表情包文件。")
            return

        yield event.plain_result(f"⚡ 开始检查并压缩 {len(rows)} 个表情包，请稍候...")

        compressed_count = 0
        skipped_count = 0
        failed_count = 0
        total_saved_bytes = 0

        for row in rows:
            filename = row["filename"]
            file_path = os.path.join(MEMES_DIR, filename)

            if not os.path.exists(file_path):
                skipped_count += 1
                continue

            try:
                with open(file_path, "rb") as f:
                    orig_bytes = f.read()

                orig_size = len(orig_bytes)

                new_bytes, new_filename = compress_image(
                    image_bytes=orig_bytes,
                    max_size_kb=max_size_kb,
                    max_width=max_width,
                    quality=quality,
                    compress_gif=compress_gif,
                    filename=filename,
                    compression_format=compression_format,
                )

                new_size = len(new_bytes)
                if new_filename != filename or new_size < orig_size:
                    new_file_path = os.path.join(MEMES_DIR, new_filename)
                    with open(new_file_path, "wb") as f:
                        f.write(new_bytes)

                    if new_filename != filename:
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception as ex:
                                logger.warning(f"无法删除原格式图片 {file_path}: {ex}")
                        cursor.execute(
                            "UPDATE memes SET filename = ? WHERE filename = ?",
                            (new_filename, filename),
                        )
                    compressed_count += 1
                    total_saved_bytes += orig_size - new_size
                else:
                    skipped_count += 1
            except Exception as e:
                logger.error(f"手动压缩表情包 {filename} 失败: {e}")
                failed_count += 1

        conn.commit()
        conn.close()

        saved_mb = total_saved_bytes / (1024 * 1024)
        yield event.plain_result(
            f"📊 表情包压缩完成！\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ 成功压缩: {compressed_count} 个表情包\n"
            f"⏩ 无需压缩: {skipped_count} 个表情包\n"
            f"❌ 压缩失败: {failed_count} 个表情包\n"
            f"💾 共节省空间: {saved_mb:.2f} MB"
        )

    @staticmethod
    async def rebuild_tag_embeddings(sender, event: AstrMessageEvent):
        """清空缓存的标签向量并重新计算"""
        import asyncio

        from ..core.emotion_handler import sync_tag_embeddings
        from ..db.database import clear_all_tag_embeddings

        clear_all_tag_embeddings()
        yield event.plain_result(
            "✅ 已清空所有表情标签的向量缓存。正在后台调用配置的 Embedding 提供商重新同步计算向量，完成会有后台日志..."
        )
        asyncio.create_task(sync_tag_embeddings(sender))
