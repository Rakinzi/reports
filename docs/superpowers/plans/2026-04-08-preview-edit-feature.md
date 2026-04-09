# Preview & Edit Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a report generates, users can view each slide as a PNG image and edit key text fields with AI-assisted rewriting (Gemini), then re-export the updated PPTX.

**Architecture:** Backend converts PPTX → PNGs via LibreOffice headless after generation, stores them under `artifacts/slides/{report_id}/`. New FastAPI endpoints serve slide images and handle field edits. A new Svelte route `/reports/[id]/preview` shows a slide carousel on the left and editable fields on the right. The poll completion handler auto-navigates to preview; completed report rows also get a "Preview & Edit" button.

**Tech Stack:** Python (python-pptx, subprocess LibreOffice), FastAPI, SvelteKit 5, TypeScript, Tailwind CSS.

---

## File Map

| File | Change |
|---|---|
| `src/reports/db.py` | Add `slides_dir` and `edits` columns; add `update_report_slides_dir()` and `update_report_edits()` db helpers |
| `src/reports/runtime.py` | Add `get_slides_dir()` helper |
| `src/reports/slides.py` | **New** — PPTX → PNG rendering via LibreOffice, slide field extraction |
| `src/reports/app.py` | Add `/reports/{id}/slides`, `/reports/{id}/slides/{index}/image`, `/reports/{id}/slides/{index}/rewrite`, `/reports/{id}/apply-edits` endpoints; call render after generation completes |
| `frontend/src/lib/backend.ts` | Add `SlideField`, `Slide`, `RewriteRequest`, `RewriteResponse` types and `fetchSlides`, `rewriteField`, `applyEdits` helpers |
| `frontend/src/routes/reports/[id]/preview/+page.svelte` | **New** — preview/edit page |
| `frontend/src/routes/+page.svelte` | Add "Preview & Edit" button to completed report rows; auto-navigate to preview on poll completion |

---

### Task 1: Add DB columns and helpers for slides

**Files:**
- Modify: `src/reports/db.py`

- [ ] **Step 1: Add migration for new columns**

Open `src/reports/db.py`. Update `init_db()` to add the two new columns via `ALTER TABLE IF NOT EXISTS` pattern (safe for existing DBs):

```python
def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                report_name TEXT    NOT NULL,
                date_range  TEXT    NOT NULL,
                report_date TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                output_path TEXT,
                error       TEXT,
                slides_dir  TEXT,
                edits       TEXT,
                created_at  TEXT    NOT NULL
            )
        """)
        # Safe migration for existing databases
        for col, coldef in [("slides_dir", "TEXT"), ("edits", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {col} {coldef}")
            except Exception:
                pass  # Column already exists
        conn.commit()
```

- [ ] **Step 2: Add `update_report_slides_dir()` and `update_report_edits()`**

```python
def update_report_slides_dir(report_id: int, slides_dir: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET slides_dir=? WHERE id=?",
            (slides_dir, report_id),
        )
        conn.commit()


def update_report_edits(report_id: int, edits: str) -> None:
    """edits is a JSON string of {field_id: new_text}."""
    with _connect() as conn:
        conn.execute(
            "UPDATE reports SET edits=? WHERE id=?",
            (edits, report_id),
        )
        conn.commit()
```

- [ ] **Step 3: Export new functions from db.py imports in app.py**

Open `src/reports/app.py`. Update the db import line:

```python
from .db import (
    init_db, create_report, list_reports, get_report,
    update_report_completed, update_report_failed,
    update_report_slides_dir, update_report_edits,
)
```

- [ ] **Step 4: Commit**

```bash
git add src/reports/db.py src/reports/app.py
git commit -m "feat: add slides_dir and edits columns to reports DB"
```

---

### Task 2: Add `get_slides_dir()` to runtime

**Files:**
- Modify: `src/reports/runtime.py`

- [ ] **Step 1: Add the helper after `get_screenshots_dir()`**

