"""Audit current GA4/GSC and screenshot captures for every built-in report.

Usage: python -m scripts.audit_live_report_captures "Sep 1, 2026" "Sep 28, 2026" [report ...]
Only captures evidence and writes an audit JSON file; no PPTX is changed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from pptx import Presentation

from reports.generator_2026 import (
    OUTPUT_DIR,
    TEMPLATES_2026,
    TEMPLATES_DIR,
    _remove_unrefreshable_slides,
    _required_captures,
    _seo_picture_slots,
    _sitecheck_picture_slot,
    _validate_core_metrics,
    capture_2026,
)


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    start_date, end_date = sys.argv[1:3]
    names = sys.argv[3:] or sorted(TEMPLATES_2026)
    audit = {
        "period": {"start": start_date, "end": end_date},
        "captured_at": datetime.now().astimezone().isoformat(),
        "reports": {},
    }
    audit_path = OUTPUT_DIR / "live-capture-audit.json"
    if audit_path.is_file():
        previous = json.loads(audit_path.read_text(encoding="utf-8"))
        if previous.get("period") == audit["period"]:
            audit["reports"].update(previous.get("reports", {}))
    for name in names:
        print(f"AUDIT {name}: capturing...", flush=True)
        try:
            (
                screenshots, home, snapshot, page_views, pages, total_views,
                countries, search, traffic, traffic_totals,
            ) = capture_2026(name, start_date, end_date)
            _validate_core_metrics(home, name)
            prs = Presentation(str(TEMPLATES_DIR / TEMPLATES_2026[name]))
            _remove_unrefreshable_slides(prs)
            required = _required_captures(prs, screenshots, countries, pages, traffic, search, name)
            extra = [key for _, _, _, key in _seo_picture_slots(prs, name)]
            if _sitecheck_picture_slot(prs, name):
                extra.append("sitecheck_screenshot")
            missing = [key for key in extra if key not in screenshots or not Path(screenshots[key]).is_file()]
            if missing:
                raise RuntimeError("Current SEO/SiteCheck captures missing: " + ", ".join(missing))
            audit["reports"][name] = {
                "status": "ready",
                "home_metrics": home,
                "country_rows": len(countries),
                "page_rows": len(pages),
                "traffic_rows": len(traffic),
                "traffic_totals": traffic_totals,
                "required_screenshots": sorted(set(required.values()) | set(extra)),
                "capture_paths": {key: str(path) for key, path in screenshots.items()},
            }
            print(f"AUDIT {name}: READY ({len(countries)} countries, {len(pages)} pages, {len(traffic)} traffic rows)", flush=True)
        except Exception as exc:
            audit["reports"][name] = {"status": "failed", "error": str(exc)}
            print(f"AUDIT {name}: FAILED: {exc}", flush=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return 1 if any(r["status"] == "failed" for r in audit["reports"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
