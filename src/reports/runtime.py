import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .browser_support import find_browser_executable


def _packaged_resources_dir() -> Path | None:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    return Path(base)


def get_templates_dir() -> Path:
    packaged = _packaged_resources_dir()
    if packaged:
        return packaged / "src" / "reports" / "report-templates"
    return Path(__file__).parent / "report-templates"


def get_app_data_dir() -> Path:
    configured = os.getenv("REPORTS_APP_DATA_DIR")
    path = Path(configured).expanduser() if configured else Path.cwd() / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_output_dir() -> Path:
    path = get_app_data_dir() / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_screenshots_dir() -> Path:
    path = get_app_data_dir() / "screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_slides_dir() -> Path:
    path = get_app_data_dir() / "slides"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_database_path() -> Path:
    return get_app_data_dir() / "reports.db"


def get_settings_path() -> Path:
    return get_app_data_dir() / "settings.json"


def get_user_templates_dir() -> Path:
    path = get_app_data_dir() / "user-templates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_managed_chrome_user_data_dir() -> Path:
    path = get_app_data_dir() / "chrome-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_managed_chrome_profile_directory() -> str:
    return "Default"


def load_settings() -> dict[str, str]:
    path = get_settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {key: value for key, value in data.items() if isinstance(value, str)}


def save_settings(settings: dict[str, str]) -> dict[str, str]:
    current = load_settings()
    for key, value in settings.items():
        if not isinstance(value, str):
            continue
        if key in {"chrome_user_data_dir", "chrome_profile_directory"}:
            continue
        value = value.strip()
        if value:
            current[key] = value
    get_settings_path().write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def load_runtime_environment() -> dict[str, str]:
    load_dotenv(override=False)
    settings = load_settings()

    env_map = {
        "GEMINI_API_KEY": settings.get("gemini_api_key", ""),
        "CHROME_USER_DATA_DIR": str(get_managed_chrome_user_data_dir()),
        "CHROME_PROFILE_DIRECTORY": get_managed_chrome_profile_directory(),
    }
    for env_name, value in env_map.items():
        if value:
            os.environ[env_name] = value

    mplconfig_dir = get_app_data_dir() / "mplconfig"
    mplconfig_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mplconfig_dir))

    return settings


def get_runtime_status() -> dict[str, str | bool]:
    settings = load_runtime_environment()
    chrome_user_data_dir = os.getenv("CHROME_USER_DATA_DIR") or str(get_managed_chrome_user_data_dir())
    chrome_profile_directory = os.getenv("CHROME_PROFILE_DIRECTORY") or get_managed_chrome_profile_directory()
    gemini_api_key_set = bool(os.getenv("GEMINI_API_KEY"))
    browser_path = find_browser_executable()

    return {
        "configured": gemini_api_key_set and bool(browser_path),
        "gemini_api_key_set": gemini_api_key_set,
        "browser_available": bool(browser_path),
        "browser_path": browser_path or "",
        "chrome_user_data_dir": chrome_user_data_dir,
        "chrome_profile_directory": chrome_profile_directory,
        "chrome_profile_label": "App Google Session",
        "app_data_dir": str(get_app_data_dir()),
    }
