from pathlib import Path

from pptx import Presentation

from reports.generator_2026 import (
    TEMPLATES_2026,
    _find_traffic_acquisition_slide_index,
    _parse_traffic_acquisition_row,
    _traffic_acquisition_paras,
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


def test_traffic_acquisition_paras_uses_top_two_channels(monkeypatch):
    from reports import generator_2026

    monkeypatch.setattr(
        generator_2026, "_gemini_paras_batch", lambda raws: [r for r in raws]
    )

    rows = [
        {
            "source_medium": "an / paid", "sessions": 1967, "sessions_pct": "46.7%",
            "engaged_sessions": 564, "engaged_sessions_pct": "41.93%",
            "engagement_rate": "28.67%", "avg_engagement_time": "22s",
            "events_per_session": "3.70",
        },
        {
            "source_medium": "fb / paid", "sessions": 1138, "sessions_pct": "27.02%",
            "engaged_sessions": 312, "engaged_sessions_pct": "23.2%",
            "engagement_rate": "27.42%", "avg_engagement_time": "20s",
            "events_per_session": "3.86",
        },
    ]
    totals = {
        "sessions": 4212, "engaged_sessions": 1345, "engagement_rate": "31.93%",
        "avg_engagement_time": "24s", "events_per_session": "3.86",
    }

    subtitle, para1, para2, para3, para4 = _traffic_acquisition_paras(rows, totals)
    assert "an / paid" in subtitle
    assert "46.7%" in subtitle
    assert "1,967" in para1
    assert "fb / paid" in para2
    assert "4,212" in para4


def test_traffic_acquisition_paras_empty_rows_returns_blank():
    result = _traffic_acquisition_paras([], {})
    assert result == ("", "", "", "", "")