```python
def get_slides_dir() -> Path:
    path = get_app_data_dir() / "slides"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

- [ ] **Step 2: Commit**

```bash
git add src/reports/runtime.py
git commit -m "feat: add get_slides_dir() runtime helper"
```

---

### Task 3: Create `slides.py` — PPTX to PNG rendering and field extraction

**Files:**
- Create: `src/reports/slides.py`

- [ ] **Step 1: Create the file with LibreOffice rendering**

```python
"""
PPTX → PNG slide rendering and structured field extraction.

Rendering uses LibreOffice headless (soffice) which must be installed on the system.
Each slide is saved as slide_0.png, slide_1.png, etc. in a report-specific directory.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

from pptx import Presentation

from .logging_utils import configure_logging
from .runtime import get_slides_dir

logger = configure_logging()


def _find_libreoffice() -> str | None:
    """Return the path to the soffice binary, or None if not found."""
    for candidate in ["soffice", "/usr/bin/soffice", "/usr/local/bin/soffice",
                       "/Applications/LibreOffice.app/Contents/MacOS/soffice"]:
        if shutil.which(candidate):
            return candidate
    return None


def render_slides(report_id: int, pptx_path: Path) -> Path:
    """
    Convert a PPTX to PNG images using LibreOffice headless.
    Returns the directory containing slide_0.png, slide_1.png, etc.
    Raises RuntimeError if LibreOffice is not installed.
    """
    soffice = _find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice is not installed. Install it to enable slide preview. "
            "On macOS: brew install --cask libreoffice"
        )

    slides_dir = get_slides_dir() / str(report_id)
    slides_dir.mkdir(parents=True, exist_ok=True)

    # LibreOffice outputs files named like "Report Name.png" in the outdir
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "png", "--outdir", str(slides_dir), str(pptx_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")

    # LibreOffice converts the whole PPTX as one image per slide, naming them:
    # <basename>.png for single-slide, or <basename>1.png, <basename>2.png, ... for multi-slide
    # Rename to canonical slide_0.png, slide_1.png, ...
    stem = pptx_path.stem
    pngs = sorted(slides_dir.glob(f"{stem}*.png"))
    for i, png in enumerate(pngs):
        target = slides_dir / f"slide_{i}.png"
        if png != target:
            png.rename(target)

    logger.info("Rendered %d slides for report_id=%s to %s", len(pngs), report_id, slides_dir)
    return slides_dir


def extract_slide_fields(pptx_path: Path) -> list[dict]:
    """
    Extract editable text fields from each slide.
    Returns a list of slide dicts:
      [{ "slide_index": 0, "fields": [{ "field_id": "s0_date", "label": "Date", "value": "March, 2026" }] }]
    """
    prs = Presentation(str(pptx_path))
    result = []

    for slide_idx, slide in enumerate(prs.slides):
        fields = []
        for shape_idx, shape in enumerate(slide.shapes):
            if not shape.has_text_frame:
                continue
            for para_idx, para in enumerate(shape.text_frame.paragraphs):
                text = para.text.strip()
                if not text:
                    continue

                field_id = f"s{slide_idx}_shape{shape_idx}_para{para_idx}"
                label = _label_for_field(slide_idx, shape.name, text)
                if label:
                    fields.append({
                        "field_id": field_id,
                        "label": label,
                        "value": text,
                        "slide_index": slide_idx,
                        "shape_name": shape.name,
                        "para_index": para_idx,
                    })

        result.append({"slide_index": slide_idx, "fields": fields})
    return result


def _label_for_field(slide_idx: int, shape_name: str, text: str) -> str | None:
    """Return a human-readable label for a text field, or None if it should not be editable."""
    # Skip very short non-meaningful text
    if len(text) < 3:
        return None

    # Slide 1 — date
    if slide_idx == 0 and re.match(r"^[A-Za-z]+,?\s*\d{4}$", text):
        return "Report Month"

    # Slide 2 — executive summary
    if slide_idx == 1:
        if re.match(r"^\d+K?$", text):
            return "Active Users (short)"
        if re.match(r"^\d+%$", text) and len(text) <= 5:
            return "New Visitors %"
        if re.match(r"^\d+\.\d+%$", text):
            return "CTR"
        if len(text) > 60:
            return "Executive Summary Paragraph"

    # Slide 3 — site overview
    if slide_idx == 2:
        if "total active users" in text.lower():
            return "Active Users Label"
        if "new users" in text.lower():
            return "New Users Label"
        if "engagement" in text.lower():
            return "Engagement Time Label"
        if len(text) > 60:
            return "Site Overview Paragraph"
        if re.match(r"^[\d,]+$", text):
            return "Stat Value"

    # Slide 4 — geographic
    if slide_idx == 3 and len(text) > 40:
        return "Geographic Performance Paragraph"

    # Slide 5 — page performance
    if slide_idx == 4 and len(text) > 40:
        return "Page Performance Insight"

    # Slide 6 — search performance
    if slide_idx == 5 and len(text) > 40:
        return "Search Performance Paragraph"

    # Recommendations slide (index 6 for 8-slide, 5 for 7-slide)
    if slide_idx in (5, 6) and re.match(r"^\d\.", text):
        return f"Recommendation {text[0]}"

    return None


def apply_field_edits(pptx_path: Path, edits: dict[str, str], output_path: Path) -> None:
    """
    Re-open the PPTX, apply field edits (field_id -> new_text), and save to output_path.
    edits keys match the field_id format: "s{slide_idx}_shape{shape_idx}_para{para_idx}"
    """
    prs = Presentation(str(pptx_path))

    for field_id, new_text in edits.items():
        # Parse field_id: s0_shape3_para1
        m = re.match(r"^s(\d+)_shape(\d+)_para(\d+)$", field_id)
        if not m:
            logger.warning("Unrecognised field_id format: %s", field_id)
            continue
        slide_idx, shape_idx, para_idx = int(m.group(1)), int(m.group(2)), int(m.group(3))

        if slide_idx >= len(prs.slides):
            continue
        slide = prs.slides[slide_idx]
        shapes_with_text = [s for s in slide.shapes if s.has_text_frame]
        if shape_idx >= len(shapes_with_text):
            continue
        shape = shapes_with_text[shape_idx]
        if para_idx >= len(shape.text_frame.paragraphs):
            continue
        para = shape.text_frame.paragraphs[para_idx]
        _fill_para(para, new_text)

    prs.save(str(output_path))


def _fill_para(para, new_text: str) -> None:
    """Replace paragraph text preserving first run's rPr formatting."""
    from copy import deepcopy
    import lxml.etree as etree
    from pptx.oxml.ns import qn

    if not para.runs:
        return
    first_rpr = para.runs[0]._r.find(qn("a:rPr"))
    saved_rpr = deepcopy(first_rpr) if first_rpr is not None else None
    for child in list(para._p):
        if child.tag != qn("a:pPr"):
            para._p.remove(child)
    new_r = etree.SubElement(para._p, qn("a:r"))
    if saved_rpr is not None:
        new_r.insert(0, saved_rpr)
    new_t = etree.SubElement(new_r, qn("a:t"))
    new_t.text = new_text
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
python3 -c "from src.reports.slides import render_slides, extract_slide_fields, apply_field_edits; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/reports/slides.py
git commit -m "feat: add slides.py for PPTX-to-PNG rendering and field extraction"
```

---

### Task 4: Add slide API endpoints to `app.py`

**Files:**
- Modify: `src/reports/app.py`

- [ ] **Step 1: Update `_run_generate` to render slides after generation**

Find `_run_generate()` in `app.py`. After `update_report_completed(report_id, str(output_path))`, add the render step:

```python
def _run_generate(report_id: int, report_name: str, date_range: str, report_date: str, start_date: str, end_date: str):
    try:
        from .generator import generate_report

        logger.info("Starting report generation for report_id=%s report_name=%s", report_id, report_name)
        output_path = generate_report(
            report_name=report_name,
            date_range=date_range,
            report_date=report_date,
            start_date=start_date,
            end_date=end_date,
        )
        update_report_completed(report_id, str(output_path))
        logger.info("Completed report generation for report_id=%s output_path=%s", report_id, output_path)

        # Render slides to PNG for preview
        try:
            from .slides import render_slides
            from pathlib import Path as _Path
            slides_dir = render_slides(report_id, _Path(output_path))
            update_report_slides_dir(report_id, str(slides_dir))
            logger.info("Rendered slides for report_id=%s slides_dir=%s", report_id, slides_dir)
        except Exception as render_err:
            logger.warning("Slide rendering failed for report_id=%s: %s", report_id, render_err)
            # Non-fatal — report still available for download

    except Exception as e:
        update_report_failed(report_id, str(e))
        logger.exception("Report generation failed for report_id=%s", report_id)
