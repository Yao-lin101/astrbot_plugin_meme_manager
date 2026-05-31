import hashlib
import logging
import shutil
import sqlite3
from pathlib import Path

from ..config import MEMES_DIR, PLUGIN_DATA_DIR

logger = logging.getLogger(__name__)
DB_PATH = PLUGIN_DATA_DIR / "memes.db"
MIGRATION_MARKER = PLUGIN_DATA_DIR / ".db_migrated"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def get_db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库并创建表格"""
    PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        emotions TEXT,
        personas TEXT,
        original_hash TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS meme_steal_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_hash TEXT,
        persona_id TEXT,
        is_matched INTEGER,
        attempt_time INTEGER,
        reason TEXT
    )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_steal_attempts_hash_persona ON meme_steal_attempts (image_hash, persona_id)"
    )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS meme_seen_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_hash TEXT UNIQUE,
        seen_count INTEGER DEFAULT 1,
        last_seen_time INTEGER
    )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_seen_records_hash ON meme_seen_records (image_hash)"
    )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tag_embeddings (
        tag TEXT UNIQUE,
        embedding TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS meme_similarity_features (
        filename TEXT UNIQUE,
        width INTEGER,
        height INTEGER,
        aspect_ratio REAL,
        frame_count INTEGER,
        features_json TEXT
    )
    """)
    conn.commit()

    # 升级 similarity_features 表数据（版本2：使用整型哈希与彩色直方图，需要清空旧数据重新同步）
    SIMILARITY_V2_MARKER = PLUGIN_DATA_DIR / ".similarity_v2_migrated"
    if not SIMILARITY_V2_MARKER.exists():
        try:
            cursor.execute("DELETE FROM meme_similarity_features")
            conn.commit()
            with open(SIMILARITY_V2_MARKER, "w") as f:
                f.write("migrated")
            logger.info("已清空旧版图片相似度特征缓存以进行 V2 升级。")
        except Exception as e:
            logger.warning(f"升级相似度特征缓存失败: {e}")

    # 检查 meme_steal_attempts 表中的 reason 字段是否存在
    cursor.execute("PRAGMA table_info(meme_steal_attempts)")
    steal_columns = [row["name"] for row in cursor.fetchall()]
    if "reason" not in steal_columns:
        logger.info("数据库表 meme_steal_attempts 缺少 reason 字段，正在进行升级...")
        cursor.execute("ALTER TABLE meme_steal_attempts ADD COLUMN reason TEXT")
        conn.commit()

    # 检查 original_hash 列是否存在
    cursor.execute("PRAGMA table_info(memes)")
    columns = [row["name"] for row in cursor.fetchall()]
    if "original_hash" not in columns:
        logger.info("数据库表中缺少 original_hash 字段，正在进行升级...")
        cursor.execute("ALTER TABLE memes ADD COLUMN original_hash TEXT")
        conn.commit()

    # 填充现有的 original_hash (如果为 NULL)
    cursor.execute("SELECT id, filename FROM memes WHERE original_hash IS NULL")
    rows = cursor.fetchall()
    if rows:
        logger.info(f"正在为 {len(rows)} 个现有表情包填充哈希值...")
        for row in rows:
            row_id = row["id"]
            filename = row["filename"]
            file_path = Path(MEMES_DIR) / filename
            if file_path.exists() and file_path.is_file():
                try:
                    file_hash = _calculate_file_hash(file_path)
                    cursor.execute(
                        "UPDATE memes SET original_hash = ? WHERE id = ?",
                        (file_hash, row_id),
                    )
                except Exception as e:
                    logger.warning(f"为现有表情包 {filename} 计算哈希失败: {e}")
        conn.commit()

    conn.close()


