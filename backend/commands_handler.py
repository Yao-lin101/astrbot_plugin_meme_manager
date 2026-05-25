import logging
import os
import time

from astrbot.api.event import AstrMessageEvent
from astrbot.core.utils.session_waiter import (
    SessionController,
    SessionFilter,
    session_waiter,
)

from ..config import MEMES_DIR
from ..utils import (
    compress_image,
    get_default_meme_categories,
    restore_default_memes,
)
from .database import get_db_conn, migrate_filesystem_to_db
from .models import (
    clear_all_emojis,
    clear_category_emojis,
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
            set(sender.category_manager.get_descriptions())
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
            lines.append(f"- 其余 {len(non_empty_items) - limit} 个类型已省略")
        return "\n".join(lines)

    @staticmethod
    async def list_emotions(sender, event: AstrMessageEvent):
        """查看所有可用表情包类别"""
        descriptions = sender.category_mapping
        categories = "\n".join(
            [f"- {tag}: {desc}" for tag, desc in descriptions.items()]
        )
        yield event.plain_result(f"🖼️ 当前图库：\n{categories}")

    @staticmethod
    async def upload_meme(sender, event: AstrMessageEvent, category: str = None):
        """上传表情包到指定类别"""
        if not category:
            yield event.plain_result(
                "📌 若要添加表情，请按照此格式操作：\n/表情管理 添加表情 [类别名称]\n（输入/查看图库 可获取类别列表）"
            )
            return

        if category not in sender.category_manager.get_descriptions():
            yield event.plain_result(
                f"您输入的表情包类别「{category}」是无效的哦。\n可以使用/查看表情包来查看可用的类别。"
            )
            return

        user_key = f"{event.session_id}_{event.get_sender_id()}"
        sender.upload_states[user_key] = {
            "category": category,
            "expire_time": time.time() + 30,
        }
        yield event.plain_result(
            f"请在30秒内发送要添加到【{category}】类别的图片（可发送多张图片）。"
        )

    @staticmethod
    async def restore_default_memes_command(
        sender, event: AstrMessageEvent, category: str = None
    ):
        """恢复内置默认表情包，可指定类别或恢复全部。"""
        available_default_categories = get_default_meme_categories()
        if not available_default_categories:
            yield event.plain_result("❌ 未找到插件内置默认表情包资源。")
            return

        normalized_category = category.strip() if category else None
        if (
            normalized_category
            and normalized_category not in available_default_categories
        ):
            category_list = "\n".join(
                f"- {name}" for name in available_default_categories
            )
            yield event.plain_result(
                f"⚠️ 默认表情包中不存在类别「{normalized_category}」。\n"
                f"当前可恢复的默认类别如下：\n{category_list}"
            )
            return

        restore_result = restore_default_memes(normalized_category)
        if not restore_result["source_exists"]:
            yield event.plain_result("❌ 未找到插件内置默认表情包资源。")
            return

        # 触发数据库迁移，把刚复制的子文件夹表情归档到扁平结构与数据库中
        migrate_filesystem_to_db()

        copied_files = restore_result["copied_files"]
        duplicate_files = restore_result["duplicate_files"]
        renamed_files = restore_result["renamed_files"]
        restored_categories = sorted(
            set(copied_files) | set(duplicate_files) | set(renamed_files)
        )

        if restored_categories:
            sender._ensure_default_category_descriptions(restored_categories)

        copied_count = sum(len(files) for files in copied_files.values())
        duplicate_count = sum(len(files) for files in duplicate_files.values())
        renamed_count = sum(len(files) for files in renamed_files.values())

        if copied_count == 0 and duplicate_count > 0:
            yield event.plain_result(
                "ℹ️ 默认表情包已存在，本次未新增文件。"
                if not normalized_category
                else f"ℹ️ 类别「{normalized_category}」的默认表情包已存在，本次未新增文件。"
            )
            return

        if copied_count == 0:
            yield event.plain_result("ℹ️ 本次没有恢复任何默认表情包文件。")
            return

        if normalized_category:
            yield event.plain_result(
                f"✅ 已恢复类别「{normalized_category}」的默认表情包，共新增 {copied_count} 个文件"
                f"{f'，其中 {renamed_count} 个因重名自动补序号' if renamed_count > 0 else ''}"
                f"{f'，跳过 {duplicate_count} 个重复文件' if duplicate_count > 0 else ''}。"
            )
            return

        yield event.plain_result(
            f"✅ 已恢复全部默认表情包，共新增 {copied_count} 个文件，涉及 {len(copied_files)} 个类别"
            f"{f'，其中 {renamed_count} 个因重名自动补序号' if renamed_count > 0 else ''}"
            f"{f'，跳过 {duplicate_count} 个重复文件' if duplicate_count > 0 else ''}。"
        )

    @staticmethod
    async def clear_category_command(
        sender, event: AstrMessageEvent, category: str = None
    ):
        """清空指定类型下的所有表情包，但保留类型本身。"""
        if not category:
            yield event.plain_result(
                "📌 若要清空指定类型，请按照此格式操作：\n/表情管理 清空指定类型 [类别名称]"
            )
            return

        category = category.strip()
        available_categories = CommandsHandler._get_manageable_categories(sender)
        if category not in available_categories:
            yield event.plain_result(
                f"⚠️ 未找到类型「{category}」。\n可先使用 /表情管理 查看图库 查看当前类型。"
            )
            return

        emoji_count = len(get_emoji_by_category(category))
        if emoji_count == 0:
            yield event.plain_result(f"📭 类型「{category}」当前没有可清空的表情包。")
            return

        yield event.plain_result(
            f"⚠️ 即将清空类型「{category}」下的 {emoji_count} 个表情包，但会保留类型本身。\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await CommandsHandler._wait_for_command_confirmation(sender, event):
            return

        result = clear_category_emojis(category)
        deleted_count = len(result["deleted_files"])
        yield event.plain_result(
            f"✅ 已清空类型「{category}」，共删除 {deleted_count} 个表情包。"
        )

    @staticmethod
    async def clear_all_emojis_command(sender, event: AstrMessageEvent):
        """清空所有类型下的表情包，但保留类型和描述配置。"""
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
            f"⚠️ 即将清空全部表情包，共 {total_count} 个文件，涉及 {category_count} 个类型。\n"
            "该操作会保留所有类型名称和描述配置。\n"
            f"{summary}\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await CommandsHandler._wait_for_command_confirmation(sender, event):
            return

        clear_all_emojis()

        # 重新统计真正删除了多少
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memes")
        rem_count = cursor.fetchone()[0]
        conn.close()

        deleted_total = total_count - rem_count
        yield event.plain_result(
            f"✅ 已清空全部表情包，共删除 {deleted_total} 个文件，类型配置已保留。"
        )

    @staticmethod
    async def delete_category_command(
        sender, event: AstrMessageEvent, category: str = None
    ):
        """删除指定类型本身，同时移除其描述配置和本地文件夹。"""
        if not category:
            yield event.plain_result(
                "📌 若要删除类型本身，请按照此格式操作：\n/表情管理 删除类型本身 [类别名称]"
            )
            return

        category = category.strip()
        available_categories = CommandsHandler._get_manageable_categories(sender)
        if category not in available_categories:
            yield event.plain_result(
                f"⚠️ 未找到类型「{category}」。\n可先使用 /表情管理 查看图库 查看当前类型。"
            )
            return

        emoji_count = len(get_emoji_by_category(category))
        yield event.plain_result(
            f"⚠️ 即将删除类型「{category}」本身，并移除其描述配置"
            f"{f'，同时删除其中的 {emoji_count} 个表情包' if emoji_count > 0 else ''}。\n"
            "该操作不可恢复。\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await CommandsHandler._wait_for_command_confirmation(sender, event):
            return

        if not sender.category_manager.delete_category(category):
            yield event.plain_result(f"❌ 删除类型「{category}」失败，请稍后重试。")
            return

        sender._reload_personas()
        yield event.plain_result(
            f"✅ 已删除类型「{category}」"
            f"{f'，并移除 {emoji_count} 个表情包。' if emoji_count > 0 else '。'}"
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
            local_total = 0
            for row in rows:
                if row["emotions"]:
                    for emo in row["emotions"].split(","):
                        emo = emo.strip()
                        if emo:
                            local_stats[emo] = local_stats.get(emo, 0) + 1
                            local_total += 1

            result = [
                "🔄 表情包同步状态报告",
                "━━━━━━━━━━━━━━",
                f"📁 本地总计: {local_total} 个文件",
            ]

            if local_stats:
                result.append("")
                result.append("📂 本地文件分类详情:")
                for cat, count in sorted(local_stats.items()):
                    desc = sender.category_mapping.get(cat, "")
                    result.append(
                        f"  ➜ {cat} ({desc if desc else '暂无描述'}): {count} 个"
                    )

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
            result = ["📊 表情包图库统计报告", "", "📁 本地图库统计:"]

            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT emotions FROM memes")
            rows = cursor.fetchall()
            conn.close()

            local_stats = {}
            local_total = 0
            for row in rows:
                if row["emotions"]:
                    for emo in row["emotions"].split(","):
                        emo = emo.strip()
                        if emo:
                            local_stats[emo] = local_stats.get(emo, 0) + 1
                            local_total += 1

            result.append(f"总表情包数量: {local_total} 个")
            if local_stats:
                result.append("分类详情:")
                for cat, count in sorted(local_stats.items()):
                    desc = sender.category_mapping.get(cat, "")
                    result.append(f" - {cat} ({desc}): {count} 个")

            yield event.plain_result("\n".join(result))
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

        from .database import get_db_conn

        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM memes")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
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

                new_bytes = compress_image(
                    image_bytes=orig_bytes,
                    max_size_kb=max_size_kb,
                    max_width=max_width,
                    quality=quality,
                    compress_gif=compress_gif,
                    filename=filename,
                )

                new_size = len(new_bytes)
                if new_size < orig_size:
                    with open(file_path, "wb") as f:
                        f.write(new_bytes)
                    compressed_count += 1
                    total_saved_bytes += orig_size - new_size
                else:
                    skipped_count += 1
            except Exception as e:
                logger.error(f"手动压缩表情包 {filename} 失败: {e}")
                failed_count += 1

        saved_mb = total_saved_bytes / (1024 * 1024)
        yield event.plain_result(
            f"📊 表情包压缩完成！\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ 成功压缩: {compressed_count} 个表情包\n"
            f"⏩ 无需压缩: {skipped_count} 个表情包\n"
            f"❌ 压缩失败: {failed_count} 个表情包\n"
            f"💾 共节省空间: {saved_mb:.2f} MB"
        )
