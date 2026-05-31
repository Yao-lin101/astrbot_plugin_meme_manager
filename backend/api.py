import logging
import os

from quart import Blueprint, current_app, jsonify, request

from ..config import MEMES_DIR
from .models import (
    DuplicateEmojiError,
    add_emoji_to_category,
    batch_convert_to_gif,
    batch_copy_emojis,
    batch_delete_emojis,
    batch_move_emojis,
    clear_all_emojis,
    clear_category_emojis,
    delete_emoji_from_category,
    get_emoji_by_category,
    move_emoji_to_category,
)

api = Blueprint("api", __name__)

logger = logging.getLogger(__name__)


def _get_provider_label(img_sync) -> str:
    """返回当前图床 provider 的展示名称。"""
    provider_type = getattr(img_sync, "provider_type", "")
    if provider_type == "cloudflare_r2":
        return "Cloudflare R2"
    if provider_type == "stardots":
        return "StarDots"

    provider = getattr(img_sync, "provider", None)
    if provider is not None:
        return provider.__class__.__name__
    return "未知图床"


def trigger_tag_vectorization() -> None:
    """Trigger background tag embedding synchronization if the plugin sender is configured."""
    plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
    sender = plugin_config.get("sender")
    if sender:
        import asyncio

        from .emotion_handler import sync_tag_embeddings

        asyncio.create_task(sync_tag_embeddings(sender))


@api.route("/emoji", methods=["GET"])
async def get_all_emojis():
    """获取所有表情包（按类别分组），支持按人格过滤"""
    persona_id = request.args.get("persona_id")

    from .database import get_db_conn

    conn = get_db_conn()
    cursor = conn.cursor()

    if persona_id:
        cursor.execute(
            "SELECT filename, emotions FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
            (f"%,{persona_id},%",),
        )
    else:
        cursor.execute("SELECT filename, emotions FROM memes")

    rows = cursor.fetchall()
    conn.close()

    emoji_data = {}
    mtimes = {}
    for row in rows:
        filename = row["filename"]
        emotions = row["emotions"]

        # Verify file exists
        full_path = os.path.join(MEMES_DIR, filename)
        if not os.path.exists(full_path):
            continue

        try:
            mtimes[filename] = int(os.path.getmtime(full_path))
        except Exception:
            mtimes[filename] = 0

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

    return jsonify({"categories": emoji_data, "mtimes": mtimes})


@api.route("/emoji/<category>", methods=["GET"])
async def get_emojis_by_category(category):
    """获取指定类别的表情包"""
    emojis = get_emoji_by_category(category)
    if emojis is None:
        return jsonify({"message": "Category not found"}), 404
    return jsonify(emojis if isinstance(emojis, list) else []), 200


@api.route("/emoji/add", methods=["POST"])
async def add_emoji():
    """添加表情包到指定类别"""
    try:
        is_json_request = request.is_json
        if is_json_request:
            data = await request.get_json()
            category = data.get("category")
            filename = data.get("filename")
            base64_data = data.get("base64_data")
            if not category or not filename or not base64_data:
                return jsonify({"message": "没有找到上传的图片文件或缺少类别"}), 400

            import base64
            import io

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

        if not category:
            return jsonify({"message": "没有指定类别"}), 400

        if not image_file or not image_file.filename:
            return jsonify({"message": "无效的图片文件"}), 400

        # 记录上传信息
        logger.info(f"收到上传请求: 类别={category}, 文件名={image_file.filename}")

        try:
            result = add_emoji_to_category(category, image_file)

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


@api.route("/emoji/delete", methods=["POST"])
async def delete_emoji():
    """删除指定类别的表情包"""
    data = await request.get_json()
    category = data.get("category")
    image_file = data.get("image_file")
    if not category or not image_file:
        return jsonify({"message": "Category and image file are required"}), 400

    if delete_emoji_from_category(category, image_file):
        return jsonify(
            {
                "message": "Emoji deleted successfully",
                "category": category,
                "filename": image_file,
            }
        ), 200
    else:
        return jsonify({"message": "Emoji not found"}), 404


@api.route("/emoji/batch_delete", methods=["POST"])
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


@api.route("/emoji/batch_convert_gif", methods=["POST"])
async def batch_convert_emoji_gif():
    """批量将表情文件转换为 GIF 格式"""
    data = await request.get_json()
    filenames = data.get("filenames")

    if not isinstance(filenames, list) or not filenames:
        return jsonify({"message": "filenames list is required"}), 400

    result = batch_convert_to_gif(filenames)
    return jsonify(result), 200


