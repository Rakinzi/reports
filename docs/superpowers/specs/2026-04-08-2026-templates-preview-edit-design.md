# Design: 2026 Template Support + Preview & Edit

**Date:** 2026-04-08
**Status:** Approved

---

## Overview

Two independent but related features:
1. Support the new 2026 PPTX template format (located in `report-templates/new/`) with a dedicated generation pipeline
2. Add a Preview & Edit screen where users can view generated slides as images, edit text fields, and rewrite text with Gemini AI assistance

---

## Part 1 — 2026 Template Pipeline

### New Template Directory

All 2026 templates live in `src/reports/report-templates/new/`. The generator dispatches to `generate_report_2026()` when a `new/` template exists for the requested report name, otherwise falls back to the existing `generate_report()`.

### New Report Clients

Two new clients are added to the system:
- `dicomm` — Dicomm McCann
- `union_hardware` — Union Hardware

### Template Map (2026 format)

| Report Key | Template File |
|---|---|
| `econet` | `Econet February Website Report - Copy.pptx` |
| `econet_ai` | `Econet AI March Website Report.pptx` |
| `infraco` | `Econet Infraco March Website Report.pptx` |
| `ecocash` | `EcoCash March Website Report.pptx` |
| `cancer_serve` | `Cancerserve March Website Report.pptx` |
| `zimplats` | `Zimplats March Website Report.pptx` |
| `dicomm` | `Dicomm March Website Report.pptx` |
| ~~`union_hardware`~~ | Deferred — 3 branches, unique structure |

### GA4 Property IDs (new clients)

`dicomm` property ID: `382296904`. `union_hardware` is deferred (3 branches, unique structure).

### 2026 Slide Pipeline (8 slides)

| Slide | Name | Changes |
|---|---|---|
| 1 | Title | Replace date text (`"Month,YYYY"` pattern) |
| 2 | Executive Summary | Replace 3 KPI stat boxes (Active Users, New Visitors, CTR) + 3-para narrative via Gemini |
| 3 | Site Overview | Replace stat boxes (Total Active Users, New Users, Avg Engagement Time) + narrative paragraphs + line chart screenshot |
| 4 | Geographic Performance | Replace country bar chart (Picture) + narrative paragraphs via Gemini |
| 5 | Page Performance | Replace page views table screenshot + insight text paragraphs via Gemini |
| 6 | Search Performance | Replace screenshot + narrative paragraphs via Gemini (search console data) — **8-slide variants only** |
| 7 | Recommendations | Replace numbered items (1./2./3. pattern) via Gemini |
| 8 | Thank You | No changes |

**7-slide variants** (Zimplats, Dicomm): skip Slide 6 (Search Performance). Slides 6 and 7 become Recommendations and Thank You respectively.

### Text Replacement Strategy

Same as 2025 pipeline: match paragraphs by content keywords, preserve first run's XML formatting (`rPr`), replace text, remove extra runs.

Key content matchers for 2026:
- Slide 2 KPI boxes: match shapes by position/name containing numeric values like `"34K"`, `"94%"`, `"3.1%"`
- Slide 2 narrative: match paragraphs containing `"first-time users"` or `"under review"`
- Slide 3 narrative: match paragraphs containing `"reflects solid"` or `"new visitors"`
- Slide 4 narrative: match paragraphs containing `"dominant market"` or `"geographic"`
- Slide 5 insight: match paragraphs containing `"Overall Insight"` or `"drives the highest traffic"`
- Slide 6 narrative: match paragraphs containing `"impressions"` or `"click-through rate"`
- Slide 7 recs: match paragraphs starting with `"1."`, `"2."`, `"3."`

### Screenshot Map (2026)

| Slide Index | Screenshot | Shape Name |
|---|---|---|
| 2 (Slide 3) | Line chart (`home_chart`) | `Picture 18` |
| 3 (Slide 4) | Country bar chart (`country_chart`) | `Picture 10` |
| 4 (Slide 5) | Page views table (`pages_table`) | `Picture 13` |
| 5 (Slide 6) | Search console (`search_screenshot`) | `Picture 10` |

