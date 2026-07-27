# Traffic Acquisition Slide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live-data-driven "Traffic Acquisition" slide to the `generator_2026.py` pipeline, wired in for infraco's new 13-slide template while leaving the other 9 reports' 7/8-slide templates unaffected.

**Architecture:** Mirror the existing `_build_slide5` (Page Performance) pattern end-to-end: a GA4-explorer-URL navigation helper, a table scraper, a Gemini-paraphrased paragraph builder, and a slide-filling function that writes a subtitle + "Overall Insight:"-prefixed narrative + table screenshot. Detect the slide's presence by title text so untouched templates take the same code path as today.

**Tech Stack:** Python, Playwright (sync API), python-pptx, google-genai (Gemini 2.5 Flash), pytest.

## Global Constraints

- GA4 dimension key for the channel breakdown table is `sessionSourceMedium`; report id is `lifecycle-traffic-acquisition-v2`; metric is `sessions` — verified live against the infraco property on 2026-07-27.
- The dimension-switch UI is a searchable listbox (not a `menuitem`-role dropdown) — match options via `page.get_by_text(<label>, exact=True)`, not `get_by_role("menuitem")`.
- Only `src/reports/report-templates/new/Econet Infraco March Website Report.pptx` changes this session (replaced by the user-supplied 13-slide deck). No other report's template file changes.
- `rec_slide_idx = slide_count - 2` in `generate_report_2026`/`generate_quick_report` must keep working unmodified — do not hardcode slide indices for Recommendations/Thank You.
- Existing 7/8-slide reports must produce byte-identical slide content to before this change (no regressions) — verified by re-running existing behavior checks in Task 5.

---

### Task 1: Swap in the new infraco template and confirm slide detection

**Files:**
- Modify: `src/reports/report-templates/new/Econet Infraco March Website Report.pptx` (replace with `/Users/rakinzisilver/Downloads/infraco-24-July-2026.pptx`)
- Modify: `src/reports/generator_2026.py:89` (near `SEVEN_SLIDE_REPORTS`)
- Test: `tests/test_traffic_acquisition_slide.py` (new)

**Interfaces:**
- Produces: `_find_traffic_acquisition_slide_index(prs) -> int | None` — scans slide title placeholders (first non-empty paragraph of any shape with `has_text_frame`) for the literal text `"Traffic Acquisition"` (case-insensitive), searching slide indices 4 through 7 inclusive (0-based) to stay close to Page Performance without scanning the whole deck. Returns the found index or `None`.

- [ ] **Step 1: Copy the new template file into place**

```bash
cp "/Users/rakinzisilver/Downloads/infraco-24-July-2026.pptx" "/Users/rakinzisilver/Documents/GitHub/reports/src/reports/report-templates/new/Econet Infraco March Website Report.pptx"
```

- [ ] **Step 2: Write the failing test for slide detection**

Create `tests/test_traffic_acquisition_slide.py`:

```python
from pathlib import Path

from pptx import Presentation

from src.reports.generator_2026 import (
    TEMPLATES_2026,
    _find_traffic_acquisition_slide_index,
    get_templates_dir,
)


def test_finds_traffic_acquisition_slide_in_infraco_template():
    template_path = get_templates_dir() / TEMPLATES_2026["infraco"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx == 6


def test_returns_none_when_slide_absent():
    template_path = get_templates_dir() / TEMPLATES_2026["zimplats"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: FAIL with `ImportError: cannot import name '_find_traffic_acquisition_slide_index'`

- [ ] **Step 4: Implement `_find_traffic_acquisition_slide_index`**

Add near the top of `src/reports/generator_2026.py`, directly after the `SEVEN_SLIDE_REPORTS` line (line 89):

```python
def _find_traffic_acquisition_slide_index(prs) -> int | None:
    """Return the 0-based index of the 'Traffic Acquisition' slide, if present.

    Only searches indices 4-7 — the slide always sits between Page Performance
    and Search Performance in templates that have it, and restricting the scan
    avoids false-positive title matches elsewhere in the deck.
    """
    for idx in range(4, min(8, len(prs.slides))):
        slide = prs.slides[idx]
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            text = shape.text_frame.text.strip()
            if text.lower().startswith("traffic acquisition"):
                return idx
    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add "src/reports/report-templates/new/Econet Infraco March Website Report.pptx" src/reports/generator_2026.py tests/test_traffic_acquisition_slide.py
