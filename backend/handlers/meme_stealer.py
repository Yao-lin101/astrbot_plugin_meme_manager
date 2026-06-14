import hashlib
import io
import json
import re
import ssl
import time

import aiohttp
from PIL import Image as PILImage

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import Image, Reply

from ...utils import get_config_value
from ..core.helpers import get_persona_id, get_persona_setting
from ..db.database import get_db_conn, get_steal_attempt, save_steal_attempt
from ..db.models import save_and_register_meme

# 会话最近图片缓存的有效期：超过该时长的缓存图片不再用于 steal_meme 回退取图
LAST_IMAGE_CACHE_TTL = 300


async def _check_meme_preference_match(
    sender,
    event: AstrMessageEvent,
    content: bytes,
    file_type: str,
    preference_text: str,
) -> tuple[bool, str]:
    """调用多模态 LLM 判定图片是否满足人格的表情包收集偏好。

    Returns:
        (is_matched, error_message_or_reason)
    """
    provider_id = getattr(sender, "multimodal_llm_provider_id", "")
    if not provider_id:
        provider_id = await sender.context.get_current_chat_provider_id(
            umo=event.unified_msg_origin
        )
    if not provider_id:
        return False, "未找到可用的多模态模型/聊天模型提供商，无法进行偏好判定。"

    import base64

    mime_type = "image/jpeg"
    if file_type == "png":
        mime_type = "image/png"
    elif file_type == "gif":
        mime_type = "image/gif"
    elif file_type == "webp":
        mime_type = "image/webp"

    b64_data = base64.b64encode(content).decode("utf-8")
    image_data_uri = f"data:{mime_type};base64,{b64_data}"

    prompt = (
        f"请根据当前人格的表情包收集偏好，判定给定的表情包图片是否符合该收集偏好。\n"
        f"【当前人格的表情包收集偏好】：\n"
        f"{preference_text}\n\n"
        f"【判定规则（极其重要）】：\n"
        f"1. 判断图片是否属于表情包范畴，不属于的直接判false。\n"
        f"2. 仔细分析图片内容和风格，结合上述偏好描述进行判定。\n"
        f"3. 请仅以 JSON 格式返回，包含 `match`（布尔值：true 或 false）和 `reason`（字符串：简短的判定理由）。\n"
        f"例如：\n"
        f'{{"match": true, "reason": "符合科幻与警告风格"}}\n'
        f"或：\n"
        f'{{"match": false, "reason": "图片风格过于日常、可爱，不符合偏好"}}\n'
        f"不要返回任何其他内容（如 markdown 代码块标记、解释等），只返回 JSON 串本身。"
    )

    try:
        logger.debug(
            f"[meme_manager] 正在调用多模态模型 {provider_id} 判定表情包偏好匹配度..."
        )
        llm_resp = await sender.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
            image_urls=[image_data_uri],
        )
        if not llm_resp or not llm_resp.completion_text:
            return False, "模型返回内容为空，判定失败。"

        raw_text = llm_resp.completion_text.strip()
        logger.debug(f"[meme_manager] 多模态模型偏好匹配判定返回内容: {raw_text}")

        data = None
        try:
            data = json.loads(raw_text)
        except Exception:
            # 尝试使用正则匹配提取 JSON
            match = re.search(r"\{[\s\S]*\}", raw_text)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    pass

        if isinstance(data, dict) and "match" in data:
            is_match = bool(data["match"])
            reason = data.get("reason", "")
            return is_match, reason
        else:
            return False, f"无法解析模型返回的判定结果：{raw_text}"
    except Exception as e:
        logger.error(f"[meme_manager] 偏好匹配度判定失败: {e}", exc_info=True)
        return False, f"调用多模态模型出错: {str(e)}"


async def resolve_persona_preference(
    sender, event: AstrMessageEvent
) -> tuple[str, str | None, str | None]:
    """解析当前会话的人格 ID 及其表情包收集偏好。

    偏好直接读取插件内维护的人格偏好配置（persona_settings），不再依赖解析
    人格系统提示词中的 <meme_preference> 标签。

    Returns:
        (persona_id, preference_text|None, error_message|None)
    """
    persona_id = await get_persona_id(sender, event)
    preference_text = get_persona_setting(
        sender.config, persona_id, "meme_preference"
    ).strip()

    if not preference_text:
        logger.debug(f"[meme_manager] 当前解析的人格 ID: {persona_id}, 未配置收集偏好")
        return (
            persona_id,
            None,
            "当前人格未配置表情包收集偏好，已拒绝收录。请在插件的人格偏好配置中为该人格设置收集偏好后再试。",
        )

    preview = preference_text[:30] + ("…" if len(preference_text) > 30 else "")
    logger.info(f"[meme_manager] 人格 {persona_id} 的表情包收集偏好: {preview}")
    return persona_id, preference_text, None


