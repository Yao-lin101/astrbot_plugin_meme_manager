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

from ..config import MEMES_DIR
from ..utils import get_config_value
from .database import get_db_conn
from .helpers import (
    convert_to_gif,
    get_persona_id,
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
    dedicated_tag_str = p_tags.get(persona_id) or ""
    dedicated_tags = [t.strip() for t in dedicated_tag_str.split(",") if t.strip()]

    emotions_to_match = (
        [e for e in found_emotions if e not in dedicated_tags]
        if dedicated_tags
        else found_emotions
    )

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

            # 专属标签额外加分（每个匹配到的专属标签加 500 分）
            dedicated_bonus = 0
            if dedicated_tags:
                for d_tag in dedicated_tags:
                    if d_tag in meme_emotions:
                        dedicated_bonus += 500

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
        from .database import get_all_tag_embeddings, get_db_conn, save_tag_embedding

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

    logger.info(
        f"[meme_manager] _handle_resp_vector: raw_text={text!r}, extracted raw_tags={raw_tags}, clean_text={clean_text!r}"
    )
    logger.debug(
        f"[meme_manager] _handle_resp_vector: valid_emoticons={list(valid_emoticons)}"
    )

    # 3. 精确匹配校验与筛选
    found_exact = set()
    tags_to_embed = []

    for raw_tag in raw_tags:
        matched = None
        for valid in valid_emoticons:
            if raw_tag.lower() == valid.lower():
                matched = valid
                break
        if matched:
            found_exact.add(matched)
        else:
            tags_to_embed.append(raw_tag)

    if found_exact:
        logger.info(f"[meme_manager] 精确匹配到的表情标签: {list(found_exact)}")

    # 4. 获取 Embedding Provider
    provider_id = get_config_value(sender.config, "embedding_provider_id", "")
    embedding_provider = None
    if provider_id:
        embedding_provider = sender.context.get_provider_by_id(provider_id)
    if not embedding_provider:
        provs = sender.context.get_all_embedding_providers()
        if provs:
            embedding_provider = provs[0]

    if embedding_provider:
        logger.debug(
            f"[meme_manager] 使用 Embedding Provider: {getattr(embedding_provider, 'id', type(embedding_provider).__name__)}"
        )
    else:
        logger.info("[meme_manager] 没有可用的 Embedding Provider 节点")

    # 5. 计算相似度匹配
    found_vector = set()
    if embedding_provider:
        from .database import get_all_tag_embeddings

        tag_embeddings = get_all_tag_embeddings()

        # Check if there are any valid emotions missing from the embedding database
        import asyncio

        missing_tags = [tag for tag in valid_emoticons if tag not in tag_embeddings]
        if missing_tags:
            logger.info(
                f"[meme_manager] 检测到有 {len(missing_tags)} 个标签未计算向量，已触发后台增量计算。"
            )
            asyncio.create_task(sync_tag_embeddings(sender))

        raw_tags_vectors = []
        for raw_tag in tags_to_embed:
            try:
                vec = await embedding_provider.get_embedding(raw_tag)
                if vec:
                    raw_tags_vectors.append(vec)
                    logger.info(
                        f"[meme_manager] 获取标签 '{raw_tag}' 向量成功：维度={len(vec)}, "
                        f"前5位数据={vec[:5]}"
                    )
            except Exception as e:
                logger.warning(f"[meme_manager] 获取标签 '{raw_tag}' 向量失败: {e}")

        text_vector = None
        text_weight = get_config_value(sender.config, "embedding_text_weight", 0.3)
        if text_weight > 0 and clean_text.strip():
            try:
                text_vector = await embedding_provider.get_embedding(clean_text.strip())
                if text_vector:
                    logger.debug(
                        f"[meme_manager] 获取回复文本 '{clean_text.strip()}' 向量成功：维度={len(text_vector)}, "
                        f"前5位数据={text_vector[:5]}"
                    )
            except Exception as e:
                logger.warning(f"[meme_manager] 获取回复文本向量失败: {e}")

        logger.debug(
            f"[meme_manager] 提取标签向量 {len(raw_tags_vectors)} 个, 文本向量计算成功={text_vector is not None}, 缓存的标签向量总数={len(tag_embeddings)}"
        )

        if (raw_tags_vectors or text_vector) and tag_embeddings:
            similarity_threshold = get_config_value(
                sender.config, "embedding_similarity_threshold", 0.6
            )
            tag_weight = get_config_value(sender.config, "embedding_tag_weight", 0.7)

            scores = {}
            all_scores_debug = {}
            for valid_tag in valid_emoticons:
                if valid_tag in found_exact:
                    continue

                tag_vec = tag_embeddings.get(valid_tag)
                if not tag_vec:
                    all_scores_debug[valid_tag] = "no_vec"
                    continue

                sim_tag = 0.0
                if raw_tags_vectors:
                    sim_tag = max(
                        cosine_similarity(v, tag_vec) for v in raw_tags_vectors
                    )

                sim_text = 0.0
                if text_vector:
                    sim_text = cosine_similarity(text_vector, tag_vec)

                w_tag = tag_weight if raw_tags_vectors else 0.0
                w_text = text_weight if text_vector else 0.0
                total_weight = w_tag + w_text

                if total_weight > 0:
                    combined_score = (
                        sim_tag * w_tag + sim_text * w_text
                    ) / total_weight
                else:
                    combined_score = 0.0

                all_scores_debug[valid_tag] = (
                    f"sim_tag={sim_tag:.4f}, sim_text={sim_text:.4f}, combined={combined_score:.4f}"
                )
                if combined_score >= similarity_threshold:
                    scores[valid_tag] = combined_score

            logger.debug(
                f"[meme_manager] 所有候选表情标签匹配得分 (阈值={similarity_threshold}): {all_scores_debug}"
            )

            if scores:
                sorted_tags = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                logger.info(f"[meme_manager] 向量召回排序得分: {sorted_tags}")
                max_limit = sender.max_emotions_per_message
                for t, score in sorted_tags[:max_limit]:
                    found_vector.add(t)
    else:
        logger.warning(
            "[meme_manager] 未配置或未找到可用的 Embedding 模型，无法进行向量召回。"
        )

    sender.found_emotions = list(found_exact.union(found_vector))

    # 追加专属表情判定（跟原逻辑保持一致）
    if sender.found_emotions:
        import random

        if random.random() < 0.7 and dedicated_tag:
            dedicated_tag = dedicated_tag.strip()
            if dedicated_tag and dedicated_tag not in sender.found_emotions:
                sender.found_emotions.append(dedicated_tag)

    logger.info(f"[meme_manager] 向量召回最终匹配到的标签列表: {sender.found_emotions}")

    clean_text = re.sub(
        r"<emotions>.*?</emotions>",
        "",
        clean_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    response.completion_text = clean_text.strip()


async def handle_resp(sender, event: AstrMessageEvent, response: LLMResponse):
    """处理 LLM 响应，识别表情"""
    if getattr(sender, "enable_llm_tool", False):
        logger.debug("[meme_manager] LLM 发图工具已启用，跳过自动表情识别。")
        return
    if not response or not response.completion_text:
        logger.debug("[meme_manager] LLM 响应为空，跳过表情识别。")
        return

    sender.found_emotions = []  # 重置表情列表
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

    from .helpers import load_persona_tags

    p_tags = load_persona_tags()
    dedicated_tag = p_tags.get(persona_id)
    if dedicated_tag:
        dedicated_tag = dedicated_tag.strip()
        if dedicated_tag:
            valid_emoticons.add(dedicated_tag)

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


async def search_memes_for_llm(sender, query: str, persona_id: str) -> list[dict]:
    """为 LLM 搜索表情包。支持精确子串匹配与向量相似度检索。"""
    query = query.strip()
    if not query:
        return []

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT filename, emotions FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
        (f"%,{persona_id},%",),
    )
    rows = cursor.fetchall()
    conn.close()

    # 获取 Embeddings Provider
    provider_id = get_config_value(sender.config, "embedding_provider_id", "")
    embedding_provider = None
    if provider_id:
        embedding_provider = sender.context.get_provider_by_id(provider_id)
    if not embedding_provider:
        provs = sender.context.get_all_embedding_providers()
        if provs:
            embedding_provider = provs[0]

    # 计算 query 的 embedding
    query_vector = None
    if embedding_provider:
        try:
            query_vector = await embedding_provider.get_embedding(query)
        except Exception as e:
            logger.warning(f"[meme_manager] 获取查询词 '{query}' 向量失败: {e}")

    # 获取所有标签的向量
    from .database import get_all_tag_embeddings
    tag_embeddings = get_all_tag_embeddings()

    similarity_threshold = get_config_value(
        sender.config, "embedding_similarity_threshold", 0.6
    )

    scored_memes = []
    for row in rows:
        filename = row["filename"]
        full_path = os.path.join(MEMES_DIR, filename)
        if not os.path.exists(full_path):
            continue

        emotions_str = row["emotions"] or ""
        emotions = [e.strip() for e in emotions_str.split(",") if e.strip()]

        max_score = 0.0
        # 1. 尝试子串匹配
        for emotion in emotions:
            if query.lower() in emotion.lower():
                score = 1.0 + (len(query) / len(emotion)) * 0.1
                if score > max_score:
                    max_score = score

        # 2. 尝试向量相似度匹配
        if query_vector and tag_embeddings:
            for emotion in emotions:
                tag_vec = tag_embeddings.get(emotion)
                if tag_vec:
                    sim = cosine_similarity(query_vector, tag_vec)
                    if sim >= similarity_threshold:
                        score = sim
                        if score > max_score:
                            max_score = score

        if max_score > 0.0:
            scored_memes.append({
                "filename": filename,
                "emotions": emotions,
                "score": max_score
            })

    # 按分数降序排列，最多返回前 8 个
    scored_memes.sort(key=lambda x: x["score"], reverse=True)
    return scored_memes[:8]