git commit -m "feat: swap infraco template to 13-slide deck, detect Traffic Acquisition slide"
```

---

### Task 2: GA4 navigation + table scraper for Traffic Acquisition

**Files:**
- Modify: `src/reports/generator_2026.py` (near `_ga4_explorer_url` at line 1067, `_goto_snapshot_explorer` at line 1099, and `_scrape_pages_table` at line 2073)
- Test: `tests/test_traffic_acquisition_slide.py` (append)

**Interfaces:**
- Consumes: `_ga4_report_base_url(url: str) -> str` (line 1054), `_ga4_snapshot_params(snapshot_url: str) -> str` (line 1061), `_ensure_expected_ga4_property(page, property_key)` (generator.py:132)
- Produces:
  - `_ga4_explorer_url(snapshot_url, report_kind)` extended to accept `report_kind="traffic_acquisition"`.
  - `_scrape_traffic_acquisition_table(page) -> tuple[list[dict], dict]` — returns `(rows, totals)` where each row is `{"source_medium": str, "sessions": int, "sessions_pct": str, "engaged_sessions": int, "engaged_sessions_pct": str, "engagement_rate": str, "avg_engagement_time": str, "events_per_session": str}`, and `totals` is `{"sessions": int, "engaged_sessions": int, "engagement_rate": str, "avg_engagement_time": str, "events_per_session": str}`.

- [ ] **Step 1: Write the failing test for table parsing**

Append to `tests/test_traffic_acquisition_slide.py`:

```python
from src.reports.generator_2026 import _parse_traffic_acquisition_row


def test_parses_traffic_acquisition_row():
    row = _parse_traffic_acquisition_row(
        "\t1\tan / paid\t5,841 (36.81%)\t1,775 (37.06%)\t30.39%\t23s\t3.79\t22,125 (35.97%)\t0.00 (–)\t0%\t$0.00 (–)"
    )
    assert row == {
        "source_medium": "an / paid",
        "sessions": 5841,
        "sessions_pct": "36.81%",
        "engaged_sessions": 1775,
        "engaged_sessions_pct": "37.06%",
        "engagement_rate": "30.39%",
        "avg_engagement_time": "23s",
        "events_per_session": "3.79",
    }


def test_parse_traffic_acquisition_row_returns_none_for_non_data_line():
    assert _parse_traffic_acquisition_row("Rows per page:") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: FAIL with `ImportError: cannot import name '_parse_traffic_acquisition_row'`

- [ ] **Step 3: Implement the row parser**

Add directly above `_scrape_pages_table` (line 2073) in `src/reports/generator_2026.py`:

```python
def _parse_traffic_acquisition_row(line: str) -> dict | None:
    """Parse one data row from the Traffic Acquisition (Session source/medium) table.

    Expected shape (tab-separated, from page.locator('body').inner_text()):
    "\t1\tan / paid\t5,841 (36.81%)\t1,775 (37.06%)\t30.39%\t23s\t3.79\t22,125 (35.97%)\t0.00 (–)\t0%\t$0.00 (–)"
    """
    m = re.match(
        r"^\t\d+\t(.+?)\t([\d,]+)\s*\(([^)]+)\)\t([\d,]+)\s*\(([^)]+)\)\t([\d.]+%)\t(\S+(?:\s\S+)?)\t([\d.]+)\t",
        line,
    )
    if not m:
        return None
    return {
        "source_medium": m.group(1).strip(),
        "sessions": int(m.group(2).replace(",", "")),
        "sessions_pct": m.group(3),
        "engaged_sessions": int(m.group(4).replace(",", "")),
        "engaged_sessions_pct": m.group(5),
        "engagement_rate": m.group(6),
        "avg_engagement_time": m.group(7),
        "events_per_session": m.group(8),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Extend `_ga4_explorer_url` for the `traffic_acquisition` report kind**

In `src/reports/generator_2026.py`, inside `_ga4_explorer_url` (line 1067), add a new branch before the `else: raise ValueError(...)` at line 1092:

```python
    elif report_kind == "traffic_acquisition":
        report_id = "lifecycle-traffic-acquisition-v2"
        params["_r.explorerCard..selmet"] = '["sessions"]'
        params["_r.explorerCard..seldim"] = '["sessionSourceMedium"]'
        query_parts = {
            "r": report_id,
            "params": "&".join(f"{key}={value}" for key, value in params.items()),
        }
