from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reports.generator import (  # noqa: E402
    GA4_PROPERTIES,
    _ensure_expected_ga4_property,
    _ga4_navigation_url,
    _launch_persistent_context,
    _switch_ga4_property_via_search,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual GA4 property navigation test.")
    parser.add_argument(
        "report_name",
        choices=sorted(GA4_PROPERTIES.keys()),
        help="Report/property key to test.",
    )
    parser.add_argument(
        "--section",
        default="/home",
        help="GA4 section fragment to open after selecting the property. Default: /home",
    )
    args = parser.parse_args()

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            page = context.new_page()
            page.bring_to_front()

            property_id = GA4_PROPERTIES[args.report_name]
            print(f"Testing property switch for '{args.report_name}' -> {property_id}")
            page = _switch_ga4_property_via_search(page, args.report_name)
            print(f"Selected property, current URL: {page.url}")

            target_url = _ga4_navigation_url(page, args.report_name, args.section)
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            _ensure_expected_ga4_property(page, args.report_name, timeout=20000)
            print(f"Opened section URL: {page.url}")
            print("Inspect the browser window. Press Enter here to close it.")
            input()
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
