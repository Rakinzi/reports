from types import SimpleNamespace

import pikepdf

from reports.pdf_make_fillable import (
    Box,
    DEFAULTS,
    build,
    checkbox_appearance,
    collect_rectangles,
    drop_fields_crossing_closed_columns,
    drop_option_row_overlays,
    drop_fields_inside_printed_words,
    drop_fields_overlapping_short_dates,
    infer_missing_value_cells,
    infer_checkbox_above_run,
    repeated_row_boundaries,
    restorable_closed_fields,
    rule_under_heading,
    short_date_rules_from_text,
    table_column_edges,
)
from reports.pdf_fillable_service import FillablePdfError, inspect_pdf


def test_bold_heading_may_overhang_its_underline_slightly():
    rule = (42.48, 527.59, 153.86, 540.59)
    bold_heading = (42.48, 527.10, 156.93, 538.14)

    assert rule_under_heading(rule, [], [rule], [bold_heading], [])


def test_divider_immediately_above_bold_heading_is_not_a_field():
    rule = (45.0, 770.88, 551.0, 783.88)
    bold_heading = (45.0, 760.57, 130.0, 768.61)

    assert rule_under_heading(rule, [], [rule], [bold_heading], [])


def test_infers_missing_value_cell_from_next_complete_label_value_row():
    contact_label = (45.24, 496.03, 186.05, 508.57)
    email_label = (45.12, 482.23, 186.05, 496.03)
    email_value = (187.49, 482.23, 561.72, 496.03)
    words = [
        {"text": "Contact", "x0": 50.28, "x1": 81.32, "top_pdf": 497.89, "bottom_pdf": 506.89},
        {"text": "Name", "x0": 83.85, "x1": 107.82, "top_pdf": 497.89, "bottom_pdf": 506.89},
        {"text": "Email", "x0": 49.44, "x1": 71.60, "top_pdf": 483.97, "bottom_pdf": 492.97},
        {"text": "Address", "x0": 73.92, "x1": 106.38, "top_pdf": 483.97, "bottom_pdf": 492.97},
    ]

    result = infer_missing_value_cells([contact_label, email_label, email_value], words)

    assert (187.49, 496.03, 561.72, 508.57) in result


def test_table_edges_include_header_inferred_from_labelled_siblings():
    rects = [
        (0.0, 100.0, 65.0, 120.0),
        (65.0, 100.0, 130.0, 120.0),
        (130.0, 100.0, 195.0, 120.0),
        (195.0, 100.0, 260.0, 120.0),
    ]
    words = [
        {"text": "Authorize", "x0": 70.0, "x1": 120.0, "top_pdf": 105.0, "bottom_pdf": 115.0},
        {"text": "Statements", "x0": 135.0, "x1": 188.0, "top_pdf": 105.0, "bottom_pdf": 115.0},
        {"text": "Users", "x0": 205.0, "x1": 240.0, "top_pdf": 105.0, "bottom_pdf": 115.0},
    ]

    assert 65.0 in table_column_edges(rects, words)


def test_repeated_row_boundaries_preserve_permission_columns():
    rects = []
    for y0 in (0.0, 20.0, 40.0):
        rects.extend([
            (0.0, y0, 65.0, y0 + 18.0),
            (65.8, y0, 130.0, y0 + 18.0),
        ])

    assert 65.4 in repeated_row_boundaries(rects)


def test_inspection_rejects_a_non_pdf_with_pdf_extension(tmp_path):
    fake = tmp_path / "upload.pdf"
    fake.write_bytes(b"not really a pdf")

    try:
        inspect_pdf(fake)
    except FillablePdfError as exc:
        assert "not a valid PDF" in str(exc)
    else:
        raise AssertionError("invalid upload was accepted")


def test_build_preserves_existing_acroform_widgets(tmp_path):
    source = tmp_path / "partial.pdf"
    output = tmp_path / "completed.pdf"
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(300, 300))
        widget = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Annot,
                Subtype=pikepdf.Name.Widget,
                FT=pikepdf.Name.Tx,
                T=pikepdf.String("existing_name"),
                Rect=pikepdf.Array([20, 240, 140, 260]),
                F=4,
                P=page.obj,
            )
        )
        page.Annots = pikepdf.Array([widget])
        pdf.Root.AcroForm = pdf.make_indirect(
            pikepdf.Dictionary(Fields=pikepdf.Array([widget]))
        )
        pdf.save(source)

    build(
        str(source),
        str(output),
        [Box(page=1, x0=20, y0=180, x1=140, y1=200, name="new_name")],
        font_size=0,
        borders=True,
    )

    with pikepdf.open(output) as pdf:
        names = {
            str(annot.get("/T"))
            for annot in pdf.pages[0].Annots
            if annot.get("/Subtype") == pikepdf.Name.Widget
        }
        assert names == {"existing_name", "new_name"}
        assert len(pdf.Root.AcroForm.Fields) == 2


def test_inspection_flags_active_pdf_content(tmp_path):
    source = tmp_path / "active.pdf"
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page(page_size=(300, 300))
        pdf.Root.OpenAction = pikepdf.Dictionary(
            S=pikepdf.Name.JavaScript, JS=pikepdf.String("app.alert('x')")
        )
        pdf.save(source)

    assert inspect_pdf(source).has_active_content


