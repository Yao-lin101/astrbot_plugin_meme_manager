import logging

from quart import current_app, jsonify, request

from ...db.database import get_db_conn
from ...db.models import (
    batch_convert_to_gif,
    batch_copy_emojis,
    batch_delete_emojis,
    batch_move_emojis,
    move_emoji_to_category,
)

logger = logging.getLogger(__name__)


async def batch_delete_emoji():
    """批量删除指定类别的表情包"""
    data = await request.get_json()
    category = data.get("category")
    image_files = data.get("image_files")

    if not category or not isinstance(image_files, list) or not image_files:
        return jsonify({"message": "Category and image_files are required"}), 400

    result = batch_delete_emojis(category, image_files)
    if not result["category_exists"]:
        return jsonify({"message": "Category not found"}), 404

    deleted_files = result["deleted_files"]
    missing_files = result["missing_files"]
    return jsonify(
        {
            "message": "Batch delete completed",
            "category": category,
            "deleted_files": deleted_files,
            "missing_files": missing_files,
            "deleted_count": len(deleted_files),
            "missing_count": len(missing_files),
        }
    ), 200


async def batch_convert_emoji_gif():
    """批量将表情文件转换为 GIF 格式"""
    data = await request.get_json()
    filenames = data.get("filenames")

    if not isinstance(filenames, list) or not filenames:
        return jsonify({"message": "filenames list is required"}), 400

    result = batch_convert_to_gif(filenames)
    return jsonify(result), 200


async def move_emoji():
    """移动单个表情包到指定类别。"""
    data = await request.get_json()
    source_category = data.get("source_category")
    target_category = data.get("target_category")
    image_file = data.get("image_file")

    if not source_category or not target_category or not image_file:
        return (
            jsonify(
                {
                    "message": "source_category, target_category and image_file are required"
                }
            ),
            400,
        )

    if source_category == target_category:
        return jsonify({"message": "Source and target category must be different"}), 400

    result = move_emoji_to_category(source_category, image_file, target_category)
    if not result["source_category_exists"]:
        return jsonify({"message": "Source category not found"}), 404
    if result["conflict"]:
        return jsonify({"message": "Target file already exists"}), 409
    if result["missing"]:
        return jsonify({"message": "Emoji not found"}), 404

    return jsonify(
        {
            "message": "Emoji moved successfully",
            "source_category": result["source_category"],
            "target_category": result["target_category"],
            "filename": result["filename"],
        }
    ), 200


async def batch_move_emoji():
    """批量移动指定类别的表情包到另一个类别。"""
    data = await request.get_json()
    source_category = data.get("source_category")
    target_category = data.get("target_category")
    image_files = data.get("image_files")

    if (
        not source_category
        or not target_category
        or not isinstance(image_files, list)
        or not image_files
    ):
        return (
            jsonify(
                {
                    "message": "source_category, target_category and image_files are required"
                }
            ),
            400,
        )

    if source_category == target_category:
        return jsonify({"message": "Source and target category must be different"}), 400

    result = batch_move_emojis(source_category, image_files, target_category)
    if not result["source_category_exists"]:
        return jsonify({"message": "Source category not found"}), 404

    moved_files = result["moved_files"]
    missing_files = result["missing_files"]
    conflicting_files = result["conflicting_files"]
    return jsonify(
        {
            "message": "Batch move completed",
            "source_category": source_category,
            "target_category": target_category,
            "moved_files": moved_files,
            "missing_files": missing_files,
            "conflicting_files": conflicting_files,
            "moved_count": len(moved_files),
            "missing_count": len(missing_files),
            "conflict_count": len(conflicting_files),
        }
    ), 200


async def batch_copy_emoji():
    """批量复制指定类别的表情包到另一个类别。"""
    data = await request.get_json()
    source_category = data.get("source_category")
    target_category = data.get("target_category")
    image_files = data.get("image_files")

    if (
        not source_category
        or not target_category
        or not isinstance(image_files, list)
        or not image_files
    ):
        return (
            jsonify(
                {
                    "message": "source_category, target_category and image_files are required"
                }
            ),
            400,
        )

    result = batch_copy_emojis(source_category, image_files, target_category)
    if not result["source_category_exists"]:
        return jsonify({"message": "Source category not found"}), 404

    copied_files = result["copied_files"]
    missing_files = result["missing_files"]
    conflicting_files = result["conflicting_files"]
    return jsonify(
        {
            "message": "Batch copy completed",
            "source_category": source_category,
            "target_category": target_category,
            "copied_files": copied_files,
            "missing_files": missing_files,
            "conflicting_files": conflicting_files,
            "copied_count": len(copied_files),
            "missing_count": len(missing_files),
            "conflict_count": len(conflicting_files),
        }
    ), 200


async def batch_edit_personas():
    """批量修改表情包允许的人格"""
    try:
        data = await request.get_json()
        filenames = data.get("filenames")
        personas = data.get("personas")  # List of persona IDs, or ["*"]

        if not isinstance(filenames, list) or not filenames:
            return jsonify({"message": "filenames list is required"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        personas_str = ",".join(personas) if isinstance(personas, list) else personas

        for filename in filenames:
            cursor.execute(
                "UPDATE memes SET personas = ? WHERE filename = ?",
                (personas_str, filename),
            )
        conn.commit()
        conn.close()

        return jsonify({"message": "Batch personas updated successfully"}), 200
    except Exception as e:
        logger.error(f"批量更新人格限制失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


async def batch_import_emojis():
    """批量导入已存在的表情包到指定类别（为选中的表情包文件追加该类别标签）"""
    try:
        data = await request.get_json()
        category = data.get("category")
        filenames = data.get("filenames")

        if not category or not isinstance(filenames, list) or not filenames:
            return jsonify({"message": "Category and filenames list are required"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        # 遍历更新每个表情包的 emotions 字段
        for filename in filenames:
            cursor.execute("SELECT emotions FROM memes WHERE filename = ?", (filename,))
            row = cursor.fetchone()
            if row:
                existing_emotions = (
                    set(row["emotions"].split(",")) if row["emotions"] else set()
                )
                existing_emotions.add(category)
                cursor.execute(
                    "UPDATE memes SET emotions = ? WHERE filename = ?",
                    (",".join(existing_emotions), filename),
                )
        conn.commit()
        conn.close()

        # 重新加载类别
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            category_manager.sync_with_filesystem()

        return (
            jsonify(
                {
                    "message": "Batch import completed successfully",
                    "count": len(filenames),
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"批量导入表情包失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500