```

- [ ] **Step 2: Add the four new endpoints**

Add these after the existing `/reports/{report_id}/download` endpoint:

```python
@app.get("/reports/{report_id}/slides")
def get_report_slides(report_id: int):
    from pathlib import Path as _Path
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["status"] != "completed" or not report["output_path"]:
        raise HTTPException(status_code=400, detail="Report is not ready")

    output_path = _Path(report["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found on disk")

    from .slides import extract_slide_fields
    fields_by_slide = extract_slide_fields(output_path)

    slides_dir = report.get("slides_dir")
    result = []
    for slide_data in fields_by_slide:
        idx = slide_data["slide_index"]
        has_image = False
        if slides_dir:
            has_image = (_Path(slides_dir) / f"slide_{idx}.png").exists()
        result.append({
            "slide_index": idx,
            "image_url": f"/reports/{report_id}/slides/{idx}/image" if has_image else None,
            "fields": slide_data["fields"],
        })
    return JSONResponse(result)


@app.get("/reports/{report_id}/slides/{slide_index}/image")
def get_slide_image(report_id: int, slide_index: int):
    from pathlib import Path as _Path
    from fastapi.responses import FileResponse as _FileResponse
    report = get_report(report_id)
    if not report or not report.get("slides_dir"):
        raise HTTPException(status_code=404, detail="Slide images not available")
    image_path = _Path(report["slides_dir"]) / f"slide_{slide_index}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Slide {slide_index} image not found")
    return _FileResponse(str(image_path), media_type="image/png")