def extract_event_image_url(event: AstrMessageEvent) -> str | None:
    """从当前消息事件提取图片 URL：优先引用/回复中的图片，其次同消息内直发的图片。"""
    # A. 引用/回复的图片
    for comp in event.message_obj.message:
        if isinstance(comp, Reply) and comp.chain:
            for sub_comp in comp.chain:
                if isinstance(sub_comp, Image):
                    return sub_comp.url

    # B. 同消息内直发的图片
    images = [c for c in event.message_obj.message if isinstance(c, Image)]
    if images:
        return images[-1].url

    return None


def get_cached_image_url(sender, event: AstrMessageEvent) -> str | None:
    """回退取图：返回本会话最近收到且仍在有效期内的图片 URL。"""
    cache = getattr(sender, "_session_last_image", {}).get(event.unified_msg_origin)
    if cache and (time.time() - cache.get("ts", 0)) <= LAST_IMAGE_CACHE_TTL:
        logger.info(
            "[meme_manager] steal_meme 当前消息无图，回退使用本会话最近缓存的图片。"
        )
        return cache.get("url")
    return None


async def download_image(
    url: str,
) -> tuple[bytes | None, str | None, str | None, str | None]:
    """下载图片并检测类型、计算哈希。

    Returns:
        (content|None, file_type|None, raw_hash|None, error_message|None)
    """
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        if url.startswith("file:///"):
            local_path = url.replace("file:///", "")
            with open(local_path, "rb") as f:
                content = f.read()
        elif not (url.startswith("http://") or url.startswith("https://")):
            with open(url, "rb") as f:
                content = f.read()
        elif "multimedia.nt.qq.com.cn" in url:
            insecure_url = url.replace("https://", "http://", 1)
            async with aiohttp.ClientSession() as session:
                async with session.get(insecure_url) as resp:
                    content = await resp.read()
        else:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_context)
            ) as session:
                async with session.get(url) as resp:
                    content = await resp.read()

        if not content:
            return None, None, None, "下载图片失败，文件内容为空。"

        # 检测图片类型
        try:
            with PILImage.open(io.BytesIO(content)) as img_obj:
                file_type = img_obj.format.lower()
        except Exception as e:
            logger.error(f"图片格式检测失败: {str(e)}")
            file_type = "unknown"

        raw_hash = hashlib.sha256(content).hexdigest()
        return content, file_type, raw_hash, None

    except Exception as e:
        logger.error(f"下载图片或检测格式失败: {e}", exc_info=True)
        return None, None, None, f"下载/解析图片失败：{str(e)}"


async def _check_similarity_dedup(
    sender, persona_id: str, content: bytes
) -> str | None:
    """相似度去重判定 (Pillow dHash + Histogram)。

    命中相似表情时返回应回复给用户的消息（追加权限/拒绝收录）；未命中则返回 None。
    """
    enable_similarity = get_config_value(sender.config, "enable_similarity_dedup", True)
    if not enable_similarity:
        return None

    from ..db.similarity import check_image_similarity

    similarity_threshold = get_config_value(
        sender.config, "similarity_dedup_threshold", 0.85
    )
    sim_match = check_image_similarity(content, similarity_threshold)
    if not sim_match:
        return None

    matched_filename, score = sim_match
    logger.info(
        f"[meme_manager] 手动偷图被相似度检测拦截: 与 {matched_filename} 相似度 {score:.4f}"
    )

    # Query the existing similar meme to check its personas
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT personas FROM memes WHERE filename = ?",
        (matched_filename,),
    )
    row = cursor.fetchone()
    if row:
        existing_personas = (
            set(row["personas"].split(",")) if row["personas"] else set()
        )
        if "*" in existing_personas or persona_id in existing_personas:
            conn.close()
            return f"该表情包已存在相似度极高的版本（文件名：{matched_filename}，相似度：{score:.2%}），且当前人格已拥有该表情包使用权限，拒绝重复收录。"

        # Append persona_id to existing_personas
        if persona_id != "*":
            existing_personas.add(persona_id)
        else:
            existing_personas = {"*"}

        cursor.execute(
            "UPDATE memes SET personas = ? WHERE filename = ?",
            (",".join(existing_personas), matched_filename),
        )
        conn.commit()
        conn.close()
        await sender.reload_emotions()
        return f"此表情包已存在相似度极高的版本（文件名：{matched_filename}，相似度：{score:.2%}），已自动为您追加当前人格【{persona_id}】的使用权限。"
    else:
        conn.close()
        return f"该表情包已存在相似度极高的版本（文件名：{matched_filename}，相似度：{score:.2%}），拒绝重复收录。"


