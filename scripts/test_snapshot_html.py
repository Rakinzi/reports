"""
test_snapshot_html.py — Navigate to the GA4 Reports Snapshot page for a
given report, set the date range, expand the Tech sidebar section,
click Overview, and dump the full HTML to a file.

Usage:
    uv run scripts/test_snapshot_html.py econet "Mar 1, 2026" "Mar 31, 2026"
    uv run scripts/test_snapshot_html.py econet "Mar 1, 2026" "Mar 31, 2026" --out tech_overview_dump.html
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reports.generator import (  # noqa: E402
    _ensure_expected_ga4_property,
    _goto_ga4_section,
    _launch_persistent_context,
    _switch_ga4_property_via_search,
)
from src.reports.generator_2026 import (  # noqa: E402
    TEMPLATES_2026,
    _open_snapshot_and_set_dates,
)
from src.reports.runtime import load_runtime_environment  # noqa: E402

PASS = "\033[92m✓\033[0m"
INFO = "\033[94m→\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump GA4 Reports Snapshot HTML.")
    parser.add_argument("report_name", choices=sorted(TEMPLATES_2026.keys()))
    parser.add_argument("start_date", help='e.g. "Mar 1, 2026"')
    parser.add_argument("end_date", help='e.g. "Mar 31, 2026"')
    parser.add_argument("--out", default="tech_overview_dump.html", help="Output HTML file (default: tech_overview_dump.html)")
    args = parser.parse_args()

    load_runtime_environment()
    out_path = Path(args.out)

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            page = context.new_page()
            page.bring_to_front()

            print(f"{INFO} Switching GA4 property for '{args.report_name}'...")
            page = _switch_ga4_property_via_search(page, args.report_name)

            print(f"{INFO} Opening GA4 home...")
            page = _goto_ga4_section(page, args.report_name, "/home")
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            except Exception:
                pass

            print(f"{INFO} Opening Reports Snapshot and applying date range...")
            _open_snapshot_and_set_dates(page, args.report_name, args.start_date, args.end_date)
            _ensure_expected_ga4_property(page, args.report_name)
            print(f"{INFO} Snapshot URL: {page.url}")

            # Navigate to Tech > Overview via the sidebar
            print(f"{INFO} Clicking Tech in sidebar...")
            tech_btn = page.locator("ga-secondary-nav-item button").filter(has_text="Tech")
            tech_btn.wait_for(state="visible", timeout=10000)
            tech_btn.click()
            page.wait_for_timeout(1500)

            print(f"{INFO} Clicking Tech > Overview...")
            overview_btn = page.locator("ga-secondary-nav-item button").filter(has_text="Overview").last
            overview_btn.wait_for(state="visible", timeout=10000)
            overview_btn.click()
            page.wait_for_timeout(3000)
            print(f"{INFO} Tech Overview URL: {page.url}")

            # Click "View platform devices"
            print(f"{INFO} Clicking 'View platform devices'...")
            view_btn = page.locator("span.view-link-text", has_text="View platform devices")
            view_btn.wait_for(state="visible", timeout=15000)
            view_btn.click()
            page.wait_for_timeout(4000)
            print(f"{INFO} Platform devices URL: {page.url}")

            # Screenshot the table
            try:
                row_num_col = page.locator("th.cdk-column-__row_index__").first
                row_num_col.wait_for(state="visible", timeout=10000)
                page.keyboard.press("End")
                page.wait_for_timeout(1000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1000)

                table_box = page.locator("table.adv-table").bounding_box()
                screenshot_path = Path("platform_devices_table.png")
                if table_box:
                    page.screenshot(path=str(screenshot_path), clip=table_box, full_page=True)
                else:
                    page.screenshot(path=str(screenshot_path), full_page=False)
                print(f"{PASS} Screenshot saved → {screenshot_path.resolve()}")
            except Exception as e:
                print(f"  [warn] Table screenshot failed: {e} — falling back to full page")
                page.screenshot(path="platform_devices_table.png", full_page=False)

            # Go back to Tech > Overview and click "View browsers"
            print(f"{INFO} Going back to Tech Overview...")
            page.go_back()
            page.wait_for_timeout(3000)
            _ensure_expected_ga4_property(page, args.report_name)

            print(f"{INFO} Clicking 'View browsers'...")
            browsers_btn = page.locator("span.view-link-text", has_text="View browsers")
            browsers_btn.wait_for(state="visible", timeout=15000)
            browsers_btn.click()
            page.wait_for_timeout(4000)
            print(f"{INFO} Browsers URL: {page.url}")

            try:
                row_num_col = page.locator("th.cdk-column-__row_index__").first
                row_num_col.wait_for(state="visible", timeout=10000)
                page.keyboard.press("End")
                page.wait_for_timeout(1000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1000)

                table_box = page.locator("table.adv-table").bounding_box()
                screenshot_path = Path("browsers_table.png")
                if table_box:
                    page.screenshot(path=str(screenshot_path), clip=table_box, full_page=True)
                else:
                    page.screenshot(path=str(screenshot_path), full_page=False)
                print(f"{PASS} Screenshot saved → {screenshot_path.resolve()}")
            except Exception as e:
                print(f"  [warn] Browsers table screenshot failed: {e} — falling back to full page")
                page.screenshot(path="browsers_table.png", full_page=False)

            html = page.content()
            out_path.write_text(html, encoding="utf-8")
            print(f"{PASS} HTML dumped → {out_path.resolve()}  ({len(html):,} bytes)")

        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
