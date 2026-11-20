import hashlib
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from ...config import MEMES_DIR, PLUGIN_DATA_DIR
from ..core.helpers import MEME_SEND_MODE_STICKER, MEME_SEND_MODE_VALUES

logger = logging.getLogger(__name__)
DB_PATH = PLUGIN_DATA_DIR / "memes.db"


def get_db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库并创建表格"""
    PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS memes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        emotions TEXT,
        personas TEXT,
        original_hash TEXT,
        description TEXT,
        send_mode TEXT DEFAULT '{MEME_SEND_MODE_STICKER}'
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

    # 检查 description 列是否存在
    cursor.execute("PRAGMA table_info(memes)")
    columns = [row["name"] for row in cursor.fetchall()]
    if "description" not in columns:
        logger.info("数据库表中缺少 description 字段，正在进行升级...")
        cursor.execute("ALTER TABLE memes ADD COLUMN description TEXT")
        conn.commit()

    if "send_mode" not in columns:
        logger.info("数据库表中缺少 send_mode 字段，正在进行升级...")
        cursor.execute(
            f"ALTER TABLE memes ADD COLUMN send_mode TEXT DEFAULT '{MEME_SEND_MODE_STICKER}'"
        )
        conn.commit()

    cursor.execute(
        "UPDATE memes SET send_mode = ? WHERE send_mode IS NULL OR send_mode NOT IN (?, ?)",
        (MEME_SEND_MODE_STICKER, *MEME_SEND_MODE_VALUES),
    )
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


def clear_legacy_tag_embeddings() -> None:
    """Clear the pre-LanceDB cache when the administrator resets embeddings."""
    with closing(get_db_conn()) as conn, conn:
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tag_embeddings'"
        ).fetchone():
            conn.execute("DELETE FROM tag_embeddings")


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
