import hashlib
import logging
import os
from pathlib import Path

from quart import current_app
from werkzeug.utils import secure_filename

from ..config import MEMES_DIR
from ..utils import compress_image
from .database import get_db_conn

logger = logging.getLogger(__name__)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


class DuplicateEmojiError(ValueError):
    """Raised when an uploaded emoji already exists in the target category."""

    def __init__(self, existing_filename: str):
        self.existing_filename = existing_filename
        super().__init__(f"同一分类中已存在相同文件：{existing_filename}")


def _is_supported_image(filename: str) -> bool:
    return filename.lower().endswith(IMAGE_EXTENSIONS)


def _calculate_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _find_duplicate_image(content_hash: str) -> str | None:
    # 扫描 memes 目录下的所有文件并计算 hash
    if not os.path.exists(MEMES_DIR):
        return None
    for item in Path(MEMES_DIR).iterdir():
        if item.is_file() and _is_supported_image(item.name):
            try:
                if _calculate_file_hash(item.read_bytes()) == content_hash:
                    return item.name
            except OSError:
                continue
    return None


def _get_plugin_config() -> dict:
    try:
        return current_app.config.get("PLUGIN_CONFIG", {}).get("plugin_config", {})
    except RuntimeError:
        return {}


async def scan_emoji_folder():
    """扫描数据库，返回所有类别及其表情包列表"""
    emoji_data = {}
    if not os.path.exists(MEMES_DIR):
        os.makedirs(MEMES_DIR, exist_ok=True)

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT filename, emotions FROM memes")
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        filename = row["filename"]
        emotions = row["emotions"]

        # 确认文件在本地确实存在
        if not (Path(MEMES_DIR) / filename).exists():
            continue

        if emotions:
            for emotion in emotions.split(","):
                emotion = emotion.strip()
                if emotion:
                    emoji_data.setdefault(emotion, []).append(filename)

    return emoji_data


def get_emoji_by_category(category):
    """获取指定类别下的所有表情包"""
    conn = get_db_conn()
    cursor = conn.cursor()
    # 使用 SQL LIKE 精确匹配逗号分隔的值
    cursor.execute(
        "SELECT filename FROM memes WHERE ',' || emotions || ',' LIKE ?",
        (f",{category},",),
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        filename = row["filename"]
        if (Path(MEMES_DIR) / filename).exists():
            result.append(filename)
    return result


def save_and_register_meme(
    image_bytes: bytes,
    filename: str,
    category: str,
    personas: str = "*",
    config: dict = None,
) -> dict:
    """
    保存并注册表情包到数据库和磁盘（由 chat 上传或 steal tool 调用）
    """
    if not os.path.exists(MEMES_DIR):
        os.makedirs(MEMES_DIR, exist_ok=True)

    cfg = config or _get_plugin_config()

    # 1. 自动压缩
    if cfg.get("enable_compression", True):
        max_size_kb = cfg.get("compression_max_size_kb", 1024)
        max_width = cfg.get("compression_max_width", 1024)
        quality = cfg.get("compression_quality", 80)
        compress_gif = cfg.get("compress_gif", False)
        image_bytes = compress_image(
            image_bytes, max_size_kb, max_width, quality, compress_gif, filename
        )

    # 2. 生成安全文件名
    safe_name = secure_filename(filename)
    dest_path = Path(MEMES_DIR) / safe_name

    # 避免覆盖重名文件
    if dest_path.exists():
        suffix = dest_path.suffix
        stem = dest_path.stem
        idx = 1
        while True:
            safe_name = f"{stem}_{idx}{suffix}"
            dest_path = Path(MEMES_DIR) / safe_name
            if not dest_path.exists():
                break
            idx += 1

    # 3. 写入文件
    with open(dest_path, "wb") as f:
        f.write(image_bytes)

    # 4. 插入或更新数据库记录
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT emotions, personas FROM memes WHERE filename = ?", (safe_name,)
    )
    row = cursor.fetchone()

    if row:
        existing_emotions = (
            set(row["emotions"].split(",")) if row["emotions"] else set()
        )
        existing_emotions.add(category)

        existing_personas = (
            set(row["personas"].split(",")) if row["personas"] else set()
        )
        if personas != "*":
            for p in personas.split(","):
                existing_personas.add(p)
        else:
            existing_personas = {"*"}

        cursor.execute(
            "UPDATE memes SET emotions = ?, personas = ? WHERE filename = ?",
            (",".join(existing_emotions), ",".join(existing_personas), safe_name),
        )
    else:
        cursor.execute(
            "INSERT INTO memes (filename, emotions, personas) VALUES (?, ?, ?)",
            (safe_name, category, personas),
        )
    conn.commit()
    conn.close()

    return {"path": str(dest_path), "filename": safe_name}


