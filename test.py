"""
test.py — Scrape previous month metrics + client website pages, build slide 7 (recommendations) only.

Usage:
    uv run test.py econet "Mar 1, 2026" "Mar 28, 2026"
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
    _build_recommendations_slide,
    _scrape_website_pages,
    SCREENSHOTS_DIR,
)
from src.reports.runtime import get_templates_dir, load_runtime_environment  # noqa: E402

PASS = "\033[92m✓\033[0m"
INFO = "\033[94m→\033[0m"
FAIL = "\033[91m✗\033[0m"

TEMPLATES_DIR = get_templates_dir()


def run(report_name: str, start_date: str, end_date: str) -> None:
    load_runtime_environment()
    print(f"\n→ {report_name}")
    print(f"→ Date range: {start_date} → {end_date}\n")

    # --- Slide 7: Both scrapes in one browser session ---
    print(f"{INFO} Scraping client website pages + previous month metrics (single browser session)...")
    website_pages, prev_home_metrics = _scrape_website_pages(report_name, start_date, end_date)
    print(f"{PASS} Previous month metrics: {prev_home_metrics}")
    pages_data_stub = []  # not used for recommendations — website_pages has the real data
    print(f"{PASS} Top pages scraped: {len(website_pages.get('top', []))}")
    any_404 = False
    for pg in website_pages.get("top", []):
        content_len = len(pg.get("content", ""))
        status = pg.get("status", 0)
        shot = pg.get("screenshot") or "no screenshot"
        is_404 = status == 404 or content_len == 0
        flag = f"{FAIL} 404/empty" if is_404 else f"{PASS} ok"
        if is_404:
            any_404 = True
        print(f"  {flag}  [{pg.get('title', '?')}]  {pg['url']}")
        print(f"        {content_len} chars  status={status}  screenshot={shot}")

    if any_404:
        print(f"\n{FAIL} Some pages returned 404 or empty.")
    else:
        print(f"\n{PASS} All pages loaded successfully.")

    qr_codes = website_pages.get("qr_codes", [])
    if qr_codes:
        print(f"\n{PASS} QR codes detected ({len(qr_codes)}):")
        for q in qr_codes:
            print(f"  {q['url']} → {q['data']!r}")

    cta_audit = website_pages.get("cta_audit", [])
    if cta_audit:
        print(f"\n{INFO} CTA audit results:")
        for page_audit in cta_audit:
            print(f"  [{page_audit['page_title']}]  {page_audit['page_url']}")
            for c in page_audit["ctas"]:
                flag = f"{FAIL} BROKEN" if c["broken"] else f"{PASS} ok"
                print(f"    {flag}  '{c['label']}'  →  {c['resolved_url']}  (status={c['status']})")

    # --- Build PPTX with slide 7 only ---
    template_path = TEMPLATES_DIR / TEMPLATES_2026[report_name]
    prs = Presentation(str(template_path))
    slide_count = len(prs.slides)

    print(f"{INFO} Building slide 7 (recommendations)...")
    rec_slide_idx = slide_count - 2
    _build_recommendations_slide(
        prs.slides[rec_slide_idx],
        report_name,
        home_metrics={},
        snapshot_metrics={},
        pages_data=pages_data_stub,
        countries_data=[],
        date_range=f"{start_date} - {end_date}",
        report_date="",
        prev_home_metrics=prev_home_metrics,
        website_pages=website_pages,
    )
    print(f"{PASS} Slide 7 done.")

    # Keep only slide 7
    slide_list = prs.slides._sldIdLst
    ids = list(slide_list)
    for i, el in enumerate(ids):
        if i != rec_slide_idx:
            slide_list.remove(el)

    out_path = REPO_ROOT / "test_slide7.pptx"
    prs.save(str(out_path))
    print(f"\n{PASS} Saved → {out_path.resolve()}")
    print("Open test_slide7.pptx to inspect.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_name", choices=sorted(TEMPLATES_2026.keys()))
    parser.add_argument("start_date", help='e.g. "Mar 1, 2026"')
    parser.add_argument("end_date",   help='e.g. "Mar 28, 2026"')
    args = parser.parse_args()
    run(args.report_name, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
