import json
import os
import random
import re
import traceback

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import LLMResponse
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import MessageChain

from ..config import MEMES_DIR
from .database import get_db_conn
from .helpers import (
    convert_to_gif,
    get_persona_id,
    is_likely_emotion,
    is_likely_emotion_markup,
    is_position_in_thinking_tags,
)


async def _select_memes_by_emotions_priority(
    sender, found_emotions: list[str], persona_id: str
) -> list[str]:
    """根据情绪标签的重合度优先级筛选并随机推荐表情包图片。

    优先返回满足更多情绪标签的表情图片。
    """
    if not found_emotions:
        return []

    conn = get_db_conn()
    cursor = conn.cursor()

    # 构建 SQL 条件：匹配指定人格或全局，并且至少匹配其中一个情绪标签 (OR)
    conditions = []
    params = []

    conditions.append("(personas = '*' OR ',' || personas || ',' LIKE ?)")
    params.append(f"%,{persona_id},%")

    emotion_conditions = []
    for emotion in found_emotions:
        if emotion:
            emotion_conditions.append("',' || emotions || ',' LIKE ?")
            params.append(f"%,{emotion},%")

    if emotion_conditions:
        conditions.append(f"({' OR '.join(emotion_conditions)})")

    sql = f"SELECT filename, emotions FROM memes WHERE {' AND '.join(conditions)}"
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    # 获取人格专属标签，用于评分加分（而不是计入 matched_count）
    from .helpers import load_persona_tags
    p_tags = load_persona_tags()
    dedicated_tag = p_tags.get(persona_id)
    if dedicated_tag:
        dedicated_tag = dedicated_tag.strip()

    emotions_to_match = [e for e in found_emotions if e != dedicated_tag] if dedicated_tag else found_emotions

    # 评分并筛选出本地确实存在的文件
    valid_memes = []
    for row in rows:
        filename = row["filename"]
        full_path = os.path.join(MEMES_DIR, filename)
        if os.path.exists(full_path):
            # 计算与当前匹配情绪列表的重合数作为基础评分，并加上基于顺序的偏置评分
            meme_emotions = (
                [e.strip() for e in row["emotions"].split(",") if e.strip()]
                if row["emotions"]
                else []
            )
            matched_count = sum(1 for e in emotions_to_match if e in meme_emotions)

            # 偏置评分：越靠前的标签越优先
            position_bonus = 0
            for idx, e in enumerate(emotions_to_match):
                if e in meme_emotions:
                    position_bonus += max(0, 100 - idx)

            # 专属标签额外加分（500分）
            dedicated_bonus = 0
            if dedicated_tag and dedicated_tag in meme_emotions:
                dedicated_bonus = 500

            score = matched_count * 1000 + position_bonus + dedicated_bonus
            valid_memes.append((filename, score))

    if not valid_memes:
        return []

    # 按评分分组
    score_groups = {}
    for filename, score in valid_memes:
        score_groups.setdefault(score, []).append(filename)

    # 从高分到低分依次填充选择池，直至达到 max_emotions_per_message
    selected_memes = []
    sorted_scores = sorted(score_groups.keys(), reverse=True)
    max_limit = sender.max_emotions_per_message

    for score in sorted_scores:
        group_memes = score_groups[score]
        random.shuffle(group_memes)
        for m in group_memes:
            selected_memes.append(m)
            if len(selected_memes) >= max_limit:
                break
        if len(selected_memes) >= max_limit:
            break

    return selected_memes