@app.post("/reports/{report_id}/slides/{slide_index}/rewrite")
def rewrite_slide_field(report_id: int, slide_index: int, body: dict):
    """
    Body: { "field_id": str, "current_text": str, "instruction": str }
    Returns: { "rewritten_text": str }
    """
    from .runtime import load_runtime_environment
    import os
    load_runtime_environment()

    current_text = body.get("current_text", "")
    instruction = body.get("instruction", "paraphrase for a professional report")
    if not current_text:
        raise HTTPException(status_code=400, detail="current_text is required")

    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"Rewrite the following text for a professional PowerPoint report. "
                f"Instruction: {instruction}. "
                "Keep all numbers exactly as they are. Use clear, formal business English. "
                "No em dashes, bullets, or markdown. Output plain text only.\n\n"
                + current_text
            ),
        )
        return JSONResponse({"rewritten_text": response.text.strip()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini rewrite failed: {e}") from e


@app.post("/reports/{report_id}/apply-edits")
def apply_report_edits(report_id: int, body: dict):
    """
    Body: { "edits": { "field_id": "new_text", ... } }
    Re-applies edits to the PPTX and saves a new file.
    Returns: { "output_path": str, "download_url": str }
    """
    import json as _json
    from pathlib import Path as _Path
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.get("output_path"):
        raise HTTPException(status_code=400, detail="Report has no output file")

    edits = body.get("edits", {})
    if not edits:
        raise HTTPException(status_code=400, detail="No edits provided")

    original_path = _Path(report["output_path"])
    if not original_path.exists():
        raise HTTPException(status_code=404, detail="Original PPTX not found")

    # Save edited version as a new file with -edited suffix
    edited_path = original_path.with_stem(original_path.stem + "-edited")

    from .slides import apply_field_edits
    apply_field_edits(original_path, edits, edited_path)

    # Update DB with edited path and store edits JSON
    update_report_completed(report_id, str(edited_path))
    update_report_edits(report_id, _json.dumps(edits))

    # Re-render slides from edited PPTX
    try:
        from .slides import render_slides
        slides_dir = render_slides(report_id, edited_path)
        update_report_slides_dir(report_id, str(slides_dir))
    except Exception as render_err:
        logger.warning("Slide re-render failed after edits for report_id=%s: %s", report_id, render_err)

    return JSONResponse({
        "output_path": str(edited_path),
        "download_url": f"/reports/{report_id}/download",
    })
```

- [ ] **Step 3: Verify the app starts without errors**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
python3 -c "from src.reports.app import app; print('App loaded OK')"
```

Expected: `App loaded OK`

- [ ] **Step 4: Commit**

```bash
git add src/reports/app.py
git commit -m "feat: add slide preview and edit API endpoints"
```

---

### Task 5: Add frontend types and API helpers

**Files:**
- Modify: `frontend/src/lib/backend.ts`

- [ ] **Step 1: Add types and fetch helpers**

Open `frontend/src/lib/backend.ts`. Add after the existing types:

```typescript
export type SlideField = {
    field_id: string;
    label: string;
    value: string;
    slide_index: number;
    shape_name: string;
    para_index: number;
};

export type Slide = {
    slide_index: number;
    image_url: string | null;
    fields: SlideField[];
};

export async function fetchSlides(apiBaseUrl: string, reportId: number): Promise<Slide[]> {
    return fetchJson<Slide[]>(apiBaseUrl, `/reports/${reportId}/slides`);
}

export async function rewriteField(
    apiBaseUrl: string,
    reportId: number,
    slideIndex: number,
    fieldId: string,
    currentText: string,
    instruction: string
): Promise<string> {
    const res = await fetchJson<{ rewritten_text: string }>(
        apiBaseUrl,
        `/reports/${reportId}/slides/${slideIndex}/rewrite`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field_id: fieldId, current_text: currentText, instruction }),
        }
    );
    return res.rewritten_text;
}

export async function applyEdits(
    apiBaseUrl: string,
    reportId: number,
    edits: Record<string, string>
): Promise<{ output_path: string; download_url: string }> {
    return fetchJson(apiBaseUrl, `/reports/${reportId}/apply-edits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edits }),
    });
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend
git add src/lib/backend.ts
git commit -m "feat: add slide preview types and API helpers to backend.ts"
```

---

### Task 6: Create the Preview & Edit page

**Files:**
- Create: `frontend/src/routes/reports/[id]/preview/+page.svelte`

- [ ] **Step 1: Create the directory**

```bash
mkdir -p frontend/src/routes/reports/\[id\]/preview
```

- [ ] **Step 2: Create `+page.svelte`**

```svelte
<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { ChevronLeft, ChevronRight, Download, Loader2, Sparkles, ArrowLeft } from '@lucide/svelte';
    import { Button } from '$lib/components/ui/button';
    import { Label } from '$lib/components/ui/label';
    import {
        resolveBackendContext,
        fetchSlides,
        rewriteField,
        applyEdits,
        fetchJson,
        type Slide,
        type SlideField,
        type Report,
    } from '$lib/backend';
    import { saveReportFromDesktop } from '$lib/desktop';

    const reportId = Number($page.params.id);

    let apiBaseUrl = $state('http://127.0.0.1:8000');
    let isTauri = $state(false);
    let loading = $state(true);
    let error = $state('');
    let slides = $state<Slide[]>([]);
    let currentIndex = $state(0);
    let report = $state<Report | null>(null);

    // Edited values: field_id -> current text in textarea
    let editedValues = $state<Record<string, string>>({});
    // Rewrite instructions: field_id -> instruction text
    let instructions = $state<Record<string, string>>({});
    // Rewriting state: field_id -> boolean
    let rewriting = $state<Record<string, boolean>>({});

    let saving = $state(false);
    let saveError = $state('');

    const currentSlide = $derived(slides[currentIndex] ?? null);

    function initEdits(slides: Slide[]) {
        const vals: Record<string, string> = {};
        for (const slide of slides) {
            for (const field of slide.fields) {
                vals[field.field_id] = field.value;
            }
        }
        editedValues = vals;
    }

    async function load() {
        loading = true;
        error = '';
        try {
            const ctx = await resolveBackendContext();
            apiBaseUrl = ctx.apiBaseUrl;
            isTauri = ctx.isTauri;
            report = await fetchJson<Report>(apiBaseUrl, `/reports/${reportId}`);
            slides = await fetchSlides(apiBaseUrl, reportId);
            initEdits(slides);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load report';
        } finally {
            loading = false;
        }
    }

    async function handleRewrite(field: SlideField) {
        rewriting[field.field_id] = true;
        try {
            const instruction = instructions[field.field_id] || 'paraphrase for a professional report';
            const result = await rewriteField(
                apiBaseUrl,
                reportId,
                field.slide_index,
                field.field_id,
                editedValues[field.field_id] ?? field.value,
                instruction
            );
            editedValues[field.field_id] = result;
        } catch (e) {
            // show inline error
            editedValues[field.field_id] = editedValues[field.field_id]; // no change
        } finally {
            rewriting[field.field_id] = false;
        }
    }

    async function handleSaveAndExport() {
        saving = true;
        saveError = '';
        try {
            await applyEdits(apiBaseUrl, reportId, editedValues);
            // Refresh slides after edit
            slides = await fetchSlides(apiBaseUrl, reportId);

            const suggestedName = `${report?.report_name ?? 'report'}-edited.pptx`;
            if (isTauri) {
                await saveReportFromDesktop(apiBaseUrl, reportId, suggestedName);
            } else {
                window.open(`${apiBaseUrl}/reports/${reportId}/download`, '_blank', 'noopener,noreferrer');
            }
        } catch (e) {
            saveError = e instanceof Error ? e.message : 'Save failed';
        } finally {
            saving = false;
        }
    }

    onMount(() => {
        void load();
    });
