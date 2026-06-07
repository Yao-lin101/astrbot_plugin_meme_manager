import os

from astrbot.api import logger


def patch_onebot_serializer():
    """Monkeypatch OneBot image serializer to support sticker (subType=1) format."""
    try:
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        original_from_segment_to_dict = AiocqhttpMessageEvent._from_segment_to_dict

        async def patched_from_segment_to_dict(segment) -> dict:
            res = await original_from_segment_to_dict(segment)
            if res.get("type") == "image":
                sub_type = getattr(segment, "sub_type", None)
                if sub_type is None:
                    sub_type = getattr(segment, "subType", None)
                if sub_type is None:
                    sub_type = getattr(segment, "subtype", None)
                if sub_type is not None:
                    # Compatible with go-cqhttp (subType) and NapCat/Lagrange (sub_type, subtype)
                    data = res.setdefault("data", {})
                    data["subType"] = sub_type
                    data["sub_type"] = sub_type
                    data["subtype"] = sub_type
            return res

        AiocqhttpMessageEvent._from_segment_to_dict = patched_from_segment_to_dict
        logger.info(
            "Meme Manager: Successfully patched AiocqhttpMessageEvent._from_segment_to_dict for sticker support"
        )
    except Exception as e:
        logger.warning(f"Meme Manager: Failed to patch OneBot image serializer: {e}")


def wrap_api_handler(sender, handler):
    """Wrap api handlers to setup context and register a dynamic serve_emoji route."""

    async def wrapper(*args, **kwargs):
        from quart import current_app

        # Register the dynamic unauthenticated serve_emoji route on app startup/first request
        app = current_app._get_current_object()
        route_name = "meme_manager_serve_emoji"
        if route_name not in app.view_functions:

            async def serve_emoji_wrapper(category, filename):
                return await serve_emoji(sender, category, filename)

            app.add_url_rule(
                "/api/file/meme_manager/memes/<category>/<filename>",
                endpoint=route_name,
                view_func=serve_emoji_wrapper,
                methods=["GET"],
            )

        current_app.config["PLUGIN_CONFIG"] = {
            "sender": sender,
            "img_sync": sender.img_sync,
            "category_manager": sender.category_manager,
            "plugin_config": sender.config,
            "personas": [
                {
                    "id": p.get("id") or p.get("name") or "",
                    "name": p.get("name") or "",
                    "prompt": p.get("prompt") or "",
                }
                for p in sender.context.provider_manager.personas
            ]
            if hasattr(sender.context, "provider_manager")
            else [],
            "context": sender.context,
        }
        return await handler(*args, **kwargs)

    return wrapper


async def serve_emoji(sender, category, filename):
    """Serve emoji files from various directories."""
    from quart import send_from_directory

    from ...config import MEMES_DIR

    # Check absolute location directly under MEMES_DIR
    target_path = os.path.join(MEMES_DIR, filename)
    if os.path.exists(target_path):
        return await send_from_directory(MEMES_DIR, filename)

    # Check category path
    if category != "file" and category != "all":
        category_path = os.path.join(MEMES_DIR, category)
        if os.path.exists(os.path.join(category_path, filename)):
            return await send_from_directory(category_path, filename)

    # Search all subdirectories inside MEMES_DIR
    for item in os.listdir(MEMES_DIR):
        item_path = os.path.join(MEMES_DIR, item)
        if os.path.isdir(item_path):
            file_path = os.path.join(item_path, filename)
            if os.path.exists(file_path):
                return await send_from_directory(item_path, filename)

    return "File not found: " + filename, 404


