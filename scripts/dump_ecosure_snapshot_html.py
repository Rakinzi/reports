from __future__ import annotations

from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reports.generator import _launch_persistent_context, _set_date_range
from src.reports.runtime import load_runtime_environment


SNAPSHOT_URL = "https://analytics.google.com/analytics/web/#/a365869570p501944307/reports/dashboard?r=reporting-hub"
OUT_DIR = Path("artifacts/ga4_html")


def main() -> int:
    load_runtime_environment()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    url_log: list[str] = []

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            page = context.new_page()
            page.bring_to_front()

            def record_url(frame) -> None:
                if frame == page.main_frame:
                    url_log.append(frame.url)
                    print(f"URL: {frame.url}")

            page.on("framenavigated", record_url)

            page.goto(SNAPSHOT_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(7000)
            before_path = OUT_DIR / "ecosure_snapshot_before_dates.html"
            before_path.write_text(page.content(), encoding="utf-8")
            print(f"BEFORE_HTML: {before_path.resolve()}")
            print(f"BEFORE_URL: {page.url}")

            _set_date_range(page, "Apr 1, 2026", "Apr 28, 2026")
            page.wait_for_timeout(7000)
            after_path = OUT_DIR / "ecosure_snapshot_after_dates.html"
            after_path.write_text(page.content(), encoding="utf-8")
            print(f"AFTER_HTML: {after_path.resolve()}")
            print(f"AFTER_URL: {page.url}")

            url_log_path = OUT_DIR / "ecosure_snapshot_url_log.txt"
            url_log_path.write_text("\n".join(url_log + [page.url]) + "\n", encoding="utf-8")
            print(f"URL_LOG: {url_log_path.resolve()}")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
