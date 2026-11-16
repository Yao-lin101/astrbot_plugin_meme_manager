import json
import logging
import os
import random
import re
import string
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


def ensure_dir_exists(path: str) -> None:
    """确保目录存在，不存在则创建"""
    if not os.path.exists(path):
        os.makedirs(path)


def save_json(data: dict[str, Any], filepath: str | Path) -> bool:
    """保存 JSON 数据到文件"""
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存 JSON 文件失败 {filepath}: {e}")
        return False


def load_json(filepath: str | Path, default: dict | None = None) -> dict:
    """从文件加载 JSON 数据"""
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载 JSON 文件失败 {filepath}: {e}")
        return default if default is not None else {}


def generate_secret_key(length=8):
    """生成随机秘钥"""
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length))


async def get_public_ip():
    """异步获取公网IPv4地址"""
    ipv4_apis = [
        "http://ipv4.ifconfig.me/ip",  # IPv4专用接口
        "http://api-ipv4.ip.sb/ip",  # 樱花云IPv4接口
        "http://v4.ident.me",  # IPv4专用
        "http://ip.qaros.com",  # 备用国内服务
        "http://ipv4.icanhazip.com",  # IPv4专用
        "http://4.icanhazip.com",  # 另一个变种地址
    ]

    async with aiohttp.ClientSession() as session:
        for api in ipv4_apis:
            try:
                async with session.get(api, timeout=5) as response:
                    if response.status == 200:
                        ip = (await response.text()).strip()
                        # 添加二次验证确保是IPv4格式
                        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                            return ip
            except Exception:
                continue

    return "[服务器公网ip]"


def compress_image(
    image_bytes: bytes,
    max_size_kb: int,
    max_width: int,
    quality: int,
    compress_gif: bool,
    filename: str,
    compression_format: str = "original",
) -> tuple[bytes, str]:
    """压缩单张图片，支持格式转换(webp/avif)"""
    try:
        import io

        from PIL import Image as PILImage
        from PIL import features

        ext = Path(filename).suffix.lower()
        if ext == ".gif" and not compress_gif:
            return image_bytes, filename

        target_format = None
        new_filename = filename
        if ext == ".gif":
            if compression_format == "webp":
                target_format = "WEBP"
                new_filename = str(Path(filename).with_suffix(".webp"))
        else:
            if compression_format == "webp" and ext != ".webp":
                target_format = "WEBP"
                new_filename = str(Path(filename).with_suffix(".webp"))
            elif compression_format == "avif" and ext != ".avif":
                if features.check("avif"):
                    target_format = "AVIF"
                    new_filename = str(Path(filename).with_suffix(".avif"))
                else:
                    logger.warning("Pillow 不支持 AVIF，自动回退到 WEBP 格式进行压缩。")
                    target_format = "WEBP"
                    new_filename = str(Path(filename).with_suffix(".webp"))

        img = PILImage.open(io.BytesIO(image_bytes))
        orig_format = img.format or "JPEG"

        save_format = target_format or orig_format
        if save_format == "JPG":
            save_format = "JPEG"

        width, height = img.size
        out_io = io.BytesIO()

        save_args = {}
        if save_format in ("JPEG", "WEBP", "AVIF"):
            save_args["quality"] = quality
        elif save_format == "PNG":
            save_args["optimize"] = True

        is_animated = getattr(img, "is_animated", False)
        if is_animated and save_format in ("GIF", "WEBP"):
            # Preserve loop and duration
            duration = img.info.get("duration", 100)
            loop = img.info.get("loop", 0)
            save_args["duration"] = duration
            save_args["loop"] = loop

            frames = []
            for frame_idx in range(img.n_frames):
                img.seek(frame_idx)
                frame = img.copy()
                if width > max_width:
                    new_width = max_width
                    new_height = int(height * (max_width / width))
                    frame = frame.resize(
                        (new_width, new_height), PILImage.Resampling.LANCZOS
                    )
                frames.append(frame)
            save_args["save_all"] = True
            save_args["append_images"] = frames[1:]
            frames[0].save(out_io, format=save_format, **save_args)
        else:
            if width > max_width:
                new_width = max_width
                new_height = int(height * (max_width / width))
                img = img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
            img.save(out_io, format=save_format, **save_args)

        compressed_bytes = out_io.getvalue()

        size_kb = len(image_bytes) / 1024
        new_size_kb = len(compressed_bytes) / 1024

        if target_format:
            logger.info(
                f"图片格式转换成功 ({orig_format} -> {save_format}): {size_kb:.1f}KB -> {new_size_kb:.1f}KB"
            )
            return compressed_bytes, new_filename
        else:
            if size_kb > max_size_kb and len(compressed_bytes) < len(image_bytes):
                logger.info(f"图片压缩成功: {size_kb:.1f}KB -> {new_size_kb:.1f}KB")
                return compressed_bytes, filename
            return image_bytes, filename
    except Exception as e:
        logger.error(f"压缩/转换图片失败: {e}", exc_info=True)
        return image_bytes, filename


def get_config_value(config: dict, key: str, default: Any = None) -> Any:
    """从配置字典中安全获取配置值，支持新旧版（嵌套/扁平）的配置格式。"""
    if not isinstance(config, dict):
        return default

    # 1. 尝试直接获取（兼容扁平格式或顶层键）
    if key in config:
        return config[key]

    # 2. 映射新版的嵌套组
    mapping = {
        # interaction_config
        "convert_static_to_gif": "interaction_config",
        "meme_summaries": "interaction_config",
        # auto_steal_config
        "auto_steal_enabled": "auto_steal_config",
        "auto_steal_probability": "auto_steal_config",
        "auto_steal_min_seen": "auto_steal_config",
        # multimodal_config
        "meme_decision_provider_id": "multimodal_config",
        "multimodal_llm_enabled": "multimodal_config",
        "multimodal_llm_provider_id": "multimodal_config",
        "multimodal_tag_prompt": "multimodal_config",
        # compression_config
        "enable_compression": "compression_config",
        "compression_max_size_kb": "compression_config",
        "compression_max_width": "compression_config",
        "compression_quality": "compression_config",
        "compress_gif": "compression_config",
        "compression_format": "compression_config",
        # embedding_config
        "embedding_provider_id": "embedding_config",
        "embedding_similarity_threshold": "embedding_config",
        "auto_tag_merge_threshold": "embedding_config",
        # similarity_dedup_config
        "enable_similarity_dedup": "similarity_dedup_config",
        "similarity_dedup_threshold": "similarity_dedup_config",
    }

    if key in mapping:
        parent = mapping[key]
        parent_val = config.get(parent)
        if isinstance(parent_val, dict) and key in parent_val:
            return parent_val[key]

    return default


def is_giftia_mode_enabled(config: dict) -> bool:
    """快捷获取当前是否启用了 Giftia 兼容模式"""
    return bool(get_config_value(config, "enable_giftia_mode", False))
