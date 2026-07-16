# Quick Report: ad-hoc GA4 property reports

## Problem

Every report today is tied to a hardcoded slug (`econet`, `ecocash`, etc.) with a fixed GA4
property ID (`GA4_PROPERTIES` in `generator.py`) and a fixed client-specific `.pptx` template
(`TEMPLATES_2026` in `generator_2026.py`). Onboarding a brand-new client currently requires
either adding new hardcoded dict entries and a bespoke template, or going through the full
custom-template upload + shape-mapping flow (`/templates/upload`).

The user wants a fast path: paste a GA4 property ID, a client name, and dates, and get a report
back — no PPTX upload, no shape mapping.

## Approach

Reuse one existing template (`Delta Website Report - March .pptx`) as a generic base for every
ad-hoc client. Reuse the existing GA4-scraping engine unmodified by injecting the ad-hoc
property ID into the same `GA4_PROPERTIES` dict the engine already reads from — the same trick
`_switch_ga4_property_by_id()` already uses for the custom-template path (`generator.py:376`).
Reuse the existing `_apply_slide1_overrides()` post-processing step (`app.py`) to stamp the
client name (and optional logo) onto slide 1, exactly as it already does for retries on
hardcoded reports.

This keeps the change small: one new backend function, one new endpoint, one new frontend
dialog. No changes to the scraping engine, slide builders, or DB schema.

## Design

### Frontend: "Quick Report" dialog

A new **Quick Report** button sits next to the existing **Generate Report** button on the
dashboard. It opens a separate, dedicated dialog (not a mode of the existing dialog):

- **GA4 Property ID** (text input, numeric, required) — e.g. `523115644`
- **Client Name** (text input, required) — e.g. `Union Hardware`
- **GSC Site URL** (text input, optional) — e.g. `https://unionhardware.co.zw/`
- **Start Date / End Date / Report Date** (same date inputs as the existing dialog, same
  client-side formatting to GA4-picker format and long-form date range)
- **Slide 1 Logo** (optional file upload, same as the existing dialog)

Submits `POST /reports/generate-quick` with:
```json
{
  "ga4_property_id": "523115644",
  "client_name": "Union Hardware",
  "gsc_url": "",
  "date_range": "1 February 2026 - 28 February 2026",
  "report_date": "03 March 2026",
  "start_date": "Feb 1, 2026",
  "end_date": "Feb 28, 2026",
  "slide1_logo_data_url": "",
  "slide1_logo_filename": ""
}
```

Response is the same `{ id, status: "pending" }` shape as `/reports/generate`; the frontend
reuses the existing `pollReport()` / `refreshReports()` machinery unchanged. Reports created
this way show up in the same "All Reports" table as everything else — the row just displays
the auto-generated slug (e.g. `union_hardware`) if no matching entry exists in `reportOptions`,
which already degrades gracefully (`+page.svelte:474`).

### Backend: validation and slug generation

New Pydantic model in `schemas.py`:

```python
class GenerateQuickReportRequest(BaseModel):
    ga4_property_id: str
    client_name: str
    gsc_url: str = ""
    date_range: str
    report_date: str
    start_date: str
    end_date: str
    slide1_logo_data_url: str = ""
    slide1_logo_filename: str = ""
```

Validators mirror `GenerateReportRequest`: dates must match the GA4 picker format and not be in
the future; start must not be after end. Additionally:
- `ga4_property_id` must be non-empty and numeric (`str.isdigit()`).
- `client_name` must be non-empty after `.strip()`.

Slug generation (in `app.py`, alongside the new endpoint):
```python
def _slugify_client_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "custom_report"
```
No uniqueness enforcement needed — `reports.report_name` has no unique constraint, and reusing
a slug across multiple Quick Reports for the same client (e.g. rerunning next month) is exactly
the existing convention for hardcoded reports too.

### Backend: `generate_quick_report()` in `generator_2026.py`

New function, same signature shape as `generate_report_2026` plus the two new inputs:

```python
def generate_quick_report(
    report_name: str,       # the auto-generated slug
    client_name: str,       # display name for slide 1
    ga4_property_id: str,
    gsc_url: str,
    date_range: str,
    report_date: str,
    start_date: str,
    end_date: str,
    _stage_callback=None,
) -> Path:
```

