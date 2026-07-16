# Quick Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user generate a full report by entering just a GA4 property ID, a client name, and dates — no PPTX template upload required.

**Architecture:** Reuse the existing 2026 report-generation engine (`generator_2026.py`) unmodified by temporarily injecting the ad-hoc GA4 property ID (and optional GSC URL) into the same module-level dicts (`GA4_PROPERTIES`, `GSC_URLS`) the engine already reads from, keyed by an auto-generated slug. Always render against the fixed `"Delta Website Report - March .pptx"` base template, then reuse the existing `_apply_slide1_overrides()` post-processing step to rebrand slide 1 with the client's name (and optional logo). A new frontend "Quick Report" dialog and a new backend endpoint (`POST /reports/generate-quick`) wire it all together, reusing the existing reports table/polling/DB machinery untouched.

**Tech Stack:** Python 3.12, FastAPI, SQLite (stdlib `sqlite3`), python-pptx, Playwright (sync API), Svelte 5 / SvelteKit frontend (TypeScript), pytest (new dev dependency).

## Global Constraints

- Base template for every Quick Report is `TEMPLATES_2026["delta"]` (`"Delta Website Report - March .pptx"`), regardless of client — per the approved design spec.
- Slide 6 (Search Performance) renders only if a GSC Site URL was provided; otherwise the report is treated as 7-slide (matches existing `SEVEN_SLIDE_REPORTS` behavior).
- Slide 1 branding always runs for Quick Report (client name is required, not optional) — reuse `_apply_slide1_overrides()` unmodified, with `slide1_source_name="Delta"`.
- No new DB tables/columns — `reports.report_name` already has no uniqueness constraint, so the auto-slug needs no collision handling.
- No changes to the scraping engine (`generator.py`), slide builders, or existing `/reports/generate` endpoint — this is purely additive.
- Follow the existing codebase pattern of lazy in-function imports (e.g. `from .generator import GA4_PROPERTIES`) rather than top-level imports in `app.py`, matching every other handler in that file.

Full design spec: `docs/superpowers/specs/2026-07-16-quick-report-design.md`

---

## File Structure