def add_emoji_to_category(category, image_file, personas="*"):
    """添加表情包到指定类别（WebUI 上传端点调用）"""
    if not image_file:
        logger.error("没有接收到文件")
        raise ValueError("没有接收到文件")

    if not image_file.filename:
        logger.error("文件名为空")
        raise ValueError("文件名为空")

    filename = image_file.filename
    image_file.stream.seek(0)
    content = image_file.stream.read()
    if not content:
        logger.error("文件内容为空")
        raise OSError("上传文件内容为空")

    # 判重
    content_hash = _calculate_file_hash(content)
    duplicate_name = _find_duplicate_image(content_hash)
    if duplicate_name is not None:
        # 如果已存在，但在该类别下没有，则将该类别追加到现有文件的 emotions 中
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT emotions FROM memes WHERE filename = ?", (duplicate_name,)
        )
        row = cursor.fetchone()
        if row:
            emotions = set(row["emotions"].split(",")) if row["emotions"] else set()
            if category not in emotions:
                emotions.add(category)
                cursor.execute(
                    "UPDATE memes SET emotions = ? WHERE filename = ?",
                    (",".join(emotions), duplicate_name),
                )
                conn.commit()
        conn.close()
        raise DuplicateEmojiError(duplicate_name)

    result = save_and_register_meme(content, filename, category, personas)
    return result


def delete_emoji_from_category(category, image_file):
    """从指定类别删除表情（实际是移除该标签，若没有标签则删除文件）"""
    filename = Path(image_file).name
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT emotions FROM memes WHERE filename = ?", (filename,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False

    emotions = set(row["emotions"].split(",")) if row["emotions"] else set()
    if category in emotions:
        emotions.remove(category)

    if not emotions:
        # 没有分类了，删除记录与文件
        cursor.execute("DELETE FROM memes WHERE filename = ?", (filename,))
        conn.commit()
        conn.close()

        file_path = Path(MEMES_DIR) / filename
        if file_path.exists():
            file_path.unlink()
        return True
    else:
        # 更新数据库分类
        cursor.execute(
            "UPDATE memes SET emotions = ? WHERE filename = ?",
            (",".join(emotions), filename),
        )
        conn.commit()
        conn.close()
        return True


def batch_delete_emojis(category: str, image_files: list[str]) -> dict[str, object]:
    """批量删除表情"""
    deleted_files = []
    missing_files = []

    for file in dict.fromkeys(image_files):
        if delete_emoji_from_category(category, file):
            deleted_files.append(Path(file).name)
        else:
            missing_files.append(Path(file).name)

    return {
        "category_exists": True,
        "deleted_files": deleted_files,
        "missing_files": missing_files,
    }


def move_emoji_to_category(
    source_category: str, image_file: str, target_category: str
) -> dict[str, object]:
    """移动表情标签"""
    filename = Path(image_file).name
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT emotions FROM memes WHERE filename = ?", (filename,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {
            "source_category_exists": True,
            "target_category": target_category,
            "filename": filename,
            "moved": False,
            "conflict": False,
            "missing": True,
        }

    emotions = set(row["emotions"].split(",")) if row["emotions"] else set()
    if source_category in emotions:
        emotions.remove(source_category)
    emotions.add(target_category)

    cursor.execute(
        "UPDATE memes SET emotions = ? WHERE filename = ?",
        (",".join(emotions), filename),
    )
    conn.commit()
    conn.close()

    return {
        "source_category_exists": True,
        "source_category": source_category,
        "target_category": target_category,
        "filename": filename,
        "moved": True,
        "conflict": False,
        "missing": False,
    }


