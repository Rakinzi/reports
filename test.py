"""
test.py — capture GA4 Pages and Screens data and build Slide 5 only.

Usage:
    uv run test.py zimplats "Mar 1, 2026" "Mar 28, 2026"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pptx import Presentation
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent
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
    _build_slide5,
    _label_page_paths_with_gemini,
    _open_snapshot_and_set_dates,
    _scrape_pages_table,
    _switch_dimension_to_page_path,
)
from src.reports.runtime import get_templates_dir, load_runtime_environment  # noqa: E402

PASS = "\033[92m✓\033[0m"
INFO = "\033[94m→\033[0m"

TEMPLATES_DIR = get_templates_dir()


def _capture_slide5_data(
    report_name: str,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Path], list[dict], int]:
    screenshots: dict[str, Path] = {}
    pages_data: list[dict] = []
    site_total_views = 0

    dump_json_path = REPO_ROOT / "dump_page_performance_rows.json"

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            page = context.new_page()
            page.bring_to_front()

            print(f"{INFO} Switching GA4 property...")
            page = _switch_ga4_property_via_search(page, report_name)

            print(f"{INFO} Opening GA4 home...")
            page = _goto_ga4_section(page, report_name, "/home")
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            except Exception:
                pass

            print(f"{INFO} Opening snapshot and applying date range...")
            _open_snapshot_and_set_dates(page, report_name, start_date, end_date)
            _ensure_expected_ga4_property(page, report_name)

            print(f"{INFO} Opening Pages and Screens report...")
            page.get_by_role("button", name="View pages and screens", exact=True).click()
            page.wait_for_timeout(4000)
            _ensure_expected_ga4_property(page, report_name)

            row_num_col = page.locator("th.cdk-column-__row_index__").first
            end_col = page.locator("th.cdk-column-DEFAULT-userEngagementDurationPerUser").first
            table = page.locator("table.adv-table").first

            row_num_col.wait_for(state="visible", timeout=10000)
            page.keyboard.press("End")
            page.wait_for_timeout(1000)
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1000)

            print(f"{INFO} Switching table dimension to page path...")
            _switch_dimension_to_page_path(page)

            start_box = row_num_col.bounding_box()
            end_box = end_col.bounding_box()
            table_box = table.bounding_box()
            if start_box and end_box and table_box:
                clip = {
                    "x": start_box["x"],
                    "y": table_box["y"],
                    "width": (end_box["x"] + end_box["width"]) - start_box["x"],
                    "height": table_box["height"],
                }
                screenshot_path = REPO_ROOT / "dump_page_performance_table.png"
                page.screenshot(path=str(screenshot_path), clip=clip, full_page=True)
                screenshots["pages_table"] = screenshot_path

            print(f"{INFO} Scraping page rows...")
            _, pages_data, site_total_views = _scrape_pages_table(page)
            _label_page_paths_with_gemini(pages_data)

            dump_json_path.write_text(json.dumps(pages_data, indent=2), encoding="utf-8")
        finally:
            try:
                context.close()
            except Exception:
                pass

    print(f"{PASS} Wrote parsed rows → {dump_json_path.resolve()}")
    if "pages_table" in screenshots:
        print(f"{PASS} Wrote table screenshot → {screenshots['pages_table'].resolve()}")

    return screenshots, pages_data, site_total_views


def run(report_name: str, start_date: str, end_date: str) -> None:
    load_runtime_environment()
    print(f"\n{INFO} Report: {report_name}")
    print(f"{INFO} Date range: {start_date} → {end_date}\n")

    screenshots, pages_data, site_total_views = _capture_slide5_data(report_name, start_date, end_date)

    print(f"{PASS} Site total views: {site_total_views}")
    print(f"{PASS} Parsed page rows: {len(pages_data)}")
    for i, row in enumerate(pages_data, start=1):
        print(
            f"  {i}. path={row.get('path', '')} | views={row.get('views')} ({row.get('views_pct', '')}) | "
            f"active_users={row.get('active_users')} ({row.get('active_users_pct', '')}) | "
            f"views_per_user={row.get('views_per_user', '')} | "
            f"avg_engagement_time={row.get('avg_engagement_time', '')} | "
            f"title={row.get('title', '')}"
        )

    template_path = TEMPLATES_DIR / TEMPLATES_2026[report_name]
    prs = Presentation(str(template_path))

    print(f"\n{INFO} Building slide 5 (Page Performance)...")
    slide_idx = 4
    _build_slide5(prs.slides[slide_idx], pages_data, screenshots, site_total_views)
    print(f"{PASS} Slide 5 done.")

    slide_list = prs.slides._sldIdLst
    ids = list(slide_list)
    for i, el in enumerate(ids):
        if i != slide_idx:
            slide_list.remove(el)

    out_path = REPO_ROOT / "test_slide5_page_performance.pptx"
    prs.save(str(out_path))
    print(f"\n{PASS} Saved → {out_path.resolve()}")
    print("Open test_slide5_page_performance.pptx to inspect.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_name", choices=sorted(TEMPLATES_2026.keys()))
    parser.add_argument("start_date", help='e.g. "Mar 1, 2026"')
    parser.add_argument("end_date", help='e.g. "Mar 28, 2026"')
    args = parser.parse_args()
    run(args.report_name, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
