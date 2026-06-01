import os
import random
import re
import traceback

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain, ResultContentType

from ...config import MEMES_DIR
from ..core.emotion_handler import (
    _select_memes_by_emotions_priority,
    _send_memes_streaming,
)
from ..core.helpers import (
    convert_to_gif,
    get_persona_id,
    merge_components_with_images,
)


async def on_decorating_result(sender, event: AstrMessageEvent):
    """在消息发送前清理文本中的表情标签，并根据人格匹配合适表情"""
    logger.debug(
        f"[meme_manager] 进入消息装饰阶段。当前待发送表情列表: {sender.found_emotions}"
    )

    result = event.get_result()
    if not result:
        logger.debug("[meme_manager] event.get_result() 为空，结束处理。")
        return

    if getattr(sender, "enable_llm_tool", "tag") == "tool":
        logger.debug(
            "[meme_manager] LLM 发图工具仅限工具模式启用，装饰阶段仅进行文本标签清理。"
        )
        original_chain = result.chain
        if original_chain:
            cleaned_components = []
            if isinstance(original_chain, str):
                cleaned = re.sub(
                    r"<emotions>.*?</emotions>",
                    "",
                    original_chain,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                if cleaned.strip():
                    result.chain = [Plain(cleaned.strip())]
            elif isinstance(original_chain, list):
                for comp in original_chain:
                    if isinstance(comp, Plain):
                        cleaned = re.sub(
                            r"<emotions>.*?</emotions>",
                            "",
                            comp.text,
                            flags=re.DOTALL | re.IGNORECASE,
                        )
                        if cleaned.strip():
                            cleaned_components.append(Plain(cleaned.strip()))
                    else:
                        cleaned_components.append(comp)
                result.chain = cleaned_components
        return

    if result.result_content_type == ResultContentType.STREAMING_FINISH:
        if sender.streaming_compatibility:
            logger.debug(
                "[meme_manager] 检测到流式传输完成事件，调用 _send_memes_streaming"
            )
            await _send_memes_streaming(sender, event)
        return

    try:
        original_chain = result.chain
        cleaned_components = []

        if original_chain:
            if isinstance(original_chain, str):
                cleaned = original_chain
                if cleaned.strip():
                    cleaned_components.append(Plain(cleaned.strip()))

            elif isinstance(original_chain, list):
                for component in original_chain:
                    if isinstance(component, Plain):
                        cleaned = component.text
                        if cleaned.strip():
                            cleaned_components.append(Plain(cleaned.strip()))
                    else:
                        cleaned_components.append(component)

        if sender.found_emotions:
            random_value = random.randint(1, 100)
            threshold = sender.emotions_probability
            logger.debug(
                f"[meme_manager] 触发表情概率判断。设定概率: {threshold}%, 本次随机数: {random_value}"
            )

            if random_value <= threshold:
                # 获取当前人格 ID
                persona_id = await get_persona_id(sender, event)
                logger.debug(f"[meme_manager] 当前会话人格 ID: '{persona_id}'")
                emotion_images = []
                temp_files = []

                selected_memes = await _select_memes_by_emotions_priority(
                    sender, sender.found_emotions, persona_id
                )

                for meme in selected_memes:
                    meme_file = os.path.join(MEMES_DIR, meme)
                    logger.debug(
                        f"[meme_manager] 随机选中表情图片 (重合度得分): {meme_file}"
                    )

                    try:
                        final_meme_file = convert_to_gif(meme_file, sender)
                        if final_meme_file != meme_file:
                            temp_files.append(final_meme_file)
                        img = Image.fromFileSystem(final_meme_file)
                        object.__setattr__(img, "sub_type", 1)
                        emotion_images.append(img)
                    except Exception as e:
                        logger.error(f"添加表情图片失败: {e}")

                if emotion_images:
                    if temp_files:
                        existing_temp_files = (
                            event.get_extra("meme_manager_temp_files") or []
                        )
                        event.set_extra(
                            "meme_manager_temp_files",
                            existing_temp_files + temp_files,
                        )

                    # If the message has no text components, we MUST force mixed message
                    # so that the image is sent as the primary message content instead of being skipped.
                    use_mixed_message = False
                    if not cleaned_components:
                        use_mixed_message = True
                    elif sender.enable_mixed_message:
                        use_mixed_message = (
                            random.randint(1, 100) <= sender.mixed_message_probability
                        )

                    logger.debug(
                        f"[meme_manager] 成功加载 {len(emotion_images)} 张表情图片。是否混合发送: {use_mixed_message}"
                    )

                    if use_mixed_message:
                        cleaned_components = merge_components_with_images(
                            sender, cleaned_components, emotion_images
                        )
                    else:
                        event.set_extra("meme_manager_pending_images", emotion_images)
                else:
                    logger.debug("[meme_manager] 未匹配到任何可发送的表情图片")
            else:
                logger.debug("[meme_manager] 随机数大于设定发送概率，跳过发送表情包。")

            sender.found_emotions = []

        if cleaned_components:
            final_cleaned_components = []
            for comp in cleaned_components:
                if isinstance(comp, Plain):
                    text_val = re.sub(
                        r"<emotions>.*?</emotions>",
                        "",
                        comp.text,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    if text_val.strip():
                        final_cleaned_components.append(Plain(text_val.strip()))
                else:
                    final_cleaned_components.append(comp)
            result.chain = final_cleaned_components
        elif original_chain:
            if isinstance(original_chain, str):
                final_cleaned = re.sub(
                    r"<emotions>.*?</emotions>",
                    "",
                    original_chain,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                if final_cleaned.strip():
                    result.chain = [Plain(final_cleaned.strip())]
            elif isinstance(original_chain, list):
                final_components = []
                for component in original_chain:
                    if isinstance(component, Plain):
                        final_cleaned = re.sub(
                            r"<emotions>.*?</emotions>",
                            "",
                            component.text,
                            flags=re.DOTALL | re.IGNORECASE,
                        )
                        if final_cleaned.strip():
                            final_components.append(Plain(final_cleaned.strip()))
                    else:
                        final_components.append(component)
                if final_components:
                    result.chain = final_components

        logger.debug("[meme_manager] on_decorating_result 处理完成。")

    except Exception as e:
        logger.error(f"处理消息装饰失败: {str(e)}")
        logger.error(traceback.format_exc())


async def after_message_sent(sender, event: AstrMessageEvent):
    """消息发送后处理。用于发送未混合的表情图片。"""
    pending_images = event.get_extra("meme_manager_pending_images")
    logger.debug(
        f"[meme_manager] 进入 after_message_sent 发送后处理。待补发表情图片数: {len(pending_images) if pending_images else 0}"
    )

    try:
        if pending_images:
            for image in pending_images:
                if event.get_platform_name() == "gewechat":
                    logger.debug(
                        "[meme_manager] (gewechat) 正在直接通过 event.send 补发表情图片..."
                    )
                    await event.send(MessageChain([image]))
                else:
                    logger.debug(
                        f"[meme_manager] 正在通过 context.send_message 补发表情图片到 {event.unified_msg_origin}..."
                    )
                    await sender.context.send_message(
                        event.unified_msg_origin, MessageChain([image])
                    )
    except Exception as e:
        logger.error(f"发送表情图片失败: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        event.set_extra("meme_manager_pending_images", None)

        # 清理临时文件
        temp_files = event.get_extra("meme_manager_temp_files")
        if temp_files:
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.debug(f"[meme_manager] 已成功清理临时文件: {temp_file}")
                except Exception as e:
                    logger.error(f"[meme_manager] 清理临时文件失败: {e}")
            event.set_extra("meme_manager_temp_files", None)
