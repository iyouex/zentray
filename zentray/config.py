import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _user_data_dir(app_name: str) -> Path:
    """获取应用用户数据目录（其他平台恢复时在此按 sys.platform 加回分支）。"""
    if sys.platform == "linux":
        xdg = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        return Path(xdg) / app_name
    return Path.home() / f".{app_name}"


def _load_dotenv(env_path: Path, *, override: bool = False) -> None:
    """将 .env 写入 os.environ。override=True 时覆盖已有变量。"""
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    k, v = key.strip(), val.strip()
                    if override:
                        os.environ[k] = v
                    else:
                        os.environ.setdefault(k, v)
    except OSError as e:
        logger.warning("Failed to load .env from %s: %s", env_path, e)


_PROJECT_ROOT = Path(__file__).parent.parent

# 加载顺序（后覆盖前，用户数据优先）：
# 1) 开发项目根 .env（setdefault）
# 2) frozen 可执行文件旁 .env（setdefault）
# 3) DATA_DIR/.env（override）
_load_dotenv(_PROJECT_ROOT / ".env", override=False)
if getattr(sys, "frozen", False):
    _load_dotenv(Path(sys.executable).parent / ".env", override=False)

APP_NAME = "ZenTray"
APP_AUTHOR = "Zen-Geek"
# 语义化版本：见 docs/VERSIONING.md
# PATCH +0.0.1 修 bug/优化；MINOR +0.1.0 功能迭代；MAJOR +1.0.0 重构改版
VERSION = "0.5.1"

DATA_DIR = _user_data_dir(APP_NAME)
_load_dotenv(DATA_DIR / ".env", override=True)

ACTIVE_TASKS_FILE = DATA_DIR / "active_tasks.json"
PERIODIC_TEMPLATES_FILE = DATA_DIR / "periodic_templates.json"
ARCHIVE_DIR = DATA_DIR / "archive"
LOG_FILE = DATA_DIR / "zentray.log"

WXPUSHER_APP_TOKEN = os.getenv("WXPUSHER_APP_TOKEN")
WXPUSHER_UID = os.getenv("WXPUSHER_UID")

AI_API_BASE_URL = os.getenv("AI_API_BASE_URL", "https://api.openai.com/v1")
AI_API_KEY = os.getenv("AI_API_KEY")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "gpt-4o")

POMODORO_MINUTES = 25
HOTKEY_QUICK_ADD = "<ctrl>+<alt>+t"

os.makedirs(ARCHIVE_DIR, exist_ok=True)


def is_notification_enabled() -> bool:
    try:
        from zentray.services.settings_manager import SettingsManager

        return SettingsManager().is_notification_configured()
    except Exception:
        return bool(WXPUSHER_APP_TOKEN and WXPUSHER_UID)


def is_ai_coach_enabled() -> bool:
    try:
        from zentray.services.settings_manager import SettingsManager

        return SettingsManager().is_ai_configured()
    except Exception:
        return bool(AI_API_KEY)


def get_enabled_features() -> dict:
    return {
        "core": True,
        "notification": is_notification_enabled(),
        "ai_coach": is_ai_coach_enabled(),
    }


def validate_config() -> list[str]:
    warnings = []
    if not is_notification_enabled():
        warnings.append(
            "通知服务未配置：在设置中填写 WxPusher 凭据，或创建 .env 设置 "
            "WXPUSHER_APP_TOKEN 与 WXPUSHER_UID。"
        )
    if not is_ai_coach_enabled():
        warnings.append(
            "AI 教练未配置：在设置中填写 AI API Key，或设置环境变量 AI_API_KEY。"
        )
    return warnings
