import logging
import os

from ..config import DEFAULT_CATEGORY_DESCRIPTIONS, MEMES_DATA_PATH, MEMES_DIR
from ..utils import ensure_dir_exists, load_json, save_json

logger = logging.getLogger(__name__)


class CategoryManager:
    def __init__(self):
        """初始化类别管理器"""
        ensure_dir_exists(MEMES_DIR)
        self._ensure_data_file()
        self.descriptions = self._load_descriptions()

    def _ensure_data_file(self) -> None:
        """确保 memes_data.json 文件存在，不存在则创建并写入默认数据"""
        if not os.path.exists(MEMES_DATA_PATH):
            save_json(DEFAULT_CATEGORY_DESCRIPTIONS, MEMES_DATA_PATH)
            logger.info(f"创建默认类别描述文件: {MEMES_DATA_PATH}")

    def _load_descriptions(self) -> dict[str, str]:
        """加载类别描述配置"""
        return load_json(MEMES_DATA_PATH, DEFAULT_CATEGORY_DESCRIPTIONS)

    def get_local_categories(self) -> set[str]:
        """获取本地表情包库中的类别标签"""
        try:
            from .database import get_db_conn

            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT emotions FROM memes")
            rows = cursor.fetchall()
            conn.close()

            categories = set()
            for row in rows:
                if row["emotions"]:
                    for emo in row["emotions"].split(","):
                        emo = emo.strip()
                        if emo:
                            categories.add(emo)
            return categories
        except Exception as e:
            logger.error(f"从数据库获取类别标签失败: {e}")
            return set()

    def get_sync_status(self) -> tuple[list[str], list[str]]:
        """获取同步状态
        返回: (missing_in_config, deleted_categories)
        """
        local_categories = self.get_local_categories()
        config_categories = set(self.descriptions.keys())

        return (
            list(local_categories - config_categories),  # 本地有但配置没有
            list(config_categories - local_categories),  # 配置有但本地没有
        )

    def update_description(self, category: str, description: str) -> bool:
        """更新类别描述"""
        try:
            self.descriptions[category] = description  # 更新内存中的 descriptions
            # 同步保存到文件
            return save_json(self.descriptions, MEMES_DATA_PATH)
        except Exception as e:
            logger.error(f"更新类别描述失败: {e}")
            return False

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """重命名类别"""
        try:
            if old_name not in self.descriptions:
                return False

            # 获取旧类别的描述
            description = self.descriptions[old_name]

            # 更新配置
            del self.descriptions[old_name]
            self.descriptions[new_name] = description

            # 更新数据库中的表情标签
            from .database import get_db_conn

            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, emotions FROM memes WHERE ',' || emotions || ',' LIKE ?",
                (f"%,{old_name},%",),
            )
            rows = cursor.fetchall()
            for row in rows:
                row_id = row["id"]
                emotions = set(row["emotions"].split(",")) if row["emotions"] else set()
                if old_name in emotions:
                    emotions.remove(old_name)
                emotions.add(new_name)
                cursor.execute(
                    "UPDATE memes SET emotions = ? WHERE id = ?",
                    (",".join(emotions), row_id),
                )
            conn.commit()
            conn.close()

            # 同步更新内存中的数据
            return save_json(self.descriptions, MEMES_DATA_PATH)
        except Exception as e:
            logger.error(f"重命名类别失败: {e}")
            return False

    def delete_category(self, category: str) -> bool:
        """删除类别"""
        try:
            # 从配置中删除
            if category in self.descriptions:
                del self.descriptions[category]
                save_json(self.descriptions, MEMES_DATA_PATH)

            # 清除表情标签和空文件
            from .models import clear_category_emojis

            clear_category_emojis(category)

            return True
        except Exception as e:
            logger.error(f"删除类别失败: {e}")
            return False

    def get_descriptions(self) -> dict[str, str]:
        """获取所有类别描述"""
        return self.descriptions.copy()  # 返回字典的副本

    def sync_with_filesystem(self) -> bool:
        """同步文件系统和配置"""
        try:
            local_categories = self.get_local_categories()
            changed = False

            # 为新类别添加默认描述
            for category in local_categories:
                if category not in self.descriptions:
                    self.descriptions[category] = "请添加描述"
                    changed = True

            if changed:
                return save_json(self.descriptions, MEMES_DATA_PATH)
            return True
        except Exception as e:
            logger.error(f"同步文件系统失败: {e}")
            return False
