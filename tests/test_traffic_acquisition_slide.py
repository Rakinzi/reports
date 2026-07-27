from pathlib import Path

from pptx import Presentation

from reports.generator_2026 import (
    TEMPLATES_2026,
    _SLIDE1_KPI_CARD_PICTURE,
    _SLIDE3_SNAPSHOT_CARD_PICTURE,
    _SLIDE4_COUNTRIES_TABLE_PICTURE,
    _SLIDE5_PAGES_TABLE_PICTURE,
    _SLIDE6_SEARCH_CONSOLE_PICTURE,
    _TOP_QUERIES_PICTURE,
    _SECURITY_HEADERS_PICTURE,
    _find_slide_index,
    _build_overview_slide,
    _build_slide_traffic_acquisition,
    _clear_recommendations_slide,
    _exec_summary_texts,
    _find_traffic_acquisition_slide_index,
    _parse_traffic_acquisition_row,
    _parse_gsc_query_row,
    _traffic_acquisition_paras,
    get_templates_dir,
)


def test_finds_mandatory_traffic_acquisition_slide_in_infraco_template():
    template_path = get_templates_dir() / TEMPLATES_2026["infraco"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx == 6


def test_finds_mandatory_traffic_acquisition_slide_in_zimplats_template():
    template_path = get_templates_dir() / TEMPLATES_2026["zimplats"]
    prs = Presentation(str(template_path))
    idx = _find_traffic_acquisition_slide_index(prs)
    assert idx == 6


def test_finds_standard_slides_by_title_when_template_adds_pages():
    template_path = get_templates_dir() / TEMPLATES_2026["infraco"]
    prs = Presentation(str(template_path))

    assert _find_slide_index(prs, "Overview") == 1
    assert _find_slide_index(prs, "Executive Summary") == 2
    assert _find_slide_index(prs, "Site Overview") == 3
    assert _find_slide_index(prs, "Page Performance") == 5
    assert _find_slide_index(prs, "Search Performance") == 7
    assert _find_slide_index(prs, "Recommendations") == 11


def test_every_template_has_exactly_one_overview_on_slide_2():
    for report_name, relative_path in TEMPLATES_2026.items():
        prs = Presentation(str(get_templates_dir() / relative_path))
        overview_indices = [
            index
            for index, slide in enumerate(prs.slides)
            if any(
                getattr(shape, "has_text_frame", False)
                and shape.text.strip() == "Overview"
                for shape in slide.shapes
            )
        ]
        assert overview_indices == [1], f"{report_name}: {overview_indices}"


def test_finds_standard_slides_when_optional_pages_are_removed():
    template_path = get_templates_dir() / TEMPLATES_2026["zimplats"]
    prs = Presentation(str(template_path))

    assert _find_slide_index(prs, "Overview") == 1
    assert _find_slide_index(prs, "Executive Summary") == 2
    assert _find_slide_index(prs, "Traffic Acquisition") == 6
    assert _find_slide_index(prs, "Search Performance") is None
    assert _find_slide_index(prs, "Recommendations") == 10


def test_delta_keeps_uptime_and_empty_recommendations_tail_slides():
    prs = Presentation(str(get_templates_dir() / TEMPLATES_2026["delta"]))
    assert _find_slide_index(prs, "Uptime and System Reliability Insight") == 12
    assert _find_slide_index(prs, "Recommendations") == 13

    recommendations = prs.slides[13]
    remaining = [
        shape.text.strip()
        for shape in recommendations.shapes
        if getattr(shape, "has_text_frame", False) and shape.text.strip()
    ]
    assert remaining == ["Recommendations"]


def test_configured_image_slots_exist_in_every_active_template():
    slots = (
        (None, _SLIDE1_KPI_CARD_PICTURE),
        ("Site Overview", _SLIDE3_SNAPSHOT_CARD_PICTURE),
        ("Geographic Performance", _SLIDE4_COUNTRIES_TABLE_PICTURE),
        ("Page Performance", _SLIDE5_PAGES_TABLE_PICTURE),
        ("Search Performance", _SLIDE6_SEARCH_CONSOLE_PICTURE),
        ("Top Queries", _TOP_QUERIES_PICTURE),
        ("Security", _SECURITY_HEADERS_PICTURE),
    )

    for report_name, relative_path in TEMPLATES_2026.items():
        prs = Presentation(str(get_templates_dir() / relative_path))
        for title, mapping in slots:
            if report_name not in mapping:
                continue
            slide_idx = 0 if title is None else _find_slide_index(prs, title)
            if slide_idx is None:  # The client intentionally omits this page.
                continue
            assert any(
                shape.name == mapping[report_name]
                for shape in prs.slides[slide_idx].shapes
            ), f"{report_name}: missing {mapping[report_name]} on {title or 'cover'}"


def test_prepared_mimosa_template_has_standard_order_and_image_slots():
    prs = Presentation(
        str(get_templates_dir() / "june-2026/mimosa-29-June-2026.pptx")
    )
    assert _find_slide_index(prs, "Overview") == 1
    assert _find_slide_index(prs, "Executive Summary") == 2

    expected = {
        None: _SLIDE1_KPI_CARD_PICTURE["mimosa"],
        "Site Overview": _SLIDE3_SNAPSHOT_CARD_PICTURE["mimosa"],
        "Geographic Performance": _SLIDE4_COUNTRIES_TABLE_PICTURE["mimosa"],
        "Page Performance": _SLIDE5_PAGES_TABLE_PICTURE["mimosa"],
        "Search Performance": _SLIDE6_SEARCH_CONSOLE_PICTURE["mimosa"],
        "Top Queries": _TOP_QUERIES_PICTURE["mimosa"],
        "Security": _SECURITY_HEADERS_PICTURE["mimosa"],
    }
    for title, shape_name in expected.items():
        slide_idx = 0 if title is None else _find_slide_index(prs, title)
        assert slide_idx is not None
        assert any(shape.name == shape_name for shape in prs.slides[slide_idx].shapes)


def test_overview_uses_current_report_period():
    prs = Presentation(str(get_templates_dir() / TEMPLATES_2026["mimosa"]))
    slide = prs.slides[_find_slide_index(prs, "Overview")]

    _build_overview_slide(slide, "mimosa", "1 July 2026 - 31 July 2026")

    narrative = next(shape for shape in slide.shapes if shape.name == "object 8")
    assert "1 July - 31 July 2026" in narrative.text
    assert "Mimosa website" in narrative.text
    assert "This report aims to analyse" in narrative.text
    assert "CMS maintenance" in narrative.text
    assert "recommended actions are clearly documented" in narrative.text
    assert "June 2026" not in narrative.text


def test_recommendations_page_keeps_heading_but_clears_copy():
    prs = Presentation(str(get_templates_dir() / TEMPLATES_2026["mimosa"]))
    slide = prs.slides[_find_slide_index(prs, "Recommendations")]

    _clear_recommendations_slide(slide)

    remaining = [
        shape.text.strip()
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False) and shape.text.strip()
    ]
    assert remaining == ["Recommendations"]


