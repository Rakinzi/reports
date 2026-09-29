"""Refresh the dated GA4 country table through Event Count for built-in reports.

Usage: python -m scripts.refresh_country_table_captures "Sep 1, 2026" "Sep 28, 2026" [report ...]
Updates only the country screenshot paths in the matching live capture audit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from PIL import Image
from playwright.sync_api import sync_playwright

from reports.ga4_screenshots import capture_ga4_table
from reports.generator import _launch_persistent_context, _switch_ga4_property_via_search
from reports.generator_2026 import (
    OUTPUT_DIR,
    SCREENSHOTS_DIR,
    TEMPLATES_2026,
    _goto_snapshot_explorer,
    _open_dated_snapshot_direct,
    _scrape_countries_table,
)


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    start_date, end_date = sys.argv[1:3]
    names = sys.argv[3:] or sorted(TEMPLATES_2026)
    audit_path = OUTPUT_DIR / "live-capture-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("period") != {"start": start_date, "end": end_date}:
        raise RuntimeError("Audit period does not match the requested dates")

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            for name in names:
                print(f"COUNTRIES {name}: capturing...", flush=True)
                report = audit["reports"].setdefault(name, {})
                try:
                    page = context.new_page()
                    page = _switch_ga4_property_via_search(page, name)
                    page = _open_dated_snapshot_direct(page, name, start_date, end_date)
                    page = _goto_snapshot_explorer(page, name, page.url, "countries")
                    page.locator("table.adv-table tbody tr").first.wait_for(
                        state="visible", timeout=10000
                    )
                    rows = _scrape_countries_table(page)
                    if not rows:
                        raise RuntimeError("GA4 returned no country rows")
                    directory = SCREENSHOTS_DIR / name / uuid4().hex
                    directory.mkdir(parents=True, exist_ok=True)
                    image_path = capture_ga4_table(
                        page, directory / "countries_table.png", last_column="event count"
                    )
                    with Image.open(image_path) as image:
                        size = image.size
                    report.setdefault("capture_paths", {})["countries_table"] = str(image_path)
                    report["country_rows"] = len(rows)
                    report.pop("error", None)
                    report["status"] = "ready"
                    print(f"COUNTRIES {name}: READY ({len(rows)} rows, {size[0]}x{size[1]})", flush=True)
                except Exception as exc:
                    report["status"] = "failed"
                    report["error"] = f"Country table capture: {exc}"
                    print(f"COUNTRIES {name}: FAILED: {exc}", flush=True)
                pending = audit_path.with_name(f".{audit_path.name}.{uuid4().hex}.tmp")
                pending.write_text(json.dumps(audit, indent=2), encoding="utf-8")
                pending.replace(audit_path)
        finally:
            context.close()
    return 1 if any(audit["reports"][name]["status"] != "ready" for name in names) else 0


if __name__ == "__main__":
    raise SystemExit(main())
