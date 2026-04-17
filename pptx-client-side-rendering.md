# Plan: Client-Side PPTX Slide Thumbnail Rendering

## Context
The app is a Tauri desktop app (Windows + Mac) with a Svelte/Vite frontend and a Python FastAPI sidecar backend. The template mapping page (`/templates/[id]/map`) shows a sidebar of slide thumbnails.

**Current state:**
- Backend renders PPTX → PNG using Pillow (poor quality) or Spire.Presentation (free tier = 10 slide limit)
- All attempted Python-only PPTX→image approaches either need LibreOffice, PowerPoint, or are commercial
- The slide thumbnail divs now render at correct height (`style:height="108px"` + `style:min-height="108px"` via Svelte style directives) — this was fixed
- Backend serves slide images at `GET /templates/{id}/slides/{index}/image`

**Goal:** Use a JavaScript library in the Svelte frontend to render PPTX slides directly in the browser (Chromium is built into Tauri), then send the rendered PNGs to the backend for caching. No external dependencies needed.

---

## Candidate Libraries to Evaluate

1. **`@kandiforge/pptx-renderer`** (npm) — React + HTML5 Canvas, renders client-side, most recent (2025). May be proprietary.
2. **`pptx-preview` / `office-viewer`** — gitlab.io/develop365, JavaScript PPTX preview library
3. **`PPTX2HTML`** — converts PPTX XML to HTML, then browser renders it

Pick whichever is MIT licensed, works in Svelte 5 (no React required), and renders all slides.

---

## Architecture

```
Frontend (Svelte)                    Backend (FastAPI)
─────────────────                    ─────────────────
1. Fetch PPTX binary from            GET /templates/{id}/pptx-file
   backend

2. Pass to JS PPTX renderer
   → renders each slide to
     <canvas> element

3. canvas.toDataURL('image/png')
   → base64 PNG per slide

4. POST each PNG to backend  →       POST /templates/{id}/slides/{index}/image
                                      saves to preview_dir/slide_{i}.png
                                      updates preview_dir in DB

5. UI polls for images
   (existing polling loop works)
```

---

## Implementation Steps

### Step 1 — Add backend endpoint to receive rendered slide PNGs

In `src/reports/app.py`, add:

```python
@app.post("/templates/{template_id}/slides/{slide_index}/image")
async def upload_template_slide_image(template_id: int, slide_index: int, request: Request):
    """Accept a PNG upload from the frontend renderer and cache it."""
    template = get_template(template_id)
    if not template:
        raise HTTPException(404)
    preview_dir = Path(template["pptx_path"]).parent / f"{template['slug']}-previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    body = await request.body()
    # body is raw PNG bytes (sent as application/octet-stream)
    (preview_dir / f"slide_{slide_index}.png").write_bytes(body)
    # If all slides are uploaded, update preview_dir in DB
    slide_count = template["slide_count"]
    rendered = len(list(preview_dir.glob("slide_*.png")))
    if rendered >= slide_count:
        update_template_preview_dir(template_id, str(preview_dir))
    return JSONResponse({"ok": True})
```

Also add a `GET /templates/{id}/pptx-file` endpoint to serve the raw PPTX binary to the frontend:

```python
@app.get("/templates/{template_id}/pptx-file")
def get_template_pptx(template_id: int):
    template = get_template(template_id)
    if not template:
        raise HTTPException(404)
    path = Path(template["pptx_path"])
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(str(path), media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
```

### Step 2 — Add frontend API helpers (backend.ts)

```typescript
export async function fetchTemplatePptxBlob(apiBaseUrl: string, id: number): Promise<ArrayBuffer> {
    const res = await fetch(`${apiBaseUrl}/templates/${id}/pptx-file`);
    if (!res.ok) throw new Error(`Failed to fetch PPTX: ${res.status}`);
    return res.arrayBuffer();
}

export async function uploadSlideImage(apiBaseUrl: string, id: number, slideIndex: number, pngBlob: Blob): Promise<void> {
    await fetch(`${apiBaseUrl}/templates/${id}/slides/${slideIndex}/image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: pngBlob,
    });
}
```

### Step 3 — Install and integrate JS PPTX renderer in frontend

```bash
bun add @kandiforge/pptx-renderer
# OR whichever library works — evaluate first
```

In `map/+page.svelte`, add a `renderSlidesClientSide()` function:

```typescript
async function renderSlidesClientSide() {
    // 1. Fetch PPTX binary
    const pptxBuffer = await fetchTemplatePptxBlob(apiBaseUrl, templateId);
    
    // 2. Use JS library to render each slide to canvas
    // (API depends on library chosen)
    const renderer = new PptxRenderer(pptxBuffer);
    const slideCount = await renderer.getSlideCount();
    
    for (let i = 0; i < slideCount; i++) {
        const canvas = document.createElement('canvas');
        canvas.width = 1920;
        canvas.height = 1080;
        await renderer.renderSlide(i, canvas);
        
        // 3. Convert canvas to PNG blob
        const blob = await new Promise<Blob>(resolve => 
            canvas.toBlob(b => resolve(b!), 'image/png')
        );
        
        // 4. Upload to backend
        await uploadSlideImage(apiBaseUrl, templateId, i, blob);
    }
    
    // 5. Reload slides
    await loadAll();
}
```

Call `renderSlidesClientSide()` instead of `rerenderTemplatePreviews()` when the "↺ Re-render Slides" button is clicked (or auto-trigger on page load if no previews exist).

### Step 4 — Remove Spire from Python backend

In `src/reports/slides.py`, remove `_render_via_spire` and make `render_slides_to_dir` fall back to Pillow only (or keep as last resort for initial upload). Client-side rendering replaces server-side for thumbnails.

Remove from `pyproject.toml`:
```
"spire-presentation>=11.3.0",
```

---

## Key Files

- `src/reports/app.py` — add POST + GET pptx-file endpoints
- `frontend/src/lib/backend.ts` — add `fetchTemplatePptxBlob`, `uploadSlideImage`
- `frontend/src/routes/templates/[id]/map/+page.svelte` — add `renderSlidesClientSide()`
- `frontend/package.json` — add JS PPTX renderer library
- `src/reports/slides.py` — remove Spire, keep Pillow as server fallback only
- `pyproject.toml` — remove `spire-presentation`

---

## Notes

- The slide thumbnail divs are already fixed to `height: 108px` using Svelte `style:` directives (NOT `style="..."` string — Svelte 5 parses style strings and drops height when template literals are present)
- The polling loop (`refreshPreviews` every 3s) already handles loading images once `preview_dir` is set in DB
- The `POST /templates/{id}/slides/{index}/image` endpoint should update `preview_dir` in DB only after ALL slides are uploaded (check `rendered >= slide_count`)
- CORS: backend already runs on `127.0.0.1:8000`, frontend on `localhost:5173` — ensure CORS allows POST to new endpoint
