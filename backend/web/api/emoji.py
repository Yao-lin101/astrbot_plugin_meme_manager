import base64
import io
import logging
import mimetypes
import os
from pathlib import Path

from quart import current_app, jsonify, request

from ....config import MEMES_DIR
from ...core.helpers import (
    MEME_SEND_MODE_STICKER,
    normalize_meme_send_mode,
)
from ...db.database import get_db_conn
from ...db.models import (
    DuplicateEmojiError,
    SimilarEmojiError,
    add_emoji_to_category,
    delete_emoji_from_category,
    get_emoji_by_category,
)
from .common import trigger_tag_vectorization

logger = logging.getLogger(__name__)


async def get_all_emojis():
    """获取所有表情包（按类别分组），支持按人格过滤"""
    persona_id = request.args.get("persona_id")

    conn = get_db_conn()
    cursor = conn.cursor()

    if persona_id:
        cursor.execute(
            "SELECT filename, emotions, description FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
            (f"%,{persona_id},%",),
        )
    else:
        cursor.execute("SELECT filename, emotions, description FROM memes")

    rows = cursor.fetchall()
    conn.close()

    emoji_data = {}
    mtimes = {}
    descriptions = {}
    for row in rows:
        filename = row["filename"]
        emotions = row["emotions"]
        description = row["description"] or ""

        # Verify file exists
        full_path = os.path.join(MEMES_DIR, filename)
        if not os.path.exists(full_path):
            continue

        try:
            mtimes[filename] = int(os.path.getmtime(full_path))
        except Exception:
            mtimes[filename] = 0

        descriptions[filename] = description

        if emotions:
            for emo in emotions.split(","):
                emo = emo.strip()
                if emo:
                    emoji_data.setdefault(emo, []).append(filename)

    # 补全配置中定义的所有分类，以防前端展示错乱
    plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
    category_manager = plugin_config.get("category_manager")
    if category_manager:
        for cat in category_manager.get_categories():
            if cat not in emoji_data:
                emoji_data[cat] = []

    return jsonify(
        {"categories": emoji_data, "mtimes": mtimes, "descriptions": descriptions}
    )


async def get_emojis_by_category(category):
    """获取指定类别的表情包"""
    emojis = get_emoji_by_category(category)
    if emojis is None:
        return jsonify({"message": "Category not found"}), 404
    return jsonify(emojis if isinstance(emojis, list) else []), 200


async def add_emoji():
    """添加表情包到指定类别"""
    try:
        is_json_request = request.is_json
        ignore_similarity = False
        if is_json_request:
            data = await request.get_json()
            category = data.get("category")
            filename = data.get("filename")
            base64_data = data.get("base64_data")
            ignore_similarity = data.get("ignore_similarity", False)
            if isinstance(ignore_similarity, str):
                ignore_similarity = ignore_similarity.lower() == "true"
            if not category or not filename or not base64_data:
                return jsonify({"message": "没有找到上传的图片文件或缺少类别"}), 400

            try:
                if "," in base64_data:
                    base64_data = base64_data.split(",", 1)[1]
                content = base64.b64decode(base64_data)
            except Exception as e:
                return jsonify({"message": f"图片解码失败: {e}"}), 400

            class BytesIOFile:
                def __init__(self, filename, content):
                    self.filename = filename
                    self.stream = io.BytesIO(content)

            image_file = BytesIOFile(filename, content)
        else:
            # 检查是否有文件 - 使用 await 获取请求文件
            files = await request.files
            if not files or "image_file" not in files:
                return jsonify({"message": "没有找到上传的图片文件"}), 400

            image_file = files["image_file"]

            # 使用 await 获取表单数据
            form = await request.form
            category = form.get("category")
            ignore_similarity = form.get("ignore_similarity", "false").lower() == "true"

        if not category:
            return jsonify({"message": "没有指定类别"}), 400

        if not image_file or not image_file.filename:
            return jsonify({"message": "无效的图片文件"}), 400

        # 记录上传信息
        logger.info(
            f"收到上传请求: 类别={category}, 文件名={image_file.filename}, 忽略相似度={ignore_similarity}"
        )

        try:
            result = add_emoji_to_category(
                category, image_file, ignore_similarity=ignore_similarity
            )

            # 添加成功后同步配置
            plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
            category_manager = plugin_config.get("category_manager")
            if category_manager:
                category_manager.sync_with_filesystem()

            logger.info(f"表情包添加成功: {result['path']}")
            return jsonify(
                {
                    "message": "表情包添加成功",
                    "path": result["path"],
                    "category": category,
                    "filename": result["filename"],
                }
            ), 201

        except SimilarEmojiError as inner_e:
            logger.info(f"跳过相似表情包 (待确认): {inner_e}")
            response_payload = {
                "message": str(inner_e),
                "code": "similar_emoji",
                "category": category,
                "similarity": inner_e.similarity,
                "existing_filename": inner_e.existing_filename,
            }
            if is_json_request:
                response_payload["is_duplicate"] = True
                return jsonify(response_payload), 200
            else:
                return jsonify(response_payload), 409
        except DuplicateEmojiError as inner_e:
            logger.info(f"跳过重复表情包: {inner_e}")
            response_payload = {
                "message": str(inner_e),
                "code": "duplicate_emoji",
                "category": category,
                "filename": inner_e.existing_filename,
            }
            if is_json_request:
                response_payload["is_duplicate"] = True
                return jsonify(response_payload), 200
            else:
                return jsonify(response_payload), 409
        except Exception as inner_e:
            logger.error(f"处理上传文件时出错: {inner_e}", exc_info=True)
            return jsonify({"message": f"处理上传文件时出错: {str(inner_e)}"}), 500

    except Exception as e:
        logger.error(f"处理上传请求时发生未知异常: {e}", exc_info=True)
        return jsonify({"message": f"处理上传请求时发生未知异常: {str(e)}"}), 500