Behavior:
1. Temporarily register the ad-hoc property (and GSC URL, if given) so the existing engine
   picks them up by slug:
   ```python
   from .generator import GA4_PROPERTIES
   GA4_PROPERTIES[report_name] = ga4_property_id
   if gsc_url:
       GSC_URLS[report_name] = gsc_url
   try:
       ...
   finally:
       GA4_PROPERTIES.pop(report_name, None)
       GSC_URLS.pop(report_name, None)
   ```
2. Run `capture_2026(report_name, start_date, end_date, _stage_callback)` unmodified — it reads
   the property via `_switch_ga4_property_via_search(page, report_name)`, which resolves through
   `GA4_PROPERTIES[report_name]` exactly like any hardcoded client.
3. Load the fixed base template: `TEMPLATES_DIR / TEMPLATES_2026["delta"]`
   (`"Delta Website Report - March .pptx"`), regardless of `report_name`.
4. Determine slide count / 7-slide mode from whether `gsc_url` was provided:
   `is_7_slide = not gsc_url` (skips slide 6 exactly like `SEVEN_SLIDE_REPORTS` clients today).
5. Run the same `_build_slide1` .. `_build_slide6` + recommendations sequence as
   `generate_report_2026`, in the same order, with the same stage callbacks.
6. Save to `OUTPUT_DIR / f"{report_name}-{report_date.replace(' ', '-')}.pptx"` — same naming
   convention as every other report.

### Backend: slide 1 branding

After `generate_quick_report()` returns, `app.py`'s new endpoint handler calls the existing
`_apply_slide1_overrides()` unconditionally (not gated behind a non-empty check, since Client
Name is always present for Quick Report):

```python
logo_path = _write_logo_override(report_id, body.slide1_logo_data_url, body.slide1_logo_filename)
_apply_slide1_overrides(
    Path(output_path),
    report_name=slug,
    slide1_source_name="Delta",   # matches TEMPLATES_2026["delta"]'s source branding
    slide1_name=body.client_name.strip(),
    logo_path=logo_path,
)
```

This reuses the existing text-substitution logic that already looks for "Delta" (and
case variants) on slide 1 and swaps it for the given name, plus swaps the top-left logo image
if one was uploaded — identical to how `bancabc` already borrows Delta's template today
(`app.py:155-158`).

### Backend: new endpoint

```python
@app.post("/reports/generate-quick", status_code=202)
def post_generate_quick_report(body: GenerateQuickReportRequest):
    # same gemini_api_key_set / browser_available checks as /reports/generate
    slug = _slugify_client_name(body.client_name)
    report_id = create_report(slug, body.date_range, body.report_date)
    _cancel_flags[report_id] = threading.Event()
    _executor.submit(_run_generate_quick, report_id, slug, body)
    return JSONResponse({"id": report_id, "status": "pending"}, status_code=202)
```

`_run_generate_quick` mirrors `_run_generate`'s structure (stage callback, cancellation check,
try/except/finally updating the DB row), calling `generate_quick_report()` instead of
`generate_report_2026()`, then applying slide 1 overrides, then `update_report_completed`.

### Error handling

- Invalid/non-numeric property ID, empty client name, bad dates → 422 from Pydantic validation,
  surfaced in the dialog's error banner exactly like the existing dialog.
- GA4 property not found / no access during scraping → surfaces as a failed report with the
  underlying exception message, same as any existing report failure (visible via Retry button
  and Logs page) — no special-casing needed, this is the existing failure path.
- Cancellation mid-generation → same `_cancel_flags` / `InterruptedError` mechanism, unchanged.

## Out of scope

- No dedicated "Quick Reports" list or filter — they appear in the same reports table.
- No slug collision detection/renaming — duplicate slugs behave like existing report reruns.
- No support for multi-property/sectioned Quick Reports (that's what the full template-upload
  flow with property sections is for).
- No persistence of the ad-hoc property ID/GSC URL beyond the report's `date_range`/`report_date`
  fields already stored — rerunning requires re-entering the property ID (no "retry" support for
  Quick Reports in this iteration, since `retryReport()` only knows the existing dialog's shape).