async def _check_preference(
    sender,
    event: AstrMessageEvent,
    persona_id: str,
    raw_hash: str,
    content: bytes,
    file_type: str,
    preference_text: str,
) -> str | None:
    """表情包收集偏好判定（含历史尝试缓存）。

    不符合偏好时返回拒绝消息；符合（或可继续）则返回 None。
    """
    attempt = get_steal_attempt(raw_hash, persona_id)
    if attempt:
        is_matched = bool(attempt["is_matched"])
        logger.info(
            f"[meme_manager] 发现缓存记录：image_hash={raw_hash}, persona_id={persona_id}, is_matched={is_matched}"
        )
        if not is_matched:
            reason = (
                attempt["reason"]
                if "reason" in attempt.keys() and attempt["reason"]
                else ""
            )
            if reason:
                return f"该图片不符合当前人格的表情包收集偏好，拒绝收录。原因: {reason}"
            else:
                return "该图片不符合当前人格的表情包收集偏好，拒绝收录。"
        return None
    else:
        is_matched, match_reason = await _check_meme_preference_match(
            sender, event, content, file_type, preference_text
        )
        if not is_matched:
            if (
                "错误" in match_reason
                or "失败" in match_reason
                or "未找到" in match_reason
            ):
                return f"大模型判定失败/不支持多模态：{match_reason}"
            else:
                # 明确的拒绝，记录缓存
                try:
                    save_steal_attempt(raw_hash, persona_id, False, match_reason)
                except Exception as ex:
                    logger.warning(f"保存尝试记录失败: {ex}")
                return f"该图片不符合当前人格的表情包收集偏好，拒绝收录。原因: {match_reason}"
        return None