async def handle_resp(sender, event: AstrMessageEvent, response: LLMResponse):
    """处理 LLM 响应，识别表情"""
    if not response or not response.completion_text:
        logger.debug("[meme_manager] LLM 响应为空，跳过表情识别。")
        return

    text = response.completion_text
    sender.found_emotions = []  # 重置表情列表
    valid_emoticons = set(
        sender.category_manager.get_categories()
    )  # 预加载合法表情集合
    logger.debug(
        f"[meme_manager] 收到 LLM 响应，开始表情识别。文本: {text[:100]}...，启用情感模型: {sender.emotion_llm_enabled}"
    )

    clean_text = text

    # 第一阶段：严格匹配符号包裹的表情
    hex_pattern = r"&&([^&&]+)&&"
    matches = re.finditer(hex_pattern, clean_text)

    temp_replacements = []
    strict_emotions = []
    for match in matches:
        original = match.group(0)
        emotion = match.group(1).strip()

        if emotion in valid_emoticons:
            temp_replacements.append((original, emotion))
            strict_emotions.append(emotion)
        else:
            temp_replacements.append((original, ""))  # 非法表情静默移除

    for original, emotion in temp_replacements:
        clean_text = clean_text.replace(original, "", 1)
        if emotion:
            sender.found_emotions.append(emotion)

    logger.debug(
        f"[meme_manager] 第一阶段严格匹配符号 && 包裹的表情: {strict_emotions}"
    )

    # 第二阶段：替代标记处理
    if sender.config.get("enable_alternative_markup", True):
        remove_invalid_markup = sender.remove_invalid_alternative_markup
        bracket_pattern = r"\[([^\[\]]+)\]"
        matches = re.finditer(bracket_pattern, clean_text)
        bracket_replacements = []
        invalid_brackets = [] if remove_invalid_markup else None

        for match in matches:
            original = match.group(0)
            emotion = match.group(1).strip()

            if emotion in valid_emoticons:
                bracket_replacements.append((original, emotion))
            elif remove_invalid_markup:
                invalid_brackets.append(original)

        if remove_invalid_markup:
            for invalid in invalid_brackets:
                clean_text = clean_text.replace(invalid, "", 1)

        for original, emotion in bracket_replacements:
            clean_text = clean_text.replace(original, "", 1)
            sender.found_emotions.append(emotion)

        paren_pattern = r"\(([^()]+)\)"
        matches = re.finditer(paren_pattern, clean_text)
        paren_replacements = []
        invalid_parens = [] if remove_invalid_markup else None

        for match in matches:
            original = match.group(0)
            emotion = match.group(1).strip()

            if emotion in valid_emoticons:
                if is_likely_emotion_markup(original, clean_text, match.start()):
                    paren_replacements.append((original, emotion))
            elif remove_invalid_markup:
                invalid_parens.append(original)

        if remove_invalid_markup:
            for invalid in invalid_parens:
                clean_text = clean_text.replace(invalid, "", 1)

        for original, emotion in paren_replacements:
            clean_text = clean_text.replace(original, "", 1)
            sender.found_emotions.append(emotion)

        logger.debug(
            f"[meme_manager] 第二阶段替代标记 [] / () 包裹的表情: {[b[1] for b in bracket_replacements] + [p[1] for p in paren_replacements]}"
        )

    # 第三阶段：处理重复表情模式
    repeated_emotions = []
    if sender.config.get("enable_repeated_emotion_detection", True):
        high_confidence_emotions = sender.config.get("high_confidence_emotions", [])

        for emotion in valid_emoticons:
            if len(emotion) < 3:
                continue

            if emotion in high_confidence_emotions:
                repeat_pattern = f"({re.escape(emotion)})\\1{{1,}}"
                matches = re.finditer(repeat_pattern, clean_text)
                for match in matches:
                    if is_position_in_thinking_tags(clean_text, match.start()):
                        continue
                    original = match.group(0)
                    clean_text = clean_text.replace(original, "", 1)
                    sender.found_emotions.append(emotion)
                    repeated_emotions.append(emotion)
            else:
                if len(emotion) >= 4:
                    repeat_pattern = f"({re.escape(emotion)})\\1{{2,}}"
                    matches = re.finditer(repeat_pattern, clean_text)
                    for match in matches:
                        if is_position_in_thinking_tags(clean_text, match.start()):
                            continue
                        original = match.group(0)
                        clean_text = clean_text.replace(original, "", 1)
                        sender.found_emotions.append(emotion)
                        repeated_emotions.append(emotion)

    logger.debug(f"[meme_manager] 第三阶段重复检测阶段找到的表情: {repeated_emotions}")

    # 第四阶段：智能识别可能的表情（松散模式）
    loose_emotions = []
    if sender.config.get("enable_loose_emotion_matching", True):
        for emotion in valid_emoticons:
            pattern = r"\b(" + re.escape(emotion) + r")\b"
            for match in re.finditer(pattern, clean_text):
                word = match.group(1)
                position = match.start()

                if is_position_in_thinking_tags(clean_text, position):
                    continue

                if is_likely_emotion(
                    word, clean_text, position, valid_emoticons, sender
                ):
                    sender.found_emotions.append(word)
                    loose_emotions.append(word)
                    clean_text = (
                        clean_text[:position] + clean_text[position + len(word) :]
                    )

    logger.debug(f"[meme_manager] 第四阶段松散匹配阶段找到的表情: {loose_emotions}")

    if sender.emotion_llm_enabled:
        try:
            provider_id = sender.emotion_llm_provider_id
            if not provider_id:
                provider_id = await sender.context.get_current_chat_provider_id(
                    umo=event.unified_msg_origin
                )
            if provider_id:
                valid_list = sorted(valid_emoticons)
                prompt = (
                    "你是表情标签选择器，只能从给定标签中选择。\n"
                    "请基于文本语义判断需要的表情，并将最契合、最相关的标签排在最前面，返回JSON格式：\n"
                    '{"emotions":["tag1","tag2"]}\n'
                    "只输出JSON，不要解释。\n"
                    f"可用标签: {', '.join(valid_list)}\n"
                    f"文本: {clean_text}"
                )
                logger.debug(f"[meme_manager] 情感模型准备调用。模型 ID: {provider_id}")
                llm_resp = await sender.context.llm_generate(
                    chat_provider_id=provider_id, prompt=prompt
                )
                if llm_resp and llm_resp.completion_text:
                    raw_text = llm_resp.completion_text.strip()
                    logger.debug(f"[meme_manager] 情感模型返回原始文本: {raw_text}")
                    data = None
                    try:
                        data = json.loads(raw_text)
                    except Exception:
                        match = re.search(r"\{[\s\S]*\}", raw_text)
                        if match:
                            try:
                                data = json.loads(match.group(0))
                            except Exception:
                                data = None
                    if isinstance(data, dict):
                        emotions = data.get("emotions")
                        logger.debug(
                            f"[meme_manager] 情感模型解析得到的表情: {emotions}"
                        )
                        if isinstance(emotions, list):
                            for emo in emotions:
                                if isinstance(emo, str) and emo in valid_emoticons:
                                    sender.found_emotions.append(emo)
                        elif isinstance(emotions, str) and emotions in valid_emoticons:
                            sender.found_emotions.append(emotions)
                    else:
                        logger.warning(
                            "[meme_manager] 情感模型返回的格式无法解析为 JSON 字典。"
                        )
                else:
                    logger.warning("[meme_manager] 情感模型返回内容为空。")
        except Exception as e:
            logger.error(f"[meme_manager] 情感模型调用失败: {e}")

    # 去重
    seen = set()
    filtered_emotions = []
    for emo in sender.found_emotions:
        if emo not in seen:
            seen.add(emo)
            filtered_emotions.append(emo)

    # 仅在至少检测出一个情绪标签时，以约 70% 的概率追加人格专属标签，保持 30% 概率使用通用表情以保障多样性
    if filtered_emotions:
        import random
        if random.random() < 0.7:
            persona_id = await get_persona_id(sender, event)
            from .helpers import load_persona_tags

            p_tags = load_persona_tags()
            dedicated_tag = p_tags.get(persona_id)
            if dedicated_tag:
                dedicated_tag = dedicated_tag.strip()
                if dedicated_tag and dedicated_tag not in seen:
                    seen.add(dedicated_tag)
                    filtered_emotions.append(dedicated_tag)

    sender.found_emotions = filtered_emotions
    logger.info(f"[meme_manager] 去重后的最终表情标签列表: {sender.found_emotions}")

    clean_text = re.sub(r"&&+", "", clean_text)
    response.completion_text = clean_text.strip()