def register_apis(sender):
    """Register all Quart web endpoints for Meme Manager plugin."""
    from .api import (
        add_emoji,
        batch_analyze_emojis,
        batch_convert_emoji_gif,
        batch_copy_emoji,
        batch_delete_emoji,
        batch_edit_personas,
        batch_import_emojis,
        batch_move_emoji,
        batch_rename_emojis_to_tags,
        cancel_batch_analyze,
        check_duplicates,
        check_sync_process,
        clear_all_emoji,
        clear_category,
        delete_category,
        delete_emoji,
        edit_emoji,
        get_all_emojis,
        get_batch_analyze_status,
        get_config_schema,
        get_config_values,
        get_emoji_file_base64,
        get_emoji_info,
        get_emojis_by_category,
        get_emotions,
        get_img_host_sync_status,
        get_persona_tags,
        get_personas,
        get_prompt_template,
        get_providers,
        get_sync_status,
        merge_tags,
        move_emoji,
        rename_category,
        resolve_duplicates,
        restore_category,
        save_persona_tag,
        scan_similar_tags,
        sync_config,
        sync_from_remote,
        sync_to_remote,
        update_config_values,
    )

    PLUGIN_NAME = "astrbot_plugin_meme_manager"

    apis = [
        ("emoji", get_all_emojis, ["GET"]),
        ("emoji/add", add_emoji, ["POST"]),
        ("emoji/delete", delete_emoji, ["POST"]),
        ("emoji/batch_delete", batch_delete_emoji, ["POST"]),
        ("emoji/batch_convert_gif", batch_convert_emoji_gif, ["POST"]),
        ("emoji/batch_rename_to_tags", batch_rename_emojis_to_tags, ["POST"]),
        ("emoji/move", move_emoji, ["POST"]),
        ("emoji/batch_move", batch_move_emoji, ["POST"]),
        ("emoji/batch_copy", batch_copy_emoji, ["POST"]),
        ("category/clear", clear_category, ["POST"]),
        ("emoji/clear_all", clear_all_emoji, ["POST"]),
        ("emotions", get_emotions, ["GET"]),
        ("category/delete", delete_category, ["POST"]),
        ("sync/status", get_sync_status, ["GET"]),
        ("sync/config", sync_config, ["POST"]),
        ("category/restore", restore_category, ["POST"]),
        ("category/rename", rename_category, ["POST"]),
        ("img_host/sync/status", get_img_host_sync_status, ["GET"]),
        ("img_host/sync/upload", sync_to_remote, ["POST"]),
        ("img_host/sync/download", sync_from_remote, ["POST"]),
        ("img_host/sync/check_process", check_sync_process, ["GET"]),
        ("personas", get_personas, ["GET"]),
        ("emoji/edit", edit_emoji, ["POST"]),
        ("emoji/info", get_emoji_info, ["GET"]),
        ("emoji/info/<filename>", get_emoji_info, ["GET"]),
        ("emoji/batch_edit_personas", batch_edit_personas, ["POST"]),
        ("persona_tags", get_persona_tags, ["GET"]),
        ("persona_tags", save_persona_tag, ["POST"]),
        ("emoji/batch_import", batch_import_emojis, ["POST"]),
        ("emoji/file_base64", get_emoji_file_base64, ["GET"]),
        ("emoji/dup/check", check_duplicates, ["GET"]),
        ("emoji/dup/resolve", resolve_duplicates, ["POST"]),
        ("emoji/<category>", get_emojis_by_category, ["GET"]),
        ("providers", get_providers, ["GET"]),
        ("prompt/template", get_prompt_template, ["GET"]),
        ("emoji/batch_analyze", batch_analyze_emojis, ["POST"]),
        ("emoji/batch_analyze/status", get_batch_analyze_status, ["GET"]),
        ("emoji/batch_analyze/cancel", cancel_batch_analyze, ["POST"]),
        ("tag_merge/scan", scan_similar_tags, ["GET"]),
        ("tag_merge/merge", merge_tags, ["POST"]),
        ("config/schema", get_config_schema, ["GET"]),
        ("config/values", get_config_values, ["GET"]),
        ("config/update", update_config_values, ["POST"]),
    ]

    for route, handler, methods in apis:
        sender.context.register_web_api(
            f"/{PLUGIN_NAME}/{route}",
            wrap_api_handler(sender, handler),
            methods,
            f"Meme Manager API: {route}",
        )

    # Serve emoji static files endpoint
    async def serve_emoji_route_wrapper(category, filename):
        return await serve_emoji(sender, category, filename)

    sender.context.register_web_api(
        f"/{PLUGIN_NAME}/memes/<category>/<filename>",
        serve_emoji_route_wrapper,
        ["GET"],
        "Serve emoji files",
    )
