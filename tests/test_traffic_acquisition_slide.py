from pathlib import Path

from pptx import Presentation

from reports.generator_2026 import (
    TEMPLATES_2026,
    _find_traffic_acquisition_slide_index,
    _parse_traffic_acquisition_row,
    get_templates_dir,
)


def test_finds_traffic_acquisition_slide_in_infraco_template():
    template_path = get_templates_dir() / TEMPLATES_2026["infraco"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx == 6


def test_returns_none_when_slide_absent():
    template_path = get_templates_dir() / TEMPLATES_2026["zimplats"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx is None


def test_parses_traffic_acquisition_row():
    row = _parse_traffic_acquisition_row(
        "\t1\tan / paid\t5,841 (36.81%)\t1,775 (37.06%)\t30.39%\t23s\t3.79\t22,125 (35.97%)\t0.00 (–)\t0%\t$0.00 (–)"
    )
    assert row == {
        "source_medium": "an / paid",
        "sessions": 5841,
        "sessions_pct": "36.81%",
        "engaged_sessions": 1775,
        "engaged_sessions_pct": "37.06%",
        "engagement_rate": "30.39%",
        "avg_engagement_time": "23s",
        "events_per_session": "3.79",
    }


def test_parse_traffic_acquisition_row_returns_none_for_non_data_line():
    assert _parse_traffic_acquisition_row("Rows per page:") is None