- **Modify:** `src/reports/schemas.py` — add `GenerateQuickReportRequest` model + validators.
- **Create:** `src/reports/slugify.py` — small pure helper module for client-name → slug conversion (isolated because it's the one piece of genuinely new, easily-unit-testable logic; keeping it out of `app.py` means it can be tested without importing FastAPI/Playwright/DB at all).
- **Modify:** `src/reports/generator_2026.py` — add `generate_quick_report()` function.
- **Modify:** `src/reports/app.py` — add `POST /reports/generate-quick` endpoint + `_run_generate_quick()` background runner.
- **Modify:** `frontend/src/lib/backend.ts` — add `QuickReport` request type + `generateQuickReport()` helper (mirrors existing `fetchJson` usage).
- **Modify:** `frontend/src/routes/+page.svelte` — add "Quick Report" button + dedicated dialog.
- **Create:** `tests/test_slugify.py` — unit tests for the slug helper.
- **Create:** `tests/test_schemas_quick_report.py` — unit tests for `GenerateQuickReportRequest` validation.
- **Modify:** `pyproject.toml` — add `pytest` as a dev dependency.

---

### Task 1: Add pytest to the project

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: a working `uv run pytest` command for all later test tasks.

- [ ] **Step 1: Add pytest as a dev dependency**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports && uv add --dev pytest
```
Expected: `pyproject.toml` gets a `[dependency-groups]` (or `[tool.uv]` dev-dependencies) section listing `pytest`, and `uv.lock` is updated.

- [ ] **Step 2: Verify pytest runs with no tests yet**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports && uv run pytest --collect-only
```
Expected: exits with `no tests ran` (not an error) — confirms the pytest install and invocation work.

- [ ] **Step 3: Commit**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
git add pyproject.toml uv.lock
git commit -m "chore: add pytest as a dev dependency"
```

---

### Task 2: Client-name slugify helper

**Files:**
- Create: `src/reports/slugify.py`
- Test: `tests/test_slugify.py`

**Interfaces:**
- Produces: `slugify_client_name(name: str) -> str` — used by Task 4 (`app.py` endpoint).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_slugify.py`:
```python
from reports.slugify import slugify_client_name


def test_simple_name():
    assert slugify_client_name("Union Hardware") == "union_hardware"


def test_extra_whitespace_and_punctuation():
    assert slugify_client_name("  Union Hardware, Inc.  ") == "union_hardware_inc"


def test_already_lowercase_with_underscores():
    assert slugify_client_name("union_hardware") == "union_hardware"


def test_mixed_symbols_collapse_to_single_underscore():
    assert slugify_client_name("Union---Hardware!!!Zim") == "union_hardware_zim"


def test_empty_string_falls_back_to_default():
    assert slugify_client_name("") == "custom_report"


def test_only_punctuation_falls_back_to_default():
    assert slugify_client_name("!!!") == "custom_report"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/rakinzisilver/Documents/GitHub/reports && uv run pytest tests/test_slugify.py -v`
Expected: `ModuleNotFoundError: No module named 'reports.slugify'` (or import error) for every test.

- [ ] **Step 3: Implement the helper**

Create `src/reports/slugify.py`:
```python
"""Convert a free-text client name into a filesystem/DB-safe report slug."""

import re


def slugify_client_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "custom_report"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/rakinzisilver/Documents/GitHub/reports && uv run pytest tests/test_slugify.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
git add src/reports/slugify.py tests/test_slugify.py
git commit -m "feat: add client-name slugify helper for Quick Report"
```

---

### Task 3: `GenerateQuickReportRequest` schema + validation

**Files:**
- Modify: `src/reports/schemas.py`
- Test: `tests/test_schemas_quick_report.py`

**Interfaces:**
- Consumes: nothing new (uses the same `_GA4_DATE_FMT` constant already in `schemas.py:4`).
- Produces: `GenerateQuickReportRequest` — used by Task 4 (`app.py` endpoint) as the request body model.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schemas_quick_report.py`:
```python
import pytest
from pydantic import ValidationError

from reports.schemas import GenerateQuickReportRequest


def _valid_kwargs(**overrides):
    kwargs = dict(
        ga4_property_id="523115644",
        client_name="Union Hardware",
        gsc_url="",
        date_range="1 February 2026 - 28 February 2026",
        report_date="03 March 2026",
        start_date="Feb 1, 2026",
        end_date="Feb 28, 2026",
    )
    kwargs.update(overrides)
    return kwargs


def test_valid_request_passes():
    req = GenerateQuickReportRequest(**_valid_kwargs())
    assert req.ga4_property_id == "523115644"
    assert req.client_name == "Union Hardware"


def test_non_numeric_property_id_rejected():
    with pytest.raises(ValidationError, match="numeric"):
        GenerateQuickReportRequest(**_valid_kwargs(ga4_property_id="abc123"))


def test_empty_property_id_rejected():
    with pytest.raises(ValidationError, match="numeric"):
        GenerateQuickReportRequest(**_valid_kwargs(ga4_property_id=""))


def test_empty_client_name_rejected():
    with pytest.raises(ValidationError, match="client_name"):
        GenerateQuickReportRequest(**_valid_kwargs(client_name="   "))


def test_future_start_date_rejected():
    with pytest.raises(ValidationError, match="cannot be in the future"):
        GenerateQuickReportRequest(**_valid_kwargs(start_date="Jan 1, 2099"))


def test_start_after_end_rejected():
    with pytest.raises(ValidationError, match="must not be after"):
        GenerateQuickReportRequest(**_valid_kwargs(start_date="Feb 28, 2026", end_date="Feb 1, 2026"))


def test_gsc_url_optional_defaults_empty():
    req = GenerateQuickReportRequest(**_valid_kwargs(gsc_url=""))
    assert req.gsc_url == ""


def test_logo_fields_optional_default_empty():
    req = GenerateQuickReportRequest(**_valid_kwargs())
    assert req.slide1_logo_data_url == ""
    assert req.slide1_logo_filename == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/rakinzisilver/Documents/GitHub/reports && uv run pytest tests/test_schemas_quick_report.py -v`
Expected: `ImportError: cannot import name 'GenerateQuickReportRequest'` for every test.

- [ ] **Step 3: Implement the schema**

In `src/reports/schemas.py`, add after the existing `GenerateReportRequest` class (after line 51, before `class GenerateReportResponse`):
```python
class GenerateQuickReportRequest(BaseModel):
    ga4_property_id: str
    client_name: str
    gsc_url: str = ""
    date_range: str          # e.g. "1 February 2026 - 28 February 2026"
    report_date: str         # e.g. "03 March 2026"
    start_date: str          # GA4 picker format e.g. "Feb 1, 2026"
    end_date: str            # GA4 picker format e.g. "Feb 28, 2026"
    slide1_logo_data_url: str = ""
    slide1_logo_filename: str = ""

    @field_validator("ga4_property_id")
    @classmethod
    def property_id_must_be_numeric(cls, v: str) -> str:
        if not v.strip().isdigit():
            raise ValueError("ga4_property_id must be numeric")
        return v.strip()

    @field_validator("client_name")
    @classmethod
    def client_name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("client_name must not be blank")
        return v.strip()

    @field_validator("start_date", "end_date")
    @classmethod
    def dates_must_not_exceed_today(cls, v: str, info) -> str:
        try:
            parsed = dt.datetime.strptime(v, _GA4_DATE_FMT).date()
        except ValueError:
            raise ValueError(f"{info.field_name} must be in format 'Mon D, YYYY' (e.g. 'Feb 1, 2026')")
        if parsed > dt.date.today():
            raise ValueError(f"{info.field_name} '{v}' cannot be in the future (today is {dt.date.today()})")
        return v

    @model_validator(mode="after")
    def start_must_be_before_end(self) -> "GenerateQuickReportRequest":
        start = dt.datetime.strptime(self.start_date, _GA4_DATE_FMT).date()
        end = dt.datetime.strptime(self.end_date, _GA4_DATE_FMT).date()
        if start > end:
            raise ValueError(f"start_date '{self.start_date}' must not be after end_date '{self.end_date}'")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/rakinzisilver/Documents/GitHub/reports && uv run pytest tests/test_schemas_quick_report.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
git add src/reports/schemas.py tests/test_schemas_quick_report.py
git commit -m "feat: add GenerateQuickReportRequest schema with validation"
```

---

### Task 4: `generate_quick_report()` in `generator_2026.py`

**Files:**
- Modify: `src/reports/generator_2026.py`

**Interfaces:**
- Consumes: `capture_2026(report_name, start_date, end_date, _stage_callback)` (existing, `generator_2026.py:1132`), `TEMPLATES_DIR`, `TEMPLATES_2026` (existing module-level dict), `_build_slide1`..`_build_slide6`, `_build_recommendations_slide` (existing), `GA4_PROPERTIES` (imported from `.generator`), `GSC_URLS` (existing module-level dict in this file), `OUTPUT_DIR` (existing).
- Produces: `generate_quick_report(report_name: str, client_name: str, ga4_property_id: str, gsc_url: str, date_range: str, report_date: str, start_date: str, end_date: str, _stage_callback=None) -> Path` — used by Task 5 (`app.py`'s `_run_generate_quick`).

This task has no isolated unit test — it drives live Playwright/GA4 and can't run outside the full desktop app. It's verified in Task 6's end-to-end manual check instead. Read `generate_report_2026` (`generator_2026.py:2876-2932`) once more before starting so the step-for-step mirroring below is easy to sanity-check against it.

- [ ] **Step 1: Add the `generate_quick_report` function**

In `src/reports/generator_2026.py`, add this function immediately after `generate_report_2026` (after the existing function's closing lines, i.e. after line ~2932 where it does `logger.info("[2026] Saved report to %s", output_path)` and returns `output_path`):

```python
def generate_quick_report(
    report_name: str,
    client_name: str,
    ga4_property_id: str,
    gsc_url: str,
    date_range: str,
    report_date: str,
    start_date: str,
    end_date: str,
    _stage_callback=None,
) -> Path:
    """Ad-hoc report for any GA4 property, using the shared Delta-based template.

    Temporarily registers report_name -> ga4_property_id (and optionally -> gsc_url)
    into the same module-level dicts the rest of the 2026 pipeline already reads from,
    so capture_2026() and its helpers work completely unmodified.
    """
    from .generator import GA4_PROPERTIES

    def _stage(msg: str):
        if _stage_callback:
            _stage_callback(msg)
        logger.info("[2026][quick] Stage: %s", msg)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    GA4_PROPERTIES[report_name] = ga4_property_id
    if gsc_url:
        GSC_URLS[report_name] = gsc_url
    try:
        screenshots, home_metrics, snapshot_metrics, page_views, pages_data, site_total_views, countries_data, search_metrics = capture_2026(
            report_name, start_date, end_date, _stage_callback=_stage_callback
        )

        template_path = TEMPLATES_DIR / TEMPLATES_2026["delta"]
        prs = Presentation(str(template_path))
        slide_count = len(prs.slides)
        is_7_slide = not gsc_url

        perf_month = _performance_month(date_range)

        logger.info("[2026][quick] Building slides for %s (%d slides)", report_name, slide_count)

        _stage("Building slide 1 up to complete...")
        _build_slide1(prs.slides[0], perf_month, screenshots, report_name=report_name)
        _stage("Building slide 2 up to complete...")
        _build_slide2(prs.slides[1], home_metrics, snapshot_metrics, report_name, search_metrics)
        _stage("Building slide 3 up to complete...")
        _build_slide3(prs.slides[2], home_metrics, snapshot_metrics, report_name, screenshots)
        _stage("Building slide 4 up to complete...")
        _build_slide4(prs.slides[3], countries_data, screenshots, report_name=report_name)
        _stage("Building slide 5 up to complete...")
        _build_slide5(prs.slides[4], pages_data, screenshots, site_total_views, report_name=report_name)

        if not is_7_slide and slide_count >= 8:
            _stage("Building slide 6 up to complete...")
            _build_slide6(prs.slides[5], search_metrics, screenshots, report_name=report_name)

        rec_slide_idx = slide_count - 2
        _stage(f"Building slide {rec_slide_idx + 1} up to complete...")
        _build_recommendations_slide(prs.slides[rec_slide_idx], report_name=report_name)

        safe_name = report_name.replace("_", "-")
        output_path = OUTPUT_DIR / f"{safe_name}-{report_date.replace(' ', '-')}.pptx"
        prs.save(str(output_path))
        logger.info("[2026][quick] Saved report to %s", output_path)
        return output_path
    finally:
        GA4_PROPERTIES.pop(report_name, None)
        GSC_URLS.pop(report_name, None)
```

- [ ] **Step 2: Sanity-check the module imports cleanly**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports && uv run python -c "from reports.generator_2026 import generate_quick_report; print(generate_quick_report)"
```
Expected: prints something like `<function generate_quick_report at 0x...>` with no import errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
git add src/reports/generator_2026.py
git commit -m "feat: add generate_quick_report for ad-hoc GA4 property reports"
```

---

### Task 5: `POST /reports/generate-quick` endpoint

**Files:**
- Modify: `src/reports/app.py`

**Interfaces:**
- Consumes: `GenerateQuickReportRequest` (Task 3), `generate_quick_report()` (Task 4), `slugify_client_name()` (Task 2), existing `create_report`, `update_report_completed`, `update_report_failed`, `update_report_stage` (`db.py`), existing `_write_logo_override`, `_apply_slide1_overrides`, `_cancel_flags`, `_executor`, `get_runtime_status` (all already in `app.py`).
- Produces: `POST /reports/generate-quick` endpoint returning `{"id": int, "status": "pending"}` — used by Task 7 (frontend dialog).

No isolated unit test for this task (it's a thin FastAPI wiring layer over things already covered by Tasks 2–4, and exercising it end-to-end requires the live browser/GA4/Gemini stack). Verified manually in Task 6.

- [ ] **Step 1: Import the new pieces**

In `src/reports/app.py`, update the schemas import (currently line 28):
```python
from .schemas import AppSettingsUpdate, GenerateReportRequest, GenerateQuickReportRequest, HARDCODED_REPORT_NAMES
```

Add a new top-level import right after the existing `from .schemas import ...` line:
```python
from .slugify import slugify_client_name
```

- [ ] **Step 2: Add the background runner function**

Add this function in `src/reports/app.py` immediately after `_run_generate` (after its closing `finally: _cancel_flags.pop(report_id, None)` block, i.e. right before the line `app = FastAPI(title="Reports API")`):

```python
def _run_generate_quick(report_id: int, report_name: str, body: "GenerateQuickReportRequest"):
    cancel_flag = _cancel_flags.get(report_id)

    def stage_callback(stage: str) -> None:
        if cancel_flag and cancel_flag.is_set():
            raise InterruptedError("Report generation cancelled by user.")
        update_report_stage(report_id, stage)

    try:
        from .generator_2026 import generate_quick_report

        logger.info("Starting quick report generation for report_id=%s report_name=%s", report_id, report_name)
        update_report_stage(report_id, "Capturing GA4 data...")
        output_path = generate_quick_report(
            report_name=report_name,
            client_name=body.client_name,
            ga4_property_id=body.ga4_property_id,
            gsc_url=body.gsc_url,
            date_range=body.date_range,
            report_date=body.report_date,
            start_date=body.start_date,
            end_date=body.end_date,
            _stage_callback=stage_callback,
        )

        logo_path = _write_logo_override(report_id, body.slide1_logo_data_url, body.slide1_logo_filename)
        update_report_stage(report_id, "Applying slide 1 branding...")
        _apply_slide1_overrides(
            Path(output_path),
            report_name=report_name,
            slide1_source_name="Delta",
            slide1_name=body.client_name,
            logo_path=logo_path,
        )

        update_report_stage(report_id, "Finalising report...")
        update_report_completed(report_id, str(output_path))
        logger.info("Completed quick report generation for report_id=%s output_path=%s", report_id, output_path)
        update_report_slides_dir(report_id, "")
    except InterruptedError as e:
        update_report_failed(report_id, str(e))
        logger.info("Quick report generation cancelled for report_id=%s", report_id)
    except Exception as e:
        update_report_failed(report_id, str(e))
        logger.exception("Quick report generation failed for report_id=%s", report_id)
    finally:
        _cancel_flags.pop(report_id, None)
```

- [ ] **Step 3: Add the endpoint**

Add this immediately after the existing `post_generate_report` endpoint (after its `return JSONResponse({"id": report_id, "status": "pending"}, status_code=202)` line, before `@app.get("/reports")`):

```python
@app.post("/reports/generate-quick", status_code=202)
def post_generate_quick_report(body: GenerateQuickReportRequest):
    status = get_runtime_status()
    if not status["gemini_api_key_set"]:
        raise HTTPException(status_code=400, detail="Gemini API key is not configured")
    if not status["browser_available"]:
        raise HTTPException(
            status_code=400,
            detail="No compatible browser installation was found. Install Google Chrome, Microsoft Edge, or Chromium.",
        )

    slug = slugify_client_name(body.client_name)
    report_id = create_report(slug, body.date_range, body.report_date)
    _cancel_flags[report_id] = threading.Event()
    _executor.submit(_run_generate_quick, report_id, slug, body)
    return JSONResponse({"id": report_id, "status": "pending"}, status_code=202)
```

- [ ] **Step 4: Verify the app starts and the route is registered**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports && uv run python -c "
from reports.app import app
paths = [r.path for r in app.routes]
assert '/reports/generate-quick' in paths, paths
print('OK: /reports/generate-quick registered')
"
```
Expected: `OK: /reports/generate-quick registered` with no exceptions.

- [ ] **Step 5: Commit**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
git add src/reports/app.py
git commit -m "feat: add POST /reports/generate-quick endpoint"
```

---

### Task 6: Manual end-to-end verification of the backend

**Files:** none (verification only)

**Interfaces:**
- Consumes: the running FastAPI backend with Task 5's endpoint.

This is a manual check because report generation drives a real Playwright browser against a real GA4 property and calls the Gemini API — it cannot be meaningfully faked in an automated test without losing the point of the check (confirming the real pipeline works end-to-end).

- [ ] **Step 1: Start the backend**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports && uv run uvicorn reports.app:app --reload --port 8000
```
Expected: server starts, logs `Reports API started.`

- [ ] **Step 2: Confirm settings are configured**

Run (in a second terminal):
```bash
curl -s http://127.0.0.1:8000/settings | python3 -m json.tool
```
Expected: `"configured": true`, `"gemini_api_key_set": true`, `"browser_available": true`. If any are false, stop and finish `/settings` setup in the running desktop app first (Gemini key, Chrome, Google sign-in) before continuing.

- [ ] **Step 3: Submit a Quick Report using a known-good property ID**

Use one of the existing hardcoded property IDs (e.g. econet_ai's `511212348`) as a stand-in for an "ad-hoc" one, since it's guaranteed accessible from the saved Chrome session:
```bash
curl -s -X POST http://127.0.0.1:8000/reports/generate-quick \
  -H "Content-Type: application/json" \
  -d '{
    "ga4_property_id": "511212348",
    "client_name": "Quick Test Client",
    "gsc_url": "",
    "date_range": "1 February 2026 - 28 February 2026",
    "report_date": "03 March 2026",
    "start_date": "Feb 1, 2026",
    "end_date": "Feb 28, 2026"
  }' | python3 -m json.tool
```
Expected: `{"id": <some int>, "status": "pending"}`.

- [ ] **Step 4: Poll until the report completes**

Run (replace `<id>` with the id from Step 3):
```bash
watch -n 3 "curl -s http://127.0.0.1:8000/reports/<id> | python3 -m json.tool"
```
Expected: `status` moves through `"pending"` (with `stage` updating: "Capturing GA4 data...", "Applying slide 1 branding...", "Finalising report...") to `"completed"`, with a non-null `output_path`. If it goes to `"failed"`, read the `error` field and the app log (`uv run python -c "from reports.logging_utils import get_log_path; print(get_log_path())"`) to diagnose before proceeding.

- [ ] **Step 5: Confirm the output PPTX has the client name on slide 1**

Run (replace `<output_path>` with the path from Step 4):
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports && uv run python -c "
from pptx import Presentation
prs = Presentation('<output_path>')
slide = prs.slides[0]
texts = [shape.text_frame.text for shape in slide.shapes if getattr(shape, 'has_text_frame', False)]
print('\n'.join(texts))
assert any('Quick Test Client' in t for t in texts), 'client name not found on slide 1'
print('OK: client name present on slide 1')
"
```
Expected: `OK: client name present on slide 1`, and no occurrence of the word "Delta" remaining as a name (it should be fully replaced).

- [ ] **Step 6: No commit for this task** — it's a verification checkpoint. If anything in Steps 3–5 failed, go back to Task 4 or 5 and fix before moving on.

---

### Task 7: Frontend — `generateQuickReport` API helper

**Files:**
- Modify: `frontend/src/lib/backend.ts`

**Interfaces:**
- Consumes: `fetchJson<T>(apiBaseUrl, path, init)` (existing, `backend.ts:43`).
- Produces: `QuickReportRequest` type and `generateQuickReport(apiBaseUrl, body): Promise<{ id: number }>` — used by Task 8 (`+page.svelte`).

- [ ] **Step 1: Add the type and helper function**

In `frontend/src/lib/backend.ts`, add after the existing `Report` type (after line 14, before `ChromeProfile`):
```typescript
export type QuickReportRequest = {
	ga4_property_id: string;
	client_name: string;
	gsc_url: string;
	date_range: string;
	report_date: string;
	start_date: string;
	end_date: string;
	slide1_logo_data_url: string;
	slide1_logo_filename: string;
};
```

Add this function at the end of the file, after `uploadSlideImage`:
```typescript
export async function generateQuickReport(
	apiBaseUrl: string,
	body: QuickReportRequest
): Promise<{ id: number; status: string }> {
	return fetchJson<{ id: number; status: string }>(apiBaseUrl, '/reports/generate-quick', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
}
```

- [ ] **Step 2: Verify the frontend still type-checks**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports/frontend && bun run check
```
Expected: no new TypeScript errors related to `backend.ts`.

- [ ] **Step 3: Commit**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
git add frontend/src/lib/backend.ts
git commit -m "feat: add generateQuickReport frontend API helper"
```

---

### Task 8: Frontend — "Quick Report" button and dialog

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: `generateQuickReport`, `QuickReportRequest` (Task 7), existing `fetchJson`, `pollReport`, `refreshReports`, `toGA4Date`, `toLongDate`, `toReportDate` helpers already defined in this file (lines 98–121), existing `Button`, `Dialog`/`DialogContent`/`DialogHeader`/`DialogTitle`/`DialogDescription`/`DialogFooter`, `Label` components already imported.

- [ ] **Step 1: Add state variables for the Quick Report dialog**

In `frontend/src/routes/+page.svelte`, add after the existing `let slide1LogoFileName = $state('');` line (line 96):
```svelte
	let quickOpen = $state(false);
	let quickGenerating = $state(false);
	let quickError = $state('');
	let quickPropertyId = $state('');
	let quickClientName = $state('');
	let quickGscUrl = $state('');
	let quickStartDateRaw = $state('');
	let quickEndDateRaw = $state('');
	let quickReportDateRaw = $state('');
	let quickLogoDataUrl = $state('');
	let quickLogoFileName = $state('');

	const quickDateRange = $derived(
		quickStartDateRaw && quickEndDateRaw
			? `${toLongDate(quickStartDateRaw)} - ${toLongDate(quickEndDateRaw)}`
			: ''
	);
	const quickStartDate = $derived(toGA4Date(quickStartDateRaw));
	const quickEndDate = $derived(toGA4Date(quickEndDateRaw));
	const quickReportDate = $derived(toReportDate(quickReportDateRaw));

	const quickDateValidationError = $derived((() => {
		if (!quickStartDateRaw || !quickEndDateRaw) return '';
		if (quickStartDateRaw > today) return 'Start date cannot be in the future.';
		if (quickEndDateRaw > today) return 'End date cannot be in the future.';
		if (quickStartDateRaw > quickEndDateRaw) return 'Start date must be before end date.';
		return '';
	})());

	function handleQuickLogoChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		quickLogoDataUrl = '';
		quickLogoFileName = '';
		if (!file) return;

		const reader = new FileReader();
		reader.onload = () => {
			quickLogoDataUrl = typeof reader.result === 'string' ? reader.result : '';
			quickLogoFileName = file.name;
		};
		reader.onerror = () => {
			quickError = 'Could not read the selected logo file.';
		};
		reader.readAsDataURL(file);
	}

	async function handleQuickGenerate(event: SubmitEvent) {
		event.preventDefault();
		if (quickDateValidationError) return;
		quickGenerating = true;
		quickError = '';

		try {
			const res = await generateQuickReport(apiBaseUrl, {
				ga4_property_id: quickPropertyId.trim(),
				client_name: quickClientName.trim(),
				gsc_url: quickGscUrl.trim(),
				date_range: quickDateRange,
				report_date: quickReportDate,
				start_date: quickStartDate,
				end_date: quickEndDate,
				slide1_logo_data_url: quickLogoDataUrl,
				slide1_logo_filename: quickLogoFileName
			});
			quickOpen = false;
			await refreshReports();
			pollReport(res.id);
		} catch (error) {
			quickError = error instanceof Error ? error.message : 'Generation failed.';
		} finally {
			quickGenerating = false;
		}
	}
```

- [ ] **Step 2: Import `generateQuickReport` and `QuickReportRequest`**

Update the existing backend import line (line 46):
```svelte
	import { fetchJson, fetchReportOptions, generateQuickReport, resolveBackendContext, type Report, type ReportOption, type SettingsState, waitForBackend } from '$lib/backend';
```

- [ ] **Step 3: Add the "Quick Report" button**

In the header button group (after the existing "Generate Report" `<Button>` block, i.e. right after its closing `</Button>` around line 395, still inside the same `<div class="flex items-center gap-3">`):
```svelte
			<Button
				size="sm"
				variant="outline"
				onclick={() => (quickOpen = true)}
				disabled={!settings.configured || booting || !backendReady}
			>
				<Plus class="mr-2 h-4 w-4" />
				Quick Report
			</Button>
```

- [ ] **Step 4: Add the Quick Report dialog**

Add this new `<Dialog>` block at the end of the file, after the existing delete-confirmation `<Dialog bind:open={deleteOpen}>` block (after its closing `</Dialog>` tag, which is the last line of the file):
```svelte

<Dialog bind:open={quickOpen}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>Quick Report</DialogTitle>
			<DialogDescription>
				Generate a report for any GA4 property — no template upload required.
			</DialogDescription>
		</DialogHeader>

		<form onsubmit={handleQuickGenerate} class="space-y-4 pt-2">
			{#if quickError}
				<div class="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
					{quickError}
				</div>
			{/if}

			<div class="space-y-2">
				<Label>GA4 Property ID</Label>
				<input
					type="text"
					bind:value={quickPropertyId}
					required
					placeholder="e.g. 523115644"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
			</div>

			<div class="space-y-2">
				<Label>Client Name</Label>
				<input
					type="text"
					bind:value={quickClientName}
					required
					placeholder="e.g. Union Hardware"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
			</div>

			<div class="space-y-2">
				<Label>GSC Site URL (optional)</Label>
				<input
					type="text"
					bind:value={quickGscUrl}
					placeholder="https://example.com/"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
				<p class="text-xs text-muted-foreground">Leave blank to skip the Search Performance slide.</p>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-2">
					<Label>Start Date</Label>
					<input
						type="date"
						bind:value={quickStartDateRaw}
						required
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
					/>
				</div>
				<div class="space-y-2">
					<Label>End Date</Label>
					<input
						type="date"
						bind:value={quickEndDateRaw}
						required
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
					/>
				</div>
			</div>

			{#if quickDateValidationError}
				<div class="date-error-toast" role="alert" aria-live="assertive">
					<span class="date-error-bar"></span>
					<svg class="date-error-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
					</svg>
					<span class="date-error-text">{quickDateValidationError}</span>
				</div>
			{:else if quickDateRange}
				<p class="text-xs text-muted-foreground">Date range: <span class="text-foreground/70">{quickDateRange}</span></p>
			{/if}

			<div class="space-y-2">
				<Label>Report Date</Label>
				<input
					type="date"
					bind:value={quickReportDateRaw}
					required
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
				/>
				{#if quickReportDate}
					<p class="text-xs text-muted-foreground">Formatted: <span class="text-foreground/70">{quickReportDate}</span></p>
				{/if}
			</div>

			<div class="space-y-1">
				<Label>Logo (optional)</Label>
				<input
					type="file"
					accept="image/png,image/jpeg,image/jpg,image/gif,image/bmp,image/tiff"
					onchange={handleQuickLogoChange}
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground file:mr-3 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-xs file:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				/>
				{#if quickLogoFileName}
					<p class="text-xs text-muted-foreground">{quickLogoFileName}</p>
				{/if}
			</div>

			<div class="flex justify-end gap-3 pt-2">
				<Button
					type="button"
					variant="outline"
					onclick={() => (quickOpen = false)}
					disabled={quickGenerating}
				>
					Cancel
				</Button>
				<Button
					type="submit"
					disabled={quickGenerating || !!quickDateValidationError}
				>
					{#if quickGenerating}
						<span class="mr-2 inline-flex"><SpinnerArc size={16} stroke={2} color="currentColor" /></span>
						Generating...
					{:else}
						Generate
					{/if}
				</Button>
			</div>
		</form>
	</DialogContent>
</Dialog>
```

- [ ] **Step 5: Type-check and lint**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports/frontend && bun run check && bun run lint
```
Expected: no new errors introduced by this file.

- [ ] **Step 6: Commit**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
git add frontend/src/routes/+page.svelte
git commit -m "feat: add Quick Report dialog to the dashboard"
```

---

### Task 9: Manual end-to-end verification of the full UI flow

**Files:** none (verification only)

**Interfaces:**
- Consumes: the running backend (Task 6) and the running frontend dev server.

- [ ] **Step 1: Start the frontend dev server**

Run:
```bash
cd /Users/rakinzisilver/Documents/GitHub/reports/frontend && bun run dev
```
Expected: dev server starts, prints a local URL (typically `http://localhost:5173/`).

- [ ] **Step 2: Open the dashboard in a browser and locate the button**

Navigate to the printed URL. Confirm a "Quick Report" outline button appears next to "Generate Report" in the top-right header, and is enabled once settings show as configured.

- [ ] **Step 3: Fill in and submit the Quick Report dialog**

Click "Quick Report". Enter:
- GA4 Property ID: `511212348` (a known-accessible property, reused from Task 6 for a safe test)
- Client Name: `Quick Test Client`
- GSC Site URL: leave blank
- Start Date / End Date: any valid past range
- Report Date: today

Click Generate. Expected: dialog closes, a new row appears in the reports table with status "Pending" and a `GeneratingPulse` stage indicator that updates over time (e.g. "Capturing GA4 data...", "Applying slide 1 branding...").

- [ ] **Step 4: Confirm completion and preview**

Wait for the row's status to become "Completed" (poll interval is 3s, matching `pollReport`). Click "Preview & Edit" and confirm slide 1 shows "Quick Test Client" instead of "Delta", and that the report otherwise looks like a normal 7-slide report (no Search Performance slide, since no GSC URL was given).

- [ ] **Step 5: No commit for this task** — it's a verification checkpoint confirming the whole feature works end-to-end in the real app.

---

## Self-Review Notes

- **Spec coverage:** dialog fields (property ID, client name, GSC URL, dates, logo) → Task 8; auto-slug with no collision handling → Task 2 + Task 5 Step 3; `GA4_PROPERTIES`/`GSC_URLS` injection via existing sentinel-style pattern → Task 4; fixed Delta base template + 7-slide fallback → Task 4; always-on `_apply_slide1_overrides` reuse → Task 5 Step 2; new endpoint mirroring `/reports/generate`'s shape → Task 5 Step 3; error handling via existing failure path (no special-casing) → Task 5 Step 2's try/except mirrors `_run_generate` exactly; out-of-scope items (no retry support, no dedicated list/filter, no multi-property sections) → intentionally not built anywhere in this plan.
- **Placeholder scan:** no TBD/TODO markers; every code step has complete, concrete code (verified against the actual current file contents read during planning, not guessed).
- **Type consistency:** `generate_quick_report()`'s parameter names in Task 4 match exactly what Task 5's `_run_generate_quick` passes as keyword arguments; `QuickReportRequest`'s TS field names in Task 7 match `GenerateQuickReportRequest`'s Python field names in Task 3 (both snake_case, matching the existing `GenerateReportRequest`/dialog convention already in the codebase); `slugify_client_name` is defined once in Task 2 and imported identically in Task 5.
