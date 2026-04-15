import datetime as dt
from pydantic import BaseModel, field_validator, model_validator

_GA4_DATE_FMT = "%b %d, %Y"  # e.g. "Feb 1, 2026"

HARDCODED_REPORT_NAMES: frozenset[str] = frozenset({
    "econet", "econet_ai", "infraco", "ecocash",
    "ecosure", "zimplats", "cancer_serve", "dicomm",
})


class GenerateReportRequest(BaseModel):
    report_name: str
    date_range: str          # e.g. "1 February 2026 - 28 February 2026"
    report_date: str         # e.g. "03 March 2026"
    start_date: str          # GA4 picker format e.g. "Feb 1, 2026"
    end_date: str            # GA4 picker format e.g. "Feb 28, 2026"

    @field_validator("report_name")
    @classmethod
    def report_name_must_exist(cls, v: str) -> str:
        if v in HARDCODED_REPORT_NAMES:
            return v
        from .db import get_template_by_slug
        if get_template_by_slug(v) is None:
            raise ValueError(f"Unknown report name '{v}' — not a hardcoded report and no uploaded template found")
        return v

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
    def start_must_be_before_end(self) -> "GenerateReportRequest":
        start = dt.datetime.strptime(self.start_date, _GA4_DATE_FMT).date()
        end = dt.datetime.strptime(self.end_date, _GA4_DATE_FMT).date()
        if start > end:
            raise ValueError(f"start_date '{self.start_date}' must not be after end_date '{self.end_date}'")
        return self


class GenerateReportResponse(BaseModel):
    report_name: str
    output_path: str
    message: str


class AppSettingsUpdate(BaseModel):
    gemini_api_key: str = ""
    chrome_user_data_dir: str = ""
    chrome_profile_directory: str = "Default"
