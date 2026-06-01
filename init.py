import logging
import os

from .backend.db.database import migrate_filesystem_to_db
from .config import (
    BASE_DATA_DIR,
    DEFAULT_CATEGORIES,
    MEMES_DATA_PATH,
)
from .utils import copy_default_memes_if_needed, ensure_dir_exists, save_json

logger = logging.getLogger(__name__)


def init_plugin():
    """初始化插件，创建必要的目录和配置文件"""
    try:
        # 创建基础数据目录
        ensure_dir_exists(BASE_DATA_DIR)

        # 创建表情包目录并在首次运行复制默认表情包
        copy_default_memes_if_needed()

        # 运行数据库迁移（将分类子文件夹结构转换为扁平目录结构并存入 SQLite 数据库）
        migrate_filesystem_to_db()

        # 初始化 memes_data.json
        if not os.path.exists(MEMES_DATA_PATH):
            save_json(DEFAULT_CATEGORIES, MEMES_DATA_PATH)
            logger.info(f"创建默认分类标签文件: {MEMES_DATA_PATH}")

        return True
    except Exception as e:
        logger.error(f"插件初始化失败: {e}")
        return False