def test_inspection_rejects_oversized_page_geometry(tmp_path):
    source = tmp_path / "oversized.pdf"
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page(page_size=(3000, 300))
        pdf.save(source)

    try:
        inspect_pdf(source)
    except FillablePdfError as exc:
        assert "safe processing dimensions" in str(exc)
    else:
        raise AssertionError("oversized page was accepted")


def test_collects_small_square_raster_image_as_checkbox_geometry():
    page = SimpleNamespace(
        images=[{"x0": 10.0, "y0": 20.0, "x1": 25.0, "y1": 34.5}],
        curves=[],
        lines=[],
        rects=[],
        height=842.0,
    )

    assert (10.0, 20.0, 25.0, 34.5) in collect_rectangles(page, DEFAULTS)


def test_infers_missing_checkbox_above_two_complete_cells():
    rects = [
        (100.0, 20.0, 124.0, 34.0),
        (100.0, 34.0, 124.0, 48.0),
    ]
    words = [
        {"text": "New", "x0": 50.0, "x1": 68.0, "top_pdf": 50.0, "bottom_pdf": 60.0},
        {"text": "User", "x0": 70.0, "x1": 90.0, "top_pdf": 50.0, "bottom_pdf": 60.0},
    ]

    assert (100.0, 48.0, 124.0, 62.0) in infer_checkbox_above_run(rects, words, DEFAULTS)


def test_checked_appearance_draws_a_tick_not_an_x():
    pdf = pikepdf.Pdf.new()
    appearance = checkbox_appearance(pdf, 20.0, 20.0, checked=True)
    content = appearance.read_bytes().decode("latin-1")

    assert content.count(" l ") == 2
    assert " Tj" not in content


def test_short_date_rules_preserve_slashes_and_fixed_year():
    words = [{
        "text": "__/__/2025",
        "x0": 100.0,
        "x1": 160.0,
        "top_pdf": 200.0,
        "bottom_pdf": 208.0,
    }]

    rules = short_date_rules_from_text(words, DEFAULTS)

    assert rules == [
        (100.0, 200.0, 115.36, 213.0),
        (118.0, 200.0, 133.36, 213.0),
    ]


def test_single_underscore_ocr_date_segment_still_gets_two_digit_width():
    words = [{
        "text": "__/_/2025",
        "x0": 100.0,
        "x1": 160.0,
        "top_pdf": 200.0,
        "bottom_pdf": 208.0,
    }]

    rules = short_date_rules_from_text(words, DEFAULTS)

    assert round(rules[1][2] - rules[1][0], 2) == 15.36


def test_empty_single_line_closed_box_survives_container_cleanup():
    postal_address = (64.0, 95.0, 542.7, 110.5)

    assert postal_address in restorable_closed_fields(
        {postal_address}, [], set(), DEFAULTS
    )


def test_stretched_two_letter_ocr_noise_does_not_cover_empty_field():
    rect = (64.0, 95.0, 542.7, 110.5)
    words = [{
        "text": "PT",
        "x0": 64.1,
        "x1": 542.6,
        "top_pdf": 95.0,
        "bottom_pdf": 110.0,
    }]

    assert rect in restorable_closed_fields({rect}, words, set(), DEFAULTS)


def test_loose_field_crossing_two_closed_columns_is_removed():
    phone = (65.0, 396.0, 276.0, 410.0)
    email = (318.0, 395.0, 528.0, 409.0)
    crossing = (159.0, 401.0, 395.0, 414.0)
    classified = [(phone, "text"), (email, "email"), (crossing, "text")]

    result = drop_fields_crossing_closed_columns(classified, {phone, email})

    assert (crossing, "text") not in result
    assert (phone, "text") in result
    assert (email, "email") in result


def test_wide_option_row_field_is_removed_but_checkbox_remains():
    checkbox = (186.0, 528.0, 203.0, 541.0)
    row_overlay = (49.0, 524.0, 542.0, 537.0)

    result = drop_option_row_overlays([
        (checkbox, "checkbox"),
        (row_overlay, "text"),
    ])

    assert (checkbox, "checkbox") in result
    assert (row_overlay, "text") not in result


def test_loose_field_inside_logo_word_is_removed():
    field = (256.0, 759.1, 318.2, 772.1)
    word = {
        "text": "SuccessBank",
        "x0": 238.8,
        "x1": 336.7,
        "top_pdf": 761.5,
        "bottom_pdf": 773.0,
    }

    assert drop_fields_inside_printed_words([(field, "text")], [word], set()) == []


def test_large_field_over_short_date_and_slash_is_removed():
    short = (318.0, 82.0, 334.0, 95.0)
    broad = (297.0, 82.0, 335.0, 95.0)

    result = drop_fields_overlapping_short_dates(
        [(short, "date"), (broad, "date")], [short]
    )

    assert (short, "date") in result
    assert (broad, "date") not in result
    assert ((297.0, 82.0, 313.0, 95.0), "date") in result