@api.route("/emoji/move", methods=["POST"])
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


@api.route("/emoji/batch_move", methods=["POST"])
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


@api.route("/emoji/batch_copy", methods=["POST"])
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


@api.route("/category/clear", methods=["POST"])
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


@api.route("/emoji/clear_all", methods=["POST"])
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


@api.route("/emotions", methods=["GET"])
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


@api.route("/category/delete", methods=["POST"])
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


@api.route("/sync/status", methods=["GET"])
async def get_sync_status():
    """获取同步状态"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")

        if not category_manager:
            raise ValueError("未找到类别管理器")

        logger.info("获取同步状态...")
        missing_in_config, deleted_categories = category_manager.get_sync_status()

        return jsonify(
            {
                "status": "ok",
                "missing_in_config": missing_in_config,
                "deleted_categories": deleted_categories,
                "differences": {
                    "missing_in_config": missing_in_config,
                    "deleted_categories": deleted_categories,
                },
            }
        )
    except Exception as e:
        logger.error(f"获取同步状态失败: {e}")
        return jsonify({"error": "获取同步状态失败"}), 500


@api.route("/sync/config", methods=["POST"])
async def sync_config():
    """同步配置与文件夹结构的 API 端点"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")

        if not category_manager:
            raise ValueError("未找到类别管理器")

        logger.info("开始同步配置...")
        if category_manager.sync_with_filesystem():
            logger.info("配置同步成功")
            return jsonify({"message": "配置同步成功"}), 200
        else:
            logger.warning("配置同步失败")
            return jsonify({"message": "配置同步失败"}), 500
    except Exception as e:
        logger.error(f"配置同步失败: {e}")
        return jsonify({"message": f"配置同步失败: {str(e)}"}), 500


@api.route("/category/restore", methods=["POST"])
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


@api.route("/category/rename", methods=["POST"])
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


@api.route("/img_host/sync/status", methods=["GET"])
async def get_img_host_sync_status():
    """获取同步状态"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        img_sync = plugin_config.get("img_sync")
        if not img_sync:
            return jsonify({"error": "图床服务未配置"}), 400

        status = img_sync.check_status()
        status["upload_count"] = len(status.get("to_upload", []))
        status["download_count"] = len(status.get("to_download", []))
        status["provider_label"] = _get_provider_label(img_sync)
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/img_host/sync/upload", methods=["POST"])
async def sync_to_remote():
    """同步到云端"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        img_sync = plugin_config.get("img_sync")
        if not img_sync:
            return jsonify({"message": "图床服务未配置"}), 400

        img_sync.sync_process = img_sync._start_sync_process("upload")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@api.route("/img_host/sync/download", methods=["POST"])
