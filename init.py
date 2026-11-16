import logging
import os

from .backend.db.database import init_db
from .config import (
    BASE_DATA_DIR,
    DEFAULT_CATEGORIES,
    MEMES_DATA_PATH,
    MEMES_DIR,
)
from .utils import ensure_dir_exists, save_json

logger = logging.getLogger(__name__)


def init_plugin():
    """初始化插件，创建必要的目录和配置文件"""
    try:
        # 创建基础数据目录
        ensure_dir_exists(BASE_DATA_DIR)

        ensure_dir_exists(MEMES_DIR)
        init_db()

        # 初始化 memes_data.json
        if not os.path.exists(MEMES_DATA_PATH):
            save_json(DEFAULT_CATEGORIES, MEMES_DATA_PATH)
            logger.info(f"创建默认分类标签文件: {MEMES_DATA_PATH}")

        return True
    except Exception as e:
        logger.error(f"插件初始化失败: {e}")
        return False
