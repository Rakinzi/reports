from __future__ import annotations

from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reports.generator import _launch_persistent_context, _set_date_range
from src.reports.generator_2026 import (
    _goto_snapshot_explorer,
    _return_to_snapshot_dashboard,
)
from src.reports.runtime import load_runtime_environment


SNAPSHOT_URL = "https://analytics.google.com/analytics/web/#/a365869570p501944307/reports/dashboard?r=reporting-hub"


def main() -> int:
    load_runtime_environment()

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            page = context.new_page()
            page.bring_to_front()
            page.on(
                "framenavigated",
                lambda frame: print(f"URL: {frame.url}") if frame == page.main_frame else None,
            )

            page.goto(SNAPSHOT_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(7000)
            _set_date_range(page, "Apr 1, 2026", "Apr 28, 2026")
            page.wait_for_timeout(5000)
            snapshot_url = page.url
            print(f"SNAPSHOT_AFTER_DATES: {snapshot_url}")

            page = _goto_snapshot_explorer(page, "ecosure", snapshot_url, "countries")
            page.locator("th.cdk-column-__row_index__").first.wait_for(state="visible", timeout=20000)
            print(f"COUNTRIES_URL: {page.url}")

            page = _return_to_snapshot_dashboard(page, "ecosure", snapshot_url)
            print(f"RETURNED_SNAPSHOT_URL: {page.url}")

            page = _goto_snapshot_explorer(page, "ecosure", snapshot_url, "pages")
            page.locator("th.cdk-column-__row_index__").first.wait_for(state="visible", timeout=20000)
            print(f"PAGES_URL: {page.url}")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
