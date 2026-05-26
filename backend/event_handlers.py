import json
import os
import random
import re
import tempfile
import time
import traceback

from PIL import Image as PILImage

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import LLMResponse
from astrbot.core.message.components import Image, Plain, Reply
from astrbot.core.message.message_event_result import MessageChain, ResultContentType

from ..config import MEMES_DIR


class EventHandlers:
    @staticmethod
    async def _get_persona_id(sender, event: AstrMessageEvent) -> str:
        """获取当前会话人格 ID，若为空或为 'default' 则降级查找配置文件中指定的人格"""
        persona_id = ""
        try:
            curr_cid = (
                await sender.context.conversation_manager.get_curr_conversation_id(
                    event.unified_msg_origin
                )
            )
            if curr_cid:
                conv = await sender.context.conversation_manager.get_conversation(
                    event.unified_msg_origin, curr_cid
                )
                if conv:
                    persona_id = conv.persona_id or ""
        except Exception as e:
            logger.warning(f"获取当前会话人格失败: {e}")

        if not persona_id or persona_id == "default":
            try:
                cfg = sender.context.get_config(event.unified_msg_origin)
                persona_id = cfg.get("provider_settings", {}).get(
                    "default_personality",
                    "default",
                )
            except Exception:
                persona_id = "default"

        if not persona_id:
            persona_id = "default"

        return persona_id

    @staticmethod
    async def _select_memes_by_emotions_priority(
        sender, found_emotions: list[str], persona_id: str
    ) -> list[str]:
        """根据情绪标签的重合度优先级筛选并随机推荐表情包图片。

        优先返回满足更多情绪标签的表情图片。
        """
        if not found_emotions:
            return []

        from .database import get_db_conn

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
                matched_count = sum(1 for e in found_emotions if e in meme_emotions)
                
                # 偏置评分：越靠前的标签越优先
                position_bonus = 0
                for idx, e in enumerate(found_emotions):
                    if e in meme_emotions:
                        position_bonus += max(0, 100 - idx)
                
                score = matched_count * 1000 + position_bonus
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

    @staticmethod
    async def resp(sender, event: AstrMessageEvent, response: LLMResponse):
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
                    if EventHandlers._is_likely_emotion_markup(
                        original, clean_text, match.start()
                    ):
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
                        if EventHandlers._is_position_in_thinking_tags(
                            clean_text, match.start()
                        ):
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
                            if EventHandlers._is_position_in_thinking_tags(
                                clean_text, match.start()
                            ):
                                continue
                            original = match.group(0)
                            clean_text = clean_text.replace(original, "", 1)
                            sender.found_emotions.append(emotion)
                            repeated_emotions.append(emotion)

        logger.debug(
            f"[meme_manager] 第三阶段重复检测阶段找到的表情: {repeated_emotions}"
        )

        # 第四阶段：智能识别可能的表情（松散模式）
        loose_emotions = []
        if sender.config.get("enable_loose_emotion_matching", True):
            for emotion in valid_emoticons:
                pattern = r"\b(" + re.escape(emotion) + r")\b"
                for match in re.finditer(pattern, clean_text):
                    word = match.group(1)
                    position = match.start()

                    if EventHandlers._is_position_in_thinking_tags(
                        clean_text, position
                    ):
                        continue

                    if EventHandlers._is_likely_emotion(
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
                    logger.debug(
                        f"[meme_manager] 情感模型准备调用。模型 ID: {provider_id}"
                    )
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
                            elif (
                                isinstance(emotions, str)
                                and emotions in valid_emoticons
                            ):
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

        sender.found_emotions = filtered_emotions
        logger.info(
            f"[meme_manager] 去重后的最终表情标签列表: {sender.found_emotions}"
        )

        clean_text = re.sub(r"&&+", "", clean_text)
        response.completion_text = clean_text.strip()

    @staticmethod
    async def on_decorating_result(sender, event: AstrMessageEvent):
        """在消息发送前清理文本中的表情标签，并根据人格匹配合适表情"""
        logger.debug(
            f"[meme_manager] 进入消息装饰阶段。当前待发送表情列表: {sender.found_emotions}"
        )

        result = event.get_result()
        if not result:
            logger.debug("[meme_manager] event.get_result() 为空，结束处理。")
            return

        if result.result_content_type == ResultContentType.STREAMING_FINISH:
            if sender.streaming_compatibility:
                logger.debug(
                    "[meme_manager] 检测到流式传输完成事件，调用 _send_memes_streaming"
                )
                await EventHandlers._send_memes_streaming(sender, event)
            return

        try:
            original_chain = result.chain
            cleaned_components = []

            if original_chain:
                if isinstance(original_chain, str):
                    cleaned = (
                        re.sub(sender.content_cleanup_rule, "", original_chain)
                        if sender.content_cleanup_rule
                        else original_chain
                    )
                    if cleaned.strip():
                        cleaned_components.append(Plain(cleaned.strip()))

                elif isinstance(original_chain, MessageChain):
                    for component in original_chain.chain:
                        if isinstance(component, Plain):
                            cleaned = (
                                re.sub(sender.content_cleanup_rule, "", component.text)
                                if sender.content_cleanup_rule
                                else component.text
                            )
            if sender.found_emotions:
                random_value = random.randint(1, 100)
                threshold = sender.emotions_probability
                logger.debug(
                    f"[meme_manager] 触发表情概率判断。设定概率: {threshold}%, 本次随机数: {random_value}"
                )

                if random_value <= threshold:
                    # 获取当前人格 ID
                    persona_id = await EventHandlers._get_persona_id(sender, event)
                    logger.debug(f"[meme_manager] 当前会话人格 ID: '{persona_id}'")
                    emotion_images = []
                    temp_files = []

                    selected_memes = (
                        await EventHandlers._select_memes_by_emotions_priority(
                            sender, sender.found_emotions, persona_id
                        )
                    )

                    for meme in selected_memes:
                        meme_file = os.path.join(MEMES_DIR, meme)
                        logger.debug(
                            f"[meme_manager] 随机选中表情图片 (重合度得分): {meme_file}"
                        )

                        try:
                            final_meme_file = EventHandlers._convert_to_gif(
                                meme_file, sender
                            )
                            if final_meme_file != meme_file:
                                temp_files.append(final_meme_file)
                            emotion_images.append(Image.fromFileSystem(final_meme_file))
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

                        use_mixed_message = False
                        if sender.enable_mixed_message:
                            use_mixed_message = (
                                random.randint(1, 100)
                                <= sender.mixed_message_probability
                            )

                        logger.debug(
                            f"[meme_manager] 成功加载 {len(emotion_images)} 张表情图片。是否混合发送: {use_mixed_message}"
                        )

                        if use_mixed_message:
                            cleaned_components = (
                                EventHandlers._merge_components_with_images(
                                    sender, cleaned_components, emotion_images
                                )
                            )
                        else:
                            event.set_extra(
                                "meme_manager_pending_images", emotion_images
                            )
                    else:
                        logger.debug("[meme_manager] 未匹配到任何可发送的表情图片")
                else:
                    logger.debug(
                        "[meme_manager] 随机数大于设定发送概率，跳过发送表情包。"
                    )

                sender.found_emotions = []

            if cleaned_components:
                result.chain = cleaned_components
            elif original_chain:
                if isinstance(original_chain, str):
                    final_cleaned = re.sub(r"&&+", "", original_chain)
                    if final_cleaned.strip():
                        result.chain = [Plain(final_cleaned.strip())]
                elif isinstance(original_chain, MessageChain):
                    final_components = []
                    for component in original_chain.chain:
                        if isinstance(component, Plain):
                            final_cleaned = re.sub(r"&&+", "", component.text)
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

    @staticmethod
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
                            logger.debug(
                                f"[meme_manager] 已成功清理临时文件: {temp_file}"
                            )
                    except Exception as e:
                        logger.error(f"[meme_manager] 清理临时文件失败: {e}")
                event.set_extra("meme_manager_temp_files", None)

    @staticmethod
    async def handle_upload_image(sender, event: AstrMessageEvent):
        """处理用户上传的图片"""
        user_key = f"{event.session_id}_{event.get_sender_id()}"
        upload_state = sender.upload_states.get(user_key)

        if not upload_state or time.time() > upload_state["expire_time"]:
            if user_key in sender.upload_states:
                del sender.upload_states[user_key]
            return

        images = [c for c in event.message_obj.message if isinstance(c, Image)]

        if not images:
            yield event.plain_result("请发送图片文件来进行上传哦。")
            return

        category = upload_state["category"]

        try:
            saved_files = []

            # 创建忽略 SSL 验证的上下文
            import io
            import ssl

            import aiohttp

            from .models import save_and_register_meme

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            for idx, img in enumerate(images, 1):
                timestamp = int(time.time())

                try:
                    if "multimedia.nt.qq.com.cn" in img.url:
                        insecure_url = img.url.replace("https://", "http://", 1)
                        logger.warning(
                            f"检测到腾讯多媒体域名，使用 HTTP 协议下载: {insecure_url}"
                        )
                        async with aiohttp.ClientSession() as session:
                            async with session.get(insecure_url) as resp:
                                content = await resp.read()
                    else:
                        async with aiohttp.ClientSession(
                            connector=aiohttp.TCPConnector(ssl=ssl_context)
                        ) as session:
                            async with session.get(img.url) as resp:
                                content = await resp.read()

                    try:
                        with PILImage.open(io.BytesIO(content)) as img_obj:
                            file_type = img_obj.format.lower()
                    except Exception as e:
                        logger.error(f"图片格式检测失败: {str(e)}")
                        file_type = "unknown"

                    ext_mapping = {
                        "jpeg": ".jpg",
                        "png": ".png",
                        "gif": ".gif",
                        "webp": ".webp",
                    }
                    ext = ext_mapping.get(file_type, ".jpg")
                    filename = f"{timestamp}_{idx}{ext}"

                    res = save_and_register_meme(
                        image_bytes=content,
                        filename=filename,
                        category=category,
                        personas="*",
                        config=sender.config,
                    )
                    saved_files.append(res["filename"])

                except Exception as e:
                    logger.error(f"下载图片失败: {str(e)}")
                    yield event.plain_result(f"文件 {img.url} 下载失败啦: {str(e)}")
                    continue

            if user_key in sender.upload_states:
                del sender.upload_states[user_key]

            result_msg = [
                Plain(
                    f"✅ 已经成功收录了 {len(saved_files)} 张新表情到「{category}」图库！"
                )
            ]

            yield event.chain_result(result_msg)
            await sender.reload_emotions()

        except Exception as e:
            yield event.plain_result(f"保存失败了：{str(e)}")

    @staticmethod
    async def steal_meme(sender, event: AstrMessageEvent, categories: list[str]):
        """保存并收录上一条聊天记录中发送的表情包到当前人格的表情包库中。

        Args:
            categories(list): 对应的表情包类别/情绪分类名称列表（如 ["happy", "sad"] 等）
        """
        # 1. 从当前事件消息中提取图片（优先支持引用/回复图片，其次支持同消息内直发图片）
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

        if not last_image_url:
            return "没有在当前消息或引用的回复中找到可以收录的表情包/图片哦。请发送图片并在消息中说明，或者直接引用（回复）要收录的图片并发出指令。"

        # 2. 检查分类是否合法（如果未启用多模态判定，且 categories 为空，则报错）
        if not getattr(sender, "multimodal_llm_enabled", False) and not categories:
            return "请输入至少一个有效的标签/分类名称。"

        # 3. 获取当前会话的人格 ID (persona_id)
        persona_id = await EventHandlers._get_persona_id(sender, event)

        # 4. 下载图片
        import hashlib
        import io
        import ssl

        import aiohttp

        from .models import save_and_register_meme

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

            # 5. 保存前哈希计算与判重
            raw_hash = hashlib.sha256(content).hexdigest()

            # 6. 标签/分类解析与判定
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
            if not resolved_categories and getattr(
                sender, "multimodal_llm_enabled", False
            ):
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

                    existing_tags = sender.category_manager.get_categories()
                    prompt = (
                        "请对这张图片进行视觉分析，并生成 1-2 个最契合此图的表情包分类标签。\n"
                        "【已有标签列表】：\n"
                    )
                    for cat in sorted(existing_tags):
                        prompt += f"- {cat}\n"
                    prompt += (
                        "\n【标签生成规则（极其重要）】：\n"
                        "1. 标签设计维度：表情包标签应围绕以下两类来定义：\n"
                        "   - 情绪/情感：如 喜、怒、哀、乐、傲娇、委屈、得意、困惑、无语 等。\n"
                        "   - 行为/场景/事物：如 吃喝、睡觉、抢红包、奶茶、吃瓜、打游戏 等。\n"
                        "2. 优先匹配已有标签：你必须首选并复用【已有标签列表】中语义最接近的标签。\n"
                        "3. 绝对禁止生成同义/近义新标签（防止标签库膨胀与碎片化）：\n"
                        "   - 在生成新标签之前，请仔细比对它与已有标签的语义。如果已有标签能表达相同或极为相似的意思，必须强制复用已有标签。例如：若已有 'happy'，禁止生成 '开心'、'快乐' 或 '高兴'；若已有 '红包'，禁止生成 '抢红包' 或 '发红包'。\n"
                        "4. 支持与首选中文标签：我们全面支持中文标签。对于一些富有特色、不易用英文单词贴切表达的概念（如 奶茶、红包、吃瓜、贴贴、摸头 等）或标准中文情感词汇，请优先生成中文标签；其他通用英文标签亦可复用或生成（如 happy, sad, work, sleep）。\n"
                        "5. 只有在已有标签列表中完全没有任何语义极度沾边的标签时，才允许生成新的简短中文或英文标签。\n"
                        '6. 请仅以 JSON 数组格式返回，例如：["happy", "奶茶"]\n'
                        "不要返回任何其他内容（如 markdown 代码块标记、解释等），只返回 JSON 数组。"
                    )

                    try:
                        logger.debug(
                            f"正在调用多模态模型 {provider_id} 判定表情分类..."
                        )
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
                                for cat in existing_tags:
                                    if cat in raw_text:
                                        parsed_categories.append(cat)

                            if parsed_categories:
                                logger.debug(
                                    f"多模态模型判定表情分类为: {parsed_categories}"
                                )
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

            # 7. 数据库排重及记录更新
            from .database import get_db_conn

            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT filename, emotions, personas FROM memes WHERE original_hash = ?",
                (raw_hash,),
            )
            row = cursor.fetchone()

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

            invalid_tip = (
                f"（忽略了无效的标签 {invalid_categories}）"
                if invalid_categories
                else ""
            )

            sync_tip = ""
            if sender.img_sync:
                sync_tip = "\n☁️ 检测到已配置图床，如需同步到云端请使用命令：同步到云端"

            await sender.reload_emotions()

            return f"成功收录表情包「{res['filename']}」到标签【{', '.join(resolved_categories)}】中，且仅供人格【{persona_id}】使用。{invalid_tip}{sync_tip}"

        except Exception as e:
            logger.error(f"偷表情包失败: {e}", exc_info=True)
            return f"偷表情包失败：{str(e)}"

    @staticmethod
    def _is_likely_emotion_markup(markup, text, position):
        before_text = text[:position].strip()
        after_text = text[position + len(markup) :].strip()

        has_chinese_before = bool(
            re.search(r"[\u4e00-\u9fff]", before_text[-1:] if before_text else "")
        )
        has_chinese_after = bool(
            re.search(r"[\u4e00-\u9fff]", after_text[:1] if after_text else "")
        )
        if has_chinese_before or has_chinese_after:
            return True

        if re.match(r"\[\d+\]", markup):
            return False

        if " " in markup[1:-1]:
            return False

        return True

    @staticmethod
    def _is_likely_emotion(word, text, position, valid_emotions, sender):
        before_text = text[:position].strip()
        after_text = text[position + len(word) :].strip()

        english_context_before = bool(re.search(r"[a-zA-Z]$", before_text))
        english_context_after = bool(re.search(r"^[a-zA-Z]", after_text))

        if english_context_before or english_context_after:
            return False

        has_chinese_before = bool(
            re.search(r"[\u4e00-\u9fff]", before_text[-1:] if before_text else "")
        )
        has_chinese_after = bool(
            re.search(r"[\u4e00-\u9fff]", after_text[:1] if after_text else "")
        )

        if has_chinese_before or has_chinese_after:
            return True

        if not before_text or before_text.endswith(
            ("。", "，", "！", "？", ".", ",", ":", ";", "!", "?", "\n")
        ):
            return True

        if (not before_text or before_text[-1] in " \t\n.,!?;:'\"()[]{}") and (
            not after_text or after_text[0] in " \t\n.,!?;:'\"()[]{}"
        ):
            return True

        if word in sender.config.get("high_confidence_emotions", []):
            return True

        return False

    @staticmethod
    def _convert_to_gif(image_path: str, sender) -> str:
        if not sender.convert_static_to_gif:
            return image_path

        if image_path.lower().endswith(".gif"):
            return image_path

        try:
            with PILImage.open(image_path) as img:
                if img.format == "GIF":
                    return image_path

                temp_dir = tempfile.gettempdir()
                temp_filename = os.path.join(
                    temp_dir,
                    f"meme_{int(time.time())}_{random.randint(1000, 9999)}.gif",
                )

                if img.mode in ("RGBA", "LA") or (
                    img.mode == "P" and "transparency" in img.info
                ):
                    background = PILImage.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert("RGB")

                img.save(temp_filename, "GIF")
                logger.debug(f"[meme_manager] 已将静态图转换为 GIF: {temp_filename}")
                return temp_filename
        except Exception as e:
            logger.error(f"转换图片为 GIF 失败: {e}", exc_info=True)
            return image_path

    @staticmethod
    def _is_position_in_thinking_tags(text: str, position: int) -> bool:
        """检查指定位置是否在thinking标签内"""
        thinking_pattern = re.compile(
            r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE
        )

        for match in thinking_pattern.finditer(text):
            if match.start() <= position < match.end():
                return True
        return False

    @staticmethod
    async def _send_memes_streaming(sender, event: AstrMessageEvent):
        """流式传输兼容模式：在流式消息发送完成后，主动发送表情图片作为独立消息。"""
        if not sender.found_emotions:
            return

        try:
            random_value = random.randint(1, 100)
            if random_value > sender.emotions_probability:
                return

            persona_id = await EventHandlers._get_persona_id(sender, event)
            selected_memes = await EventHandlers._select_memes_by_emotions_priority(
                sender, sender.found_emotions, persona_id
            )

            for meme in selected_memes:
                meme_file = os.path.join(MEMES_DIR, meme)
                logger.debug(
                    f"[meme_manager] 流式模式选中表情图片 (重合度得分): {meme_file}"
                )
                final_meme_file = EventHandlers._convert_to_gif(meme_file, sender)

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

    @staticmethod
    def _merge_components_with_images(sender, components, images):
        """将表情图片与文本组件智能配对，支持分段回复"""
        logger.debug(
            f"[meme_manager] _merge_components_with_images 输入: 组件总数={len(components)}, 图片总数={len(images)}"
        )

        if not images:
            return components

        if not components:
            return images

        plain_indices = [
            i for i, comp in enumerate(components) if isinstance(comp, Plain)
        ]
        logger.debug(f"[meme_manager] Plain 组件的索引位置列表: {plain_indices}")

        if not plain_indices:
            return components + images

        merged_components = components.copy()
        images_per_text = max(1, len(images) // len(plain_indices))
        image_index = 0
        images_inserted_so_far = 0

        for idx, plain_idx in enumerate(plain_indices):
            if image_index >= len(images):
                break

            if idx == len(plain_indices) - 1:
                images_for_this_text = len(images) - image_index
            else:
                images_for_this_text = min(images_per_text, len(images) - image_index)

            logger.debug(
                f"[meme_manager] Plain 组件 {idx} (索引={plain_idx}) 分配的图片数量: {images_for_this_text}"
            )

            insert_pos = plain_idx + 1 + images_inserted_so_far

            for _ in range(images_for_this_text):
                if image_index < len(images):
                    merged_components.insert(insert_pos, images[image_index])
                    image_index += 1
                    insert_pos += 1
                    images_inserted_so_far += 1

        logger.debug(
            f"[meme_manager] 合并前组件总数: {len(components)}, 合并后组件总数: {len(merged_components)}"
        )

        return merged_components