```

Note: unlike `countries`/`pages`, this report kind has no `ruid`/`collectionId` query param — confirmed from the live-captured URL, which only carries `params` and `r`.

- [ ] **Step 6: Update `_goto_snapshot_explorer`'s confirmation check**

In `_goto_snapshot_explorer` (line 1099), the `page.wait_for_function` at line 1110 checks for `r=user-demographics-detail` or `r=all-pages-and-screens`. Update the JS to also accept the new report kind:

```python
            page.wait_for_function(
                """
                ({ reportKind }) => {
                    const href = window.location.href;
                    const expected = reportKind === 'countries'
                        ? 'r=user-demographics-detail'
                        : reportKind === 'pages'
                        ? 'r=all-pages-and-screens'
                        : 'r=lifecycle-traffic-acquisition-v2';
                    return href.includes('/reports/explorer') &&
                           href.includes(expected) &&
                           href.includes('date00%3D') &&
                           href.includes('date01%3D') &&
                           !href.includes('/reports/start');
                }
                """,
                arg={"reportKind": report_kind},
                timeout=35000,
            )
```

- [ ] **Step 7: Implement `_scrape_traffic_acquisition_table`**

Add directly after `_scrape_pages_table`'s closing (find the function ending before `_switch_dimension_to_page_path` usage resumes — insert right after the `_scrape_countries_table` function at line 2070, before `_scrape_pages_table` at line 2073):

```python
def _scrape_traffic_acquisition_table(page) -> tuple[list[dict], dict]:
    """Scrape the Traffic Acquisition (Session source/medium) table.

    Returns (rows, totals) — rows are up to 10 channel breakdown entries,
    totals holds the aggregate Total row's sessions/engaged_sessions/
    engagement_rate/avg_engagement_time/events_per_session.
    """
    rows: list[dict] = []
    totals: dict = {}

    body = page.locator("body").inner_text()
    lines = body.splitlines()

    for i, line in enumerate(lines):
        # The table's Total row is the tab-wrapped "\tTotal\t" line, distinct from
        # the plain "Total" legend entry that appears earlier in the chart legend.
        if line == "\tTotal\t" and i + 13 < len(lines):
            try:
                totals = {
                    "sessions": int(lines[i + 1].replace(",", "")),
                    "engaged_sessions": int(lines[i + 4].replace(",", "")),
                    "engagement_rate": lines[i + 7],
                    "avg_engagement_time": lines[i + 10],
                    "events_per_session": lines[i + 13],
                }
            except (ValueError, IndexError):
                totals = {}
            break

    for line in lines:
        parsed = _parse_traffic_acquisition_row(line)
        if parsed:
            rows.append(parsed)

    return rows, totals


