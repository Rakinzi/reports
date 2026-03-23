from __future__ import annotations

import os
import threading

from .logging_utils import configure_logging
from .runtime import (
    get_managed_chrome_profile_directory,
    get_managed_chrome_user_data_dir,
    load_runtime_environment,
)

_auth_lock = threading.Lock()
_auth_thread: threading.Thread | None = None


def _auth_worker(target_url: str) -> None:
    try:
        logger = configure_logging()
        from playwright.sync_api import sync_playwright

        load_runtime_environment()
        chrome_user_data_dir = os.getenv("CHROME_USER_DATA_DIR") or str(get_managed_chrome_user_data_dir().resolve())
        chrome_profile_directory = (
            os.getenv("CHROME_PROFILE_DIRECTORY") or get_managed_chrome_profile_directory()
        )

        get_managed_chrome_user_data_dir().mkdir(parents=True, exist_ok=True)

        launch_args = [
            f"--profile-directory={chrome_profile_directory}",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ]
        closed = threading.Event()

        with sync_playwright() as playwright:
            try:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=chrome_user_data_dir,
                    channel="chrome",
                    headless=False,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                    no_viewport=True,
                )
            except Exception:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=chrome_user_data_dir,
                    headless=False,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                    no_viewport=True,
                )

            page = context.pages[0] if context.pages else context.new_page()
            context.on("close", lambda *_args: closed.set())
            page.goto(target_url, wait_until="domcontentloaded")
            page.bring_to_front()
            logger.info("Opened Google sign-in Chrome session at %s", target_url)

            # Keep the browser session alive until the user closes the window.
            closed.wait()
            logger.info("Google sign-in Chrome session closed by user")
    except Exception:
        configure_logging().exception("Google sign-in session failed")
    finally:
        global _auth_thread
        with _auth_lock:
            _auth_thread = None


def open_google_sign_in(target_url: str = "https://analytics.google.com/") -> dict[str, object]:
    global _auth_thread
    with _auth_lock:
        if _auth_thread and _auth_thread.is_alive():
            return {"started": False, "already_running": True}

        thread = threading.Thread(target=_auth_worker, args=(target_url,), daemon=True)
        thread.start()
        _auth_thread = thread
        return {"started": True, "already_running": False}


def auth_session_status() -> dict[str, bool]:
    with _auth_lock:
        return {"running": bool(_auth_thread and _auth_thread.is_alive())}
