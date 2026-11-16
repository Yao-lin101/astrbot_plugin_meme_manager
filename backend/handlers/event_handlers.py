from astrbot.api.event import AstrMessageEvent


class EventHandlers:
    @staticmethod
    async def handle_upload_image(sender, event: AstrMessageEvent):
        from .upload_handler import handle_upload_image

        async for res in handle_upload_image(sender, event):
            yield res

    @staticmethod
    async def _check_meme_preference_match(
        sender,
        event: AstrMessageEvent,
        content: bytes,
        file_type: str,
        preference_text: str,
    ) -> tuple[bool | None, str]:
        from .meme_stealer import _check_meme_preference_match

        return await _check_meme_preference_match(
            sender, event, content, file_type, preference_text
        )

    @staticmethod
    async def steal_meme(
        sender,
        event: AstrMessageEvent,
        image_url: str | None = None,
        categories: list[str] | None = None,
        description: str | None = None,
    ):
        from ..core.llm_tools import steal_meme

        return await steal_meme(
            sender,
            event,
            image_url=image_url,
            categories=categories,
            description=description,
        )

    @staticmethod
    async def auto_steal_meme(sender, event: AstrMessageEvent):
        from .meme_stealer import auto_steal_meme

        await auto_steal_meme(sender, event)

    @staticmethod
    def _convert_to_gif(image_path: str, sender) -> str:
        from ..core.helpers import convert_to_gif

        return convert_to_gif(image_path, sender)