def _open_traffic_acquisition_report(page, report_name: str, snapshot_url: str):
    """Navigate from an open snapshot page to the Traffic Acquisition report,
    switched to the 'Session source / medium' dimension. Returns the page."""
    page = _goto_snapshot_explorer(page, report_name, snapshot_url, "traffic_acquisition")
    page.wait_for_timeout(3000)

    _dismiss_playwright_overlays(page)
    button = page.locator("button[data-guidedhelpid='table-dimension-picker']").first
    button.wait_for(state="visible", timeout=8000)
    button.click(force=True)
    page.wait_for_timeout(1500)

    option = page.get_by_text("Session source / medium", exact=True).first
    option.wait_for(state="visible", timeout=5000)
    option.click()
    page.wait_for_timeout(3000)
    page.locator("th.cdk-column-__row_index__").first.wait_for(state="visible", timeout=10000)
    return page
```

- [ ] **Step 8: Run the full test file to make sure nothing regressed**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: PASS (4 passed)

- [ ] **Step 9: Commit**

```bash
git add src/reports/generator_2026.py tests/test_traffic_acquisition_slide.py
git commit -m "feat: add GA4 navigation and table scraper for traffic acquisition"
```

---

### Task 3: Paragraph builder and slide filler

**Files:**
- Modify: `src/reports/generator_2026.py` (near `_page_perf_paras` at line 607 and `_build_slide5` at line 1790)
- Test: `tests/test_traffic_acquisition_slide.py` (append)

**Interfaces:**
- Consumes: `_gemini_paras_batch(raws: list[str]) -> list[str]` (line 126), `_fill_text_run(para, new_text: str) -> None` (generator.py:1317), `_fill_paragraph_slots(shape, values, *, bold_words=None, clear_extra=False, skip_first=0) -> bool` (line 1528), `_replace_picture_with_fallback(slide, image_path, *, candidate_names=(), min_left_emu=None, exclude_names=None, slot_label="picture") -> bool` (line 1399)
- Produces:
  - `_traffic_acquisition_paras(rows: list[dict], totals: dict) -> tuple[str, str, str, str, str]` — `(subtitle, para1, para2, para3, para4)`.
  - `_SLIDE_TRAFFIC_ACQ_PICTURE: dict[str, str]` module-level dict, seeded `{"infraco": "Picture 32"}`.
  - `_build_slide_traffic_acquisition(slide, rows: list[dict], totals: dict, screenshots: dict, report_name: str = "") -> None`.

- [ ] **Step 1: Write the failing test for paragraph building**

Append to `tests/test_traffic_acquisition_slide.py`:

```python
from src.reports.generator_2026 import _traffic_acquisition_paras


def test_traffic_acquisition_paras_uses_top_two_channels(monkeypatch):
    from src.reports import generator_2026

    monkeypatch.setattr(
        generator_2026, "_gemini_paras_batch", lambda raws: [r for r in raws]
    )

    rows = [
        {
            "source_medium": "an / paid", "sessions": 1967, "sessions_pct": "46.7%",
            "engaged_sessions": 564, "engaged_sessions_pct": "41.93%",
            "engagement_rate": "28.67%", "avg_engagement_time": "22s",
            "events_per_session": "3.70",
        },
        {
            "source_medium": "fb / paid", "sessions": 1138, "sessions_pct": "27.02%",
            "engaged_sessions": 312, "engaged_sessions_pct": "23.2%",
            "engagement_rate": "27.42%", "avg_engagement_time": "20s",
            "events_per_session": "3.86",
        },
    ]
    totals = {
        "sessions": 4212, "engaged_sessions": 1345, "engagement_rate": "31.93%",
        "avg_engagement_time": "24s", "events_per_session": "3.86",
    }

    subtitle, para1, para2, para3, para4 = _traffic_acquisition_paras(rows, totals)
    assert "an / paid" in subtitle
    assert "46.7%" in subtitle
    assert "1,967" in para1
    assert "fb / paid" in para2
    assert "4,212" in para4


