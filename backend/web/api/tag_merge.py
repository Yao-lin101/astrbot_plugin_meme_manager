import logging

from quart import current_app, jsonify, request

from ...core.emotion_handler import cosine_similarity
from ...core.helpers import get_settings_dict, save_settings_dict
from ...db.database import (
    delete_tag_embedding,
    get_all_tag_embeddings,
    get_db_conn,
)
from .common import trigger_tag_vectorization

logger = logging.getLogger(__name__)


def _load_tag_meme_counts() -> dict[str, int]:
    """统计每个标签当前关联的表情包数量。"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT emotions FROM memes")
    rows = cursor.fetchall()
    conn.close()

    counts: dict[str, int] = {}
    for row in rows:
        if not row["emotions"]:
            continue
        for emo in row["emotions"].split(","):
            emo = emo.strip()
            if emo:
                counts[emo] = counts.get(emo, 0) + 1
    return counts


async def scan_similar_tags():
    """扫描所有标签对，基于已缓存的标签向量聚类相似标签组。"""
    try:
        threshold = float(request.args.get("threshold", 0.8))
        logger.info(f"[meme_manager] 开始扫描相似标签，阈值={threshold}")

        tag_meme_counts = _load_tag_meme_counts()
        tag_embeddings = get_all_tag_embeddings()

        # 仅对既被表情引用、又已缓存向量的标签进行聚类
        tags = [tag for tag in tag_meme_counts if tag in tag_embeddings]
        total_tags = len(tag_meme_counts)
        tags_without_vector = total_tags - len(tags)

        # Union-Find：将相似度 >= 阈值的标签合并到同一组
        parent = {tag: tag for tag in tags}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # 记录每条合并边的相似度，用于计算组内平均相似度
        edge_sims: dict[str, list[float]] = {}
        for i in range(len(tags)):
            vec_i = tag_embeddings[tags[i]]
            for j in range(i + 1, len(tags)):
                sim = cosine_similarity(vec_i, tag_embeddings[tags[j]])
                if sim >= threshold:
                    union(tags[i], tags[j])
                    edge_sims.setdefault(tags[i], []).append(sim)
                    edge_sims.setdefault(tags[j], []).append(sim)

        # 收集每个聚类的成员
        clusters: dict[str, list[str]] = {}
        for tag in tags:
            clusters.setdefault(find(tag), []).append(tag)

        groups = []
        for members in clusters.values():
            if len(members) < 2:
                continue

            # 代表标签：关联表情数最多者（数量相同则取标签名靠前者保证稳定）
            members_sorted = sorted(
                members, key=lambda t: (-tag_meme_counts.get(t, 0), t)
            )
            representative = members_sorted[0]

            tag_entries = [
                {
                    "name": t,
                    "meme_count": tag_meme_counts.get(t, 0),
                    "is_representative": t == representative,
                }
                for t in members_sorted
            ]

            sims = [s for t in members for s in edge_sims.get(t, [])]
            avg_similarity = round(sum(sims) / len(sims), 4) if sims else 0.0

            groups.append(
                {
                    "id": f"group_{len(groups)}",
                    "tags": tag_entries,
                    "avg_similarity": avg_similarity,
                }
            )

        # 平均相似度高的组排在前面
        groups.sort(key=lambda g: g["avg_similarity"], reverse=True)
        for idx, group in enumerate(groups):
            group["id"] = f"group_{idx}"

        logger.info(
            f"[meme_manager] 相似标签扫描完成，发现 {len(groups)} 个相似组"
            f"（共 {total_tags} 个标签，其中 {tags_without_vector} 个尚未计算向量）"
        )
        return (
            jsonify(
                {
                    "groups": groups,
                    "total_tags": total_tags,
                    "total_groups": len(groups),
                    "tags_without_vector": tags_without_vector,
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"[meme_manager] 扫描相似标签失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


def _merge_emotions(emotions_str: str, source_set: set[str], target: str) -> str | None:
    """将 emotions 字段中的 source 标签替换为 target，返回新字段或 None（无变化）。"""
    emotions = [e.strip() for e in emotions_str.split(",") if e.strip()]
    if not any(e in source_set for e in emotions):
        return None

    new_emotions: list[str] = []
    seen: set[str] = set()
    for e in emotions:
        replaced = target if e in source_set else e
        if replaced not in seen:
            seen.add(replaced)
            new_emotions.append(replaced)
    if target not in seen:
        new_emotions.append(target)
    return ",".join(new_emotions)


async def merge_tags():
    """执行标签合并：将 source 标签合并到 target 标签。"""
    try:
        data = await request.get_json()
        merges = data.get("merges", []) if data else []
        if not merges:
            return jsonify({"message": "merges 列表不能为空"}), 400

        # 规范化：去除空白、过滤掉与 target 相同的 source
        normalized = []
        all_sources: set[str] = set()
        for m in merges:
            target = (m.get("target") or "").strip()
            if not target:
                continue
            sources = {
                s.strip()
                for s in m.get("sources", [])
                if s and s.strip() and s.strip() != target
            }
            if not sources:
                continue
            normalized.append((target, sources))
            all_sources.update(sources)

        if not normalized:
            return jsonify({"message": "没有有效的合并项"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        # 1. 更新 memes 表的 emotions 字段
        updated_rows = 0
        cursor.execute("SELECT id, emotions FROM memes")
        rows = cursor.fetchall()
        for row in rows:
            emotions_str = row["emotions"] or ""
            current = emotions_str
            changed = False
            for target, sources in normalized:
                new_value = _merge_emotions(current, sources, target)
                if new_value is not None:
                    current = new_value
                    changed = True
            if changed:
                cursor.execute(
                    "UPDATE memes SET emotions = ? WHERE id = ?",
                    (current, row["id"]),
                )
                updated_rows += 1
        conn.commit()
        conn.close()

        # 2. 删除 source 标签的向量缓存
        for source in all_sources:
            try:
                delete_tag_embedding(source)
            except Exception as e:
                logger.warning(f"[meme_manager] 删除标签 '{source}' 向量缓存失败: {e}")

        # 3. 更新 CategoryManager (memes_data.json)
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            for target, _sources in normalized:
                category_manager.add_category(target)
            category_manager.sync_with_filesystem()

        # 4. 更新 persona_settings 中各人格的 meme_use_preference
        sender = plugin_config.get("sender")
        if sender:
            settings = get_settings_dict(sender.config)
            settings_changed = False
            for _pid, p_cfg in settings.items():
                if not isinstance(p_cfg, dict):
                    continue
                pref = p_cfg.get("meme_use_preference", "") or ""
                if not pref:
                    continue
                tags = [t.strip() for t in pref.split(",") if t.strip()]
                new_tags: list[str] = []
                seen: set[str] = set()
                changed = False
                for t in tags:
                    replaced = t
                    for target, sources in normalized:
                        if t in sources:
                            replaced = target
                            changed = True
                            break
                    if replaced not in seen:
                        seen.add(replaced)
                        new_tags.append(replaced)
                if changed:
                    p_cfg["meme_use_preference"] = ", ".join(new_tags)
                    settings_changed = True
            if settings_changed:
                save_settings_dict(sender.config, settings)
                await sender.reload_emotions()

        # 5. 触发向量同步，确保 target 标签有向量
        trigger_tag_vectorization()

        logger.info(
            f"[meme_manager] 标签合并完成：{len(normalized)} 组，"
            f"更新 {updated_rows} 条表情记录，移除 {len(all_sources)} 个源标签"
        )
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "标签合并完成",
                    "updated_memes": updated_rows,
                    "removed_tags": len(all_sources),
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"[meme_manager] 标签合并失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500