async def delete_emoji():
    """删除指定类别的表情包"""
    data = await request.get_json()
    category = data.get("category")
    image_file = data.get("image_file")
    if not category or not image_file:
        return jsonify({"message": "Category and image file are required"}), 400

    if delete_emoji_from_category(category, image_file):
        # 删除后可能产生空标签，同步清理配置
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            category_manager.sync_with_filesystem()

        return jsonify(
            {
                "message": "Emoji deleted successfully",
                "category": category,
                "filename": image_file,
            }
        ), 200
    else:
        return jsonify({"message": "Emoji not found"}), 404


async def edit_emoji():
    """编辑表情包的标签、允许的人格、描述与发送格式"""
    try:
        data = await request.get_json()
        filename = data.get("filename")
        emotions = data.get("emotions")  # List of emotions
        personas = data.get("personas")  # List of persona IDs, or ["*"]
        description = data.get("description")
        send_mode = data.get("send_mode")
        normalized_send_mode = normalize_meme_send_mode(send_mode)

        if not filename:
            return jsonify({"message": "Filename is required"}), 400
        if send_mode is not None and normalized_send_mode != send_mode:
            return jsonify({"message": "Invalid send_mode"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        emotions_str = ",".join(emotions) if isinstance(emotions, list) else emotions
        personas_str = ",".join(personas) if isinstance(personas, list) else personas

        set_parts = ["emotions = ?", "personas = ?"]
        params = [emotions_str, personas_str]
        if "description" in data:
            set_parts.append("description = ?")
            params.append(description)
        if send_mode is not None:
            set_parts.append("send_mode = ?")
            params.append(normalized_send_mode)
        params.append(filename)
        cursor.execute(
            f"UPDATE memes SET {', '.join(set_parts)} WHERE filename = ?",
            tuple(params),
        )
        conn.commit()

        # Check if the meme has emotions. If not, delete it.
        if not emotions_str:
            cursor.execute("DELETE FROM memes WHERE filename = ?", (filename,))
            conn.commit()
            file_path = Path(MEMES_DIR) / filename
            if file_path.exists():
                file_path.unlink()

        conn.close()

        # Reload
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            category_manager.sync_with_filesystem()

        trigger_tag_vectorization()
        return jsonify({"message": "Emoji metadata updated successfully"}), 200
    except Exception as e:
        logger.error(f"更新表情元数据失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


async def get_emoji_info(filename=None):
    """获取特定表情包的信息"""
    try:
        # 优先使用查询参数 filename（兼容中文文件名，避免路径段被双重 URL 编码）；
        # 回退到路径参数以保持向后兼容。
        filename = request.args.get("filename") or filename
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT emotions, personas, description, send_mode FROM memes WHERE filename = ?",
            (filename,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify(
                {
                    "emotions": [],
                    "personas": [],
                    "description": "",
                    "send_mode": MEME_SEND_MODE_STICKER,
                }
            ), 404

        emotions = (
            [e.strip() for e in row["emotions"].split(",")] if row["emotions"] else []
        )
        personas = (
            [p.strip() for p in row["personas"].split(",")] if row["personas"] else []
        )
        description = row["description"] or ""
        send_mode = normalize_meme_send_mode(
            row["send_mode"] if "send_mode" in row.keys() else None
        )

        return jsonify(
            {
                "filename": filename,
                "emotions": emotions,
                "personas": personas,
                "description": description,
                "send_mode": send_mode,
            }
        ), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


async def get_emoji_file_base64():
    """获取表情文件的 Base64 编码数据"""
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"message": "缺少文件名"}), 400

    filename = os.path.basename(filename)

    target_path = os.path.join(MEMES_DIR, filename)
    if not os.path.exists(target_path):
        found = False
        for item in os.listdir(MEMES_DIR):
            item_path = os.path.join(MEMES_DIR, item)
            if os.path.isdir(item_path):
                file_path = os.path.join(item_path, filename)
                if os.path.exists(file_path):
                    target_path = file_path
                    found = True
                    break
        if not found:
            return jsonify({"message": "文件不存在"}), 404

    try:
        with open(target_path, "rb") as f:
            content = f.read()
        mime_type, _ = mimetypes.guess_type(target_path)
        if not mime_type:
            mime_type = "image/png"
        base64_str = base64.b64encode(content).decode("utf-8")
        return jsonify(
            {"status": "success", "mime": mime_type, "base64": base64_str}
        ), 200
    except Exception as e:
        return jsonify({"message": f"读取文件失败: {e}"}), 500


async def get_emotions():
    """获取表情包类别并返回空描述字典（保持前端兼容性）"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        categories = category_manager.get_categories()
        return jsonify(dict.fromkeys(categories, ""))
    except Exception as e:
        current_app.logger.error(f"获取标签失败: {e}")
        return jsonify({"error": "获取标签失败"}), 500


async def generate_thumbnails_api():
    """手动触发全量缩略图生成，用于调试和预生成"""
    try:
        from PIL import Image as PILImage

        from ....config import MEMES_DIR, PLUGIN_DATA_DIR
        from ...db.database import get_db_conn

        PILImage.init()
        avif_supported = "AVIF" in PILImage.SAVE
        thumb_ext = ".avif" if avif_supported else ".webp"
        thumb_format = "AVIF" if avif_supported else "WEBP"

        thumb_dir = os.path.join(PLUGIN_DATA_DIR, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)

        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM memes")
        rows = cursor.fetchall()
        conn.close()

        total = len(rows)
        existed = 0
        generated = 0
        failed = 0
        errors = []

        for row in rows:
            filename = row["filename"]
            # Find original file
            target_path = os.path.join(MEMES_DIR, filename)
            if not os.path.exists(target_path):
                # Search inside categories if not found
                found = False
                for item in os.listdir(MEMES_DIR):
                    if item == ".thumbnails" or item == "thumbnails":
                        continue
                    item_path = os.path.join(MEMES_DIR, item)
                    if os.path.isdir(item_path):
                        check_path = os.path.join(item_path, filename)
                        if os.path.exists(check_path):
                            target_path = check_path
                            found = True
                            break
                if not found:
                    failed += 1
                    errors.append(
                        {
                            "filename": filename,
                            "error": "Original file not found on disk",
                        }
                    )
                    continue

            thumb_filename = filename + thumb_ext
            thumb_path = os.path.join(thumb_dir, thumb_filename)

            need_generate = True
            if os.path.exists(thumb_path):
                try:
                    if os.path.getmtime(target_path) <= os.path.getmtime(thumb_path):
                        need_generate = False
                        existed += 1
                except Exception:
                    pass

            if need_generate:
                try:
                    with PILImage.open(target_path) as img:
                        orig_format = img.format
                        if orig_format == "GIF":
                            img.seek(0)
                            img = img.copy()

                        img.thumbnail((150, 150))

                        temp_thumb_path = thumb_path + ".tmp"
                        img.save(temp_thumb_path, format=thumb_format)
                        os.replace(temp_thumb_path, thumb_path)
                        generated += 1
                except Exception as e:
                    failed += 1
                    errors.append({"filename": filename, "error": str(e)})

        return (
            jsonify(
                {
                    "status": "success",
                    "avif_supported": avif_supported,
                    "total": total,
                    "existed": existed,
                    "generated": generated,
                    "failed": failed,
                    "errors": errors,
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Failed manual thumbnail generation: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


async def clear_all_thumbnails_api():
    """Clear all thumbnail cache files."""
    try:
        from ....config import PLUGIN_DATA_DIR

        thumb_dir = Path(PLUGIN_DATA_DIR) / "thumbnails"
        removed = 0
        if thumb_dir.exists():
            for f in thumb_dir.iterdir():
                if f.is_file():
                    f.unlink()
                    removed += 1

        return jsonify({"status": "success", "removed": removed}), 200
    except Exception as e:
        logger.error(f"Failed to clear all thumbnails: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


async def clear_orphaned_thumbnails_api():
    """Clear thumbnail files that have no matching meme in the database."""
    try:
        from ....config import PLUGIN_DATA_DIR

        thumb_dir = Path(PLUGIN_DATA_DIR) / "thumbnails"
        if not thumb_dir.exists():
            return jsonify({"status": "success", "removed": 0, "total": 0}), 200

        # Get all known meme filenames from DB
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM memes")
        rows = cursor.fetchall()
        conn.close()
        known_filenames = {row["filename"] for row in rows}

        # Scan thumbnail directory and remove orphans
        removed = 0
        total = 0
        for thumb_file in thumb_dir.iterdir():
            if not thumb_file.is_file():
                continue
            total += 1
            # Thumbnail filename format: <original_filename>.<thumb_ext>
            # e.g. "image.jpg.avif" or "image.jpg.webp"
            name = thumb_file.name
            # Strip the thumbnail extension (.avif or .webp) to get original filename
            original_name = None
            for ext in (".avif", ".webp"):
                if name.endswith(ext):
                    original_name = name[: -len(ext)]
                    break
            if original_name is None:
                # Unknown format, treat as orphan
                thumb_file.unlink()
                removed += 1
                continue

            if original_name not in known_filenames:
                thumb_file.unlink()
                removed += 1

        return (
            jsonify({"status": "success", "removed": removed, "total": total}),
            200,
        )
    except Exception as e:
        logger.error(f"Failed to clear orphaned thumbnails: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
