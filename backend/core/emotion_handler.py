import math
import os
import random
import re

from astrbot.api.event import AstrMessageEvent

from ...config import MEMES_DIR
from ...utils import get_config_value
from ..db.database import get_db_conn
from .helpers import get_persona_id, normalize_meme_send_mode


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

    sql = f"SELECT id, filename, emotions, description, send_mode FROM memes WHERE {' AND '.join(conditions)}"
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
            send_mode = normalize_meme_send_mode(
                row["send_mode"] if "send_mode" in row.keys() else None
            )
            score = matched_score + dedicated_bonus

            if score > 0:
                valid_memes.append(
                    {
                        "id": row["id"] if "id" in row.keys() else None,
                        "filename": filename,
                        "emotions": meme_emotions,
                        "description": description or "",
                        "send_mode": send_mode,
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


def cosine_similarity(v1, v2):
    dot_product = sum(x * y for x, y in zip(v1, v2))
    norm_v1 = math.sqrt(sum(x * x for x in v1))
    norm_v2 = math.sqrt(sum(x * x for x in v2))
    if not norm_v1 or not norm_v2:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)


async def search_memes_for_llm(
    sender, query: str, persona_id: str, event: AstrMessageEvent = None, limit: int = 8
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
    query_parts = [q.strip() for q in re.split(r"[,，\s]+", query) if q.strip()]
    matched_emotions = await match_emotions_by_tags(
        sender, event, query_parts, valid_emoticons
    )

    if not matched_emotions:
        return []

    # 4. Get scoring details
    scored_memes = await get_scored_memes_by_emotions(
        sender, matched_emotions, persona_id
    )

    # Return the top matched memes (required format: id, filename, emotions, description, score)
    results = []
    for item in scored_memes[:limit]:
        results.append(
            {
                "id": item.get("id"),
                "filename": item["filename"],
                "emotions": item["emotions"],
                "description": item["description"],
                "send_mode": normalize_meme_send_mode(item.get("send_mode")),
                "score": item["score"],
            }
        )
    return results


async def get_direct_trigger_memes(
    sender, event: AstrMessageEvent, raw_tags: list[str]
) -> list[dict]:
    """Return matching memes for legacy callers such as BigBanana.

    Args:
        sender: Plugin instance providing configuration and retrieval services.
        event: Message event used to resolve the current persona.
        raw_tags: Ordered tags supplied by the calling plugin.

    Returns:
        Ranked matching meme records, or an empty list when no tags match.
        The caller is responsible for constructing and sending the images.
    """
    query = ", ".join(tag.strip() for tag in raw_tags if tag.strip())
    if not query:
        return []

    persona_id = await get_persona_id(sender, event)
    return await search_memes_for_llm(sender, query, persona_id, event)


async def get_candidate_memes_for_plugin(
    sender,
    persona_id: str = "default",
    query: str = "",
    count: int = 5,
    event: AstrMessageEvent = None,
) -> list[dict]:
    """供外部插件 (如 Giftia) 获取结构化表情包候选列表的统一公共入口。
    优先执行基于标签/向量的多通道评分检索；若无匹配或 query 为空则返回该人设下的表情包。
    """
    if count <= 0:
        return []

    if query and query.strip():
        results = await search_memes_for_llm(
            sender=sender,
            query=query,
            persona_id=persona_id,
            event=event,
            limit=count,
        )
        if results:
            return results

    # 兜底：返回当前人设下的表情包
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, emotions, description, send_mode FROM memes WHERE personas = '*' OR ',' || personas || ',' LIKE ?",
        (f"%,{persona_id},%",),
    )
    rows = cursor.fetchall()
    conn.close()

    candidates = []
    for row in rows:
        fn = str(row["filename"])
        full_path = os.path.join(MEMES_DIR, fn)
        if os.path.exists(full_path):
            emotions_list = (
                [e.strip() for e in row["emotions"].split(",") if e.strip()]
                if row["emotions"]
                else []
            )
            candidates.append(
                {
                    "id": row["id"],
                    "filename": fn,
                    "emotions": emotions_list,
                    "description": row["description"] or "",
                    "send_mode": normalize_meme_send_mode(row["send_mode"]),
                    "score": 0,
                }
            )

    random.shuffle(candidates)
    return candidates[:count]


async def match_emotions_by_tags(
    sender, event: AstrMessageEvent, raw_tags: list[str], valid_emoticons: set[str]
) -> list[tuple[str, list[str]]]:
    """Match query tags to exact and semantically similar library tags.

    Args:
        sender: Plugin instance providing configuration and embedding providers.
        event: Optional message event associated with the search.
        raw_tags: Ordered tags from a tool or external plugin query.
        valid_emoticons: Tags available to the selected persona.

    Returns:
        Query tags paired with their ranked matching library tags.
    """
    if not raw_tags or not valid_emoticons:
        return []

    threshold = get_config_value(sender.config, "embedding_similarity_threshold", 0.6)
    final_emotions = []
    for raw_tag in raw_tags:
        normalized = raw_tag.lower()
        exact_match = next(
            (tag for tag in valid_emoticons if tag.lower() == normalized), None
        )
        candidates = [exact_match] if exact_match else []
        similar = await sender.tag_embeddings.search(
            raw_tag, valid_emoticons.difference(candidates), threshold, limit=5
        )
        candidates.extend(tag for tag, _ in similar)
        if candidates:
            final_emotions.append((raw_tag, candidates))
    return final_emotions
