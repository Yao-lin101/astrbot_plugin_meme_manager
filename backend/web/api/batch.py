import logging

from quart import current_app, jsonify, request

from ...db.database import get_db_conn
from ...db.models import (
    batch_convert_to_gif,
    batch_copy_emojis,
    batch_delete_emojis,
    batch_move_emojis,
    move_emoji_to_category,
)

logger = logging.getLogger(__name__)


async def batch_delete_emoji():
    """批量删除指定类别的表情包"""
    data = await request.get_json()
    category = data.get("category")
    image_files = data.get("image_files")

    if not category or not isinstance(image_files, list) or not image_files:
        return jsonify({"message": "Category and image_files are required"}), 400

    result = batch_delete_emojis(category, image_files)
    if not result["category_exists"]:
        return jsonify({"message": "Category not found"}), 404

    deleted_files = result["deleted_files"]
    missing_files = result["missing_files"]
    return jsonify(
        {
            "message": "Batch delete completed",
            "category": category,
            "deleted_files": deleted_files,
            "missing_files": missing_files,
            "deleted_count": len(deleted_files),
            "missing_count": len(missing_files),
        }
    ), 200


async def batch_convert_emoji_gif():
    """批量将表情文件转换为 GIF 格式"""
    data = await request.get_json()
    filenames = data.get("filenames")

    if not isinstance(filenames, list) or not filenames:
        return jsonify({"message": "filenames list is required"}), 400

    result = batch_convert_to_gif(filenames)
    return jsonify(result), 200


async def move_emoji():
    """移动单个表情包到指定类别。"""
    data = await request.get_json()
    source_category = data.get("source_category")
    target_category = data.get("target_category")
    image_file = data.get("image_file")

    if not source_category or not target_category or not image_file:
        return (
            jsonify(
                {
                    "message": "source_category, target_category and image_file are required"
                }
            ),
            400,
        )

    if source_category == target_category:
        return jsonify({"message": "Source and target category must be different"}), 400

    result = move_emoji_to_category(source_category, image_file, target_category)
    if not result["source_category_exists"]:
        return jsonify({"message": "Source category not found"}), 404
    if result["conflict"]:
        return jsonify({"message": "Target file already exists"}), 409
    if result["missing"]:
        return jsonify({"message": "Emoji not found"}), 404

    return jsonify(
        {
            "message": "Emoji moved successfully",
            "source_category": result["source_category"],
            "target_category": result["target_category"],
            "filename": result["filename"],
        }
    ), 200


async def batch_move_emoji():
    """批量移动指定类别的表情包到另一个类别。"""
    data = await request.get_json()
    source_category = data.get("source_category")
    target_category = data.get("target_category")
    image_files = data.get("image_files")

    if (
        not source_category
        or not target_category
        or not isinstance(image_files, list)
        or not image_files
    ):
        return (
            jsonify(
                {
                    "message": "source_category, target_category and image_files are required"
                }
            ),
            400,
        )

    if source_category == target_category:
        return jsonify({"message": "Source and target category must be different"}), 400

    result = batch_move_emojis(source_category, image_files, target_category)
    if not result["source_category_exists"]:
        return jsonify({"message": "Source category not found"}), 404

    moved_files = result["moved_files"]
    missing_files = result["missing_files"]
    conflicting_files = result["conflicting_files"]
    return jsonify(
        {
            "message": "Batch move completed",
            "source_category": source_category,
            "target_category": target_category,
            "moved_files": moved_files,
            "missing_files": missing_files,
            "conflicting_files": conflicting_files,
            "moved_count": len(moved_files),
            "missing_count": len(missing_files),
            "conflict_count": len(conflicting_files),
        }
    ), 200


async def batch_copy_emoji():
    """批量复制指定类别的表情包到另一个类别。"""
    data = await request.get_json()
    source_category = data.get("source_category")
    target_category = data.get("target_category")
    image_files = data.get("image_files")

    if (
        not source_category
        or not target_category
        or not isinstance(image_files, list)
        or not image_files
    ):
        return (
            jsonify(
                {
                    "message": "source_category, target_category and image_files are required"
                }
            ),
            400,
        )

    result = batch_copy_emojis(source_category, image_files, target_category)
    if not result["source_category_exists"]:
        return jsonify({"message": "Source category not found"}), 404

    copied_files = result["copied_files"]
    missing_files = result["missing_files"]
    conflicting_files = result["conflicting_files"]
    return jsonify(
        {
            "message": "Batch copy completed",
            "source_category": source_category,
            "target_category": target_category,
            "copied_files": copied_files,
            "missing_files": missing_files,
            "conflicting_files": conflicting_files,
            "copied_count": len(copied_files),
            "missing_count": len(missing_files),
            "conflict_count": len(conflicting_files),
        }
    ), 200


