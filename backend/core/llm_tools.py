import os
import random

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.message.message_event_result import MessageChain

from ...config import MEMES_DIR
from .emotion_handler import search_memes_for_llm
from .helpers import convert_to_gif, get_persona_id


def _build_display_groups(candidates: list[dict]) -> list[dict]:
    """Group candidates by description / tags to dedupe identical entries for selection."""
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

    return display_groups


async def send_meme(
    sender,
    event: AstrMessageEvent,
    query: str | None = None,
    index: int | None = None,
) -> str:
    """Search and send a meme based on query and index selection."""
    persona_id = await get_persona_id(sender, event)
    session_key = event.unified_msg_origin

    if not hasattr(sender, "_meme_tool_candidates"):
        sender._meme_tool_candidates = {}

    # A fresh query re-searches and refreshes this session's candidate cache;
    # otherwise fall back to the candidates cached from a previous call so the
    # follow-up selection call only needs `index`.
    if query and query.strip():
        candidates = await search_memes_for_llm(sender, query, persona_id, event)
        if not candidates:
            sender._meme_tool_candidates.pop(session_key, None)
            return f"未找到与标签 '{query}' 相关的表情包，请尝试其他的关键词检索。"
        display_groups = _build_display_groups(candidates)
        sender._meme_tool_candidates[session_key] = display_groups
    else:
        display_groups = sender._meme_tool_candidates.get(session_key)
        if not display_groups:
            return "请先传入 `query` 检索表情包候选列表，再传入 `index` 选择并发送。"

    if index is None:
        response_text = "已找到相关的表情包候选列表：\n"
        for i, group in enumerate(display_groups, start=1):
            response_text += f"{i}. {group['display_text']}\n"
        response_text += (
            "请从以上候选中选择最合适的一项，再次调用本工具并传入 `index` 参数"
            "（如 index=1）即可发送，此时无需重复传入 query。"
        )
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

        event.set_extra("meme_tool_executed", True)

        if final_meme_file != meme_file and os.path.exists(final_meme_file):
            try:
                os.remove(final_meme_file)
            except Exception:
                pass

        sender._meme_tool_candidates.pop(session_key, None)

        desc_info = (
            f"描述为 '{selected_meme['description']}'"
            if selected_meme.get("description")
            else f"标签为 [{', '.join(selected_meme['emotions'])}]"
        )
        return f"表情包已成功发送！已选择{desc_info}的表情包。"
    except Exception as e:
        logger.error(f"[meme_manager] LLM发图工具发送失败: {e}")
        return f"表情包发送失败：{e}"


async def steal_meme(
    sender,
    event: AstrMessageEvent,
    categories: list[str] | None = None,
    image_content: bytes | None = None,
    image_hash: str | None = None,
    image_type: str | None = None,
    description: str | None = None,
) -> str:
    """保存并收录最近聊天中发送的表情包到当前人格的表情包库中。

    取图优先级：当前消息直发 > 引用/回复 > 本会话最近收到的图片。下载完成后
    交由 meme_stealer.process_stolen_image 走统一的去重/偏好/分类/入库流程。
    """
    from ..handlers.meme_stealer import (
        download_image,
        extract_event_image_url,
        get_cached_image_url,
        process_stolen_image,
        resolve_persona_preference,
    )

    # 1. 解析人格与表情包收集偏好
    persona_id, preference_text, pref_err = await resolve_persona_preference(
        sender, event
    )
    if pref_err:
        return pref_err

    # 2. 取图（被动偷图路径会直接传入 image_content，此处仅在缺图时解析 URL）
    url = None
    if image_content is None:
        url = extract_event_image_url(event) or get_cached_image_url(sender, event)
        if not url:
            return "没有在最近的聊天中找到可以收录的表情包/图片哦。请发送图片并在消息中说明，或者直接引用（回复）要收录的图片并发出指令。"

    # 3. 检查分类是否合法（未启用多模态判定且未显式提供分类时报错）
    if not getattr(sender, "multimodal_llm_enabled", False) and not categories:
        return "请输入至少一个有效的标签/分类名称。"

    # 4. 下载图片（已提供完整图片信息时直接复用）
    content = image_content
    file_type = image_type
    raw_hash = image_hash
    if content is None or file_type is None or raw_hash is None:
        content, file_type, raw_hash, dl_err = await download_image(url)
        if dl_err:
            return dl_err

    # 5. 进入统一的收录处理流水线
    return await process_stolen_image(
        sender,
        event,
        persona_id,
        preference_text,
        content,
        file_type,
        raw_hash,
        categories,
        description or "",
    )
