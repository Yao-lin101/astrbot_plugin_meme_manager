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

from ..utils import get_config_value
from .database import get_db_conn, get_steal_attempt, save_steal_attempt
from .helpers import get_persona_id, get_persona_prompt
from .models import save_and_register_meme


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


async def steal_meme(
    sender,
    event: AstrMessageEvent,
    categories: list[str] | None = None,
    image_content: bytes | None = None,
    image_hash: str | None = None,
    image_type: str | None = None,
):
    """保存并收录上一条聊天记录中发送的表情包到当前人格的表情包库中。

    Args:
        categories(list): 对应的表情包类别/情绪分类名称列表（如 ["happy", "sad"] 等）
    """
    # 1. 获取当前会话的人格 ID (persona_id) 和人格提示词，并检查表情包收集偏好配置
    persona_id = await get_persona_id(sender, event)
    persona_prompt = await get_persona_prompt(sender, event)
    logger.debug(
        f"[meme_manager] 当前解析的人格 ID: {persona_id}, 提示词长度: {len(persona_prompt)}, 提示词内容: {persona_prompt}"
    )

    pref_match = re.search(
        r"<meme_preference>(.*?)</meme_preference>",
        persona_prompt,
        re.DOTALL | re.IGNORECASE,
    )
    if not pref_match:
        return "当前人格未配置表情包收集偏好（需要使用 <meme_preference> 标签包裹偏好设置），拒绝收录。"
    preference_text = pref_match.group(1).strip()
    if not preference_text:
        return "当前人格未配置表情包收集偏好（需要使用 <meme_preference> 标签包裹偏好设置），拒绝收录。"

    logger.info(f"[meme_manager] 人格 {persona_id} 的表情包收集偏好: {preference_text}")

    # 2. 从当前事件消息中提取图片（优先支持引用/回复图片，其次支持同消息内直发图片）
    last_image_url = None

    # A. 检测当前事件是否引用了图片
    for comp in event.message_obj.message:
        if isinstance(comp, Reply) and comp.chain:
            for sub_comp in comp.chain:
                if isinstance(sub_comp, Image):
                    last_image_url = sub_comp.url
                    break
            if last_image_url:
                break

    # B. 检测当前事件是否直发了图片
    if not last_image_url:
        images = [c for c in event.message_obj.message if isinstance(c, Image)]
        if images:
            last_image_url = images[-1].url

    if not last_image_url and image_content is None:
        return "没有在当前消息或引用的回复中找到可以收录的表情包/图片哦。请发送图片并在消息中说明，或者直接引用（回复）要收录的图片并发出指令。"

    # 3. 检查分类是否合法（如果未启用多模态判定，且 categories 为空，则报错）
    if not getattr(sender, "multimodal_llm_enabled", False) and not categories:
        return "请输入至少一个有效的标签/分类名称。"

    # 4. 下载图片
    content = image_content
    file_type = image_type
    raw_hash = image_hash

    if content is None or file_type is None or raw_hash is None:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        try:
            if "multimedia.nt.qq.com.cn" in last_image_url:
                insecure_url = last_image_url.replace("https://", "http://", 1)
                async with aiohttp.ClientSession() as session:
                    async with session.get(insecure_url) as resp:
                        content = await resp.read()
            else:
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl_context)
                ) as session:
                    async with session.get(last_image_url) as resp:
                        content = await resp.read()

            if not content:
                return "下载图片失败，文件内容为空。"

            # 检测图片类型
            try:
                with PILImage.open(io.BytesIO(content)) as img_obj:
                    file_type = img_obj.format.lower()
            except Exception as e:
                logger.error(f"图片格式检测失败: {str(e)}")
                file_type = "unknown"

            # 5. 保存前哈希计算
            raw_hash = hashlib.sha256(content).hexdigest()

        except Exception as e:
            logger.error(f"下载图片或检测格式失败: {e}", exc_info=True)
            return f"下载/解析图片失败：{str(e)}"

    # 6. 表情包收集偏好判定
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

    # 7. 标签/分类解析与判定
    resolved_categories = []
    invalid_categories = []
    valid_categories = set(sender.category_manager.get_categories())

    # A. 首先尝试解析显式传入的 categories 参数
    if categories:
        for category in categories:
            category = category.strip()
            if not category:
                continue
            if category in valid_categories:
                resolved_categories.append(category)
            else:
                # 允许作为自定义的新标签
                clean_cat = category.lower()
                if len(clean_cat) <= 20:
                    resolved_categories.append(clean_cat)
                else:
                    invalid_categories.append(category)

    # B. 如果解析后没有得到任何分类，且启用了多模态，则调用多模态模型自动分类
    multimodal_called = False
    multimodal_failed = False
    if not resolved_categories and getattr(sender, "multimodal_llm_enabled", False):
        provider_id = getattr(sender, "multimodal_llm_provider_id", "")
        if not provider_id:
            provider_id = await sender.context.get_current_chat_provider_id(
                umo=event.unified_msg_origin
            )
        if provider_id:
            multimodal_called = True
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
                '- 请仅以 JSON 数组格式返回，例如：["敷衍", "猫猫", "职场发疯"]\n'
                "不要返回任何其他内容（如 markdown 代码块标记、解释等），只返回 JSON 数组。"
            )

            try:
                logger.debug(f"正在调用多模态模型 {provider_id} 判定表情分类...")
                llm_resp = await sender.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    image_urls=[image_data_uri],
                )
                if llm_resp and llm_resp.completion_text:
                    raw_text = llm_resp.completion_text.strip()
                    logger.debug(f"多模态模型返回内容: {raw_text}")
                    data = None
                    try:
                        data = json.loads(raw_text)
                    except Exception:
                        match = re.search(r"\[\s*\"[\s\S]*\"\s*\]", raw_text)
                        if match:
                            try:
                                data = json.loads(match.group(0))
                            except Exception:
                                pass

                    parsed_categories = []
                    if isinstance(data, list):
                        parsed_categories = [str(x) for x in data]
                    else:
                        for cat in valid_categories:
                            if cat in raw_text:
                                parsed_categories.append(cat)

                    if parsed_categories:
                        logger.debug(f"多模态模型判定表情分类为: {parsed_categories}")
                        for cat in parsed_categories:
                            cat = cat.strip()
                            if cat in valid_categories:
                                resolved_categories.append(cat)
                            else:
                                # 允许作为自定义的新标签
                                clean_cat = cat.lower()
                                if len(clean_cat) <= 20:
                                    resolved_categories.append(clean_cat)
                                else:
                                    invalid_categories.append(cat)
                if not resolved_categories:
                    multimodal_failed = True
            except Exception as e:
                multimodal_failed = True
                logger.error(f"多模态模型分析图片分类失败: {e}", exc_info=True)

    # C. 最终校验
    if not resolved_categories:
        if multimodal_called and multimodal_failed:
            return "多模态模型判定表情分类失败，且未提供有效的分类名称。"
        elif invalid_categories:
            return f"无效的表情包分类 {invalid_categories}，当前可用的分类有：{', '.join(valid_categories)}"
        else:
            return "请输入至少一个有效的标签/分类名称。"

    # 8. 数据库排重及记录更新
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT filename, emotions, personas FROM memes WHERE original_hash = ?",
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

            cursor.execute(
                "UPDATE memes SET emotions = ?, personas = ? WHERE filename = ?",
                (
                    ",".join(existing_emotions),
                    ",".join(existing_personas),
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


async def auto_steal_meme(sender, event: AstrMessageEvent):
    """暗中自动偷表情包功能（被动监听群聊消息）"""
    # 1. 获取当前会话的人格 ID，并检查偏好设置
    persona_id = await get_persona_id(sender, event)
    persona_prompt = await get_persona_prompt(sender, event)

    pref_match = re.search(
        r"<meme_preference>(.*?)</meme_preference>",
        persona_prompt,
        re.DOTALL | re.IGNORECASE,
    )
    if not pref_match or not pref_match.group(1).strip():
        logger.debug(
            f"[meme_manager] 当前人格 {persona_id} 未配置表情包收集偏好，跳过自动偷表情。"
        )
        return

    # 2. 从消息中提取图片 URL
    last_image_url = None
    for comp in event.message_obj.message:
        if isinstance(comp, Reply) and comp.chain:
            for sub_comp in comp.chain:
                if isinstance(sub_comp, Image):
                    last_image_url = sub_comp.url
                    break
            if last_image_url:
                break

    if not last_image_url:
        images = [c for c in event.message_obj.message if isinstance(c, Image)]
        if images:
            last_image_url = images[-1].url

    if not last_image_url:
        return

    # 3. 下载图片并计算 hash
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        if "multimedia.nt.qq.com.cn" in last_image_url:
            insecure_url = last_image_url.replace("https://", "http://", 1)
            async with aiohttp.ClientSession() as session:
                async with session.get(insecure_url) as resp:
                    content = await resp.read()
        else:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_context)
            ) as session:
                async with session.get(last_image_url) as resp:
                    content = await resp.read()

        if not content:
            logger.warning("[meme_manager] 自动偷表情失败：下载图片内容为空")
            return

        try:
            with PILImage.open(io.BytesIO(content)) as img_obj:
                file_type = img_obj.format.lower()
        except Exception as e:
            logger.error(f"[meme_manager] 自动偷表情：图片格式检测失败: {str(e)}")
            file_type = "unknown"

        raw_hash = hashlib.sha256(content).hexdigest()

    except Exception as e:
        logger.error(
            f"[meme_manager] 自动偷表情：下载图片或解析格式失败: {e}", exc_info=True
        )
        return

    # 4. 判断是否被当前人格使用工具盗取/尝试过
    # A. 检查 attempts 表
    attempt = get_steal_attempt(raw_hash, persona_id)
    if attempt is not None:
        logger.debug(
            f"[meme_manager] 自动偷表情：图片 {raw_hash} 存在历史处理记录，跳过。"
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
    from .database import increment_image_seen_count

    min_seen = get_config_value(sender.config, "auto_steal_min_seen", 2)
    seen_count = increment_image_seen_count(raw_hash)
    if seen_count < min_seen:
        logger.info(
            f"[meme_manager] 自动偷表情：图片 {raw_hash} 全局第 {seen_count} 次被看见，未达到设定阈值 {min_seen}，仅记录次数并跳过偷图。"
        )
        return

    # 5. 调用原本的 steal_meme 工具流程进行盗取
    logger.info(
        f"[meme_manager] 自动偷表情：开始对图片 {raw_hash} 进行暗中收录判定 (已看见 {seen_count} 次)..."
    )
    try:
        result = await steal_meme(
            sender=sender,
            event=event,
            categories=None,
            image_content=content,
            image_hash=raw_hash,
            image_type=file_type,
        )
        logger.info(f"[meme_manager] 自动偷表情执行结果: {result}")
    except Exception as e:
        logger.error(f"[meme_manager] 自动偷表情执行失败: {e}", exc_info=True)
