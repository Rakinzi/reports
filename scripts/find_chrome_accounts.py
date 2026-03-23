#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path


def candidate_user_data_dirs() -> list[Path]:
    home = Path.home()
    dirs = []

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

    # Useful fallback for this project setup.
    dirs.append(Path("artifacts/chrome-profile"))
    return dirs


def choose_user_data_dir(explicit_dir: str | None) -> Path:
    if explicit_dir:
        chosen = Path(explicit_dir).expanduser()
        if not chosen.exists():
            raise FileNotFoundError(f"User data dir not found: {chosen}")
        return chosen

    for path in candidate_user_data_dirs():
        if path.exists():
            return path

    raise FileNotFoundError(
        "Could not find a Chrome user data directory. "
        "Pass one with --user-data-dir."
    )


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def extract_profile_emails(preferences: dict) -> list[str]:
    emails = set()
    signin = preferences.get("signin", {})
    metadata = signin.get("accounts_metadata_dict", {})
    if isinstance(metadata, dict):
        for value in metadata.values():
            if isinstance(value, dict):
                email = value.get("email")
                if email:
                    emails.add(email)
    return sorted(emails)


def find_profiles(user_data_dir: Path) -> list[dict]:
    local_state = read_json(user_data_dir / "Local State")
    info_cache = local_state.get("profile", {}).get("info_cache", {})

    profile_dirs = set()
    if isinstance(info_cache, dict):
        profile_dirs.update(info_cache.keys())

    for child in user_data_dir.iterdir():
        if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile ")):
            profile_dirs.add(child.name)

    results = []
    for profile_dir in sorted(profile_dirs):
        info = info_cache.get(profile_dir, {}) if isinstance(info_cache, dict) else {}
        prefs = read_json(user_data_dir / profile_dir / "Preferences")

        results.append(
            {
                "profile_dir": profile_dir,
                "profile_name": info.get("name") or prefs.get("profile", {}).get("name", profile_dir),
                "signed_in_email": info.get("user_name") or "",
                "gaia_name": info.get("gaia_name") or "",
                "emails_from_preferences": extract_profile_emails(prefs),
            }
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Find Chrome profiles/accounts on this machine.")
    parser.add_argument(
        "--user-data-dir",
        help="Chrome user data directory (example macOS: ~/Library/Application Support/Google/Chrome)",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    args = parser.parse_args()

    user_data_dir = choose_user_data_dir(args.user_data_dir)
    profiles = find_profiles(user_data_dir)

    output = {
        "user_data_dir": str(user_data_dir),
        "profiles_found": len(profiles),
        "profiles": profiles,
    }

    if args.json:
        print(json.dumps(output, indent=2))
        return

    print(f"Chrome user data dir: {output['user_data_dir']}")
    print(f"Profiles found: {output['profiles_found']}")
    print("")
    for p in profiles:
        print(f"- Profile dir: {p['profile_dir']}")
        print(f"  Profile name: {p['profile_name']}")
        print(f"  Signed-in email (Local State): {p['signed_in_email'] or '(none)'}")
        print(f"  Gaia name: {p['gaia_name'] or '(none)'}")
        pref_emails = ", ".join(p["emails_from_preferences"]) or "(none)"
        print(f"  Emails from Preferences: {pref_emails}")
        print("")


if __name__ == "__main__":
    main()