def _calculate_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def migrate_filesystem_to_db():
    """迁移旧的文件系统分类目录结构到单文件夹+数据库结构"""
    init_db()

    if not MEMES_DIR.exists():
        return

    has_subdirs = any(item.is_dir() for item in MEMES_DIR.iterdir())
    if not has_subdirs:
        return

    logger.info("开始进行表情包数据库结构迁移...")
    conn = get_db_conn()
    cursor = conn.cursor()

    # 扫描 memes 目录下的子目录
    if MEMES_DIR.exists():
        for item in MEMES_DIR.iterdir():
            if item.is_dir():
                category = item.name
                logger.info(f"正在迁移分类: {category}")

                for file_path in item.iterdir():
                    if file_path.is_file() and file_path.name.lower().endswith(
                        IMAGE_EXTENSIONS
                    ):
                        orig_filename = file_path.name
                        dest_filename = orig_filename
                        dest_path = MEMES_DIR / dest_filename

                        # 处理文件名冲突
                        if (
                            dest_path.exists()
                            and dest_path.resolve() != file_path.resolve()
                        ):
                            # 计算两个文件的 hash，看看是否完全一致
                            orig_hash = _calculate_file_hash(file_path)
                            dest_hash = _calculate_file_hash(dest_path)

                            if orig_hash == dest_hash:
                                # 完全一样的文件，不需要移动，只更新数据库标签
                                logger.info(
                                    f"发现重复文件 {orig_filename}，仅合并数据库标签"
                                )
                                cursor.execute(
                                    "SELECT emotions FROM memes WHERE filename = ?",
                                    (dest_filename,),
                                )
                                row = cursor.fetchone()
                                if row:
                                    existing_emotions = (
                                        set(row[0].split(",")) if row[0] else set()
                                    )
                                    existing_emotions.add(category)
                                    cursor.execute(
                                        "UPDATE memes SET emotions = ? WHERE filename = ?",
                                        (",".join(existing_emotions), dest_filename),
                                    )
                                continue
                            else:
                                # 名字相同但内容不同，重命名
                                suffix = file_path.suffix
                                stem = file_path.stem
                                idx = 1
                                while True:
                                    dest_filename = f"{stem}_{idx}{suffix}"
                                    dest_path = MEMES_DIR / dest_filename
                                    if not dest_path.exists():
                                        break
                                    idx += 1
                                logger.info(
                                    f"文件名冲突，重命名: {orig_filename} -> {dest_filename}"
                                )

                        # 移动文件到 memes 根目录
                        shutil.move(str(file_path), str(dest_path))

                        # 计算文件哈希值
                        file_hash = None
                        try:
                            file_hash = _calculate_file_hash(dest_path)
                        except Exception as e:
                            logger.warning(
                                f"迁移表情包 {dest_filename} 计算哈希失败: {e}"
                            )

                        # 写入/更新数据库
                        cursor.execute(
                            "SELECT emotions FROM memes WHERE filename = ?",
                            (dest_filename,),
                        )
                        row = cursor.fetchone()
                        if row:
                            existing_emotions = (
                                set(row[0].split(",")) if row[0] else set()
                            )
                            existing_emotions.add(category)
                            cursor.execute(
                                "UPDATE memes SET emotions = ?, original_hash = ? WHERE filename = ?",
                                (",".join(existing_emotions), file_hash, dest_filename),
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO memes (filename, emotions, personas, original_hash) VALUES (?, ?, ?, ?)",
                                (dest_filename, category, "*", file_hash),
                            )

                # 移除已空的旧分类目录
                try:
                    shutil.rmtree(str(item))
                except Exception as e:
                    logger.warning(f"删除已迁移的空分类目录 {item} 失败: {e}")

    conn.commit()
    conn.close()

    # 写入迁移成功标记
    with open(MIGRATION_MARKER, "w") as f:
        f.write("migrated")
    logger.info("表情包数据库结构迁移完成！")


def get_steal_attempt(image_hash: str, persona_id: str) -> sqlite3.Row | None:
    """查询指定图片哈希和人格ID的盗图尝试记录"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_matched, reason FROM meme_steal_attempts WHERE image_hash = ? AND persona_id = ?",
        (image_hash, persona_id),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def save_steal_attempt(
    image_hash: str, persona_id: str, is_matched: bool, reason: str = ""
) -> None:
    """保存盗图尝试记录"""
    import time

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO meme_steal_attempts (image_hash, persona_id, is_matched, reason, attempt_time) VALUES (?, ?, ?, ?, ?)",
        (image_hash, persona_id, 1 if is_matched else 0, reason, int(time.time())),
    )
    conn.commit()
    conn.close()


def get_image_seen_count(image_hash: str) -> int:
    """获取图片哈希的全局出现次数"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT seen_count FROM meme_seen_records WHERE image_hash = ?",
        (image_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["seen_count"] if row else 0


def increment_image_seen_count(image_hash: str) -> int:
    """递增图片哈希的全局出现次数，并返回新的次数"""
    import time

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT seen_count FROM meme_seen_records WHERE image_hash = ?",
        (image_hash,),
    )
    row = cursor.fetchone()
    if row:
        new_count = row["seen_count"] + 1
        cursor.execute(
            "UPDATE meme_seen_records SET seen_count = ?, last_seen_time = ? WHERE image_hash = ?",
            (new_count, int(time.time()), image_hash),
        )
    else:
        new_count = 1
        cursor.execute(
            "INSERT INTO meme_seen_records (image_hash, seen_count, last_seen_time) VALUES (?, ?, ?)",
            (image_hash, 1, int(time.time())),
        )
    conn.commit()
    conn.close()
    return new_count


def get_all_tag_embeddings() -> dict[str, list[float]]:
    """获取所有已缓存的标签向量"""
    import json

    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT tag, embedding FROM tag_embeddings")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()

    result = {}
    for row in rows:
        try:
            result[row["tag"]] = json.loads(row["embedding"])
        except Exception:
            continue
    return result


def save_tag_embedding(tag: str, embedding: list[float]) -> None:
    """保存或更新标签向量"""
    import json

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO tag_embeddings (tag, embedding) VALUES (?, ?)",
        (tag, json.dumps(embedding)),
    )
    conn.commit()
    conn.close()


def delete_tag_embedding(tag: str) -> None:
    """删除指定标签的向量缓存"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tag_embeddings WHERE tag = ?", (tag,))
    conn.commit()
    conn.close()


def clear_all_tag_embeddings() -> None:
    """清空所有缓存的标签向量"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tag_embeddings")
    conn.commit()
    conn.close()


def delete_meme_similarity_features(filename: str) -> None:
    """删除指定表情包的相似度特征"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM meme_similarity_features WHERE filename = ?", (filename,)
    )
    conn.commit()
    conn.close()


def clear_all_meme_similarity_features() -> None:
    """清空所有缓存的表情相似度特征"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM meme_similarity_features")
    conn.commit()
    conn.close()
