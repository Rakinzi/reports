"""Read Zimplats user totals from the authenticated GA4 report.

Run: uv run python scripts/get_zimplats_users.py --start 'Sep 1, 2026' --end 'Sep 27, 2026'
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reports.generator import (  # noqa: E402
    GA4_PROPERTIES,
    _launch_persistent_context,
    _switch_ga4_property_via_search,
)
from src.reports.generator_2026 import _open_snapshot_and_set_dates  # noqa: E402
from src.reports.generator_2026 import _ga4_explorer_url  # noqa: E402


def _latest_report_dates() -> tuple[str, str]:
    import sqlite3

    db_path = REPO_ROOT / "artifacts" / "reports.db"
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT date_range FROM reports WHERE report_name='zimplats' "
            "AND status='completed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise ValueError("No completed Zimplats report found; pass --start and --end")
    dates = re.fullmatch(r"(\d{1,2} \w+ \d{4}) - (\d{1,2} \w+ \d{4})", row[0])
    if not dates:
        raise ValueError(f"Could not parse report date range: {row[0]}")
    parsed = [datetime.strptime(value, "%d %B %Y") for value in dates.groups()]
    return tuple(f"{value:%b} {value.day}, {value.year}" for value in parsed)


def _parse_number(text: str) -> int:
    match = re.match(r"\s*([\d,]+)\b", text)
    if not match:
        raise ValueError(f"Expected an exact GA4 count, got {text!r}")
    return int(match.group(1).replace(",", ""))


def _read_table(page, expected_metric: str) -> dict:
    table = page.locator("table.adv-table").first
    table.wait_for(state="visible", timeout=30000)
    table.locator(f"thead th.cdk-column-DEFAULT-{expected_metric}").first.wait_for(
        state="visible", timeout=30000
    )
    page.wait_for_timeout(1500)
    return table.evaluate(
        """table => ({
            headers: Array.from(table.querySelectorAll('thead th')).map(el => ({
                text: el.innerText.trim().replace(/\\s+/g, ' '),
                className: el.className,
            })),
            rows: Array.from(table.querySelectorAll('tbody tr')).map(row => ({
                text: row.innerText.trim().replace(/\\s+/g, ' '),
                cells: Array.from(row.querySelectorAll('th, td')).map(el => ({
                    text: el.innerText.trim().replace(/\\s+/g, ' '),
                    className: el.className,
                })),
            })),
        })"""
    )


def _summary_metric(data: dict, metric: str) -> int:
    class_name = f"cdk-column-0-DEFAULT-{metric}"
    matches = [
        cell["text"] for cell in data["headers"]
        if class_name in cell["className"].split()
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one GA4 Total cell for {metric}, found {len(matches)}")
    return _parse_number(matches[0])


def _visible_metric_sum(data: dict, metric: str) -> int:
    class_name = f"cdk-column-DEFAULT-{metric}"
    return sum(
        _parse_number(cell["text"])
        for row in data["rows"]
        for cell in row["cells"]
        if class_name in cell["className"].split()
    )


def _assert_report_dates(url: str, start: str, end: str) -> None:
    expected = [
        f"date00%3D{datetime.strptime(start, '%b %d, %Y'):%Y%m%d}",
        f"date01%3D{datetime.strptime(end, '%b %d, %Y'):%Y%m%d}",
    ]
    if not all(token in url for token in expected):
        raise RuntimeError(f"GA4 report lost the requested date range: {url}")


def _data_quality_labels(page) -> list[str]:
    """Collect GA4's visible data-quality labels without inferring a cause."""
    return page.evaluate(
        """() => [...new Set(Array.from(document.querySelectorAll('[aria-label], [title]'))
            .flatMap(el => [el.getAttribute('aria-label'), el.getAttribute('title')])
            .filter(value => value && /data quality|threshold|unsampled|sampl/i.test(value)))]"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Get exact Zimplats user counts from GA4")
    parser.add_argument("--start", help="GA4 date, e.g. 'Sep 1, 2026'")
    parser.add_argument("--end", help="GA4 date, e.g. 'Sep 27, 2026'")
    parser.add_argument("--debug", action="store_true", help="Print table headers and first rows")
    args = parser.parse_args()
    if bool(args.start) != bool(args.end):
        parser.error("Pass both --start and --end")
    start, end = (args.start, args.end) if args.start else _latest_report_dates()
    for value in (start, end):
        datetime.strptime(value, "%b %d, %Y")

    with sync_playwright() as playwright:
        context = _launch_persistent_context(playwright, headless=False)
        try:
            page = context.new_page()
            page = _switch_ga4_property_via_search(page, "zimplats")
            page = _open_snapshot_and_set_dates(page, "zimplats", start, end)
            snapshot_url = page.url
            result = {"property_id": GA4_PROPERTIES["zimplats"], "start": start, "end": end}
            for locator in (
                page.get_by_role("button", name="View user acquisition", exact=True),
                page.locator("span.view-link-text", has_text="View user acquisition"),
            ):
                try:
                    locator.first.click(timeout=5000)
                    break
                except Exception:
                    pass
            else:
                raise RuntimeError("Could not open GA4 User acquisition report")
            page.reload(wait_until="domcontentloaded", timeout=30000)
            _assert_report_dates(page.url, start, end)
            acquisition_url = page.url
            data = _read_table(page, "totalUsers")
            result["data_quality_labels"] = _data_quality_labels(page)
            result["total_users"] = _summary_metric(data, "totalUsers")
            result["new_users"] = _summary_metric(data, "newUsers")
            result["returning_users"] = _summary_metric(data, "returningUsers")

            page.goto(_ga4_explorer_url(snapshot_url, "countries"), wait_until="domcontentloaded", timeout=30000)
            _assert_report_dates(page.url, start, end)
            countries = _read_table(page, "activeUsers")
            result["active_users"] = _summary_metric(countries, "activeUsers")
            result["country_rows_shown"] = len(countries["rows"])
            result["visible_country_active_users_sum"] = _visible_metric_sum(countries, "activeUsers")
            result["active_users_minus_visible_country_rows"] = (
                result["active_users"] - result["visible_country_active_users_sum"]
            )
            result["new_users_exceed_total_users_by"] = max(0, result["new_users"] - result["total_users"])
            result["consistent"] = (
                result["total_users"] >= result["new_users"]
                and result["total_users"] >= result["active_users"]
            )
            if not result["consistent"]:
                result["error"] = (
                    "GA4's displayed user metrics contradict their definitions for this date range. "
                    "Do not use these figures as a reconciled user count."
                )
            if args.debug:
                result["user_acquisition_url"] = acquisition_url
                result["user_acquisition_headers"] = data["headers"]
                result["countries_headers"] = countries["headers"]
            print(json.dumps(result, indent=2))
        finally:
            context.close()
    return 0 if result["consistent"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
