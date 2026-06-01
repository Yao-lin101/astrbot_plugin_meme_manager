import logging
import os

from quart import current_app, jsonify, request

from ....config import MEMES_DIR
from ...db.models import clear_all_emojis, clear_category_emojis
from .common import trigger_tag_vectorization

logger = logging.getLogger(__name__)


async def clear_category():
    """清空指定类别下的所有表情包，但保留类别和配置。"""
    data = await request.get_json()
    category = data.get("category")
    if not category:
        return jsonify({"message": "Category is required"}), 400

    result = clear_category_emojis(category)
    if not result["category_exists"]:
        return jsonify({"message": "Category not found"}), 404

    deleted_files = result["deleted_files"]
    return jsonify(
        {
            "message": "Category cleared successfully",
            "category": category,
            "deleted_files": deleted_files,
            "deleted_count": len(deleted_files),
        }
    ), 200


async def clear_all_emoji():
    """清空所有类别中的表情包，但保留类别和配置。"""
    result = clear_all_emojis()
    deleted_by_category = result["deleted_by_category"]
    deleted_count = sum(deleted_by_category.values())
    return jsonify(
        {
            "message": "All emojis cleared successfully",
            "deleted_by_category": deleted_by_category,
            "deleted_count": deleted_count,
            "affected_categories": len(deleted_by_category),
        }
    ), 200


async def delete_category():
    """删除表情包类别"""
    try:
        data = await request.get_json()

        category = data.get("category")
        if not category:
            return jsonify({"message": "Category is required"}), 400

        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")

        if not category_manager:
            return jsonify({"message": "Category manager not found"}), 404

        if category_manager.delete_category(category):
            return jsonify({"message": "Category deleted successfully"}), 200
        else:
            return jsonify({"message": "Failed to delete category"}), 500
    except Exception as e:
        return jsonify({"message": f"Failed to delete category: {str(e)}"}), 500


async def restore_category():
    """恢复或创建新类别"""
    try:
        data = await request.get_json()

        category = data.get("category")

        if not category:
            return jsonify({"message": "Category is required"}), 400

        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")

        if not category_manager:
            return jsonify({"message": "Category manager not found"}), 404

        # 创建类别目录
        category_path = os.path.join(MEMES_DIR, category)
        os.makedirs(category_path, exist_ok=True)

        # 添加分类
        if category_manager.add_category(category):
            trigger_tag_vectorization()
            return jsonify({"message": "Category created successfully"}), 200
        else:
            return jsonify({"message": "Failed to create category"}), 500

    except Exception as e:
        return jsonify({"message": f"Failed to create category: {str(e)}"}), 500


async def rename_category():
    """重命名类别"""
    try:
        data = await request.get_json()
        old_name = data.get("old_name")
        new_name = data.get("new_name")
        if not old_name or not new_name:
            return jsonify({"message": "Old and new category names are required"}), 400

        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")

        if not category_manager:
            return jsonify({"message": "Category manager not found"}), 404

        if category_manager.rename_category(old_name, new_name):
            trigger_tag_vectorization()
            return jsonify({"message": "Category renamed successfully"}), 200
        else:
            return jsonify({"message": "Failed to rename category"}), 500
    except Exception as e:
        return jsonify({"message": f"Failed to rename category: {str(e)}"}), 500