def batch_move_emojis(
    source_category: str, image_files: list[str], target_category: str
) -> dict[str, object]:
    """批量移动表情"""
    moved_files = []
    missing_files = []
    conflicting_files = []

    for image_file in dict.fromkeys(image_files):
        res = move_emoji_to_category(source_category, image_file, target_category)
        if res["moved"]:
            moved_files.append(res["filename"])
        elif res["missing"]:
            missing_files.append(res["filename"])

    return {
        "source_category_exists": True,
        "source_category": source_category,
        "target_category": target_category,
        "moved_files": moved_files,
        "missing_files": missing_files,
        "conflicting_files": conflicting_files,
    }


def copy_emoji_to_category(
    source_category: str, image_file: str, target_category: str
) -> dict[str, object]:
    """复制表情（即在已有记录上追加一个标签）"""
    filename = Path(image_file).name
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT emotions FROM memes WHERE filename = ?", (filename,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {
            "source_category_exists": True,
            "target_category": target_category,
            "filename": filename,
            "copied": False,
            "conflict": False,
            "missing": True,
        }

    emotions = set(row["emotions"].split(",")) if row["emotions"] else set()
    emotions.add(target_category)

    cursor.execute(
        "UPDATE memes SET emotions = ? WHERE filename = ?",
        (",".join(emotions), filename),
    )
    conn.commit()
    conn.close()

    return {
        "source_category_exists": True,
        "source_category": source_category,
        "target_category": target_category,
        "filename": filename,
        "copied": True,
        "conflict": False,
        "missing": False,
    }


def batch_copy_emojis(
    source_category: str, image_files: list[str], target_category: str
) -> dict[str, object]:
    """批量复制表情"""
    copied_files = []
    missing_files = []
    conflicting_files = []

    for image_file in dict.fromkeys(image_files):
        res = copy_emoji_to_category(source_category, image_file, target_category)
        if res["copied"]:
            copied_files.append(res["filename"])
        elif res["missing"]:
            missing_files.append(res["filename"])

    return {
        "source_category_exists": True,
        "source_category": source_category,
        "target_category": target_category,
        "copied_files": copied_files,
        "missing_files": missing_files,
        "conflicting_files": conflicting_files,
    }


def clear_category_emojis(category: str) -> dict[str, object]:
    """清除指定类别表情"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT filename, emotions FROM memes WHERE ',' || emotions || ',' LIKE ?",
        (f",{category},",),
    )
    rows = cursor.fetchall()

    deleted_files = []
    for row in rows:
        filename = row["filename"]
        emotions = set(row["emotions"].split(",")) if row["emotions"] else set()
        if category in emotions:
            emotions.remove(category)

        if not emotions:
            cursor.execute("DELETE FROM memes WHERE filename = ?", (filename,))
            file_path = Path(MEMES_DIR) / filename
            if file_path.exists():
                file_path.unlink()
        else:
            cursor.execute(
                "UPDATE memes SET emotions = ? WHERE filename = ?",
                (",".join(emotions), filename),
            )
        deleted_files.append(filename)

    conn.commit()
    conn.close()

    return {
        "category_exists": True,
        "deleted_files": deleted_files,
    }


def clear_all_emojis() -> dict[str, object]:
    """清空所有表情"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM memes")
    rows = cursor.fetchall()

    deleted_by_category = {}
    for row in rows:
        filename = row["filename"]
        file_path = Path(MEMES_DIR) / filename
        if file_path.exists():
            file_path.unlink()

    cursor.execute("DELETE FROM memes")
    conn.commit()
    conn.close()

    return {"deleted_by_category": deleted_by_category}


def update_emoji_in_category(category, old_image_file, new_image_file):
    """更新/替换表情包"""
    # 移除旧的表情包分类标签
    delete_emoji_from_category(category, old_image_file)
    # 添加新的表情包到该分类
    add_emoji_to_category(category, new_image_file)
    return True
