from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from .auth_session import auth_session_status, open_google_sign_in
from .chrome_profiles import list_profiles
from .db import init_db, create_report, list_reports, get_report, update_report_completed, update_report_failed
from .logging_utils import configure_logging, get_log_path, read_recent_logs
from .runtime import get_runtime_status, load_runtime_environment, save_settings
from .schemas import AppSettingsUpdate, GenerateReportRequest

_executor = ThreadPoolExecutor(max_workers=1)
logger = configure_logging()


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


@app.get("/reports/{report_id}/download")
def download_report(report_id: int):
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["status"] != "completed" or not report["output_path"]:
        raise HTTPException(status_code=400, detail="Report is not ready for download")
    output_path = Path(report["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found on disk")
    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=output_path.name,
    )


@app.get("/reports/econet")
def get_econet():
    from .extractors import extract_econet

    return JSONResponse(extract_econet())


@app.get("/reports/econet-ai")
def get_econet_ai():
    from .extractors import extract_econet_ai

    return JSONResponse(extract_econet_ai())


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