async def _classify_with_multimodal(
    sender, event: AstrMessageEvent, content: bytes, file_type: str
) -> tuple[list[str], str, bool, bool]:
    """调用多模态模型对图片自动分类并生成描述。

    Returns:
        (parsed_tags, description, called, failed)
        called=是否实际调用了模型（有可用 provider）；failed=调用过程中是否异常。
    """
    provider_id = getattr(sender, "multimodal_llm_provider_id", "")
    if not provider_id:
        provider_id = await sender.context.get_current_chat_provider_id(
            umo=event.unified_msg_origin
        )
    if not provider_id:
        return [], "", False, False

    import base64

    mime_type = "image/jpeg"
    if file_type == "png":
        mime_type = "image/png"
    elif file_type == "gif":
        mime_type = "image/gif"
    elif file_type == "webp":
        mime_type = "image/webp"

    b64_data = base64.b64encode(content).decode("utf-8")
    image_data_uri = f"data:{mime_type};base64,{b64_data}"

    guidelines = getattr(sender, "multimodal_tag_prompt", None)
    if not guidelines:
        guidelines = (
            "请对这张表情包图片进行深度的视觉与语义分析，并从以下几个社交使用维度中提炼出最契合该图的 2-5 个中文分类标签：\n\n"
            "1. 意图与社交功能维度（使用者想用它达到什么社交目的？）：\n"
            "   - 如：破冰、开场、敷衍、话题终结（呵呵/递茶）、赞同、反对、索求（抱抱/摸头/红包）等行为补偿。\n"
            "2. 情绪与心理映射维度（传达的原生或复合情绪是什么？）：\n"
            "   - 如：开心、委屈、得意、尴尬、强颜欢笑、开摆、自嘲、暴躁、发疯、吃惊、无语。\n"
            "3. 符号与画面主体维度（画面的主角和主要动作是什么？）：\n"
            "   - 如：猫猫、柴犬、熊猫头、二次元少女、电脑、睡觉、指点、吃瓜。\n"
            "4. 社交关系、风格与态度维度（表达了怎样的对话语气或关系态度？）：\n"
            "   - 如：职场发疯、向下示弱、阴阳怪气、沙雕、高糊、二次元、玩梗、土味、治愈。\n\n"
            "【标签规则】：\n"
            "- 标签应当使用简短、高频的中文词汇（如：贴贴、无语、猫猫、开摆、敷衍、职场）。\n"
            "- 请结合图片内容和上述维度，选择最具有代表性的 2-5 个标签，不需要每个维度都覆盖。"
        )

    prompt = (
        f"{guidelines}\n\n"
        "【输出格式要求（极其重要）】：\n"
        "- 请仅以 JSON 格式的字典对象返回，其中必须包含两个字段：\n"
        '  1. `tags` (数组，表情包对应的标签列表，如 ["敷衍", "猫猫"])\n'
        '  2. `description` (字符串，对这张表情包画面的简洁描述，如 "一只猫猫摊在地上露出无语的表情")\n'
        "例如：\n"
        "{\n"
        '  "tags": ["敷衍", "猫猫"],\n'
        '  "description": "一只摊在地上表情无语的猫猫"\n'
        "}\n"
        "不要返回任何其他内容（如 markdown 代码块标记、解释等），只返回 JSON 串本身。"
    )

    try:
        logger.debug(f"正在调用多模态模型 {provider_id} 判定表情分类与描述...")
        llm_resp = await sender.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
            image_urls=[image_data_uri],
        )
        parsed_categories: list[str] = []
        description = ""
        if llm_resp and llm_resp.completion_text:
            raw_text = llm_resp.completion_text.strip()
            logger.debug(f"多模态模型返回内容: {raw_text}")
            data = None
            try:
                data = json.loads(raw_text)
            except Exception:
                match = re.search(r"\{[\s\S]*\}", raw_text)
                if match:
                    try:
                        data = json.loads(match.group(0))
                    except Exception:
                        pass

            if isinstance(data, dict):
                parsed_categories = [str(x) for x in data.get("tags", [])]
                description = str(data.get("description", "")).strip()
            elif isinstance(data, list):
                parsed_categories = [str(x) for x in data]
            else:
                valid_categories = set(sender.category_manager.get_categories())
                for cat in valid_categories:
                    if cat in raw_text:
                        parsed_categories.append(cat)

        return parsed_categories, description, True, False
    except Exception as e:
        logger.error(f"多模态模型分析图片分类失败: {e}", exc_info=True)
        return [], "", True, True


async def _snap_new_tags_to_existing(
    sender,
    new_tags: list[str],
    existing_tags: set[str],
) -> list[str]:
    """将新标签按向量相似度自动吸附到已有标签，从源头减少标签碎片化。

    仅当配置的 auto_tag_merge_threshold > 0 且存在可用 Embedding 提供商时生效。
    新标签会与已缓存向量的已有标签逐一比较，若最高相似度 >= 阈值则替换为该已有标签；
    否则保持新标签原样（作为全新标签收录）。整个过程为尽力而为：缺少向量、无 Provider
    或计算失败时静默跳过该标签，不影响收录主流程。
    """
    threshold = float(get_config_value(sender.config, "auto_tag_merge_threshold", 0))
    if threshold <= 0 or not new_tags:
        return new_tags

    # 只把"已有标签"中尚未出现在本次结果里的作为吸附目标
    candidate_targets = [t for t in existing_tags if t]
    if not candidate_targets:
        return new_tags

    from ..core.emotion_handler import cosine_similarity
    from ..db.database import get_all_tag_embeddings

    tag_embeddings = get_all_tag_embeddings()
    if not tag_embeddings:
        return new_tags

    provider_id = get_config_value(sender.config, "embedding_provider_id", "")
    embedding_provider = None
    if provider_id:
        embedding_provider = sender.context.get_provider_by_id(provider_id)
    if not embedding_provider:
        provs = sender.context.get_all_embedding_providers()
        if provs:
            embedding_provider = provs[0]
    if not embedding_provider:
        return new_tags

    snapped: list[str] = []
    seen: set[str] = set()
    for tag in new_tags:
        # 已经是已有标签的，无需吸附
        if tag in existing_tags:
            if tag not in seen:
                seen.add(tag)
                snapped.append(tag)
            continue

        try:
            tag_vec = await embedding_provider.get_embedding(tag)
        except Exception as e:
            logger.warning(f"[meme_manager] 自动合并：获取新标签 '{tag}' 向量失败: {e}")
            tag_vec = None

        best_tag = None
        best_sim = 0.0
        if tag_vec:
            for target in candidate_targets:
                target_vec = tag_embeddings.get(target)
                if not target_vec:
                    continue
                sim = cosine_similarity(tag_vec, target_vec)
                if sim >= threshold and sim > best_sim:
                    best_sim = sim
                    best_tag = target

        final_tag = tag
        if best_tag is not None:
            logger.info(
                f"[meme_manager] 自动合并：新标签 '{tag}' 已吸附到已有标签 "
                f"'{best_tag}' (相似度={best_sim:.4f}, 阈值={threshold})"
            )
            final_tag = best_tag

        if final_tag not in seen:
            seen.add(final_tag)
            snapped.append(final_tag)

    return snapped