async def sync_from_remote():
    """从云端同步"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        img_sync = plugin_config.get("img_sync")
        if not img_sync:
            return jsonify({"message": "图床服务未配置"}), 400

        img_sync.sync_process = img_sync._start_sync_process("download")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@api.route("/img_host/sync/check_process", methods=["GET"])
async def check_sync_process():
    """检查同步进程状态"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        img_sync = plugin_config.get("img_sync")
        if not img_sync or not img_sync.sync_process:
            return jsonify({"completed": True, "success": True})

        if not img_sync.sync_process.is_alive():
            success = img_sync.sync_process.exitcode == 0
            img_sync.sync_process = None
            return jsonify({"completed": True, "success": success})

        return jsonify({"completed": False})
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@api.route("/personas", methods=["GET"])
async def get_personas():
    """获取所有系统注册的人格列表"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        context = plugin_config.get("context")
        if context:
            personas = context.provider_manager.personas
            result = []
            for p in personas:
                result.append(
                    {
                        "id": p.get("id") or p.get("name") or "",
                        "name": p.get("name") or "",
                        "prompt": p.get("prompt") or "",
                    }
                )
            return jsonify(result)
        elif "personas" in plugin_config:
            return jsonify(plugin_config["personas"])
        return jsonify([])
    except Exception as e:
        logger.error(f"获取人格列表失败: {e}")
        return jsonify({"error": str(e)}), 500


@api.route("/emoji/edit", methods=["POST"])
async def edit_emoji():
    """编辑表情包的标签和允许的人格"""
    try:
        from pathlib import Path

        data = await request.get_json()
        filename = data.get("filename")
        emotions = data.get("emotions")  # List of emotions
        personas = data.get("personas")  # List of persona IDs, or ["*"]

        if not filename:
            return jsonify({"message": "Filename is required"}), 400

        from .database import get_db_conn

        conn = get_db_conn()
        cursor = conn.cursor()

        emotions_str = ",".join(emotions) if isinstance(emotions, list) else emotions
        personas_str = ",".join(personas) if isinstance(personas, list) else personas

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


@api.route("/emoji/info/<filename>", methods=["GET"])
async def get_emoji_info(filename):
    """获取特定表情包的信息"""
    try:
        from .database import get_db_conn

        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT emotions, personas FROM memes WHERE filename = ?", (filename,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"emotions": [], "personas": []}), 404

        emotions = (
            [e.strip() for e in row["emotions"].split(",")] if row["emotions"] else []
        )
        personas = (
            [p.strip() for p in row["personas"].split(",")] if row["personas"] else []
        )

        return jsonify(
            {"filename": filename, "emotions": emotions, "personas": personas}
        ), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/emoji/batch_edit_personas", methods=["POST"])
async def batch_edit_personas():
    """批量修改表情包允许的人格"""
    try:
        data = await request.get_json()
        filenames = data.get("filenames")
        personas = data.get("personas")  # List of persona IDs, or ["*"]

        if not isinstance(filenames, list) or not filenames:
            return jsonify({"message": "filenames list is required"}), 400

        from .database import get_db_conn

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


@api.route("/persona_tags", methods=["GET"])
async def get_persona_tags():
    """获取所有的人格专属标签"""
    from .helpers import load_persona_tags

    return jsonify(load_persona_tags())


@api.route("/persona_tags", methods=["POST"])
async def save_persona_tag():
    """保存某个人格的专属标签"""
    try:
        data = await request.get_json()
        persona_id = data.get("persona_id")
        tag = data.get("tag")

        if not persona_id:
            return jsonify({"message": "Persona ID is required"}), 400

        from .helpers import load_persona_tags, save_persona_tags

        tags = load_persona_tags()

        # 如果 tag 为空，则移除此配置
        if not tag or not tag.strip():
            if persona_id in tags:
                del tags[persona_id]
        else:
            tags[persona_id] = tag.strip()

        save_persona_tags(tags)
        trigger_tag_vectorization()
        return (
            jsonify({"message": "Persona tag updated successfully", "tags": tags}),
            200,
        )
    except Exception as e:
        logger.error(f"保存人格专属标签失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


@api.route("/emoji/batch_import", methods=["POST"])
async def batch_import_emojis():
    """批量导入已存在的表情包到指定类别（为选中的表情包文件追加该类别标签）"""
    try:
        data = await request.get_json()
        category = data.get("category")
        filenames = data.get("filenames")

        if not category or not isinstance(filenames, list) or not filenames:
            return jsonify({"message": "Category and filenames list are required"}), 400

        from .database import get_db_conn

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


@api.route("/emoji/file_base64", methods=["GET"])
async def get_emoji_file_base64():
    """获取表情文件的 Base64 编码数据"""
    import base64
    import mimetypes

    from ..config import MEMES_DIR

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


@api.route("/emoji/check_duplicates", methods=["GET"])
async def check_duplicates():
    """扫描所有表情包以查找重复的相似表情"""
    try:
        threshold = float(request.args.get("threshold", 0.85))

        from .database import get_db_conn
        import json
        from .similarity import calculate_similarity_score

        conn = get_db_conn()
        cursor = conn.cursor()

        # Load all memes metadata
        cursor.execute("SELECT filename, emotions, personas FROM memes")
        meme_rows = cursor.fetchall()
        meme_meta = {
            row["filename"]: {
                "emotions": [e.strip() for e in row["emotions"].split(",")]
                if row["emotions"]
                else [],
                "personas": [p.strip() for p in row["personas"].split(",")]
                if row["personas"]
                else [],
            }
            for row in meme_rows
        }

        # Load all similarity features
        cursor.execute(
            "SELECT filename, width, height, aspect_ratio, frame_count, features_json FROM meme_similarity_features"
        )
        rows = cursor.fetchall()
        conn.close()

        features_list = []
        for row in rows:
            filename = row["filename"]
            if filename not in meme_meta:
                continue
            try:
                features_list.append(
                    {
                        "filename": filename,
                        "width": row["width"],
                        "height": row["height"],
                        "aspect_ratio": row["aspect_ratio"],
                        "frame_count": row["frame_count"],
                        "frames": json.loads(row["features_json"]),
                        "meta": meme_meta[filename],
                    }
                )
            except Exception:
                continue

        # Group similar memes
        from pathlib import Path
        from ..config import MEMES_DIR
        groups = []
        visited = set()

        for i, f1 in enumerate(features_list):
            if f1["filename"] in visited:
                continue

            group_memes = [f1]
            visited.add(f1["filename"])

            for f2 in features_list[i + 1 :]:
                if f2["filename"] in visited:
                    continue

                if abs(f1["aspect_ratio"] - f2["aspect_ratio"]) > 0.15:
                    continue

                score = calculate_similarity_score(f1, f2)
                if score >= threshold:
                    f2_copy = dict(f2)
                    f2_copy["similarity"] = score
                    group_memes.append(f2_copy)
                    visited.add(f2["filename"])

            if len(group_memes) > 1:
                f1_copy = dict(f1)
                f1_copy["similarity"] = 1.0
                group_memes[0] = f1_copy

                clean_memes = []
                for m in group_memes:
                    file_path = Path(MEMES_DIR) / m["filename"]
                    size_bytes = file_path.stat().st_size if file_path.exists() else 0
                    clean_memes.append({
                        "filename": m["filename"],
                        "emotions": m["meta"]["emotions"],
                        "personas": m["meta"]["personas"],
                        "similarity": m["similarity"],
                        "width": m.get("width", 0),
                        "height": m.get("height", 0),
                        "size_bytes": size_bytes
                    })
                groups.append({"id": f"group_{len(groups) + 1}", "memes": clean_memes})

        return jsonify({"status": "success", "groups": groups}), 200
    except Exception as e:
        logger.error(f"检查重复表情包失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


@api.route("/emoji/resolve_duplicates", methods=["POST"])
async def resolve_duplicates():
    """解析重复表情包：保留一部分，删除另外一部分，并可选地合并他们的标签和人格"""
    try:
        data = await request.get_json()
        keeps = data.get("keeps", [])
        deletes = data.get("deletes", [])
        merge = bool(data.get("merge", True))

        if not keeps or not deletes:
            return jsonify({"message": "keeps and deletes lists are required"}), 400

        from pathlib import Path

        from ..config import MEMES_DIR
        from .database import delete_meme_similarity_features, get_db_conn

        conn = get_db_conn()
        cursor = conn.cursor()

        # 1. If merge is true, extract all emotions and personas from deleted memes
        merged_emotions = set()
        merged_personas = set()

        if merge:
            for filename in deletes:
                cursor.execute(
                    "SELECT emotions, personas FROM memes WHERE filename = ?",
                    (filename,),
                )
                row = cursor.fetchone()
                if row:
                    if row["emotions"]:
                        merged_emotions.update(
                            e.strip() for e in row["emotions"].split(",")
                        )
                    if row["personas"]:
                        merged_personas.update(
                            p.strip() for p in row["personas"].split(",")
                        )

        # 2. Delete the deleted memes from database and filesystem
        for filename in deletes:
            cursor.execute("DELETE FROM memes WHERE filename = ?", (filename,))
            delete_meme_similarity_features(filename)

            file_path = Path(MEMES_DIR) / filename
            if file_path.exists():
                file_path.unlink()

        # 3. Apply merged emotions & personas to kept memes if merge is enabled
        if merge and (merged_emotions or merged_personas):
            for filename in keeps:
                cursor.execute(
                    "SELECT emotions, personas FROM memes WHERE filename = ?",
                    (filename,),
                )
                row = cursor.fetchone()
                if row:
                    existing_emotions = (
                        set(row["emotions"].split(",")) if row["emotions"] else set()
                    )
                    existing_personas = (
                        set(row["personas"].split(",")) if row["personas"] else set()
                    )

                    for emo in merged_emotions:
                        if emo:
                            existing_emotions.add(emo)

                    if "*" in merged_personas or "*" in existing_personas:
                        existing_personas = {"*"}
                    else:
                        for p in merged_personas:
                            if p:
                                existing_personas.add(p)

                    cursor.execute(
                        "UPDATE memes SET emotions = ?, personas = ? WHERE filename = ?",
                        (
                            ",".join(existing_emotions),
                            ",".join(existing_personas),
                            filename,
                        ),
                    )

        conn.commit()
        conn.close()

        # Reload
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            category_manager.sync_with_filesystem()

        trigger_tag_vectorization()

        return jsonify({"status": "success", "message": "重复表情清理完成"}), 200
    except Exception as e:
        logger.error(f"清理重复表情包失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500

