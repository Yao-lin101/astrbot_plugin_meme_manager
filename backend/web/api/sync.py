import logging

from quart import current_app, jsonify

from .common import _get_provider_label

logger = logging.getLogger(__name__)


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
