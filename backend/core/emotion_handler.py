import math
import os
import random
import re
import traceback

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import LLMResponse
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import MessageChain

from ...config import MEMES_DIR
from ...utils import get_config_value
from ..db.database import get_db_conn
from .helpers import (
    convert_to_gif,
    get_persona_id,
)


async def get_scored_memes_by_emotions(
    sender, found_emotions: list, persona_id: str
) -> list[dict]:
    """根据情绪标签的重合度评分规则，计算并返回所有匹配表情包的评分列表。"""
    if not found_emotions:
        return []

    # 兼容处理：提取所有可能的目标表情标签，用于构建 SQL 查询条件
    flat_emotions = set()
    for item in found_emotions:
        if isinstance(item, tuple):
            flat_emotions.update(item[1])
        else:
            flat_emotions.add(item)

    if not flat_emotions:
        return []

    conn = get_db_conn()
    cursor = conn.cursor()

    # 构建 SQL 条件：匹配指定人格或全局，并且至少匹配其中一个候选情绪标签 (OR)
    conditions = []
    params = []

    conditions.append("(personas = '*' OR ',' || personas || ',' LIKE ?)")
    params.append(f"%,{persona_id},%")

    emotion_conditions = []
    for emotion in flat_emotions:
        if emotion:
            emotion_conditions.append("',' || emotions || ',' LIKE ?")
            params.append(f"%,{emotion},%")

    if emotion_conditions:
        conditions.append(f"({' OR '.join(emotion_conditions)})")

    sql = f"SELECT filename, emotions, description FROM memes WHERE {' AND '.join(conditions)}"
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    # 获取人格专属标签，用于评分加分（而不是计入 matched_count）
    from .helpers import load_persona_tags

    p_tags = load_persona_tags(sender.config)
    dedicated_tag_str = p_tags.get(persona_id) or ""
    dedicated_tags = [t.strip() for t in dedicated_tag_str.split(",") if t.strip()]

    # Filter out auto-appended dedicated tags, keeping only the tags meant for active matching/scoring
    emotions_to_match = []
    for item in found_emotions:
        if isinstance(item, tuple):
            if len(item) == 3 and item[2] is True:
                continue
            raw_tag, candidates = item[0], item[1]
            emotions_to_match.append((raw_tag, candidates))
        else:
            emotions_to_match.append(item)

    # 评分并筛选出本地确实存在的文件
    last_tag_score = 1000
    if len(emotions_to_match) > 1:
        last_tag_score = max(1, 400 // (2 ** (len(emotions_to_match) - 2)))

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

            # 计算匹配到的意图/输入标签重合数（matched_count）与位置权重分
            matched_count = 0
            matched_score = 0
            matched_details = []
            for idx, item in enumerate(emotions_to_match):
                if idx == 0:
                    tag_weight = 1000
                else:
                    tag_weight = max(1, 400 // (2 ** (idx - 1)))

                if isinstance(item, tuple):
                    raw_tag, candidates = item
                    # 找到所有匹配的候选词及其在候选列表中的索引
                    matching_indices = [
                        idx_c
                        for idx_c, c in enumerate(candidates)
                        if c in meme_emotions
                    ]
                    if matching_indices:
                        matched_count += 1
                        # 取匹配度最高的那个候选词（即 index 最小的那个）
                        best_candidate_idx = min(matching_indices)
                        # 基于候选词排名的衰减系数：排在第 1 的（index 0）保留 100% 分值，后面每顺延一位衰减 5%，保底保留 80%
                        decay_factor = max(0.8, 1.0 - best_candidate_idx * 0.05)
                        weighted_tag_score = int(tag_weight * decay_factor)
                        matched_score += weighted_tag_score
                        matched_details.append(
                            f"{raw_tag}->{candidates[best_candidate_idx]}(+{weighted_tag_score})"
                        )
                else:
                    if item in meme_emotions:
                        matched_count += 1
                        matched_score += tag_weight
                        matched_details.append(f"{item}(+{tag_weight})")

            # 专属标签额外加分（只有第一个是专属标签，其余偏好标签不参与计算。加分设定最高 10 分且必须低于最后一个标签的分数）
            dedicated_bonus = 0
            matched_dedicated = []
            if dedicated_tags:
                primary_dedicated = dedicated_tags[0]
                if primary_dedicated in meme_emotions:
                    dedicated_bonus = min(10, max(0, (last_tag_score + 1) // 2 - 1))
                    if dedicated_bonus > 0:
                        matched_dedicated.append(primary_dedicated)

            description = row["description"] if "description" in row.keys() else ""
            score = matched_score + dedicated_bonus

            if score > 0:
                valid_memes.append(
                    {
                        "filename": filename,
                        "emotions": meme_emotions,
                        "description": description or "",
                        "score": score,
                        "matched_count": matched_count,
                        "matched_details": matched_details,
                        "dedicated_bonus": dedicated_bonus,
                        "matched_dedicated": matched_dedicated,
                    }
                )

    # 按分数降序排列
    valid_memes.sort(key=lambda x: x["score"], reverse=True)
    return valid_memes


async def _select_memes_by_emotions_priority(
    sender, found_emotions: list, persona_id: str
) -> list[str]:
    """根据情绪标签的重合度优先级筛选并随机推荐表情包图片。

    优先返回满足更多情绪标签的表情图片。
    """
    scored_memes = await get_scored_memes_by_emotions(
        sender, found_emotions, persona_id
    )
    if not scored_memes:
        return []

    # 按评分分组
    score_groups = {}
    memes_scoring_details = {}
    for item in scored_memes:
        filename = item["filename"]
        score = item["score"]
        score_groups.setdefault(score, []).append(filename)
        memes_scoring_details[filename] = item

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

    # 打印最终选中的表情的标签命中及打分详情
    if selected_memes:
        log_lines = []
        for filename in selected_memes:
            detail = memes_scoring_details.get(filename, {})
            desc = detail.get("description", "")
            desc_line = f"    描述: {desc}\n" if desc else ""
            log_lines.append(
                f"  - 表情包所有标签: {detail.get('emotions')}\n"
                f"{desc_line}"
                f"    总分: {detail.get('score')} | 意图匹配数: {detail.get('matched_count')}\n"
                f"    匹配详情: {detail.get('matched_details')} |\n"
                f"    专属标签加分: {detail.get('dedicated_bonus')} (命中专属标签: {detail.get('matched_dedicated')})"
            )
        logger.info(
            "[meme_manager] 最终发送的表情匹配打分情况:\n" + "\n".join(log_lines)
        )

    return selected_memes


def cosine_similarity(v1, v2):
    dot_product = sum(x * y for x, y in zip(v1, v2))
    norm_v1 = math.sqrt(sum(x * x for x in v1))
    norm_v2 = math.sqrt(sum(x * x for x in v2))
    if not norm_v1 or not norm_v2:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)


async def sync_tag_embeddings(sender):
    """后台增量计算缺失标签的向量并同步至 SQLite"""
    try:
        from ..db.database import (
            get_all_tag_embeddings,
            get_db_conn,
            save_tag_embedding,
        )

        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT emotions FROM memes")
        rows = cursor.fetchall()
        conn.close()

        all_tags = set()
        for row in rows:
            if row["emotions"]:
                for emo in row["emotions"].split(","):
                    emo = emo.strip()
                    if emo:
                        all_tags.add(emo)

        if not all_tags:
            return

        cached_embeddings = get_all_tag_embeddings()
        missing_tags = [tag for tag in all_tags if tag not in cached_embeddings]

        if not missing_tags:
            return

        logger.info(
            f"[meme_manager] 检测到 {len(missing_tags)} 个表情标签缺失向量，正在后台计算..."
        )

        provider_id = get_config_value(sender.config, "embedding_provider_id", "")
        embedding_provider = None
        if provider_id:
            embedding_provider = sender.context.get_provider_by_id(provider_id)
        if not embedding_provider:
            provs = sender.context.get_all_embedding_providers()
            if provs:
                embedding_provider = provs[0]

        if not embedding_provider:
            logger.warning(
                "[meme_manager] 未配置或未找到可用的 Embedding 提供商，跳过向量同步。"
            )
            return

        logger.info(
            f"[meme_manager] 向量计算开始：使用 Provider ID: {getattr(embedding_provider, 'id', 'unknown')}, "
            f"类型: {type(embedding_provider).__name__}, Model: {getattr(embedding_provider, 'model', 'unknown')}"
        )

        for tag in missing_tags:
            try:
                embedding = await embedding_provider.get_embedding(tag)
                if embedding:
                    save_tag_embedding(tag, embedding)
                    logger.info(
                        f"[meme_manager] 标签 '{tag}' 向量计算成功：维度={len(embedding)}, "
                        f"前5位数据={embedding[:5]}"
                    )
            except Exception as e:
                logger.error(f"[meme_manager] 标签 '{tag}' 向量计算失败: {e}")

        logger.info("[meme_manager] 标签向量增量同步完成")
    except Exception as e:
        logger.error(f"[meme_manager] 标签向量同步过程发生错误: {e}")


async def _handle_resp_vector(
    sender,
    event: AstrMessageEvent,
    response: LLMResponse,
    valid_emoticons: set[str],
    dedicated_tag: str | None,
):
    text = response.completion_text
    clean_text = text
    raw_tags = []

    # 1. 提取 <emotions>...</emotions> 包裹的标签块
    emotions_pattern = r"<emotions>(.*?)</emotions>"
    emotions_matches = list(
        re.finditer(emotions_pattern, clean_text, re.DOTALL | re.IGNORECASE)
    )
    for match in emotions_matches:
        original = match.group(0)
        inner_content = match.group(1)
        for tag in re.split(r"[,，\s]+", inner_content):
            tag = tag.strip()
            if tag:
                raw_tags.append(tag)
        clean_text = clean_text.replace(original, "")

    logger.debug(
        f"[meme_manager] _handle_resp_vector: raw_text={text!r}, extracted raw_tags={raw_tags}, clean_text={clean_text!r}"
    )
    logger.debug(
        f"[meme_manager] _handle_resp_vector: valid_emoticons={list(valid_emoticons)}"
    )

    # 2. 调用 match_emotions_by_tags 匹配标签
    sender.found_emotions = await match_emotions_by_tags(
        sender, event, raw_tags, valid_emoticons
    )

    # 3. 追加专属表情判定（跟原逻辑保持一致，支持新的 tuple 结构）
    if sender.found_emotions:
        import random

        if random.random() < 0.7 and dedicated_tag:
            # 只取第一个标签作为专属标签进行追加，后面的标签只是偏好
            d_tags = [t.strip() for t in dedicated_tag.split(",") if t.strip()]
            if d_tags:
                chosen_tag = d_tags[0]
                already_matched = False
                for item in sender.found_emotions:
                    if isinstance(item, tuple):
                        raw_tag, candidates = item
                        if chosen_tag == raw_tag or chosen_tag in candidates:
                            already_matched = True
                            break
                    else:
                        if chosen_tag == item:
                            already_matched = True
                            break
                if not already_matched:
                    sender.found_emotions.append((chosen_tag, [chosen_tag], True))

    logger.debug(
        f"[meme_manager] 向量召回最终匹配到的标签列表: {sender.found_emotions}"
    )

    clean_text = re.sub(
        r"<emotions>.*?</emotions>",
        "",
        clean_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    response.completion_text = clean_text.strip()


async def handle_resp(sender, event: AstrMessageEvent, response: LLMResponse):
    """处理 LLM 响应，识别表情"""
    if getattr(sender, "enable_llm_tool", "tag") == "tool":
        logger.debug("[meme_manager] LLM 发图工具仅限工具模式启用，跳过自动表情识别。")
        return
    if not response or not response.completion_text:
        logger.debug("[meme_manager] LLM 响应为空，跳过表情识别。")
        return

    sender.found_emotions = []  # 重置表情列表
    persona_id = await get_persona_id(sender, event)

    # Print config and persona prompt details
    logger.debug(
        f"[meme_manager] Debug handle_resp: enable_emotion_llm={getattr(sender, 'enable_emotion_llm', False)}, "
        f"enable_llm_tool={getattr(sender, 'enable_llm_tool', 'tag')}, persona_id={persona_id}"
    )
    for p in sender.context.provider_manager.personas:
        if p.get("name") == persona_id or p.get("id") == persona_id:
            logger.debug(
                f"[meme_manager] Debug Persona prompt in use: {p.get('prompt')!r}"
            )
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT emotions FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
        (f"%,{persona_id},%",),
    )
    rows = cursor.fetchall()
    conn.close()

    valid_emoticons = set()
    for row in rows:
        if row["emotions"]:
            for emo in row["emotions"].split(","):
                emo = emo.strip()
                if emo:
                    valid_emoticons.add(emo)

    from .helpers import load_persona_tags

    p_tags = load_persona_tags(sender.config)
    dedicated_tag = p_tags.get(persona_id)
    if dedicated_tag:
        # 偏好标签可能由逗号分隔，将其中的每个单独标签都加入有效候选集
        for tag in [t.strip() for t in dedicated_tag.split(",") if t.strip()]:
            valid_emoticons.add(tag)

    if getattr(sender, "enable_emotion_llm", False):
        if event.get_extra("meme_tool_executed"):
            logger.debug(
                "[meme_manager] 检测到本次对话已成功调用 send_meme 工具发送表情包，跳过情感分析模型。"
            )
            return

        try:
            import random

            random_value = random.randint(1, 100)
            threshold = sender.emotions_probability
            logger.debug(
                f"[meme_manager] 启用情感模型判定。触发表情概率判断。设定概率: {threshold}%, 本次随机数: {random_value}"
            )
            if random_value > threshold:
                logger.debug(
                    "[meme_manager] 情感模型判定：未命中触发概率，跳过表情包匹配。"
                )
                event.set_extra("meme_probability_checked", True)
                return

            event.set_extra("meme_probability_checked", True)

            provider_id = getattr(sender, "emotion_llm_provider_id", "")
            if not provider_id:
                try:
                    provider_id = await sender.context.get_current_chat_provider_id(
                        umo=event.unified_msg_origin
                    )
                except Exception as e:
                    logger.warning(f"[meme_manager] 获取当前聊天提供商失败: {e}")

            if not provider_id:
                logger.warning(
                    "[meme_manager] 情感模型判定：未找到可用的模型提供商，跳过。"
                )
                return

            user_input = event.message_str or ""
            bot_response = response.completion_text

            from .helpers import get_persona_setting

            pref = get_persona_setting(sender.config, persona_id, "meme_use_preference")
            pref_str = ""
            if pref:
                d_tags = [t.strip() for t in pref.split(",") if t.strip()]
                # 第一个标签是专属标签，自动追加，因此不需要且不应该写入提示词中；仅将后面的偏好标签写入提示词
                if len(d_tags) > 1:
                    pref_filtered = ", ".join(d_tags[1:])
                    pref_str = f"【当前人格的常用偏好表情标签】:\n{pref_filtered}\n\n"

            base_prompt = getattr(sender, "emotion_llm_prompt", "")
            prompt = (
                f"{base_prompt}\n\n"
                f"{pref_str}"
                f"【对话背景】:\n"
                f"用户发送: {user_input}\n"
                f"助手回复: {bot_response}\n\n"
                f"【输出格式要求】:\n"
                f"1. 请根据对话背景和助手回复，自由输出最符合当前回复语气、画面主体或情感的多个表情包标签，用英文逗号分隔（例如：得意, 摸头, 猫猫, 委屈）。**注意：输出的标签顺序会影响权重，请将重点、核心的标签排在更靠前的位置。**\n"
                f"2. 请直接输出标签文本，不要包含任何解释或额外文字。如果不需要任何表情包，请直接返回空。"
            )

            logger.debug(
                f"[meme_manager] 正在调用情感模型 {provider_id} 判定表情标签。Prompt内容:\n{prompt}"
            )
            llm_resp = await sender.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )
            if llm_resp and llm_resp.completion_text:
                raw_text = llm_resp.completion_text.strip()
                logger.debug(f"[meme_manager] 情感模型返回内容: {raw_text}")
                if raw_text:
                    # Clean up any accidental markdown or html wrappers the LLM might have outputted
                    clean_tags = re.sub(r"<[^>]*>", "", raw_text)
                    clean_tags = clean_tags.replace("`", "").strip()
                    if clean_tags:
                        wrapped_tags = f"<emotions>{clean_tags}</emotions>"
                        response.completion_text = (
                            f"{response.completion_text}\n{wrapped_tags}"
                        )
        except Exception as e:
            logger.error(f"[meme_manager] 调用情感模型失败: {e}", exc_info=True)

    try:
        await _handle_resp_vector(
            sender, event, response, valid_emoticons, dedicated_tag
        )
    except Exception as e:
        logger.error(
            f"[meme_manager] 向量匹配失败: {e}",
            exc_info=True,
        )


async def _send_memes_streaming(sender, event: AstrMessageEvent):
    """流式传输兼容模式：在流式消息发送完成后，主动发送表情图片作为独立消息。"""
    if not sender.found_emotions:
        return

    try:
        if event.get_extra("meme_tool_executed"):
            logger.debug(
                "[meme_manager] 检测到已使用 send_meme 工具发送表情包，流式发送阶段跳过情绪表情。"
            )
            return

        if not getattr(sender, "enable_emotion_llm", False):
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
                img = Image.fromFileSystem(final_meme_file)
                object.__setattr__(img, "sub_type", 1)
                if event.get_platform_name() == "gewechat":
                    await event.send(MessageChain([img]))
                else:
                    await sender.context.send_message(
                        event.unified_msg_origin,
                        MessageChain([img]),
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


async def search_memes_for_llm(
    sender, query: str, persona_id: str, event: AstrMessageEvent = None
) -> list[dict]:
    """为 LLM 搜索表情包。使用精确匹配与向量相似度检索，并采用与情绪表情匹配一致的评分规则。"""
    query = query.strip()
    if not query:
        return []

    # 1. Get all available emotions for the current persona and global
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT emotions FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
        (f"%,{persona_id},%",),
    )
    rows = cursor.fetchall()
    conn.close()

    valid_emoticons = set()
    for row in rows:
        if row["emotions"]:
            for emo in row["emotions"].split(","):
                emo = emo.strip()
                if emo:
                    valid_emoticons.add(emo)

    # 2. Append the dedicated tag for the current persona
    from .helpers import load_persona_tags

    p_tags = load_persona_tags(sender.config)
    dedicated_tag = p_tags.get(persona_id)
    if dedicated_tag:
        for tag in [t.strip() for t in dedicated_tag.split(",") if t.strip()]:
            valid_emoticons.add(tag)

    # 3. Split query by comma and call match_emotions_by_tags
    query_parts = [q.strip() for q in query.split(",") if q.strip()]
    matched_emotions = await match_emotions_by_tags(
        sender, event, query_parts, valid_emoticons
    )

    if not matched_emotions:
        return []

    # 4. Get scoring details
    scored_memes = await get_scored_memes_by_emotions(
        sender, matched_emotions, persona_id
    )

    # Return the top 8 matched memes (required format: filename, emotions, description, score)
    results = []
    for item in scored_memes[:8]:
        results.append(
            {
                "filename": item["filename"],
                "emotions": item["emotions"],
                "description": item["description"],
                "score": item["score"],
            }
        )
    return results


async def match_emotions_by_tags(
    sender, event: AstrMessageEvent, raw_tags: list[str], valid_emoticons: set[str]
) -> list[tuple[str, list[str]]]:
    """根据原始标签列表，通过精确匹配 + 向量相似度匹配，返回命中的有效表情标签列表 (每个标签对应其候选列表)。

    与 `_handle_resp_vector` 的核心匹配逻辑一致（均为仅基于标签的单通道检索），
    供 `<emotions>...</emotions>` 直接触发场景复用。
    """
    if not raw_tags or not valid_emoticons:
        return []

    # 1. Check for exact matches and initialize lists
    exact_matches = {}
    tags_to_embed = []
    for raw_tag in raw_tags:
        matched = None
        for valid in valid_emoticons:
            if raw_tag.lower() == valid.lower():
                matched = valid
                break
        if matched:
            exact_matches[raw_tag] = matched

        # Always run vector similarity matching to recall related tags even on exact matches
        tags_to_embed.append(raw_tag)

    if exact_matches:
        logger.debug(
            f"[meme_manager] (直接触发) 精确匹配到的表情标签: {list(exact_matches.values())}"
        )

    # 2. Vector similarity matching (run for all tags to recall related ones)
    vector_matches = {}
    if tags_to_embed:
        provider_id = get_config_value(sender.config, "embedding_provider_id", "")
        embedding_provider = None
        if provider_id:
            embedding_provider = sender.context.get_provider_by_id(provider_id)
        if not embedding_provider:
            provs = sender.context.get_all_embedding_providers()
            if provs:
                embedding_provider = provs[0]

        if embedding_provider:
            from ..db.database import get_all_tag_embeddings

            tag_embeddings = get_all_tag_embeddings()

            # Trigger background synchronization if any valid emotions lack embeddings
            import asyncio

            missing_tags = [tag for tag in valid_emoticons if tag not in tag_embeddings]
            if missing_tags:
                logger.info(
                    f"[meme_manager] (直接触发) 检测到有 {len(missing_tags)} 个标签未计算向量，已触发后台增量计算。"
                )
                asyncio.create_task(sync_tag_embeddings(sender))

            raw_tags_vectors = {}
            for raw_tag in tags_to_embed:
                # Prefer cached tag vectors to avoid redundant remote API calls
                if raw_tag in tag_embeddings:
                    raw_tags_vectors[raw_tag] = tag_embeddings[raw_tag]
                    continue
                try:
                    vec = await embedding_provider.get_embedding(raw_tag)
                    if vec:
                        raw_tags_vectors[raw_tag] = vec
                except Exception as e:
                    logger.warning(
                        f"[meme_manager] (直接触发) 获取标签 '{raw_tag}' 向量失败: {e}"
                    )

            if raw_tags_vectors and tag_embeddings:
                similarity_threshold = get_config_value(
                    sender.config, "embedding_similarity_threshold", 0.6
                )

                # Search similar database tags for each query tag
                for raw_tag, raw_vec in raw_tags_vectors.items():
                    candidates_with_scores = []
                    for valid_tag in valid_emoticons:
                        # Skip comparing with the exact matched tag itself
                        if (
                            raw_tag in exact_matches
                            and valid_tag == exact_matches[raw_tag]
                        ):
                            continue
                        tag_vec = tag_embeddings.get(valid_tag)
                        if not tag_vec:
                            continue
                        sim = cosine_similarity(raw_vec, tag_vec)
                        if sim >= similarity_threshold:
                            candidates_with_scores.append((valid_tag, sim))

                    # Sort by similarity score descending
                    candidates_with_scores.sort(key=lambda x: x[1], reverse=True)

                    # Gather top 5 non-duplicate similar candidate tags
                    filtered_candidates = []
                    used_candidates_for_tag = set()
                    if raw_tag in exact_matches:
                        used_candidates_for_tag.add(exact_matches[raw_tag])

                    for valid_tag, sim in candidates_with_scores:
                        if valid_tag not in used_candidates_for_tag:
                            filtered_candidates.append(valid_tag)
                            used_candidates_for_tag.add(valid_tag)
                            if len(filtered_candidates) == 5:
                                break

                    logger.debug(
                        f"[meme_manager] (直接触发) 查询标签 '{raw_tag}' 召回候选匹配 (已去重/顺延/最多5个): {filtered_candidates} (阈值={similarity_threshold})"
                    )

                    if filtered_candidates:
                        vector_matches[raw_tag] = filtered_candidates
        else:
            logger.debug(
                "[meme_manager] (直接触发) 没有可用的 Embedding Provider，跳过向量匹配。"
            )

    # 3. Merge exact matches and recalled tags, preserving query tag order
    final_emotions = []
    for raw_tag in raw_tags:
        candidates = []
        if raw_tag in exact_matches:
            candidates.append(exact_matches[raw_tag])
        if raw_tag in vector_matches:
            for c in vector_matches[raw_tag]:
                if c not in candidates:
                    candidates.append(c)
        if candidates:
            final_emotions.append((raw_tag, candidates))

    return final_emotions


async def get_direct_trigger_memes(
    sender, event: AstrMessageEvent, raw_tags: list[str]
) -> list[str]:
    """根据原始标签，匹配当前会话人格的有效表情，并按重合度优先级选出要发送的表情包文件列表。"""
    persona_id = await get_persona_id(sender, event)

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT emotions FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
        (f"%,{persona_id},%",),
    )
    rows = cursor.fetchall()
    conn.close()

    valid_emoticons = set()
    for row in rows:
        if row["emotions"]:
            for emo in row["emotions"].split(","):
                emo = emo.strip()
                if emo:
                    valid_emoticons.add(emo)

    # 追加当前人格的专属标签
    from .helpers import load_persona_tags

    p_tags = load_persona_tags(sender.config)
    dedicated_tag = p_tags.get(persona_id)
    if dedicated_tag:
        # 偏好标签可能由逗号分隔，将其中的每个单独标签都加入有效候选集
        for tag in [t.strip() for t in dedicated_tag.split(",") if t.strip()]:
            valid_emoticons.add(tag)

    matched_emotions = await match_emotions_by_tags(
        sender, event, raw_tags, valid_emoticons
    )
    logger.debug(f"[meme_manager] (直接触发) 最终匹配到的标签列表: {matched_emotions}")
    if not matched_emotions:
        return []

    return await _select_memes_by_emotions_priority(
        sender, matched_emotions, persona_id
    )
