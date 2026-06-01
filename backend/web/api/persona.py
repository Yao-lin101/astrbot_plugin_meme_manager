import logging

from quart import current_app, jsonify, request

from ...core.helpers import get_settings_dict, save_settings_dict
from .common import trigger_tag_vectorization

logger = logging.getLogger(__name__)


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


async def get_persona_tags():
    """获取所有的人格专属表情包配置（包含收集偏好和使用偏好）"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        sender = plugin_config.get("sender")
        if not sender:
            return jsonify({})

        settings = get_settings_dict(sender.config)
        return jsonify(settings)
    except Exception as e:
        logger.error(f"获取人格专属标签失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


async def save_persona_tag():
    """保存某个人格的专属表情包配置"""
    try:
        data = await request.get_json()
        persona_id = data.get("persona_id")
        meme_preference = data.get("meme_preference", "")
        meme_use_preference = data.get(
            "meme_use_preference", data.get("tag", "")
        )  # tag 兼容旧格式

        if not persona_id:
            return jsonify({"message": "Persona ID is required"}), 400

        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        sender = plugin_config.get("sender")
        if not sender:
            return jsonify({"message": "Sender not found"}), 404

        settings = get_settings_dict(sender.config)

        # 如果 tag 和偏好描述都为空，则移除此配置
        if not meme_preference.strip() and not meme_use_preference.strip():
            if persona_id in settings:
                del settings[persona_id]
        else:
            settings[persona_id] = {
                "meme_preference": meme_preference.strip(),
                "meme_use_preference": meme_use_preference.strip(),
            }

        save_settings_dict(sender.config, settings)

        # 重新加载表情配置
        await sender.reload_emotions()

        trigger_tag_vectorization()
        return (
            jsonify({"message": "Persona tag updated successfully", "tags": settings}),
            200,
        )
    except Exception as e:
        logger.error(f"保存人格专属标签失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500
