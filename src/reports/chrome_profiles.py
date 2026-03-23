import json
import os
import sys
from pathlib import Path


def candidate_user_data_dirs() -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []

    env_dir = os.getenv("CHROME_USER_DATA_DIR")
    if env_dir:
        dirs.append(Path(env_dir).expanduser())

    if sys.platform == "darwin":
        dirs.append(home / "Library/Application Support/Google/Chrome")
    elif sys.platform.startswith("linux"):
        dirs.append(home / ".config/google-chrome")
        dirs.append(home / ".config/chromium")
    elif sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            dirs.append(Path(local_app_data) / "Google/Chrome/User Data")

    dirs.append(Path.cwd() / "artifacts" / "chrome-profile")
    return dirs


def choose_user_data_dir(explicit_dir: str | None = None) -> Path:
    if explicit_dir:
        chosen = Path(explicit_dir).expanduser()
        if not chosen.exists():
            raise FileNotFoundError(f"Chrome user data directory not found: {chosen}")
        return chosen

    for path in candidate_user_data_dirs():
        if path.exists():
            return path

    raise FileNotFoundError(
        "Could not find a Chrome user data directory. Pass an explicit path in settings."
    )


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _extract_profile_emails(preferences: dict) -> list[str]:
    emails = set()
    metadata = preferences.get("signin", {}).get("accounts_metadata_dict", {})
    if isinstance(metadata, dict):
        for value in metadata.values():
            if isinstance(value, dict) and value.get("email"):
                emails.add(value["email"])
    return sorted(emails)


def list_profiles(user_data_dir: str | None = None) -> dict[str, object]:
    resolved = choose_user_data_dir(user_data_dir)
    local_state = _read_json(resolved / "Local State")
    info_cache = local_state.get("profile", {}).get("info_cache", {})

    profile_dirs = set()
    if isinstance(info_cache, dict):
        profile_dirs.update(info_cache.keys())

    for child in resolved.iterdir():
        if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile ")):
            profile_dirs.add(child.name)

    profiles = []
    for profile_dir in sorted(profile_dirs):
        info = info_cache.get(profile_dir, {}) if isinstance(info_cache, dict) else {}
        preferences = _read_json(resolved / profile_dir / "Preferences")
        profiles.append(
            {
                "profile_dir": profile_dir,
                "profile_name": info.get("name")
                or preferences.get("profile", {}).get("name", profile_dir),
                "signed_in_email": info.get("user_name") or "",
                "emails_from_preferences": _extract_profile_emails(preferences),
            }
        )

    return {
        "user_data_dir": str(resolved),
        "profiles_found": len(profiles),
        "profiles": profiles,
    }
