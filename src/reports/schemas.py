import datetime as dt
from pydantic import BaseModel, field_validator, model_validator

_GA4_DATE_FMT = "%b %d, %Y"  # e.g. "Feb 1, 2026"

HARDCODED_REPORT_NAMES: frozenset[str] = frozenset({
    "econet", "econet_ai", "infraco", "ecocash",
    "ecosure", "zimplats", "cancer_serve", "dicomm", "delta",
    "bancabc", "mimosa",
})


class GenerateReportRequest(BaseModel):
    report_name: str
    date_range: str          # e.g. "1 February 2026 - 28 February 2026"
    report_date: str         # e.g. "03 March 2026"
    start_date: str          # GA4 picker format e.g. "Feb 1, 2026"
    end_date: str            # GA4 picker format e.g. "Feb 28, 2026"
    slide1_source_name: str = ""
    slide1_name: str = ""
    slide1_logo_data_url: str = ""
    slide1_logo_filename: str = ""
    reuse_report_id: int | None = None

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
    reuse_report_id: int | None = None

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


class GenerateReportResponse(BaseModel):
    report_name: str
    output_path: str
    message: str


class AppSettingsUpdate(BaseModel):
    gemini_api_key: str = ""
    chrome_user_data_dir: str = ""
    chrome_profile_directory: str = "Default"
