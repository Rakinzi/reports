# Traffic Acquisition Slide — Design

## Context

`generator_2026.py` drives the monthly client report pipeline via `TEMPLATES_2026`
(per-report `.pptx` files) and a fixed sequence of `_build_slideN` functions keyed
by 0-based slide index. All current templates are 7 or 8 slides: Cover, Executive
Summary, Site Overview, Geographic Performance, Page Performance, [Search
Performance], Recommendations, Thank You.

The user supplied a newer infraco deck (`infraco-24-July-2026.pptx`, 13 slides)
that adds five slides not yet supported by the pipeline: Overview, Traffic
Acquisition, Top Queries, SEO, Uptime and System Reliability. This design covers
**only Traffic Acquisition**. The other four are out of scope for this session and
will each get their own brainstorm/design pass later.

`generator_2026.py` remains the primary pipeline for the 10 named monthly
reports (confirmed with user — not migrating this to the newer config-driven
`template_runner.py` system).

## Confirmed GA4 navigation (verified live against the infraco property)

From an already-open Reports Snapshot page:

1. Click `span.view-link-text` with text "View traffic acquisition" → lands on
   `.../reports/explorer?...&r=lifecycle-traffic-acquisition-v2`, default
   dimension "Session primary channel group (Default Channel Group)".
2. This is a GA4 Explore-based report, not a plain report table — its dimension
   picker is a **searchable listbox**, not the `menuitem`-based dropdown used by
   `_switch_dimension_to_page_path`. Open it via
   `button[data-guidedhelpid='table-dimension-picker']`, then click the option
   via `page.get_by_text("Session source / medium", exact=True)` (confirmed
   working; `get_by_role("menuitem")` does NOT match here).
3. Resulting table matches the existing slide's screenshot exactly: rows like
   `an / paid`, `fb / paid`, `google / cpc`, `(direct) / (none)`,
   `google / organic`, with columns Sessions, Engaged sessions, Engagement rate,
   Avg engagement time per session, Events per session, Event count, Key
   events, Session key event rate, Total revenue.

Reference dumps saved during exploration (kept for future selector work):
`artifacts/ga4_html/infraco_traffic_acquisition*.html` and
`infraco_traffic_acquisition_source_medium_body_text.txt`.

## New code in `generator_2026.py`

1. **`_open_traffic_acquisition_report(page, report_name)`**
   Given an already-open snapshot page: click "View traffic acquisition",
   `_leave_ga4_start_page(page, report_name, "/reports/overview")`,
   `_ensure_expected_ga4_property`, then switch dimension to "Session source /
   medium" per the sequence above.

2. **`_scrape_traffic_acquisition_table(page) -> tuple[list[dict], dict]`**
   Parse `table.adv-table tbody tr` (same cell-cleaning helpers as
   `_scrape_pages_table`) into up to 10 rows of:
   `{source_medium, sessions, sessions_pct, engaged_sessions,
   engaged_sessions_pct, engagement_rate, avg_engagement_time,
   events_per_session}`, plus a `totals` dict from the Total row
   (`sessions, engaged_sessions, engagement_rate, avg_engagement_time,
   events_per_session`).

3. **Screenshot capture** — reuse the clip-box technique from
   `_capture_slide5_data` (bounding boxes of first/last header cells + table),
   stored as `screenshots["traffic_acquisition_table"]`.

4. **`_traffic_acquisition_paras(traffic_data, totals) -> tuple[str, str, str, str, str]`**
   Build subtitle + 4 raw narrative strings from the real top-2 channels and
   totals (same shape as `_search_perf_paras`), then run through
   `_gemini_paras_batch(...)` for paraphrasing.

5. **`_build_slide_traffic_acquisition(slide, traffic_data, totals, screenshots, report_name)`**
   - `object 3` → subtitle (single content paragraph, `_fill_text_run`)
   - `object 7` → 4 narrative paragraphs via `_fill_paragraph_slots`
   - Picture → `_replace_picture_with_fallback` using a new
     `_SLIDE_TRAFFIC_ACQ_PICTURE: dict[str, str]` per-report picture-name map
     (seeded with `infraco: "Picture 32"`), falling back to
     largest-picture-on-slide for reports not yet in the map.

## Wiring

- Detect the slide's presence and index by scanning slide title placeholders
  for the text "Traffic Acquisition" within slides 5–7 (0-based), rather than
  hardcoding index 6. If not found, skip — existing 7/8-slide templates are
  unaffected.
- Call the scrape + `_build_slide_traffic_acquisition` step conditionally,
  inserted after the Page Performance step and before the Search Performance /
  Recommendations steps, in both `generate_report_2026()` and
  `generate_quick_report()`.
- `rec_slide_idx = slide_count - 2` already derives from `slide_count`, so
  Recommendations/Thank You keep landing correctly on 9-, 12-, or 13-slide
  decks without further change.

## Template change

Replace `src/reports/report-templates/new/Econet Infraco March Website Report.pptx`
with the user-supplied 13-slide `infraco-24-July-2026.pptx` (path updated in
`TEMPLATES_2026["infraco"]`). Only Traffic Acquisition gets live-generated
content this session; Overview, Top Queries, SEO, and Uptime slides retain
their static July text until built in future sessions — acceptable since the
title-scan detection means only Traffic Acquisition is touched programmatically.

Other 9 reports' templates are untouched.

## Out of scope (future sessions)

- Overview slide (new field, needs its own copy/data source design)
- Top Queries slide (likely GSC-query-table driven, separate from existing
  Search Performance slide)
- SEO slide (Google search-results screenshot + narrative)
- Uptime and System Reliability slide (uptime monitor integration — new data
  source entirely)
- Migrating any of this to `template_runner.py`'s config-driven system

## Testing approach

Extend `test.py`'s pattern: a throwaway script (or an extended `test.py` mode)
that runs only the new traffic-acquisition scrape + slide build against the
live infraco property, saving a single-slide pptx for visual inspection,
mirroring how slide 5 was validated.
