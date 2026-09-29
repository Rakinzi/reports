"""Capture fresh Google results and Sucuri SiteCheck evidence for a report.

Usage: python scripts/capture_report_evidence.py bancabc
The saved report browser profile is used so Google can render normal results.
This command only writes PNGs; it does not edit a PowerPoint file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from reports.evidence_screenshots import capture_google_results, capture_sitecheck
from reports.generator import _launch_persistent_context
from reports.generator_2026 import GSC_URLS, REPORT_DISPLAY_NAMES, SECURITY_HEADER_URLS
from reports.runtime import get_screenshots_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_name", choices=sorted(GSC_URLS))
    parser.add_argument("--query", help="Google search query (defaults to the client name)")
    parser.add_argument("--web-only", action="store_true", help="Show Google's Web results tab")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    report_name = args.report_name
    site_url = SECURITY_HEADER_URLS.get(report_name) or GSC_URLS[report_name]
    query = args.query or REPORT_DISPLAY_NAMES.get(report_name, report_name.replace("_", " ").title())
    output_dir = args.output_dir or get_screenshots_dir() / report_name
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            page = context.new_page()
            for label, capture, value, filename in (
                ("Google results", capture_google_results, query, "seo_google_results.png"),
                ("Sucuri SiteCheck", capture_sitecheck, site_url, "sucuri_sitecheck.png"),
            ):
                output = output_dir / filename
                try:
                    if capture is capture_google_results:
                        capture(page, value, output, web_only=args.web_only)
                    else:
                        capture(page, value, output)
                    print(f"{label}: {output}")
                except Exception as exc:
                    print(f"{label}: {exc}")
        finally:
            context.close()


if __name__ == "__main__":
    main()
