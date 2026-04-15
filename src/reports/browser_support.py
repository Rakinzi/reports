from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _darwin_browser_candidates() -> list[Path]:
    return [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]


def _windows_browser_candidates() -> list[Path]:
    roots = [
        os.getenv("PROGRAMFILES"),
        os.getenv("PROGRAMFILES(X86)"),
        os.getenv("LOCALAPPDATA"),
    ]
    candidates: list[Path] = []
    suffixes = [
        Path("Google/Chrome/Application/chrome.exe"),
        Path("Google/Chrome Beta/Application/chrome.exe"),
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Chromium/Application/chrome.exe"),
    ]
    for root in roots:
        if not root:
            continue
        for suffix in suffixes:
            candidates.append(Path(root) / suffix)
    return candidates


def _linux_browser_candidates() -> list[Path]:
    names = [
        "google-chrome-stable",
        "google-chrome",
        "chromium",
        "chromium-browser",
        "microsoft-edge-stable",
        "microsoft-edge",
        "msedge",
    ]
    result: list[Path] = []
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            result.append(Path(resolved))
    return result


def find_browser_executable() -> str | None:
    candidates: list[Path]
    if sys.platform == "darwin":
        candidates = _darwin_browser_candidates()
    elif sys.platform == "win32":
        candidates = _windows_browser_candidates()
    else:
        candidates = _linux_browser_candidates()

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def build_launch_prefs() -> list[dict[str, object]]:
    prefs: list[dict[str, object]] = []
    executable_path = find_browser_executable()
    if executable_path:
        prefs.append({"executable_path": executable_path})

    # Channel-based launch still helps in dev if Chrome/Edge is installed in the
    # standard location but executable discovery missed it.
    prefs.append({"channel": "chrome"})
    if sys.platform in {"win32", "darwin"}:
        prefs.append({"channel": "msedge"})

    # Final fallback uses Playwright-managed Chromium if available.
    prefs.append({})
    return prefs