Shape names confirmed from template inspection. Variants may differ — use `shape_name` lookup with fallback to index.

---

## Part 2 — Preview & Edit Feature

### Backend Changes

#### Slide Rendering

After PPTX generation, convert each slide to a PNG using LibreOffice headless:

```bash
soffice --headless --convert-to png --outdir <slides_dir> <report.pptx>
```

LibreOffice must be installed on the system (bundled detection in Tauri, path config in settings). PNGs are saved to `artifacts/slides/{report_id}/slide_N.png`.

#### New API Endpoints

**`GET /reports/{id}/slides`**
Returns structured slide data:
```json
[
  {
    "slide_index": 0,
    "image_url": "/reports/1/slides/0/image",
    "fields": [
      { "field_id": "slide1_date", "label": "Report Date", "value": "March, 2026" }
    ]
  }
]
```

**`GET /reports/{id}/slides/{index}/image`**
Serves the PNG for a specific slide.

**`POST /reports/{id}/slides/{index}/rewrite`**
Request:
```json
{ "field_id": "slide3_narrative", "current_text": "...", "instruction": "make it shorter" }
```
Response:
```json
{ "rewritten_text": "..." }
```
Calls `gemini-2.5-flash` with the instruction + current text. Returns plain text only.

**`POST /reports/{id}/apply-edits`**
Request: dict of `{ field_id: new_text }` for all edited fields.
Skips GA4/screenshot capture — re-runs only the PPTX substitution step with the provided values, saves a new PPTX, updates the report record's `output_path`.
Response: `{ "output_path": "..." }`

#### DB Changes

Report record needs a `slides_dir` column (nullable path to rendered slide PNGs) and an `edits` column (nullable JSON storing last applied field values).

### Frontend Changes

#### New Route: `/reports/[id]/preview`

Split layout:
- **Left panel (60%):** Slide carousel — PNG image display with prev/next navigation, slide counter (`2 / 8`), zoom-fit to panel
- **Right panel (40%):** Editable fields for the current slide — each field has:
  - Label
  - `<textarea>` with current text
  - Instruction input placeholder: `"e.g. make it shorter, focus on new users"`
  - "Rewrite with AI" button — calls rewrite endpoint, streams result into textarea, shows spinner
- **Top bar:** "Save & Export" button — calls apply-edits then triggers PPTX download; "Back to Dashboard" link

#### Auto-open After Generation

When the poll detects `status === 'completed'`, navigate to `/reports/{id}/preview` instead of auto-downloading.

#### Table Row Actions (completed reports)

Add a "Preview & Edit" button alongside the existing "Save" button in each completed report row.

### Tauri Compatibility

All image URLs are relative to `apiBaseUrl` (already resolved via `resolveBackendContext()`). LibreOffice path is detected at startup — if not found, a warning is shown in the preview screen with a fallback message: "Install LibreOffice to enable slide preview."

---

## Files to Create / Modify

### Backend
- `src/reports/generator.py` — add `TEMPLATES_2026`, `GA4_PROPERTIES` entries for dicomm/union_hardware, `generate_report_2026()`, slide rendering function, format dispatch in `generate_report()`
- `src/reports/schemas.py` — add `dicomm`, `union_hardware` to `ReportName` literal
- `src/reports/api/` — add new slide endpoints
- `src/reports/db.py` — add `slides_dir`, `edits` columns to reports table

### Frontend
- `frontend/src/routes/reports/[id]/preview/+page.svelte` — new preview/edit page
- `frontend/src/routes/+page.svelte` — add "Preview & Edit" button to table rows, change poll completion behavior
- `frontend/src/lib/backend.ts` — add slide API types and fetch helpers
- `frontend/src/routes/settings/+page.svelte` — add LibreOffice path setting

---

## Out of Scope

- Union Hardware — deferred entirely (3 separate branch properties, 33-slide template with unique structure)
- `union_hardware` removed from `ReportName` and `TEMPLATES_2026`
- Search console data scraping (Slide 6) — depends on whether Search Console is accessible via GA4 session; implementation deferred to next iteration, screenshot placeholder used
- Real-time collaborative editing
