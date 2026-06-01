from quart import current_app


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

        from ...core.emotion_handler import sync_tag_embeddings

        asyncio.create_task(sync_tag_embeddings(sender))