async def _resolve_categories(
    sender,
    event: AstrMessageEvent,
    content: bytes,
    file_type: str,
    categories: list[str] | None,
    description_str: str,
) -> tuple[list[str], list[str], str, str | None]:
    """解析最终分类标签：显式传入优先，否则在启用多模态时自动分类。

    Returns:
        (resolved_categories, invalid_categories, description_str, error_message|None)
    """
    resolved_categories: list[str] = []
    invalid_categories: list[str] = []
    valid_categories = set(sender.category_manager.get_categories())

    def _sort_tags(tags: list[str]) -> None:
        for cat in tags:
            cat = cat.strip()
            if not cat:
                continue
            if cat in valid_categories:
                resolved_categories.append(cat)
            else:
                # 允许作为自定义的新标签
                clean_cat = cat.lower()
                if len(clean_cat) <= 20:
                    resolved_categories.append(clean_cat)
                else:
                    invalid_categories.append(cat)

    # A. 首先尝试解析显式传入的 categories 参数
    if categories:
        _sort_tags(categories)

    # B. 如果解析后没有得到任何分类，且启用了多模态，则调用多模态模型自动分类
    multimodal_called = False
    multimodal_failed = False
    if not resolved_categories and getattr(sender, "multimodal_llm_enabled", False):
        (
            parsed,
            desc,
            multimodal_called,
            classify_failed,
        ) = await _classify_with_multimodal(sender, event, content, file_type)
        if multimodal_called:
            if not description_str:
                description_str = desc
            if parsed:
                logger.debug(
                    f"多模态模型判定表情分类为: {parsed}, 描述为: {description_str}"
                )
                _sort_tags(parsed)
            if classify_failed or not resolved_categories:
                multimodal_failed = True

    # C. 最终校验
    if not resolved_categories:
        if multimodal_called and multimodal_failed:
            return (
                [],
                invalid_categories,
                description_str,
                "多模态模型判定表情分类失败，且未提供有效的分类名称。",
            )
        elif invalid_categories:
            return (
                [],
                invalid_categories,
                description_str,
                f"无效的表情包分类 {invalid_categories}，当前可用的分类有：{', '.join(valid_categories)}",
            )
        else:
            return (
                [],
                invalid_categories,
                description_str,
                "请输入至少一个有效的标签/分类名称。",
            )

    # D. 新标签自动吸附到语义相近的已有标签（从源头减少碎片化）
    resolved_categories = await _snap_new_tags_to_existing(
        sender, resolved_categories, valid_categories
    )

    return resolved_categories, invalid_categories, description_str, None


