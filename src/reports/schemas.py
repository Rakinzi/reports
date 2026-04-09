from pydantic import BaseModel
from typing import Literal


ReportName = Literal[
    "econet",
    "econet_ai",
    "infraco",
    "ecocash",
    "ecosure",
    "zimplats",
    "cancer_serve",
    "dicomm",
]


class GenerateReportRequest(BaseModel):
    report_name: ReportName
    date_range: str          # e.g. "1 February 2026 - 28 February 2026"
    report_date: str         # e.g. "03 March 2026"
    start_date: str          # GA4 picker format e.g. "Feb 1, 2026"
    end_date: str            # GA4 picker format e.g. "Feb 28, 2026"


class GenerateReportResponse(BaseModel):
    report_name: str
    output_path: str
    message: str


class AppSettingsUpdate(BaseModel):
    gemini_api_key: str = ""
    chrome_user_data_dir: str = ""
    chrome_profile_directory: str = "Default"
