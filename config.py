import os
import sys
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

# 获取当前插件目录的绝对路径
PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_PLUGIN_NAME = "meme_manager"


def resolve_plugin_name(plugin_name: str | None = None) -> str:
    """优先使用运行时插件名，失败时回退到硬编码插件名。"""
    candidate = plugin_name or DEFAULT_PLUGIN_NAME
    return candidate.strip() or DEFAULT_PLUGIN_NAME


def get_plugin_data_dir(plugin_name: str | None = None) -> Path:
    """返回插件数据目录，规范落在 data/plugin_data/{plugin_name}/ 下。"""
    resolved_plugin_name = resolve_plugin_name(plugin_name)
    try:
        plugin_data_root = Path(get_astrbot_plugin_data_path())
        return (plugin_data_root / resolved_plugin_name).resolve()
    except Exception:
        fallback_data_path = (
            PLUGIN_DIR / "data" / "plugin_data" / resolved_plugin_name
        ).resolve()
        print(
            f"获取 AstrBot 数据目录失败，回退到本地路径: {fallback_data_path}",
            file=sys.stderr,
        )
        return fallback_data_path


PLUGIN_DATA_DIR = get_plugin_data_dir()
BASE_DATA_DIR = PLUGIN_DATA_DIR
MEMES_DIR = PLUGIN_DATA_DIR / "memes"
MEMES_DATA_PATH = PLUGIN_DATA_DIR / "memes_data.json"  # 类别描述数据文件路径
TEMP_DIR = PLUGIN_DATA_DIR / "temp"

# 确保目录存在
os.makedirs(MEMES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 添加日志输出帮助调试
print(f"插件目录: {PLUGIN_DIR}", file=sys.stderr)
print(f"插件数据目录: {PLUGIN_DATA_DIR}", file=sys.stderr)
print(f"表情包目录: {MEMES_DIR}", file=sys.stderr)

# 默认的分类标签
DEFAULT_CATEGORIES = [
    "angry",
    "happy",
    "sad",
    "surprised",
    "confused",
    "color",
    "cpu",
    "fool",
    "givemoney",
    "like",
    "see",
    "shy",
    "work",
    "reply",
    "meow",
    "baka",
    "morning",
    "sleep",
    "sigh",
]
