import base64
import io
import logging
import mimetypes
import os
from pathlib import Path

from quart import current_app, jsonify, request

from ....config import MEMES_DIR
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

    return jsonify({"categories": emoji_data, "mtimes": mtimes, "descriptions": descriptions})


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
    """编辑表情包的标签和允许的人格与描述"""
    try:
        data = await request.get_json()
        filename = data.get("filename")
        emotions = data.get("emotions")  # List of emotions
        personas = data.get("personas")  # List of persona IDs, or ["*"]
        description = data.get("description")

        if not filename:
            return jsonify({"message": "Filename is required"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        emotions_str = ",".join(emotions) if isinstance(emotions, list) else emotions
        personas_str = ",".join(personas) if isinstance(personas, list) else personas

        if "description" in data:
            cursor.execute(
                "UPDATE memes SET emotions = ?, personas = ?, description = ? WHERE filename = ?",
                (emotions_str, personas_str, description, filename),
            )
        else:
            cursor.execute(
                "UPDATE memes SET emotions = ?, personas = ? WHERE filename = ?",
                (emotions_str, personas_str, filename),
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
            "SELECT emotions, personas, description FROM memes WHERE filename = ?",
            (filename,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"emotions": [], "personas": [], "description": ""}), 404

        emotions = (
            [e.strip() for e in row["emotions"].split(",")] if row["emotions"] else []
        )
        personas = (
            [p.strip() for p in row["personas"].split(",")] if row["personas"] else []
        )
        description = row["description"] or ""

        return jsonify(
            {
                "filename": filename,
                "emotions": emotions,
                "personas": personas,
                "description": description,
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