async def batch_edit_personas():
    """批量修改表情包允许的人格"""
    try:
        data = await request.get_json()
        filenames = data.get("filenames")
        personas = data.get("personas")  # List of persona IDs, or ["*"]

        if not isinstance(filenames, list) or not filenames:
            return jsonify({"message": "filenames list is required"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        personas_str = ",".join(personas) if isinstance(personas, list) else personas

        for filename in filenames:
            cursor.execute(
                "UPDATE memes SET personas = ? WHERE filename = ?",
                (personas_str, filename),
            )
        conn.commit()
        conn.close()

        return jsonify({"message": "Batch personas updated successfully"}), 200
    except Exception as e:
        logger.error(f"批量更新人格限制失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


async def batch_import_emojis():
    """批量导入已存在的表情包到指定类别（为选中的表情包文件追加该类别标签）"""
    try:
        data = await request.get_json()
        category = data.get("category")
        filenames = data.get("filenames")

        if not category or not isinstance(filenames, list) or not filenames:
            return jsonify({"message": "Category and filenames list are required"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        # 遍历更新每个表情包的 emotions 字段
        for filename in filenames:
            cursor.execute("SELECT emotions FROM memes WHERE filename = ?", (filename,))
            row = cursor.fetchone()
            if row:
                existing_emotions = (
                    set(row["emotions"].split(",")) if row["emotions"] else set()
                )
                existing_emotions.add(category)
                cursor.execute(
                    "UPDATE memes SET emotions = ? WHERE filename = ?",
                    (",".join(existing_emotions), filename),
                )
        conn.commit()
        conn.close()

        # 重新加载类别
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            category_manager.sync_with_filesystem()

        return (
            jsonify(
                {
                    "message": "Batch import completed successfully",
                    "count": len(filenames),
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"批量导入表情包失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


# 全局批量分析状态
batch_analyze_status = {
    "status": "idle",  # "idle", "running", "completed"
    "total": 0,
    "current_index": 0,
    "current_file": "",
    "results": [],
}
# 取消信号
cancel_batch_analyze_flag = False
active_analyze_task = None


async def get_providers():
    """获取所有可用的 LLM 提供商 (Chat Completion)"""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        context = plugin_config.get("context")
        if context:
            providers = context.get_all_providers()
            result = []
            for p in providers:
                meta = p.meta()
                result.append(
                    {
                        "id": meta.id,
                        "name": getattr(p, "name", meta.id) or meta.id,
                    }
                )
            return jsonify(result), 200
        return jsonify([]), 200
    except Exception as e:
        logger.error(f"获取提供商列表失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


async def get_prompt_template():
    """Get the meme analysis prompt template split into intro, tags, and desc."""
    try:
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        sender = plugin_config.get("sender")
        user_prompt = ""
        if sender:
            user_prompt = (
                sender.config.get("multimodal_config", {})
                .get("multimodal_tag_prompt", "")
                .strip()
            )

        # Default prompt fallback if not configured
        if not user_prompt:
            user_prompt = (
                "你是一个专业的表情包内容分析师，需要全面分析表情包的各个维度，重点识别角色来源、作品归属和物品特征，为用户提供详细、准确、实用的信息。\n"
                "标签策略（重点优化）：\n"
                "- 标签数量：4-6个精选标签，避免冗余\n"
                "- 标签优先级（从高到低）：\n"
                '  * 角色/作品标签（最高优先级）：如果能识别角色或作品，必须包含。如"派蒙"、"原神"、"海绵宝宝"、"柴犬"\n'
                '  * 物品/主体标签（高优先级）：描述表情包的主体是什么。如"猫"、"狗"、"食物"、"机器人"\n'
                '  * 情感/表情标签（中优先级）：描述表情包表达的情感。如"开心"、"无语"、"生气"、"摆烂"、"震惊"\n'
                '  * 动作/状态标签（中优先级）：描述角色或物品的动作。如"奔跑"、"吃东西"、"睡觉"、"跳舞"\n'
                '  * 风格/形式标签（低优先级）：如"二次元"、"像素风"、"真人"、"手绘"\n'
                "- 标签质量：\n"
                "  * 使用通俗易懂的词汇\n"
                "  * 考虑用户搜索习惯与词汇偏好\n"
                "  * 平衡具体性与通用性\n"
                "  * 避免过于专业或生僻的术语\n\n"
                "描述：\n根据画面和标签结果进行简洁描述。"
            )

        intro = "你是一个专业的表情包内容分析师，需要全面分析表情包的各个维度，重点识别角色来源、作品归属和物品特征，为用户提供详细、准确、实用的信息。"
        tags = (
            "标签策略（重点优化）：\n"
            "- 标签数量：4-6个精选标签，避免冗余\n"
            "- 标签优先级（从高到低）：\n"
            '  * 角色/作品标签（最高优先级）：如果能识别角色或作品，必须包含。如"派蒙"、"原神"、"海绵宝宝"、"柴犬"\n'
            '  * 物品/主体标签（高优先级）：描述表情包的主体是什么。如"猫"、"狗"、"食物"、"机器人"\n'
            '  * 情感/表情标签（中优先级）：描述表情包表达的情感。如"开心"、"无语"、"生气"、"摆烂"、"震惊"\n'
            '  * 动作/状态标签（中优先级）：描述角色或物品的动作。如"奔跑"、"吃东西"、"睡觉"、"跳舞"\n'
            '  * 风格/形式标签（低优先级）：如"二次元"、"像素风"、"真人"、"手绘"\n'
            "- 标签质量：\n"
            "  * 使用通俗易懂的词汇\n"
            "  * 考虑用户搜索习惯与词汇偏好\n"
            "  * 平衡具体性与通用性\n"
            "  * 避免过于专业或生僻的术语"
        )
        desc = "描述：\n根据画面和标签结果进行简洁描述。"

        # Parse user prompt into three parts
        tag_idx = user_prompt.find("标签策略")
        desc_idx = user_prompt.find("描述")
        if tag_idx != -1 and desc_idx != -1:
            if tag_idx < desc_idx:
                intro = user_prompt[:tag_idx].strip()
                tags = user_prompt[tag_idx:desc_idx].strip()
                desc = user_prompt[desc_idx:].strip()
            else:
                intro = user_prompt[:desc_idx].strip()
                desc = user_prompt[desc_idx:tag_idx].strip()
                tags = user_prompt[tag_idx:].strip()

        return (
            jsonify({"intro": intro, "tags": tags, "desc": desc}),
            200,
        )
    except Exception as e:
        logger.error(f"获取提示词模板失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


async def batch_analyze_emojis():
    """Trigger the batch analysis task."""
    global batch_analyze_status, cancel_batch_analyze_flag, active_analyze_task
    if batch_analyze_status["status"] == "running":
        return jsonify({"message": "批量分析任务已在运行中"}), 400

    data = await request.get_json()
    filenames = data.get("filenames")
    provider_id = data.get("provider_id")
    analyze_tags = data.get("analyze_tags", True)
    analyze_description = data.get("analyze_description", True)
    pass_existing_tags_as_ref = data.get("pass_existing_tags_as_ref", False)
    prompt_content = data.get("prompt_content", "")

    if not isinstance(filenames, list) or not filenames:
        return jsonify({"message": "filenames 列表是必需的"}), 400
    if not provider_id:
        return jsonify({"message": "provider_id 是必需的"}), 400

    plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
    sender = plugin_config.get("sender")
    if not sender:
        return jsonify({"message": "未找到插件 Sender"}), 500

    cancel_batch_analyze_flag = False
    batch_analyze_status = {
        "status": "running",
        "total": len(filenames),
        "current_index": 0,
        "current_file": "",
        "results": [],
    }

    # Start the background task as an asyncio.Task to support instant cancellation
    import asyncio
    loop = asyncio.get_running_loop()
    active_analyze_task = loop.create_task(
        run_batch_analyze_task(
            filenames,
            provider_id,
            analyze_tags,
            analyze_description,
            pass_existing_tags_as_ref,
            prompt_content,
            sender,
        )
    )

    return jsonify({"message": "批量分析任务已启动"}), 200


async def get_batch_analyze_status():
    """获取批量分析任务的状态和结果"""
    global batch_analyze_status
    return jsonify(batch_analyze_status), 200


async def cancel_batch_analyze():
    """取消当前的批量分析任务"""
    global cancel_batch_analyze_flag, batch_analyze_status, active_analyze_task
    if batch_analyze_status["status"] == "running":
        cancel_batch_analyze_flag = True
        if active_analyze_task and not active_analyze_task.done():
            active_analyze_task.cancel()
        return jsonify({"message": "已发送取消信号并中止当前请求"}), 200
    return jsonify({"message": "当前没有正在运行的任务"}), 200


async def run_batch_analyze_task(
    filenames,
    provider_id,
    analyze_tags,
    analyze_description,
    pass_existing_tags_as_ref,
    prompt_content,
    sender,
):
    """后台批量分析执行函数"""
    global batch_analyze_status, cancel_batch_analyze_flag
    import asyncio
    import base64
    import io
    import json
    import os
    import re

    from PIL import Image as PILImage

    from ....config import MEMES_DIR
    from ...db.database import get_db_conn
    from .common import trigger_tag_vectorization

    # 在一开始，先将所有文件状态置为等待中
    batch_analyze_status["results"] = [
        {
            "filename": filename,
            "status": "waiting",
            "tags": [],
            "description": "",
        }
        for filename in filenames
    ]

    try:
        for idx, filename in enumerate(filenames):
            if cancel_batch_analyze_flag:
                logger.info("批量分析表情包任务被用户取消。")
                # 将后续等待中的更新为已取消/失败
                for r in batch_analyze_status["results"]:
                    if r["status"] == "waiting":
                        r["status"] = "error"
                        r["error"] = "任务已被取消"
                break

            batch_analyze_status["current_index"] = idx + 1
            batch_analyze_status["current_file"] = filename

            # 更新当前文件的状态为分析中
            r_item = batch_analyze_status["results"][idx]
            r_item["status"] = "running"

            try:
                file_path = os.path.join(MEMES_DIR, filename)
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"文件不存在: {filename}")

                with open(file_path, "rb") as f:
                    content = f.read()

                try:
                    with PILImage.open(io.BytesIO(content)) as img_obj:
                        file_type = img_obj.format.lower()
                except Exception:
                    file_type = "unknown"

                mime_type = "image/jpeg"
                if file_type == "png":
                    mime_type = "image/png"
                elif file_type == "gif":
                    mime_type = "image/gif"
                elif file_type == "webp":
                    mime_type = "image/webp"

                b64_data = base64.b64encode(content).decode("utf-8")
                image_data_uri = f"data:{mime_type};base64,{b64_data}"

                # 查询现有数据，以便进行参考及后续的部分更新
                conn = get_db_conn()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT emotions, description FROM memes WHERE filename = ?",
                    (filename,),
                )
                db_row = cursor.fetchone()
                conn.close()

                if db_row:
                    existing_emotions = db_row["emotions"] or ""
                    existing_desc = db_row["description"] or ""
                else:
                    existing_emotions = ""
                    existing_desc = ""

                guidelines = prompt_content
                if not guidelines:
                    config_prompt = ""
                    if hasattr(sender, "config"):
                        config_prompt = (
                            sender.config.get("multimodal_config", {})
                            .get("multimodal_tag_prompt", "")
                            .strip()
                        )
                    guidelines = config_prompt if config_prompt else getattr(sender, "multimodal_tag_prompt", None)
                    if not guidelines:
                        guidelines = (
                            "你是一个专业的表情包内容分析师，需要全面分析表情包的各个维度，重点识别角色来源、作品归属和物品特征，为用户提供详细、准确、实用的信息。\n"
                            "标签策略（重点优化）：\n"
                            "- 标签数量：4-6个精选标签，避免冗余\n"
                            "- 标签优先级（从高到低）：\n"
                            '  * 角色/作品标签（最高优先级）：如果能识别角色或作品，必须包含。如"派蒙"、"原神"、"海绵宝宝"、"柴犬"\n'
                            '  * 物品/主体标签（高优先级）：描述表情包的主体是什么。如"猫"、"狗"、"食物"、"机器人"\n'
                            '  * 情感/表情标签（中优先级）：描述表情包表达的情感。如"开心"、"无语"、"生气"、"摆烂"、"震惊"\n'
                            '  * 动作/状态标签（中优先级）：描述角色或物品的动作。如"奔跑"、"吃东西"、"睡觉"、"跳舞"\n'
                            '  * 风格/形式标签（低优先级）：如"二次元"、"像素风"、"真人"、"手绘"\n'
                            "- 标签质量：\n"
                            "  * 使用通俗易懂的词汇\n"
                            "  * 考虑用户搜索习惯与词汇偏好\n"
                            "  * 平衡具体性与通用性\n"
                            "  * 避免过于专业或生僻的术语\n\n"
                            "描述：\n根据画面和标签结果进行简洁描述。"
                        )

                if pass_existing_tags_as_ref and not analyze_tags and existing_emotions:
                    guidelines = (
                        f"{guidelines}\n\n"
                        f"【该表情包当前已有的标签】：{existing_emotions}\n"
                        f"请结合并参考这些已有标签的语境，为您生成的描述提供辅助参考。"
                    )

                # 根据勾选条件，优化模型提示词
                target_str = []
                if analyze_tags:
                    target_str.append("tags (数组，表情包对应的标签列表)")
                if analyze_description:
                    target_str.append("description (字符串，对这张表情包画面的简洁描述)")

                prompt = (
                    f"{guidelines}\n\n"
                    f"【输出格式要求（极其重要）】：\n"
                    f"- 请仅以 JSON 格式的字典对象返回，其中必须包含以下字段：\n"
                )
                if analyze_tags:
                    prompt += (
                        '  1. `tags` (数组，表情包对应的标签列表，如 ["敷衍", "猫猫"])\n'
                    )
                if analyze_description:
                    prompt += '  2. `description` (字符串，对这张表情包画面的简洁描述，如 "一只猫猫摊在地上露出无语的表情")\n'

                prompt += "例如：\n{\n"
                if analyze_tags:
                    prompt += '  "tags": ["敷衍", "猫猫"]'
                    if analyze_description:
                        prompt += ",\n"
                if analyze_description:
                    prompt += '  "description": "一只摊在地上表情无语的猫猫"\n'
                prompt += (
                    "}\n"
                    "不要返回任何其他内容（如 markdown 代码块标记、解释等），只返回 JSON 串本身。"
                )

                llm_resp = await sender.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    image_urls=[image_data_uri],
                )

                if not llm_resp or not llm_resp.completion_text:
                    raise ValueError("模型返回内容为空")

                raw_text = llm_resp.completion_text.strip()
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

                if not isinstance(data, dict):
                    raise ValueError(f"无法解析模型返回的结果: {raw_text}")

                parsed_tags = []
                parsed_desc = ""

                if analyze_tags:
                    if "tags" in data:
                        parsed_tags = [
                            str(x).strip()
                            for x in data["tags"]
                            if str(x).strip() and len(str(x).strip()) <= 20
                        ]
                    else:
                        raise ValueError("模型返回中缺少 tags 字段")

                if analyze_description:
                    if "description" in data:
                        parsed_desc = str(data["description"]).strip()
                    else:
                        raise ValueError("模型返回中缺少 description 字段")

                # 更新数据库
                conn = get_db_conn()
                cursor = conn.cursor()

                final_emotions = (
                    ",".join(parsed_tags) if analyze_tags else existing_emotions
                )
                final_desc = parsed_desc if analyze_description else existing_desc

                cursor.execute(
                    "UPDATE memes SET emotions = ?, description = ? WHERE filename = ?",
                    (final_emotions, final_desc, filename),
                )
                conn.commit()
                conn.close()

                # 填充结果
                r_item["status"] = "success"
                r_item["tags"] = (
                    parsed_tags
                    if analyze_tags
                    else (existing_emotions.split(",") if existing_emotions else [])
                )
                r_item["description"] = final_desc

            except Exception as e:
                logger.error(f"分析表情包失败: {filename}, 错误: {e}", exc_info=True)
                r_item["status"] = "error"
                r_item["error"] = str(e)

            # 稍微间隔一下，避免请求太频繁
            await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        logger.info("批量分析表情包任务被用户强行取消 (asyncio.CancelledError)。")
        # 将当前及后续等待中的更新为已取消/失败
        for r in batch_analyze_status["results"]:
            if r["status"] in ("waiting", "running"):
                r["status"] = "error"
                r["error"] = "任务已被取消"
        raise
    finally:
        batch_analyze_status["status"] = "completed"

        # 全局重构向量与重新加载
        try:
            trigger_tag_vectorization()
        except Exception as e:
            logger.error(f"批量分析后触发向量化失败: {e}")

        try:
            await sender.reload_emotions()
        except Exception as e:
            logger.error(f"批量分析后重新加载表情配置失败: {e}")


async def batch_rename_emojis_to_tags():
    """批量根据标签为表情包文件更名"""
    try:
        data = await request.get_json()
        filenames = data.get("filenames")

        if not isinstance(filenames, list) or not filenames:
            return jsonify({"message": "filenames 列表是必需的"}), 400

        import re
        import os
        from pathlib import Path
        from ....config import MEMES_DIR
        from ...db.database import get_db_conn
        from .common import trigger_tag_vectorization

        def sanitize_filename(name: str) -> str:
            name = re.sub(r'[\\/*?:"<>|]', "", name)
            name = name.strip(" .")
            return name or "emoji"

        conn = get_db_conn()
        cursor = conn.cursor()

        renamed = []
        skipped = []

        for filename in filenames:
            filename = os.path.basename(filename)
            file_path = Path(MEMES_DIR) / filename
            if not file_path.exists():
                skipped.append({"filename": filename, "reason": "文件不存在"})
                continue

            cursor.execute("SELECT emotions FROM memes WHERE filename = ?", (filename,))
            row = cursor.fetchone()
            if not row or not row["emotions"]:
                skipped.append({"filename": filename, "reason": "表情包无标签"})
                continue

            # Parse emotions
            emotions = [e.strip() for e in row["emotions"].split(",") if e.strip()]
            if not emotions:
                skipped.append({"filename": filename, "reason": "标签解析为空"})
                continue

            stem = "_".join(emotions)
            sanitized_stem = sanitize_filename(stem)
            suffix = file_path.suffix

            target_name = f"{sanitized_stem}{suffix}"
            if target_name == filename:
                # Already named correctly, no action needed
                skipped.append({"filename": filename, "reason": "文件名已是标签集合"})
                continue

            # Handle duplicate conflicts
            test_path = Path(MEMES_DIR) / target_name
            cursor.execute("SELECT 1 FROM memes WHERE filename = ?", (target_name,))
            db_exists = cursor.fetchone()

            if test_path.exists() or db_exists:
                idx = 1
                while True:
                    test_name = f"{sanitized_stem}_{idx}{suffix}"
                    test_path_check = Path(MEMES_DIR) / test_name
                    cursor.execute("SELECT 1 FROM memes WHERE filename = ?", (test_name,))
                    if not test_path_check.exists() and not cursor.fetchone():
                        target_name = test_name
                        break
                    idx += 1

            # Perform physical rename
            try:
                os.rename(file_path, Path(MEMES_DIR) / target_name)
            except Exception as e:
                logger.error(f"物理重命名文件失败: {filename} -> {target_name}, 错误: {e}")
                skipped.append({"filename": filename, "reason": f"重命名文件失败: {e}"})
                continue

            # Update database
            try:
                cursor.execute(
                    "UPDATE memes SET filename = ? WHERE filename = ?",
                    (target_name, filename),
                )
                cursor.execute(
                    "UPDATE meme_similarity_features SET filename = ? WHERE filename = ?",
                    (target_name, filename),
                )
                renamed.append({"original": filename, "new": target_name})
            except Exception as e:
                logger.error(f"更新数据库重命名记录失败 for {filename}: {e}")
                # Try to rollback rename
                try:
                    os.rename(Path(MEMES_DIR) / target_name, file_path)
                except Exception:
                    pass
                skipped.append({"filename": filename, "reason": f"更新数据库失败: {e}"})

        conn.commit()
        conn.close()

        # Sync configurations
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            category_manager.sync_with_filesystem()

        try:
            trigger_tag_vectorization()
        except Exception as e:
            logger.error(f"重命名后触发向量化失败: {e}")

        sender = plugin_config.get("sender")
        if sender:
            try:
                await sender.reload_emotions()
            except Exception as e:
                logger.error(f"重命名后重新加载表情配置失败: {e}")

        return jsonify({
            "message": "批量重命名完成",
            "renamed": renamed,
            "skipped": skipped,
            "renamed_count": len(renamed),
            "skipped_count": len(skipped),
        }), 200

    except Exception as e:
        logger.error(f"批量重命名标签失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500