async def _send_memes_streaming(sender, event: AstrMessageEvent):
    """流式传输兼容模式：在流式消息发送完成后，主动发送表情图片作为独立消息。"""
    if not sender.found_emotions:
        return

    try:
        random_value = random.randint(1, 100)
        if random_value > sender.emotions_probability:
            return

        persona_id = await get_persona_id(sender, event)
        selected_memes = await _select_memes_by_emotions_priority(
            sender, sender.found_emotions, persona_id
        )

        for meme in selected_memes:
            meme_file = os.path.join(MEMES_DIR, meme)
            logger.debug(
                f"[meme_manager] 流式模式选中表情图片 (重合度得分): {meme_file}"
            )
            final_meme_file = convert_to_gif(meme_file, sender)

            try:
                if event.get_platform_name() == "gewechat":
                    await event.send(
                        MessageChain([Image.fromFileSystem(final_meme_file)])
                    )
                else:
                    await sender.context.send_message(
                        event.unified_msg_origin,
                        MessageChain([Image.fromFileSystem(final_meme_file)]),
                    )
            except Exception as e:
                logger.error(f"[meme_manager] 流式模式发送表情失败: {e}")
            finally:
                if final_meme_file != meme_file and os.path.exists(final_meme_file):
                    try:
                        os.remove(final_meme_file)
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"[meme_manager] 流式模式处理表情失败: {e}")
        logger.error(traceback.format_exc())
    finally:
        sender.found_emotions = []
