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