def test_traffic_acquisition_paras_empty_rows_returns_blank():
    result = _traffic_acquisition_paras([], {})
    assert result == ("", "", "", "", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: FAIL with `ImportError: cannot import name '_traffic_acquisition_paras'`

- [ ] **Step 3: Implement `_traffic_acquisition_paras`**

Add directly before `_build_slide6` (line 1879) in `src/reports/generator_2026.py`:

```python
def _traffic_acquisition_paras(rows: list[dict], totals: dict) -> tuple[str, str, str, str, str]:
    """Traffic Acquisition slide — subtitle + 4 narrative paragraphs from real data."""
    if not rows:
        return ("", "", "", "", "")

    top = rows[0]
    second = rows[1] if len(rows) > 1 else None

    raw_subtitle = (
        f"{top['source_medium'].title()}"
        + (f" and {second['source_medium'].title()}" if second else "")
        + f" lead Traffic Acquisition engagement with {top['sessions_pct']}"
        + (f" and {second['sessions_pct']}" if second else "")
        + " respectively"
    )

    raw_para1 = (
        f"Paid traffic remains a primary source of website activity, with {top['source_medium']} "
        f"generating {top['sessions']:,} sessions, accounting for {top['sessions_pct']} of total sessions. "
        f"Its {top['engagement_rate']} engagement rate and {top['avg_engagement_time']} average engagement "
        f"time show that it attracts substantial traffic, although user interaction remains moderate."
    )

    if second:
        raw_para2 = (
            f"{second['source_medium']} is the second-largest source with {second['sessions']:,} sessions, "
            f"but its {second['engagement_rate']} engagement rate and {second['avg_engagement_time']} average "
            f"engagement time indicate limited interaction relative to its traffic volume."
        )
    else:
        raw_para2 = "No secondary traffic source was recorded with comparable volume during this period."

    organic_rows = [r for r in rows if "organic" in r["source_medium"].lower()]
    if organic_rows:
        organic = max(organic_rows, key=lambda r: r["sessions"])
        raw_para3 = (
            f"Organic search produced strong traffic quality. {organic['source_medium']} achieved a "
            f"{organic['engagement_rate']} engagement rate, an average engagement time of "
            f"{organic['avg_engagement_time']}, and {organic['events_per_session']} events per session."
        )
    else:
        raw_para3 = (
            "Organic channels contributed a smaller share of sessions during this period, with paid "
            "channels driving the majority of traffic volume."
        )

    raw_para4 = (
        f"Overall, the website generated {totals.get('sessions', 0):,} sessions and "
        f"{totals.get('engaged_sessions', 0):,} engaged sessions, with an overall engagement rate of "
        f"{totals.get('engagement_rate', 'N/A')}. While paid campaigns drive most traffic volume, "
        f"organic channels continue to deliver higher-quality engagement per session."
    )

    return tuple(_gemini_paras_batch([raw_subtitle, raw_para1, raw_para2, raw_para3, raw_para4]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Add the picture-name map and slide builder**

Add directly after `_SLIDE6_SEARCH_CONSOLE_PICTURE` (line 1499) in `src/reports/generator_2026.py`:

```python
_SLIDE_TRAFFIC_ACQ_PICTURE: dict[str, str] = {
    "infraco": "Picture 32",
}
```

Add directly after `_build_slide5` (ends at line 1828, before `_search_perf_paras` at line 1830):

```python
def _build_slide_traffic_acquisition(
    slide, rows: list[dict], totals: dict, screenshots: dict, report_name: str = "",
) -> None:
    """Fill the Traffic Acquisition slide: subtitle, narrative, and table screenshot."""
    if rows:
        subtitle, para1, para2, para3, para4 = _traffic_acquisition_paras(rows, totals)
        source_medium_names = {r["source_medium"] for r in rows}

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue

            if shape.name == "object 3":
                content_paras = [p for p in shape.text_frame.paragraphs if p.text.strip()]
                if content_paras:
                    _fill_text_run(content_paras[0], subtitle)

            elif shape.name == "object 7":
                _fill_paragraph_slots(
                    shape,
                    [para1, para2, para3, para4],
                    bold_words=source_medium_names,
                    clear_extra=True,
                    skip_first=1,
                )

    if "traffic_acquisition_table" in screenshots:
        pic_name = _SLIDE_TRAFFIC_ACQ_PICTURE.get(report_name)
        _replace_picture_with_fallback(
            slide,
            screenshots["traffic_acquisition_table"],
            candidate_names=(pic_name,) if pic_name else (),
            slot_label=f"{report_name} traffic acquisition table",
        )
```

- [ ] **Step 6: Run the full test file**

Run: `uv run pytest tests/test_traffic_acquisition_slide.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add src/reports/generator_2026.py tests/test_traffic_acquisition_slide.py
git commit -m "feat: add traffic acquisition paragraph builder and slide filler"
```

---

### Task 4: Wire the capture step into `capture_2026` and both pipeline entry points

**Files:**
- Modify: `src/reports/generator_2026.py` (`capture_2026` at line 1173, `generate_report_2026` at line 2959, `generate_quick_report` at line 3023)

**Interfaces:**
- Consumes: `_open_traffic_acquisition_report(page, report_name, snapshot_url)`, `_scrape_traffic_acquisition_table(page)`, `_build_slide_traffic_acquisition(...)`, `_find_traffic_acquisition_slide_index(prs)`.
- Produces: `capture_2026` return tuple grows from 8 to 10 elements: `(screenshots, home_metrics, snapshot_metrics, page_views, pages_data, site_total_views, countries_data, search_metrics, traffic_acquisition_rows, traffic_acquisition_totals)`.

- [ ] **Step 1: Add the capture step inside `capture_2026`**

In `src/reports/generator_2026.py`, `capture_2026` (line 1173): add `traffic_acquisition_rows: list[dict] = []` and `traffic_acquisition_totals: dict = {}` to the local variable block (after `search_metrics: dict = {}` at line 1197), and change the return type annotation on line 1178 to `-> tuple[dict[str, Path], dict, dict, dict, list, int, list, dict, list, dict]`.

Insert this block directly after the "Pages and screens" try/except (ends at line 1355), before the "Google Search Console" block (line 1357):

```python
            # --- Traffic acquisition: screenshot + scrape channel breakdown ---
            _stage("Capturing traffic acquisition data...")
            try:
                page = _return_to_snapshot_dashboard(page, report_name, snapshot_dashboard_url)
                page = _open_traffic_acquisition_report(page, report_name, snapshot_dashboard_url)
                row_num_col = page.locator("th.cdk-column-__row_index__").first
                end_col = page.locator("th.cdk-column-DEFAULT-eventsPerSession").first
                table = page.locator("table.adv-table").first
                row_num_col.wait_for(state="visible", timeout=10000)
                start_box = row_num_col.bounding_box()
                end_box = end_col.bounding_box()
                table_box = table.bounding_box()
                clip = {
                    "x": start_box["x"],
                    "y": table_box["y"],
                    "width": (end_box["x"] + end_box["width"]) - start_box["x"],
                    "height": table_box["height"],
                }
                path = out_dir / "traffic_acquisition_table.png"
                page.screenshot(path=str(path), clip=clip, full_page=True)
                screenshots["traffic_acquisition_table"] = path

                traffic_acquisition_rows, traffic_acquisition_totals = _scrape_traffic_acquisition_table(page)
                page = _return_to_snapshot_dashboard(page, report_name, snapshot_dashboard_url)
            except Exception as e:
                logger.warning("[2026] Traffic acquisition capture failed for %s: %s", report_name, e)
```

Update the final `return` statement of `capture_2026` (search for the return at the end of the function, after the `finally` block) to include the two new values:

```python
    return (
        screenshots, home_metrics, snapshot_metrics, page_views,
        pages_data, site_total_views, countries_data, search_metrics,
        traffic_acquisition_rows, traffic_acquisition_totals,
    )
```

- [ ] **Step 2: Update `generate_report_2026`'s unpacking and slide build call**

In `generate_report_2026` (line 2959), update the unpacking at line 2976:

```python
    screenshots, home_metrics, snapshot_metrics, page_views, pages_data, site_total_views, countries_data, search_metrics, traffic_acquisition_rows, traffic_acquisition_totals = capture_2026(
        report_name, start_date, end_date, _stage_callback=_stage_callback
    )
```

After loading the template and computing `slide_count` (line 2984), add the detection call:

```python
    traffic_acq_idx = _find_traffic_acquisition_slide_index(prs)
```

Insert the build call directly after the `_build_slide5` call (line 3001), before the `if not is_7_slide and slide_count >= 8:` block (line 3003):

```python
    if traffic_acq_idx is not None:
        _stage(f"Building slide {traffic_acq_idx + 1} up to complete...")
        _build_slide_traffic_acquisition(
            prs.slides[traffic_acq_idx], traffic_acquisition_rows, traffic_acquisition_totals,
            screenshots, report_name=report_name,
        )
```

- [ ] **Step 3: Update `generate_quick_report`'s unpacking and slide build call**

In `generate_quick_report` (line 3023), apply the identical change to the unpacking at line 3053 and add the same `traffic_acq_idx` detection (after line 3059's `slide_count = len(prs.slides)`) and build call (after the `_build_slide5` call at line 3075, before the `if not is_7_slide...` block at line 3077).

- [ ] **Step 4: Manual verification — run the full pipeline for infraco**

Run: `uv run python -c "
from src.reports.generator_2026 import generate_report_2026
generate_report_2026('infraco', '24 June 2026 - 24 July 2026', '27 July 2026', 'Jun 24, 2026', 'Jul 24, 2026')
"`

Expected: Completes without raising, logs include `Building slide 7 up to complete...` (traffic_acq_idx=6, 1-indexed in the log message), and the output pptx in `artifacts/output/` has real scraped channel data in slide 6's `object 3`/`object 7` text and a fresh table screenshot in place of `Picture 32`. Open the file and visually confirm.

- [ ] **Step 5: Run the existing test suite to confirm no regressions**

Run: `uv run pytest tests/ -v`
Expected: All prior tests (test_schemas_quick_report.py, test_slugify.py) plus the new test_traffic_acquisition_slide.py pass.

- [ ] **Step 6: Commit**

```bash
git add src/reports/generator_2026.py
git commit -m "feat: wire traffic acquisition capture and slide build into both pipeline entry points"
```

---

### Task 5: Regression check for unaffected reports

**Files:**
- None modified — verification only.

- [ ] **Step 1: Confirm `_find_traffic_acquisition_slide_index` returns `None` for all other 9 templates**

Run:
```bash
uv run python -c "
from pptx import Presentation
from src.reports.generator_2026 import TEMPLATES_2026, _find_traffic_acquisition_slide_index, get_templates_dir
for name, path in TEMPLATES_2026.items():
    prs = Presentation(str(get_templates_dir() / path))
    idx = _find_traffic_acquisition_slide_index(prs)
    print(name, '->', idx)
"
```
Expected: `infraco -> 6`, every other report `-> None`.

- [ ] **Step 2: Run one non-infraco report end-to-end to confirm untouched behavior**

Run: `uv run python -c "
from src.reports.generator_2026 import generate_report_2026
generate_report_2026('zimplats', '24 June 2026 - 24 July 2026', '27 July 2026', 'Jun 24, 2026', 'Jul 24, 2026')
"`

Expected: Completes exactly as it did before this change — no `Building slide` log line referencing traffic acquisition, `traffic_acq_idx=None` means the new block is skipped entirely.

- [ ] **Step 3: Clean up exploratory script**

The `dump_snapshot_html.py` script at the repo root was exploratory (used to confirm GA4 selectors before writing this plan). Decide with the user whether to keep it as a standing debug utility or remove it:

```bash
git status --short  # confirm it's still untracked
```

If the user wants it removed: `rm dump_snapshot_html.py`. If kept, `git add dump_snapshot_html.py` and commit separately with a clear message that it's a debug/exploration tool.