async def _persist_stolen_meme(
    sender,
    persona_id: str,
    content: bytes,
    file_type: str,
    raw_hash: str,
    resolved_categories: list[str],
    invalid_categories: list[str],
    description_str: str,
) -> str:
    """将表情包写入数据库：已存在则合并分类/人格，否则保存并注册新表情。"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT filename, emotions, personas, description FROM memes WHERE original_hash = ?",
        (raw_hash,),
    )
    row = cursor.fetchone()

    try:
        if row:
            existing_filename = row["filename"]
            existing_emotions = (
                set(row["emotions"].split(",")) if row["emotions"] else set()
            )
            existing_personas = (
                set(row["personas"].split(",")) if row["personas"] else set()
            )

            for cat in resolved_categories:
                existing_emotions.add(cat)

            if persona_id != "*":
                existing_personas.add(persona_id)
            else:
                existing_personas = {"*"}

            existing_description = row["description"] or ""
            final_description = (
                description_str
                if (description_str and description_str.strip())
                else existing_description
            )

            cursor.execute(
                "UPDATE memes SET emotions = ?, personas = ?, description = ? WHERE filename = ?",
                (
                    ",".join(existing_emotions),
                    ",".join(existing_personas),
                    final_description,
                    existing_filename,
                ),
            )
            conn.commit()
            conn.close()

            # 执行成功，记录缓存
            try:
                save_steal_attempt(raw_hash, persona_id, True)
            except Exception as ex:
                logger.warning(f"保存尝试记录失败: {ex}")

            await sender.reload_emotions()

            invalid_tip = (
                f"（忽略了无效的标签 {invalid_categories}）"
                if invalid_categories
                else ""
            )
            return f"此表情包已经存在（文件名：{existing_filename}），已为您合并/追加分类【{', '.join(resolved_categories)}】并对当前人格生效。{invalid_tip}"

        conn.close()

        # 不存在则保存并注册
        ext_mapping = {
            "jpeg": ".jpg",
            "png": ".png",
            "gif": ".gif",
            "webp": ".webp",
        }
        ext = ext_mapping.get(file_type, ".jpg")

        timestamp = int(time.time())
        filename = f"stolen_{timestamp}{ext}"

        res = save_and_register_meme(
            image_bytes=content,
            filename=filename,
            category=resolved_categories,
            personas=persona_id,
            config=sender.config,
            original_hash=raw_hash,
            description=description_str,
        )

        # 执行成功，记录缓存
        try:
            save_steal_attempt(raw_hash, persona_id, True)
        except Exception as ex:
            logger.warning(f"保存尝试记录失败: {ex}")

        invalid_tip = (
            f"（忽略了无效的标签 {invalid_categories}）" if invalid_categories else ""
        )
        await sender.reload_emotions()

        return f"成功收录表情包「{res['filename']}」到标签【{', '.join(resolved_categories)}】中，且仅供人格【{persona_id}】使用。{invalid_tip}"

    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        raise e


async def process_stolen_image(
    sender,
    event: AstrMessageEvent,
    persona_id: str,
    preference_text: str,
    content: bytes,
    file_type: str,
    raw_hash: str,
    categories: list[str] | None,
    description_str: str,
) -> str:
    """图片下载完成后的统一收录流水线：相似度去重 → 偏好判定 → 分类解析 → 入库。

    手动 steal_meme 与被动 auto_steal_meme 共用此流程，返回值为应回复/记录的消息。
    """
    # 1. 相似度去重判定
    dedup_msg = await _check_similarity_dedup(sender, persona_id, content)
    if dedup_msg is not None:
        return dedup_msg

    # 2. 表情包收集偏好判定
    pref_msg = await _check_preference(
        sender, event, persona_id, raw_hash, content, file_type, preference_text
    )
    if pref_msg is not None:
        return pref_msg

    # 3. 标签/分类解析与判定
    (
        resolved_categories,
        invalid_categories,
        description_str,
        cat_err,
    ) = await _resolve_categories(
        sender, event, content, file_type, categories, description_str
    )
    if cat_err is not None:
        return cat_err

    # 4. 数据库排重及记录更新
    return await _persist_stolen_meme(
        sender,
        persona_id,
        content,
        file_type,
        raw_hash,
        resolved_categories,
        invalid_categories,
        description_str,
    )


async def auto_steal_meme(sender, event: AstrMessageEvent):
    """暗中自动偷表情包功能（被动监听群聊消息）"""
    # 1. 获取当前会话的人格 ID，并检查偏好设置
    persona_id, preference_text, _ = await resolve_persona_preference(sender, event)
    if not preference_text:
        logger.debug(
            f"[meme_manager] 当前人格 {persona_id} 未配置表情包收集偏好，跳过自动偷表情。"
        )
        return

    # 2. 从消息中提取图片 URL
    last_image_url = extract_event_image_url(event)
    if not last_image_url:
        return

    # 3. 下载图片并计算 hash
    content, file_type, raw_hash, dl_err = await download_image(last_image_url)
    if dl_err or not content:
        logger.warning(f"[meme_manager] 自动偷表情：{dl_err or '下载图片内容为空'}")
        return

    # 4. 判断是否被当前人格使用工具盗取/尝试过
    # A. 检查 attempts 表
    attempt = get_steal_attempt(raw_hash, persona_id)
    if attempt is not None:
        logger.debug(
            f"[meme_manager] 自动偷表情：图片 {raw_hash} 存在历史处理记录，跳过。"
        )
        return

    # A.5 检查相似度去重 (Pillow dHash + Histogram)
    enable_similarity = get_config_value(sender.config, "enable_similarity_dedup", True)
    if enable_similarity:
        from ..db.similarity import check_image_similarity

        similarity_threshold = get_config_value(
            sender.config, "similarity_dedup_threshold", 0.85
        )
        sim_match = check_image_similarity(content, similarity_threshold)
        if sim_match:
            matched_filename, score = sim_match

            # Check if this persona already owns it
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT personas FROM memes WHERE filename = ?",
                (matched_filename,),
            )
            row = cursor.fetchone()
            if row:
                existing_personas = (
                    set(row["personas"].split(",")) if row["personas"] else set()
                )
                if "*" in existing_personas or persona_id in existing_personas:
                    conn.close()
                    logger.debug(
                        f"[meme_manager] 自动偷表情：图片 {raw_hash} 相似于已有表情 {matched_filename} 且已被当前人格拥有，跳过。"
                    )
                    return

                # Append persona_id to existing_personas
                if persona_id != "*":
                    existing_personas.add(persona_id)
                else:
                    existing_personas = {"*"}

                cursor.execute(
                    "UPDATE memes SET personas = ? WHERE filename = ?",
                    (",".join(existing_personas), matched_filename),
                )
                conn.commit()
                conn.close()
                await sender.reload_emotions()
                logger.info(
                    f"[meme_manager] 自动偷表情：检测到相似表情 {matched_filename} (相似度: {score:.4f})，已为人格 {persona_id} 追加使用权限。"
                )
                return
            else:
                conn.close()
                logger.debug(
                    f"[meme_manager] 自动偷表情：图片 {raw_hash} 相似于已有表情 {matched_filename} (相似度: {score:.4f})，但记录已丢失，跳过。"
                )
                return

    # B. 检查 memes 表中是否已经包含这个 original_hash 且已被此 persona 拥有
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT personas FROM memes WHERE original_hash = ?",
        (raw_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        personas = row["personas"]
        if personas:
            persona_list = [p.strip() for p in personas.split(",")]
            if "*" in persona_list or persona_id in persona_list:
                logger.debug(
                    f"[meme_manager] 自动偷表情：图片 {raw_hash} 已经在当前人格的图库中，跳过。"
                )
                return

    # C. 统计并递增该图片哈希的全局看见次数，若小于设定的阈值，则仅记录次数不触发偷图
    from ..db.database import increment_image_seen_count

    min_seen = get_config_value(sender.config, "auto_steal_min_seen", 2)
    seen_count = increment_image_seen_count(raw_hash)
    if seen_count < min_seen:
        logger.info(
            f"[meme_manager] 自动偷表情：图片 {raw_hash} 全局第 {seen_count} 次被看见，未达到设定阈值 {min_seen}，仅记录次数并跳过偷图。"
        )
        return

    # 5. 进入与手动收录一致的处理流水线（去重/偏好/分类/入库）
    logger.info(
        f"[meme_manager] 自动偷表情：开始对图片 {raw_hash} 进行暗中收录判定 (已看见 {seen_count} 次)..."
    )
    try:
        result = await process_stolen_image(
            sender,
            event,
            persona_id,
            preference_text,
            content,
            file_type,
            raw_hash,
            None,
            "",
        )
        logger.info(f"[meme_manager] 自动偷表情执行结果: {result}")
    except Exception as e:
        logger.error(f"[meme_manager] 自动偷表情执行失败: {e}", exc_info=True)
