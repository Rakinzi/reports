from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

from .auth_session import auth_session_status, open_google_sign_in
from .chrome_profiles import list_profiles
from .db import (
    init_db, create_report, list_reports, get_report,
    update_report_completed, update_report_failed,
    update_report_slides_dir, update_report_edits, update_report_stage,
)
from .logging_utils import configure_logging, get_log_path, read_recent_logs, stream_logs
from .runtime import get_app_data_dir, get_runtime_status, load_runtime_environment, save_settings
from .schemas import AppSettingsUpdate, GenerateReportRequest

_executor = ThreadPoolExecutor(max_workers=1)
logger = configure_logging()


def _run_generate(report_id: int, report_name: str, date_range: str, report_date: str, start_date: str, end_date: str):
    try:
        from .generator_2026 import TEMPLATES_2026, generate_report_2026
        from .generator import generate_report

        if report_name in TEMPLATES_2026:
            generate_fn = generate_report_2026
        else:
            generate_fn = generate_report

        logger.info("Starting report generation for report_id=%s report_name=%s", report_id, report_name)
        update_report_stage(report_id, "Capturing GA4 data...")
        output_path = generate_fn(
            report_name=report_name,
            date_range=date_range,
            report_date=report_date,
            start_date=start_date,
            end_date=end_date,
            _stage_callback=lambda stage: update_report_stage(report_id, stage),
        )
        update_report_stage(report_id, "Finalising report...")
        update_report_completed(report_id, str(output_path))
        logger.info("Completed report generation for report_id=%s output_path=%s", report_id, output_path)

        # Render slides to PNG for preview (non-fatal if LibreOffice not installed)
        try:
            from .slides import render_slides
            from pathlib import Path as _Path
            update_report_stage(report_id, "Rendering slide previews...")
            slides_dir = render_slides(report_id, _Path(output_path))
            update_report_slides_dir(report_id, str(slides_dir))
            logger.info("Rendered slides for report_id=%s slides_dir=%s", report_id, slides_dir)
        except Exception as render_err:
            logger.warning("Slide rendering failed for report_id=%s: %s", report_id, render_err)
    except Exception as e:
        update_report_failed(report_id, str(e))
        logger.exception("Report generation failed for report_id=%s", report_id)

app = FastAPI(title="Reports API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    load_runtime_environment()
    init_db()
    logger.info("Reports API started. log_path=%s", get_log_path())


@app.get("/health")
def health():
    return JSONResponse({"status": "ok", **get_runtime_status()})


@app.get("/settings")
def get_settings():
    return JSONResponse(get_runtime_status())


@app.put("/settings")
def put_settings(body: AppSettingsUpdate):
    save_settings(body.model_dump())
    return JSONResponse(get_runtime_status())


@app.get("/settings/chrome-profiles")
def get_chrome_profiles(user_data_dir: str | None = None):
    try:
        return JSONResponse(list_profiles(user_data_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/settings/google-sign-in")
def get_google_sign_in_status():
    return JSONResponse(auth_session_status())


@app.post("/settings/google-sign-in")
def post_google_sign_in():
    return JSONResponse(open_google_sign_in())


@app.get("/logs")
def get_logs(limit: int = 200):
    return JSONResponse({"path": str(get_log_path()), "lines": read_recent_logs(limit)})


@app.get("/logs/stream")
def get_logs_stream():
    """SSE endpoint — streams log lines in real time to any connected client."""
    return StreamingResponse(
        stream_logs(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/reports/generate", status_code=202)
def post_generate_report(body: GenerateReportRequest):
    status = get_runtime_status()
    if not status["configured"]:
        raise HTTPException(status_code=400, detail="Gemini API key is not configured")

    report_id = create_report(body.report_name, body.date_range, body.report_date)
    _executor.submit(
        _run_generate,
        report_id,
        body.report_name,
        body.date_range,
        body.report_date,
        body.start_date,
        body.end_date,
    )
    return JSONResponse({"id": report_id, "status": "pending"}, status_code=202)


@app.get("/reports")
def get_reports():
    return JSONResponse(list_reports())


@app.get("/reports/{report_id}")
def get_report_by_id(report_id: int):
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return JSONResponse(report)


def _resolve_report_path(stored: str) -> Path:
    """Resolve a stored output_path to an absolute path.

    New records are always absolute. Old records may have been written with a relative
    path (e.g. 'artifacts/output/foo.pptx'). Try resolving those against the project
    root (parent of app_data_dir) so dev-mode old records still work.
    """
    p = Path(stored)
    if p.is_absolute():
        return p
    candidate = get_app_data_dir().parent / p
    if candidate.exists():
        return candidate
    return Path.cwd() / p


@app.get("/reports/{report_id}/download")
def download_report(report_id: int):
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["status"] != "completed" or not report["output_path"]:
        raise HTTPException(status_code=400, detail="Report is not ready for download")
    output_path = _resolve_report_path(report["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found on disk")
    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=output_path.name,
    )


@app.get("/reports/{report_id}/slides")
def get_report_slides(report_id: int):
    from pathlib import Path as _Path
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["status"] != "completed" or not report["output_path"]:
        raise HTTPException(status_code=400, detail="Report is not ready")

    output_path = _resolve_report_path(report["output_path"])
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
    report = get_report(report_id)
    if not report or not report.get("slides_dir"):
        raise HTTPException(status_code=404, detail="Slide images not available")
    image_path = _Path(report["slides_dir"]) / f"slide_{slide_index}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Slide {slide_index} image not found")
    return FileResponse(str(image_path), media_type="image/png")


@app.post("/reports/{report_id}/slides/{slide_index}/rewrite")
def rewrite_slide_field(report_id: int, slide_index: int, body: dict):
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

    original_path = _resolve_report_path(report["output_path"])
    if not original_path.exists():
        raise HTTPException(status_code=404, detail="Original PPTX not found")

    edited_path = original_path.with_stem(original_path.stem + "-edited")

    from .slides import apply_field_edits
    apply_field_edits(original_path, edits, edited_path)

    update_report_completed(report_id, str(edited_path))
    update_report_edits(report_id, _json.dumps(edits))

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


@app.get("/reports/econet")
def get_econet():
    from .extractors import extract_econet

    return JSONResponse(extract_econet())


@app.get("/reports/econet-ai")
def get_econet_ai():
    from .extractors import extract_econet_ai

    return JSONResponse(extract_econet_ai())


@app.get("/reports/infraco")
def get_infraco():
    from .extractors import extract_infraco

    return JSONResponse(extract_infraco())


@app.get("/reports/ecocash")
def get_ecocash():
    from .extractors import extract_ecocash

    return JSONResponse(extract_ecocash())


@app.get("/reports/ecosure")
def get_ecosure():
    from .extractors import extract_ecosure

    return JSONResponse(extract_ecosure())


@app.get("/reports/zimplats")
def get_zimplats():
    from .extractors import extract_zimplats

    return JSONResponse(extract_zimplats())


@app.get("/reports/union-hardware")
def get_union_hardware():
    from .extractors import extract_union_hardware

    return JSONResponse(extract_union_hardware())


@app.get("/reports/cancer-serve")
def get_cancer_serve():
    from .extractors import extract_cancer_serve

    return JSONResponse(extract_cancer_serve())