</script>

<div class="flex h-full flex-col">
    <!-- Top bar -->
    <div class="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
        <button
            class="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-100"
            onclick={() => goto('/')}
        >
            <ArrowLeft class="h-4 w-4" />
            Dashboard
        </button>
        <div class="flex items-center gap-3">
            {#if saveError}
                <span class="text-xs text-red-400">{saveError}</span>
            {/if}
            <Button
                size="sm"
                class="bg-zinc-100 font-semibold text-zinc-900 hover:bg-zinc-200"
                onclick={handleSaveAndExport}
                disabled={saving || loading}
            >
                {#if saving}
                    <Loader2 class="mr-2 h-3.5 w-3.5 animate-spin" />
                {:else}
                    <Download class="mr-2 h-3.5 w-3.5" />
                {/if}
                Save & Export
            </Button>
        </div>
    </div>

    {#if loading}
        <div class="flex flex-1 items-center justify-center">
            <div class="flex items-center gap-3 text-sm text-zinc-400">
                <Loader2 class="h-4 w-4 animate-spin" />
                Loading slides...
            </div>
        </div>
    {:else if error}
        <div class="flex flex-1 items-center justify-center">
            <div class="rounded-lg border border-red-500/20 bg-red-500/10 px-5 py-4 text-sm text-red-300">
                {error}
            </div>
        </div>
    {:else}
        <div class="flex flex-1 overflow-hidden">
            <!-- Left: Slide carousel -->
            <div class="flex w-[60%] flex-col border-r border-zinc-800 bg-zinc-950">
                <div class="flex flex-1 items-center justify-center p-6">
                    {#if currentSlide?.image_url}
                        <img
                            src="{apiBaseUrl}{currentSlide.image_url}"
                            alt="Slide {currentIndex + 1}"
                            class="max-h-full max-w-full rounded shadow-lg object-contain"
                        />
                    {:else}
                        <div class="flex flex-col items-center gap-3 text-zinc-600">
                            <p class="text-sm">Slide preview unavailable</p>
                            <p class="text-xs">Install LibreOffice to enable slide previews</p>
                        </div>
                    {/if}
                </div>
                <!-- Navigation -->
                <div class="flex items-center justify-center gap-4 border-t border-zinc-800 py-3">
                    <Button
                        variant="ghost"
                        size="sm"
                        class="text-zinc-400 hover:text-zinc-100"
                        onclick={() => currentIndex = Math.max(0, currentIndex - 1)}
                        disabled={currentIndex === 0}
                    >
                        <ChevronLeft class="h-4 w-4" />
                    </Button>
                    <span class="text-sm text-zinc-400">
                        {currentIndex + 1} / {slides.length}
                    </span>
                    <Button
                        variant="ghost"
                        size="sm"
                        class="text-zinc-400 hover:text-zinc-100"
                        onclick={() => currentIndex = Math.min(slides.length - 1, currentIndex + 1)}
                        disabled={currentIndex === slides.length - 1}
                    >
                        <ChevronRight class="h-4 w-4" />
                    </Button>
                </div>
                <!-- Slide thumbnails strip -->
                <div class="flex gap-2 overflow-x-auto border-t border-zinc-800 px-4 py-2">
                    {#each slides as slide (slide.slide_index)}
                        <button
                            class="flex-shrink-0 rounded border-2 transition-colors {currentIndex === slide.slide_index ? 'border-zinc-400' : 'border-zinc-700 hover:border-zinc-500'}"
                            onclick={() => currentIndex = slide.slide_index}
                        >
                            {#if slide.image_url}
                                <img
                                    src="{apiBaseUrl}{slide.image_url}"
                                    alt="Slide {slide.slide_index + 1}"
                                    class="h-12 w-20 rounded object-cover"
                                />
                            {:else}
                                <div class="flex h-12 w-20 items-center justify-center rounded bg-zinc-800 text-xs text-zinc-500">
                                    {slide.slide_index + 1}
                                </div>
                            {/if}
                        </button>
                    {/each}
                </div>
            </div>

            <!-- Right: Edit fields -->
            <div class="flex w-[40%] flex-col overflow-y-auto p-6">
                {#if currentSlide && currentSlide.fields.length > 0}
                    <h2 class="mb-4 text-sm font-semibold text-zinc-300">
                        Slide {currentIndex + 1} — Editable Fields
                    </h2>
                    <div class="space-y-6">
                        {#each currentSlide.fields as field (field.field_id)}
                            <div class="space-y-2">
                                <Label class="text-xs font-medium text-zinc-400">{field.label}</Label>
                                <textarea
                                    class="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-500 resize-none"
                                    rows={field.value.length > 100 ? 5 : 2}
                                    bind:value={editedValues[field.field_id]}
                                ></textarea>
                                <div class="flex gap-2">
                                    <input
                                        type="text"
                                        placeholder="e.g. make it shorter, focus on new users"
                                        class="flex-1 rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500"
                                        bind:value={instructions[field.field_id]}
                                    />
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        class="border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 text-xs"
                                        onclick={() => handleRewrite(field)}
                                        disabled={rewriting[field.field_id]}
                                    >
                                        {#if rewriting[field.field_id]}
                                            <Loader2 class="mr-1.5 h-3 w-3 animate-spin" />
                                        {:else}
                                            <Sparkles class="mr-1.5 h-3 w-3" />
                                        {/if}
                                        Rewrite
                                    </Button>
                                </div>
                            </div>
                        {/each}
                    </div>
                {:else}
                    <div class="flex flex-1 items-center justify-center text-sm text-zinc-600">
                        No editable fields on this slide.
                    </div>
                {/if}
            </div>
        </div>
    {/if}
</div>
```

- [ ] **Step 3: Run the Svelte autofixer**

Use the `mcp__svelte__svelte-autofixer` tool on the file content above and fix any reported issues before committing.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/routes/reports/\[id\]/preview/+page.svelte
git commit -m "feat: add preview and edit page for generated reports"
```

---

### Task 7: Wire auto-navigate and "Preview & Edit" button into dashboard

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

- [ ] **Step 1: Change poll completion to navigate to preview instead of auto-downloading**

Find `pollReport()` in `+page.svelte` (around line 172). Change the `completed` branch:

```typescript
function pollReport(id: number) {
    const interval = setInterval(async () => {
        try {
            const report = await fetchJson<Report>(apiBaseUrl, `/reports/${id}`);
            await refreshReports();
            if (report.status === 'completed') {
                clearInterval(interval);
                goto(`/reports/${id}/preview`);  // Navigate to preview instead of auto-download
            } else if (report.status === 'failed') {
                clearInterval(interval);
            }
        } catch {
            // keep polling
        }
    }, 3000);
}
```

- [ ] **Step 2: Add "Preview & Edit" button to completed report rows**

Find the completed report row actions (around line 340 in the `{#if report.status === 'completed'}` block). Add the preview button:

```svelte
{#if report.status === 'completed' && report.output_path}
    <div class="flex items-center justify-end gap-2">
        <Button
            size="sm"
            variant="ghost"
            class="text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
            onclick={() => goto(`/reports/${report.id}/preview`)}
        >
            Preview & Edit
        </Button>
        <Button
            size="sm"
            variant="ghost"
            class="text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
            onclick={() => void downloadReport(report)}
        >
            <Download class="mr-1.5 h-3.5 w-3.5" />
            Save
        </Button>
    </div>
```

- [ ] **Step 3: Add `goto` import if not already present**

Check line 3 of the file — `goto` is already imported from `$app/navigation`. No change needed.

- [ ] **Step 4: Run the Svelte autofixer on the modified file and fix any issues.**

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/routes/+page.svelte
git commit -m "feat: auto-navigate to preview on completion, add Preview & Edit button"
```
