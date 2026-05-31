import os
import random
import re
import tempfile
import time

from PIL import Image as PILImage

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import Plain


async def get_persona_id(sender, event: AstrMessageEvent) -> str:
    """获取当前会话实际生效的人格 ID"""
    conversation_persona_id = None
    try:
        curr_cid = await sender.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        if curr_cid:
            conv = await sender.context.conversation_manager.get_conversation(
                event.unified_msg_origin, curr_cid
            )
            if conv:
                conversation_persona_id = conv.persona_id
    except Exception as e:
        logger.warning(f"获取当前会话失败: {e}")

    try:
        cfg = sender.context.get_config(event.unified_msg_origin)
        (
            persona_id,
            _,
            _,
            _,
        ) = await sender.context.persona_manager.resolve_selected_persona(
            umo=event.unified_msg_origin,
            conversation_persona_id=conversation_persona_id,
            platform_name=event.get_platform_name(),
            provider_settings=cfg,
        )
        if persona_id:
            return persona_id
    except Exception as e:
        logger.warning(f"解析当前会话实际生效人格失败，使用降级逻辑: {e}")

    # 降级逻辑
    persona_id = conversation_persona_id or ""
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


async def get_persona_prompt(sender, event: AstrMessageEvent) -> str:
    """获取当前会话实际生效的人格系统提示词"""
    persona_id = await get_persona_id(sender, event)
    try:
        persona_obj = sender.context.provider_manager.persona_mgr.get_persona_v3_by_id(
            persona_id
        )
        if persona_obj:
            return persona_obj.get("prompt", "") or ""
    except Exception as e:
        logger.warning(f"获取当前会话实际生效人格 Prompt 失败: {e}")
    return ""


def convert_to_gif(image_path: str, sender) -> str:
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


def is_position_in_thinking_tags(text: str, position: int) -> bool:
    """检查指定位置是否在thinking标签内"""
    thinking_pattern = re.compile(
        r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE
    )

    for match in thinking_pattern.finditer(text):
        if match.start() <= position < match.end():
            return True
    return False


def is_likely_emotion_markup(markup, text, position):
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


def is_likely_emotion(word, text, position, valid_emotions, sender):
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


def merge_components_with_images(sender, components, images):
    """将表情图片与文本组件智能配对，支持分段回复"""
    logger.debug(
        f"[meme_manager] _merge_components_with_images 输入: 组件总数={len(components)}, 图片总数={len(images)}"
    )

    if not images:
        return components

    if not components:
        return images

    plain_indices = [i for i, comp in enumerate(components) if isinstance(comp, Plain)]
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


PERSONA_TAGS_PATH = None


def _get_persona_tags_path():
    global PERSONA_TAGS_PATH
    if PERSONA_TAGS_PATH is None:
        from ..config import PLUGIN_DATA_DIR

        PERSONA_TAGS_PATH = PLUGIN_DATA_DIR / "persona_tags.json"
    return PERSONA_TAGS_PATH


def get_settings_dict(config: dict) -> dict:
    """获取解析后的人格偏好配置字典"""
    import json

    val = config.get("persona_settings", "{}")
    if not val:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception as e:
            logger.warning(f"[meme_manager] Failed to parse persona_settings JSON: {e}")
            return {}
    return {}


def save_settings_dict(config: dict, settings: dict) -> None:
    """序列化并保存人格偏好配置字典"""
    import json

    config["persona_settings"] = json.dumps(settings, ensure_ascii=False)
    if hasattr(config, "save_config"):
        config.save_config()


def migrate_old_persona_tags_if_needed(config: dict) -> None:
    """如果存在旧的 persona_tags.json，则将其迁移到插件配置项中，并删除旧文件。"""
    path = _get_persona_tags_path()
    if path.exists() and path.is_file():
        try:
            from ..utils import load_json

            old_tags = load_json(path, {})
            if old_tags:
                settings = get_settings_dict(config)
                for pid, tag in old_tags.items():
                    if pid not in settings:
                        settings[pid] = {
                            "meme_preference": "",
                            "meme_use_preference": tag,
                        }
                save_settings_dict(config, settings)
                logger.info("[meme_manager] 成功将旧的人格表情包标签迁移至配置项")
            path.unlink()
        except Exception as e:
            logger.warning(f"[meme_manager] 迁移旧的人格标签文件失败: {e}")


def get_persona_setting(config: dict, persona_id: str, key: str) -> str:
    """获取人格的特定偏好配置 (meme_preference 或 meme_use_preference)"""
    if not config:
        return ""
    settings = get_settings_dict(config)
    p_cfg = settings.get(persona_id)
    if not p_cfg or not isinstance(p_cfg, dict):
        return ""
    return p_cfg.get(key, "") or ""


def load_persona_tags(config: dict | None = None) -> dict[str, str]:
    """获取所有人格的专属标签（兼容旧逻辑，返回 {persona_id: tags_str} 字典）"""
    if config is None:
        try:
            from quart import current_app

            plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
            if plugin_config:
                config = plugin_config.get("plugin_config")
        except Exception:
            pass

    if config is not None:
        settings = get_settings_dict(config)
        res = {}
        for pid, val in settings.items():
            if isinstance(val, dict):
                res[pid] = val.get("meme_use_preference", "") or ""
            else:
                res[pid] = str(val)
        return res

    return {}


def save_persona_tags(tags: dict[str, str], config: dict | None = None) -> None:
    """保存人格标签（兼容旧逻辑）"""
    if config is None:
        try:
            from quart import current_app

            plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
            if plugin_config:
                config = plugin_config.get("plugin_config")
        except Exception:
            pass

    if config is not None:
        settings = get_settings_dict(config)
        for pid, tag in tags.items():
            if pid not in settings:
                settings[pid] = {"meme_preference": "", "meme_use_preference": tag}
            else:
                settings[pid]["meme_use_preference"] = tag
        save_settings_dict(config, settings)
