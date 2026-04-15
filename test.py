"""
test.py — capture GA4 home/snapshot metrics and build Slide 2 only.

Usage:
    uv run test.py zimplats "Mar 1, 2026" "Mar 28, 2026"
"""
from __future__ import annotations

import argparse
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
    _scrape_home_metrics,
    _scrape_snapshot_metrics,
    _switch_ga4_property_via_search,
)
from src.reports.generator_2026 import (  # noqa: E402
    TEMPLATES_2026,
    _build_slide2,
    _open_snapshot_and_set_dates,
)
from src.reports.runtime import get_templates_dir, load_runtime_environment  # noqa: E402

PASS = "\033[92m✓\033[0m"
INFO = "\033[94m→\033[0m"

TEMPLATES_DIR = get_templates_dir()


def _capture_slide2_metrics(
    report_name: str,
    start_date: str,
    end_date: str,
) -> tuple[dict, dict]:
    home_metrics: dict = {}
    snapshot_metrics: dict = {}

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

            print(f"{INFO} Scraping snapshot metrics...")
            snapshot_metrics = _scrape_snapshot_metrics(page)

            print(f"{INFO} Returning to GA4 home for KPI metrics...")
            page = _goto_ga4_section(page, report_name, "/home")
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            except Exception:
                pass

            # Keep the same date range on Home before scraping KPI cards.
            from src.reports.generator import _set_date_range  # noqa: E402

            _set_date_range(page, start_date, end_date)
            _ensure_expected_ga4_property(page, report_name)

            print(f"{INFO} Scraping home metrics...")
            home_metrics = _scrape_home_metrics(page)
        finally:
            try:
                context.close()
            except Exception:
                pass

    return home_metrics, snapshot_metrics


def run(report_name: str, start_date: str, end_date: str) -> None:
    load_runtime_environment()
    print(f"\n{INFO} Report: {report_name}")
    print(f"{INFO} Date range: {start_date} → {end_date}\n")

    home_metrics, snapshot_metrics = _capture_slide2_metrics(report_name, start_date, end_date)

    print(f"{PASS} Home metrics: {home_metrics}")
    print(f"{PASS} Snapshot metrics: {snapshot_metrics}")

    template_path = TEMPLATES_DIR / TEMPLATES_2026[report_name]
    prs = Presentation(str(template_path))

    print(f"\n{INFO} Building slide 2 (Executive Summary)...")
    slide_idx = 1
    _build_slide2(prs.slides[slide_idx], home_metrics, snapshot_metrics, report_name)
    print(f"{PASS} Slide 2 done.")

    slide_list = prs.slides._sldIdLst
    ids = list(slide_list)
    for i, el in enumerate(ids):
        if i != slide_idx:
            slide_list.remove(el)

    out_path = REPO_ROOT / "test_slide2_executive_summary.pptx"
    prs.save(str(out_path))
    print(f"\n{PASS} Saved → {out_path.resolve()}")
    print("Open test_slide2_executive_summary.pptx to inspect.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_name", choices=sorted(TEMPLATES_2026.keys()))
    parser.add_argument("start_date", help='e.g. "Mar 1, 2026"')
    parser.add_argument("end_date", help='e.g. "Mar 28, 2026"')
    args = parser.parse_args()
    run(args.report_name, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
