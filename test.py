"""
test.py — Capture GSC data and build slide 6 only for inspection.

Usage:
    python test.py econet "Mar 1, 2026" "Mar 28, 2026"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pptx import Presentation

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reports.generator_2026 import (  # noqa: E402
    TEMPLATES_2026,
    SCREENSHOTS_DIR,
    _build_slide6,
    _capture_gsc,
    GA4_PROPERTIES_2026,
)
from src.reports.runtime import get_templates_dir, load_runtime_environment  # noqa: E402

PASS = "\033[92m✓\033[0m"
INFO = "\033[94m→\033[0m"
FAIL = "\033[91m✗\033[0m"

TEMPLATES_DIR = get_templates_dir()


def capture_gsc_only(report_name: str, start_date: str, end_date: str) -> tuple[dict, dict]:
    """Navigate to GSC, select property, set custom date range, return (search_metrics, screenshots)."""
    from playwright.sync_api import sync_playwright
    from src.reports.generator_2026 import _launch_persistent_context

    out_dir = SCREENSHOTS_DIR / report_name
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = _launch_persistent_context(p, headless=False)
        try:
            search_metrics, screenshots = _capture_gsc(context, report_name, start_date, end_date, out_dir)
            print(f"{PASS} Search metrics: {search_metrics}")
            print(f"{PASS} Screenshot saved → {screenshots.get('search_screenshot', 'N/A')}")
            return search_metrics, screenshots
        finally:
            try:
                context.close()
            except Exception:
                pass


def run(report_name: str, start_date: str, end_date: str) -> None:
    load_runtime_environment()
    print(f"\n→ {report_name}")
    print(f"→ Date range: {start_date} → {end_date}\n")

    search_metrics, screenshots = capture_gsc_only(report_name, start_date, end_date)

    template_path = TEMPLATES_DIR / TEMPLATES_2026[report_name]
    prs = Presentation(str(template_path))

    print(f"{INFO} Building slide 6...")
    _build_slide6(prs.slides[5], search_metrics, screenshots)
    print(f"{PASS} Slide 6 done.")

    # Keep only slide 6
    slide_list = prs.slides._sldIdLst
    ids = list(slide_list)
    # Remove everything except index 5
    for i, el in enumerate(ids):
        if i != 5:
            slide_list.remove(el)

    out_path = REPO_ROOT / "test_slide6.pptx"
    prs.save(str(out_path))
    print(f"{PASS} Saved → {out_path.resolve()}")
    print(f"\nOpen test_slide6.pptx to inspect.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_name", choices=sorted(TEMPLATES_2026.keys()))
    parser.add_argument("start_date", help='e.g. "Mar 1, 2026"')
    parser.add_argument("end_date",   help='e.g. "Mar 28, 2026"')
    args = parser.parse_args()
    run(args.report_name, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
