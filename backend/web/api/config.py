import json
import logging
import os

from quart import current_app, jsonify, request

from astrbot.core.star.star import star_registry
from astrbot.dashboard.routes.config import validate_config

logger = logging.getLogger(__name__)


async def get_config_schema():
    """Get the configuration schema for the meme manager plugin."""
    try:
        plugin_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        schema_path = os.path.join(plugin_root, "_conf_schema.json")
        if not os.path.exists(schema_path):
            return jsonify({"message": "Schema file not found"}), 404
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        return jsonify(schema), 200
    except Exception as e:
        logger.exception("Failed to get config schema")
        return jsonify({"message": str(e)}), 500


async def get_config_values():
    """Get the current configuration values for the meme manager plugin."""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        sender = plugin_config.get("sender")
        if not sender:
            return jsonify({"message": "Plugin sender not found"}), 504
        return jsonify(sender.config), 200
    except Exception as e:
        logger.exception("Failed to get config values")
        return jsonify({"message": str(e)}), 500


async def update_config_values():
    """Update and save the configuration values for the meme manager plugin."""
    try:
        post_configs = await request.get_json()
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        sender = plugin_config.get("sender")
        if not sender:
            return jsonify({"message": "Plugin sender not found"}), 504

        plugin_name = "astrbot_plugin_meme_manager"
        md = None
        for plugin_md in star_registry:
            if plugin_md.name == plugin_name:
                md = plugin_md
                break

        if not md:
            return jsonify({"message": f"Plugin {plugin_name} not found"}), 404
        if not md.config:
            return jsonify(
                {"message": f"Plugin {plugin_name} has no config registered"}
            ), 400

        # Validate configuration using standard validator
        errors, post_configs = validate_config(
            post_configs, getattr(md.config, "schema", {}), is_core=False
        )
        if errors:
            return jsonify({"message": f"Validation failed: {errors}"}), 400

        # Save the configuration
        md.config.save_config(post_configs)

        # Trigger hot reload of the plugin in background
        import asyncio

        async def do_reload():
            await asyncio.sleep(0.5)  # wait a moment for the response to finish
            try:
                if (
                    hasattr(sender.context, "_star_manager")
                    and sender.context._star_manager
                ):
                    logger.info(f"Triggering hot reload for plugin {plugin_name}...")
                    await sender.context._star_manager.reload(plugin_name)
            except Exception as reload_err:
                logger.error(
                    f"Failed to reload plugin {plugin_name}: {reload_err}",
                    exc_info=True,
                )

        asyncio.create_task(do_reload())

        return jsonify({"message": "配置保存成功，插件正在热重载。"}), 200
    except Exception as e:
        logger.exception("Failed to update config")
        return jsonify({"message": f"Failed to save config: {str(e)}"}), 500


async def get_ui_settings():
    """Get UI settings from a local json file in PLUGIN_DATA_DIR."""
    try:
        from ...config import PLUGIN_DATA_DIR

        settings_path = PLUGIN_DATA_DIR / "ui_settings.json"
        if not settings_path.exists():
            return jsonify({}), 200
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        logger.exception("Failed to get UI settings")
        return jsonify({"message": str(e)}), 500


async def save_ui_settings():
    """Save UI settings to a local json file in PLUGIN_DATA_DIR."""
    try:
        from ...config import PLUGIN_DATA_DIR

        post_data = await request.get_json()
        settings_path = PLUGIN_DATA_DIR / "ui_settings.json"
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(post_data, f, ensure_ascii=False, indent=2)
        return jsonify({"message": "UI settings saved"}), 200
    except Exception as e:
        logger.exception("Failed to save UI settings")
        return jsonify({"message": str(e)}), 500
