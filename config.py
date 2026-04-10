import os
import shutil
import sys
from pathlib import Path

from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_data_path,
)

# 获取当前插件目录的绝对路径
PLUGIN_DIR = Path(__file__).resolve().parent
CURRENT_DIR = str(PLUGIN_DIR)
DEFAULT_PLUGIN_NAME = "meme_manager"


def resolve_plugin_name(plugin_name: str | None = None) -> str:
    """优先使用运行时插件名，失败时回退到硬编码插件名。"""
    candidate = plugin_name or DEFAULT_PLUGIN_NAME
    return candidate.strip() or DEFAULT_PLUGIN_NAME


def get_legacy_plugin_data_dir() -> Path | None:
    """返回旧版插件数据目录 data/memes_data。"""
    try:
        return (Path(get_astrbot_data_path()) / "memes_data").resolve()
    except Exception:
        return None


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


def _plugin_data_dir_has_content(plugin_data_dir: Path) -> bool:
    """判断目标插件数据目录是否已有有效内容。"""
    metadata_file = plugin_data_dir / "memes_data.json"
    if metadata_file.is_file():
        return True

    memes_dir = plugin_data_dir / "memes"
    return memes_dir.is_dir() and any(memes_dir.iterdir())


def _copy_directory_contents(source_dir: Path, target_dir: Path) -> None:
    """合并复制目录内容，不覆盖已存在文件。"""
    for item in source_dir.iterdir():
        target_path = target_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target_path, dirs_exist_ok=True)
            continue
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_path)


def migrate_legacy_data_dir_if_needed(plugin_data_dir: Path) -> None:
    """将旧版 data/memes_data 安全迁移到 data/plugin_data/meme_manager。"""
    legacy_data_dir = get_legacy_plugin_data_dir()
    if legacy_data_dir is None or not legacy_data_dir.exists():
        return

    if legacy_data_dir.resolve() == plugin_data_dir.resolve():
        return

    if _plugin_data_dir_has_content(plugin_data_dir):
        return

    try:
        plugin_data_dir.mkdir(parents=True, exist_ok=True)
        _copy_directory_contents(legacy_data_dir, plugin_data_dir)
        print(
            f"检测到旧版插件数据目录，已迁移到: {plugin_data_dir}",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"迁移旧版插件数据目录失败: {exc}",
            file=sys.stderr,
        )


PLUGIN_DATA_DIR = get_plugin_data_dir()
migrate_legacy_data_dir_if_needed(PLUGIN_DATA_DIR)
BASE_DATA_DIR = PLUGIN_DATA_DIR
MEMES_DIR = PLUGIN_DATA_DIR / "memes"
MEMES_DATA_PATH = PLUGIN_DATA_DIR / "memes_data.json"  # 类别描述数据文件路径
TEMP_DIR = PLUGIN_DATA_DIR / "temp"
DEFAULT_MEMES_INIT_MARKER = PLUGIN_DATA_DIR / ".default_memes_initialized"

# 确保目录存在
os.makedirs(MEMES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 添加日志输出帮助调试
print(f"插件目录: {PLUGIN_DIR}", file=sys.stderr)
print(f"插件数据目录: {PLUGIN_DATA_DIR}", file=sys.stderr)
print(f"表情包目录: {MEMES_DIR}", file=sys.stderr)

# 默认的类别描述
DEFAULT_CATEGORY_DESCRIPTIONS = {
    "angry": "当对话包含抱怨、批评或激烈反对时使用（如用户投诉/观点反驳）",
    "happy": "用于成功确认、积极反馈或庆祝场景（问题解决/获得成就）",
    "sad": "表达伤心, 歉意、遗憾或安慰场景（遇到挫折/传达坏消息）",
    "surprised": "响应超出预期的信息（重大发现/意外转折）注意：轻微惊讶慎用",
    "confused": "请求澄清或表达理解障碍时（概念模糊/逻辑矛盾）或对于用户的请求感到困惑",
    "color": "社交场景中的暧昧表达（调情）使用频率≤1次/对话",
    "cpu": "技术讨论中表示思维卡顿（复杂问题/需要加载时间）",
    "fool": "自嘲或缓和气氛的幽默场景（小失误/无伤大雅的玩笑）",
    "givemoney": "涉及报酬讨论时使用（服务付费/奖励机制）需配合明确金额",
    "like": "表达对事物或观点的喜爱（美食/艺术/优秀方案）",
    "see": "表示偷瞄或持续关注（监控进度/观察变化）常与时间词搭配",
    "shy": "涉及隐私话题或收到赞美时（个人故事/外貌评价）",
    "work": "工作流程相关场景（任务分配/进度汇报）",
    "reply": "等待用户反馈时（提问后/需要确认）最长间隔30分钟",
    "meow": "卖萌或萌系互动场景（宠物话题/安抚情绪）慎用于正式场合",
    "baka": "轻微责备或吐槽（低级错误/可爱型抱怨）禁用程度：友善级",
    "morning": "早安问候专用（UTC时间6:00-10:00）跨时区需换算",
    "sleep": "涉及作息场景（熬夜/疲劳/休息建议）",
    "sigh": "表达无奈, 无语或感慨（重复问题/历史遗留难题）",
}
