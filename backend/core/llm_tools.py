import os
import random

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.message.message_event_result import MessageChain

from ...config import MEMES_DIR
from .emotion_handler import search_memes_for_llm
from .helpers import convert_to_gif, get_persona_id


async def send_meme(
    sender, event: AstrMessageEvent, query: str, index: int | None = None
) -> str:
    """Search and send a meme based on query and index selection."""
    persona_id = await get_persona_id(sender, event)
    candidates = await search_memes_for_llm(sender, query, persona_id)

    if not candidates:
        return f"未找到与标签 '{query}' 相关的表情包，请尝试其他的关键词检索。"

    # Group candidates to avoid duplicates and implement selection logic.
    display_groups = []
    desc_lookup = {}
    tags_lookup = {}

    for c in candidates:
        desc = c.get("description")
        if desc and desc.strip():
            desc_text = desc.strip()
            if desc_text in desc_lookup:
                desc_lookup[desc_text]["memes"].append(c)
            else:
                group = {
                    "type": "description",
                    "display_text": f"描述：{desc_text}",
                    "memes": [c],
                }
                display_groups.append(group)
                desc_lookup[desc_text] = group
        else:
            key = tuple(sorted(e.strip().lower() for e in c["emotions"]))
            if key in tags_lookup:
                tags_lookup[key]["memes"].append(c)
            else:
                tags_str = ", ".join(c["emotions"])
                group = {
                    "type": "tags",
                    "display_text": f"标签：[{tags_str}]",
                    "memes": [c],
                }
                display_groups.append(group)
                tags_lookup[key] = group

    if index is None:
        response_text = f"已找到与标签 '{query}' 相关的表情包候选列表：\n"
        for i, group in enumerate(display_groups, start=1):
            response_text += f"{i}. {group['display_text']}\n"
        response_text += "请在上述候选中选择最合适的一个序号，并再次调用本工具传入 `index` 参数（如 index=1）来发送对应的表情包。"
        return response_text

    idx = int(index) - 1
    if idx < 0 or idx >= len(display_groups):
        return f"无效的序号 {index}。当前可选的序号范围是 1 到 {len(display_groups)}。"

    selected_group = display_groups[idx]
    selected_meme = random.choice(selected_group["memes"])
    filename = selected_meme["filename"]
    meme_file = os.path.join(MEMES_DIR, filename)

    if not os.path.exists(meme_file):
        return "所选表情包文件不存在或已被删除。"

    final_meme_file = convert_to_gif(meme_file, sender)

    try:
        img = Image.fromFileSystem(final_meme_file)
        object.__setattr__(img, "sub_type", 1)  # Send as sticker subtype format

        if event.get_platform_name() == "gewechat":
            await event.send(MessageChain([img]))
        else:
            await sender.context.send_message(
                event.unified_msg_origin,
                MessageChain([img]),
            )

        if final_meme_file != meme_file and os.path.exists(final_meme_file):
            try:
                os.remove(final_meme_file)
            except Exception:
                pass

        desc_info = (
            f"描述为 '{selected_meme['description']}'"
            if selected_meme.get("description")
            else f"标签为 [{', '.join(selected_meme['emotions'])}]"
        )
        return f"表情包已成功发送！已选择{desc_info}的表情包。"
    except Exception as e:
        logger.error(f"[meme_manager] LLM发图工具发送失败: {e}")
        return f"表情包发送失败：{e}"