def test_traffic_acquisition_insight_is_never_empty_when_scrape_has_no_rows():
    prs = Presentation(str(get_templates_dir() / TEMPLATES_2026["delta"]))
    slide = prs.slides[_find_slide_index(prs, "Traffic Acquisition")]

    _build_slide_traffic_acquisition(slide, [], {}, {}, "delta")

    narrative = next(shape for shape in slide.shapes if shape.name == "object 7")
    assert "Overall Insight:" in narrative.text
    assert "The table compares website acquisition sources" in narrative.text


def test_executive_summary_copy_matches_previous_template_style():
    texts = _exec_summary_texts(
        "delta",
        {
            "Active users": "15K",
            "New users": "14K",
            "Average engagement time per active user": "36s",
        },
        {},
    )
    assert "15K active users" in texts["para0"]
    assert "14K (93.3%) new visitors" in texts["para0"]
    assert "audience mix" in texts["para0"]
    assert "36s" in texts["para2"]
    assert texts["para1_no_gsc"] == ""
    assert texts["para3"] == ""


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


def test_parses_newline_formatted_traffic_acquisition_row():
    parsed = _parse_traffic_acquisition_row(
        "1\n(direct) / (none)\n10,180 (62.25%)\n1,201 (22.72%)\n11.8%\n11s\n4.62"
    )
    assert parsed["source_medium"] == "(direct) / (none)"
    assert parsed["sessions"] == 10180
    assert parsed["engagement_rate"] == "11.8%"


def test_parses_gsc_query_row():
    assert _parse_gsc_query_row("econet customer care\t623\t1,204") == {
        "query": "econet customer care",
        "clicks": 623,
        "impressions": 1204,
    }


def test_gsc_query_parser_ignores_header():
    assert _parse_gsc_query_row("Query\tClicks\tImpressions") is None


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
