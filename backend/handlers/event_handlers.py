from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import LLMResponse


class EventHandlers:
    @staticmethod
    async def _get_persona_id(sender, event: AstrMessageEvent) -> str:
        from ..core.helpers import get_persona_id

        return await get_persona_id(sender, event)

    @staticmethod
    async def _select_memes_by_emotions_priority(
        sender, found_emotions: list[str], persona_id: str
    ) -> list[str]:
        from ..core.emotion_handler import _select_memes_by_emotions_priority

        return await _select_memes_by_emotions_priority(
            sender, found_emotions, persona_id
        )

    @staticmethod
    async def resp(sender, event: AstrMessageEvent, response: LLMResponse):
        from ..core.emotion_handler import handle_resp

        await handle_resp(sender, event, response)

    @staticmethod
    async def on_decorating_result(sender, event: AstrMessageEvent):
        from .message_handler import on_decorating_result

        await on_decorating_result(sender, event)

    @staticmethod
    async def after_message_sent(sender, event: AstrMessageEvent):
        from .message_handler import after_message_sent

        await after_message_sent(sender, event)

    @staticmethod
    async def handle_upload_image(sender, event: AstrMessageEvent):
        from .upload_handler import handle_upload_image

        async for res in handle_upload_image(sender, event):
            yield res

    @staticmethod
    async def handle_direct_meme_trigger(sender, event: AstrMessageEvent):
        from .message_handler import handle_direct_meme_trigger

        async for res in handle_direct_meme_trigger(sender, event):
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
        categories: list[str],
        description: str | None = None,
    ):
        from ..core.llm_tools import steal_meme

        return await steal_meme(sender, event, categories, description=description)

    @staticmethod
    async def auto_steal_meme(sender, event: AstrMessageEvent):
        from .meme_stealer import auto_steal_meme

        await auto_steal_meme(sender, event)

    @staticmethod
    def _is_likely_emotion_markup(markup, text, position):
        from ..core.helpers import is_likely_emotion_markup

        return is_likely_emotion_markup(markup, text, position)

    @staticmethod
    def _is_likely_emotion(word, text, position, valid_emotions, sender):
        from ..core.helpers import is_likely_emotion

        return is_likely_emotion(word, text, position, valid_emotions, sender)

    @staticmethod
    def _convert_to_gif(image_path: str, sender) -> str:
        from ..core.helpers import convert_to_gif

        return convert_to_gif(image_path, sender)

    @staticmethod
    def _is_position_in_thinking_tags(text: str, position: int) -> bool:
        from ..core.helpers import is_position_in_thinking_tags

        return is_position_in_thinking_tags(text, position)

    @staticmethod
    async def _send_memes_streaming(sender, event: AstrMessageEvent):
        from ..core.emotion_handler import _send_memes_streaming

        await _send_memes_streaming(sender, event)

    @staticmethod
    def _merge_components_with_images(sender, components, images):
        from ..core.helpers import merge_components_with_images

        return merge_components_with_images(sender, components, images)
