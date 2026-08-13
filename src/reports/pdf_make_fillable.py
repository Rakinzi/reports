#!/usr/bin/env python3
"""
Turn a printed PDF form into a fillable one.

Finds the boxes that were drawn for people to write in, and adds real AcroForm
fields on top of them, so the PDF becomes typeable in any viewer. Where the page
still has a text layer, nearby wording is used to name and label each field.

The output also feeds PDF Form Builder's precise import path, so the same file
can be used to build the web version without any guessing.

    python3 pdf_make_fillable.py form.pdf -o form-fillable.pdf
    python3 pdf_make_fillable.py form.pdf -o out.pdf --report fields.csv
    python3 pdf_make_fillable.py form.pdf -o out.pdf --pages 1-3 --dry-run

Requires: pdfplumber, pikepdf
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import logging
import re
import sys
import unicodedata
import warnings
from dataclasses import dataclass, field as dataclass_field, asdict
from typing import Iterable, Sequence

warnings.filterwarnings("ignore")
logging.getLogger("pdfminer").setLevel(logging.ERROR)

try:
    import pdfplumber
    from pdfplumber.utils import extract_words as plumber_extract_words
except ImportError:  # pragma: no cover
    sys.exit("pdfplumber is required:  pip install pdfplumber")

try:
    import pikepdf
    from pikepdf import Array, Dictionary, Name, String
except ImportError:  # pragma: no cover
    sys.exit("pikepdf is required:  pip install pikepdf")

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

# Points per inch, for converting OCR pixel coordinates back to PDF units.
OCR_RESOLUTION = 300

# The official-use dates in the reference bank forms use this width for a
# two-digit day/month cell.  OCR-derived underscore runs can measure several
# points narrower, which clips the second digit in browser PDF viewers.
SHORT_DATE_MIN_WIDTH = 15.36


# ---------------------------------------------------------------------------
# Tuning. Values are PDF points, 72 to the inch.
# ---------------------------------------------------------------------------

DEFAULTS = {
    # A box narrower than this is decoration, not somewhere to write.
    "min_text_width": 38.0,
    "min_text_height": 8.0,
    "max_text_height": 34.0,
    # Taller than this and it wants several lines.
    "multiline_height": 34.0,
    # A small square is a tick box.
    "checkbox_min": 5.0,
    "checkbox_max": 26.0,
    "checkbox_squareness": 0.45,
    # A box this large is for a signature or a photograph.
    "signature_min_area": 9000.0,
    # How far left of a box to look for its label.
    "label_search_left": 320.0,
    # How far above a box to look, when nothing sits to its left.
    "label_search_above": 26.0,
    # Words closer together than this belong to the same label.
    "label_word_gap": 14.0,
    # Two rectangles within this tolerance on every edge are the same box.
    "dedupe_tolerance": 2.0,
    # A run of underscores or dots this long is a line to write on.
    "rule_min_chars": 3,
    "rule_min_width": 34.0,
    # How tall to make a field sitting on a ruled line.
    "rule_height": 13.0,
    # A label is a phrase, not a whole row of the form.
    "label_max_words": 7,
    "label_max_chars": 52,
}

# Label keyword to field type. First match wins, so specific rules go first.
TYPE_RULES: Sequence[tuple[str, str]] = (
    (r"\b(e-?mail)\b", "email"),
    (r"\b(date of birth|d\.?o\.?b\.?|birth ?date)\b", "date"),
    (r"\b(date|expiry|expires|issued|appointed|incorporation)\b", "date"),
    (r"\b(cell|mobile|phone|telephone|tel|fax|whatsapp)\b", "tel"),
    (r"\b(website|web ?site|url)\b", "url"),
    (r"\b(amount|fee|balance|salary|total|quantity|qty|number of|age)\b", "number"),
    (r"\b(signature|signed by)\b", "signature"),
    (r"\b(address)\b", "address"),
)

ACRONYMS = {
    "id", "dob", "url", "vat", "tin", "nrc", "pin", "iban", "swift", "zip",
    "cr", "fca", "usd", "zar", "sms", "cv",
}


@dataclass
class Box:
    """A rectangle that looks like somewhere to write."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str = "text"
    label: str = ""
    name: str = ""
    group: str = ""
    labelled: bool = True
    max_length: int = 0
    confidence: float = 0.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class Result:
    boxes: list[Box] = dataclass_field(default_factory=list)
    pages_without_text: list[int] = dataclass_field(default_factory=list)
    pages_ocred: list[int] = dataclass_field(default_factory=list)
    page_count: int = 0


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def split_rect_by_verticals(
    rect: tuple[float, float, float, float], lines: list[dict], tolerance: float = 1.5
) -> list[tuple[float, float, float, float]]:
    """
    Cut a drawn rectangle into cells wherever a vertical line crosses it
    full height.

    A row of single-character boxes - a split date field, an account number
    with one digit per cell - is sometimes drawn as one outer `re` rectangle
    with the cell dividers as separate line strokes inside it, rather than as
    N independent boxes. Left as one rectangle it becomes a single field wide
    enough for the whole row, which defeats the one-character-per-cell intent
    the drawing shows. A vertical only counts as a divider if it spans (close
    to) the rectangle's full height - a shorter mark inside it is content,
    not structure.
    """
    x0, y0, x1, y1 = rect
    height = y1 - y0
    if height <= 0:
        return [rect]

    cuts = set()
    for line in lines:
        if abs(line["x0"] - line["x1"]) > tolerance:
            continue  # not vertical
        x = line["x0"]
        if not (x0 + tolerance < x < x1 - tolerance):
            continue
        ly0, ly1 = sorted((line["y0"], line["y1"]))
        if ly0 <= y0 + tolerance and ly1 >= y1 - tolerance:
            cuts.add(round(x, 2))

    if not cuts:
        return [rect]

    xs = [x0] + sorted(cuts) + [x1]
    return [(xs[i], y0, xs[i + 1], y1) for i in range(len(xs) - 1)]


def curve_rects_and_lines(page, tolerance: float = 0.6) -> tuple[list[tuple[float, float, float, float]], list[dict]]:
    """
    Boxes and rules that a design tool drew as a closed vector path instead
    of the `re` rectangle operator pdfplumber's page.rects looks for.

    Some form exporters trace every box and underline through an
    illustration layer, closing the path back on its own start point rather
    than issuing a single `re`. pdfplumber still sees the geometry, but only
    ever files it under page.curves - genuinely curved artwork (a logo's
    swash, a decorative flourish) lives there too, so a path only counts
    here when its points never wander more than a hair off the straight
    line between its own bounding box's edges in one axis or the other: no
    way to bow a real curve into that shape, but exactly what a
    straight-edged box or line looks like once traced this way. A row of
    dividers sharing one rail is sometimes drawn as a single path that
    revisits the same y twice at every x it passes through rather than a
    plain two-point stroke, so the test is against the path's own bounding
    box, not a fixed count of distinct coordinates.

    A path whose points span both a real width and a real height is a
    closed box, returned the same shape as a page.rects entry. One that
    collapses flat in one direction was never a box at all, only a single
    stroke - a divider between split cells, or a bare underline - and is
    returned as a line dict instead, in the same shape page.lines entries
    already have, so split_rect_by_verticals and rectangles_from_lines can
    use it without knowing where it came from.
    """
    rects: list[tuple[float, float, float, float]] = []
    lines: list[dict] = []
    page_height = page.height

    for curve in page.curves:
        if not curve.get("stroke"):
            continue
        pts = curve.get("pts") or []
        if len(pts) < 4:
            continue

        x0, x1 = curve["x0"], curve["x1"]
        y0, y1 = curve["y0"], curve["y1"]

        # pts is reported top-down, the same as page.chars and page.lines'
        # own top/bottom fields, while x0/y0/x1/y1 here are already in
        # PDF's bottom-up space - flipped to match before comparing them,
        # or every point looks arbitrarily far from its own bounding box.
        flipped_pts = [(px, page_height - py) for px, py in pts]

        # Every point of a straight-edged path sits on one of its own two
        # x rails or one of its own two y rails - a real curve's points
        # wander in between instead, on both axes at once.
        axis_aligned = all(
            min(abs(px - x0), abs(px - x1)) <= tolerance
            or min(abs(py - y0), abs(py - y1)) <= tolerance
            for px, py in flipped_pts
        )
        if not axis_aligned:
            continue

        width, height = x1 - x0, y1 - y0

        if width > tolerance and height > tolerance:
            rects.append((x0, y0, x1, y1))
        else:
            lines.append(
                {
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "stroking_color": curve.get("stroking_color"),
                    "fill": curve.get("fill"),
                    "stroke": curve.get("stroke"),
                }
            )

    return rects, lines


def filled_border_lines(page, tolerance: float = 2.0) -> list[dict]:
    """
    Table borders drawn as thin filled rectangles rather than strokes.

    Some export tools rule a table by painting a run of narrow, unstroked
    rectangles along each row and column boundary instead of drawing a
    stroked line - a cell wall this way is fill=True, stroke=False, and
    thin in exactly one dimension, the same shape a page.lines entry has
    once reduced to two points. It is not the same shape a dot leader's
    dash is, though - rules_from_slivers already claims those separately,
    and they are thin in both dimensions at once, never spanning a whole
    row or column the way a cell wall does. Returned in the same line-dict
    shape rectangles_from_lines already expects, so a table ruled this way
    can be paired into cells the same as one ruled with real strokes.
    """
    lines: list[dict] = []
    for rect in page.rects:
        if not rect.get("fill") or rect.get("stroke"):
            continue
        width, height = rect["x1"] - rect["x0"], rect["bottom"] - rect["top"]
        if width <= tolerance and height > tolerance:
            x = (rect["x0"] + rect["x1"]) / 2
            lines.append({"x0": x, "y0": rect["y0"], "x1": x, "y1": rect["y1"]})
        elif height <= tolerance and width > tolerance:
            y = (rect["y0"] + rect["y1"]) / 2
            lines.append({"x0": rect["x0"], "y0": y, "x1": rect["x1"], "y1": y})
    return lines


def collect_rectangles(page, cfg: dict) -> list[tuple[float, float, float, float]]:
    """
    Every rectangle on the page, in PDF coordinates with the origin at the
    bottom left.

    Boxes reach a page three ways: as a `re` operator, which pdfplumber reports
    in page.rects; as four separate line segments closing off a box, which it
    reports in page.lines; and as a single stroke drawn under a blank space for
    someone to write on, with no box at all. Forms mix these freely, sometimes
    on the same page, so all three are gathered here - along with a fourth,
    rarer case: a box or underline traced as a closed vector path rather than
    any of the above, recovered by curve_rects_and_lines.
    """
    curve_rects, curve_lines = curve_rects_and_lines(page)

    out: list[tuple[float, float, float, float]] = list(curve_rects)

    # Some PDF compressors rasterize isolated empty checkbox squares while
    # leaving neighbouring boxes as vectors.  A small, near-square image is
    # the checkbox artwork itself and should contribute the same geometry as
    # a stroked rectangle.  The 10-point floor avoids treating rasterized
    # punctuation or tiny glyph fragments as fields.
    for image in page.images:
        width = image["x1"] - image["x0"]
        height = image["y1"] - image["y0"]
        longest = max(width, height)
        if (
            10.0 <= width <= cfg["checkbox_max"]
            and 10.0 <= height <= cfg["checkbox_max"]
            and longest > 0
            and abs(width - height) / longest <= cfg["checkbox_squareness"]
        ):
            out.append((image["x0"], image["y0"], image["x1"], image["y1"]))
    all_lines = list(page.lines) + curve_lines
    slivers: list[dict] = []

    for rect in page.rects:
        # A compressor can leave behind filled rectangles with zero alpha:
        # invisible on the rendered page, but still geometry to pdfplumber.
        # Neither a stroked box nor a visibly filled one, so never a real
        # field - only ever image-tiling debris.
        colour = rect.get("non_stroking_color")
        invisible_fill = (
            rect.get("fill")
            and not rect.get("stroke")
            and isinstance(colour, tuple)
            and len(colour) == 4
            and colour[3] == 0
        )
        if invisible_fill:
            continue

        # A dot leader is sometimes drawn as many small filled slivers
        # rather than typed dots or a single stroke - each one far too
        # small on its own to be a field or worth splitting by a vertical,
        # so it is set aside here and only turned into a field, as a run,
        # once every rect on the page has been seen.
        width, height = rect["x1"] - rect["x0"], rect["bottom"] - rect["top"]
        if rect.get("fill") and not rect.get("stroke") and width < 10 and height < 2:
            slivers.append(rect)
            continue

        box = (rect["x0"], rect["y0"], rect["x1"], rect["y1"])
        out.extend(split_rect_by_verticals(box, all_lines))

    out.extend(rules_from_slivers(slivers, cfg["rule_height"]))

    closed, loose = rectangles_from_lines(page)
    # A rect pieced together from four strokes can still have its own
    # interior dividers among those same strokes - a split date field's
    # cell walls, say - so it needs the same verticals pass a page.rects
    # entry gets above, or the whole span comes out as one field.
    for rect in closed:
        out.extend(split_rect_by_verticals(rect, all_lines))

    # A short answer split across several strokes - "Date __/__/2025", one
    # stroke per digit pair either side of a printed slash - is narrower
    # than rule_min_width per piece even though the whole answer isn't, so
    # adjacent pieces are joined into one field first and only the result
    # checked against the width floor, the same order rules_from_text's
    # own dot-leader pieces are merged and checked in.
    #
    # A pair of strokes short enough to need merging at all is never
    # decorative noise the way one lone short stroke elsewhere on the page
    # might be - nothing draws two dashes side by side just for
    # ornamentation - so a merged run earns a lower floor than a single
    # untouched piece would, one still comfortably above a tick box or a
    # stray sliver.
    out.extend(merge_and_filter_rules(rules_from_loose_lines(loose, cfg["rule_height"]), cfg))
    return out


def rules_from_slivers(
    slivers: list[dict], rule_height: float = 13.0, gap: float = 2.0, min_run: int = 4
) -> list[tuple[float, float, float, float]]:
    """
    Turn a run of tiny filled rectangles - a dot leader drawn as many small
    dashes rather than typed dots or a single stroke - into one field.

    A lone tiny filled rect this size is decorative (a logo's own accent
    mark), indistinguishable from one dash of a leader by shape alone - only
    the run gives it away. Several of them in a row, close enough that no
    real content could sit between them, is instead a blank line meant to be
    written on, same as a run of literal dots would be.
    """
    by_row: dict[float, list[dict]] = {}
    for sliver in slivers:
        by_row.setdefault(round(sliver["top"], 1), []).append(sliver)

    boxes: list[tuple[float, float, float, float]] = []
    for row in by_row.values():
        row.sort(key=lambda r: r["x0"])
        run = [row[0]]
        for sliver in row[1:]:
            if sliver["x0"] - run[-1]["x1"] <= gap:
                run.append(sliver)
                continue
            if len(run) >= min_run:
                boxes.append(_sliver_run_to_rule(run, rule_height))
            run = [sliver]
        if len(run) >= min_run:
            boxes.append(_sliver_run_to_rule(run, rule_height))
    return boxes


def _sliver_run_to_rule(
    run: list[dict], rule_height: float
) -> tuple[float, float, float, float]:
    x_low = run[0]["x0"]
    x_high = run[-1]["x1"]
    y = max(run[0]["y0"], run[0]["y1"])
    return (x_low, y, x_high, y + rule_height)


def rectangles_from_lines(
    page, tolerance: float = 2.5
) -> tuple[list[tuple[float, float, float, float]], list[dict]]:
    """
    Reconstruct rectangles drawn as four separate strokes.

    Pairs of horizontal lines that share their span are matched with pairs of
    vertical lines that close them off at both ends. Horizontal lines that
    never pair up this way are returned separately: a form ruled with plain
    underlines, no box, draws exactly one stroke per answer and no verticals
    at all, so those lines are just as much a place to write as a closed box
    is, and are handled by the caller as rules instead of being discarded.

    A single stroke can also reach the page as a flat, degenerate curve path
    rather than a page.lines entry - curve_rects_and_lines finds those and
    they are folded in here too, so a divider or underline drawn that way
    still pairs up with the rest of a box's strokes the same as any other.
    A table ruled with thin filled rectangles instead of any stroke at all
    is folded in the same way, via filled_border_lines.
    """
    _, curve_lines = curve_rects_and_lines(page)
    border_lines = filled_border_lines(page)
    horizontals: list[dict] = []
    verticals: list[dict] = []

    for line in list(page.lines) + curve_lines + border_lines:
        # A compressor can leave a stroke drawn with zero-alpha colour:
        # invisible on the rendered page, but still geometry to pdfplumber,
        # the same way it can leave an invisible filled rectangle. Never a
        # real underline or box border - only ever grid debris left behind
        # by whatever flattened the page.
        colour = line.get("stroking_color")
        if isinstance(colour, tuple) and len(colour) == 4 and colour[3] == 0:
            continue
        if abs(line["y0"] - line["y1"]) <= tolerance and abs(line["x1"] - line["x0"]) > tolerance:
            horizontals.append(line)
        elif abs(line["x0"] - line["x1"]) <= tolerance and abs(line["y1"] - line["y0"]) > tolerance:
            verticals.append(line)

    found: list[tuple[float, float, float, float]] = []
    used: set[int] = set()

    for i, top in enumerate(horizontals):
        for j in range(i + 1, len(horizontals)):
            bottom = horizontals[j]
            if abs(top["x0"] - bottom["x0"]) > tolerance:
                continue
            if abs(top["x1"] - bottom["x1"]) > tolerance:
                continue

            y_low, y_high = sorted((min(top["y0"], top["y1"]), min(bottom["y0"], bottom["y1"])))
            if y_high - y_low <= tolerance:
                continue

            x_low, x_high = min(top["x0"], bottom["x0"]), max(top["x1"], bottom["x1"])

            left = any(
                abs(v["x0"] - x_low) <= tolerance
                and min(v["y0"], v["y1"]) <= y_low + tolerance
                and max(v["y0"], v["y1"]) >= y_high - tolerance
                for v in verticals
            )
            right = any(
                abs(v["x0"] - x_high) <= tolerance
                and min(v["y0"], v["y1"]) <= y_low + tolerance
                and max(v["y0"], v["y1"]) >= y_high - tolerance
                for v in verticals
            )

            if left and right:
                found.append((x_low, y_low, x_high, y_high))
                used.add(i)
                used.add(j)

    loose = [line for i, line in enumerate(horizontals) if i not in used]
    return found, loose


def rules_from_loose_lines(
    lines: list[dict], rule_height: float = 13.0
) -> list[tuple[float, float, float, float]]:
    """
    Turn standalone underline strokes into write-on-this-line boxes.

    A line that never paired into a closed rectangle is a bare underline, the
    vector equivalent of a run of underscores. The field sits above it, same
    as a typed rule. pdfplumber's line objects already report y0/y1 in PDF's
    native bottom-up coordinates (mirroring them again here would place the
    field on the opposite side of the page from the line it was drawn under).

    A "line" that is only ever filled, never stroked, is a thin decorative
    bar - a logo's accent rule, for instance - rather than a stroke drawn to
    write on. A real underline is always a stroke, so a fill-only one is
    skipped here rather than turned into a field.
    """
    boxes: list[tuple[float, float, float, float]] = []
    for line in lines:
        if line.get("fill") and not line.get("stroke"):
            continue
        x_low, x_high = sorted((line["x0"], line["x1"]))
        y = max(line["y0"], line["y1"])
        boxes.append((x_low, y, x_high, y + rule_height))
    return boxes


def rule_under_heading(
    rect: tuple[float, float, float, float],
    words: list[dict],
    all_loose_rules: list[tuple[float, float, float, float]],
    bold_boxes: list[tuple[float, float, float, float]] | None = None,
    banners: list[tuple[float, str, float, float]] | None = None,
) -> bool:
    """
    True when a loose-line rule is really a heading's own underline rather
    than a blank waiting for an answer.

    A bare stroke reconstructed by rules_from_loose_lines carries no memory
    of what, if anything, is printed near it - unlike a dot leader from
    rules_from_text, whose rule is always read straight off a specific
    word's own trailing dots, so overlapping that one word is expected and
    already exempted elsewhere. Word overlap alone can't safely tell a
    heading's own underline apart from a genuine two-line answer area, "All
    documents to be signed by: (Please specify ...)" with its first blank
    sitting close enough beneath the label to overlap it exactly the same
    way once the rule's own field height reaches back up into it - both
    read as "a rule whose zone contains the label above it" by width and
    overlap alike.

    Three different, narrower signals each rule out that overlap on their
    own instead: the single topmost loose-line rule on the whole page is
    always the document's own title if it overlaps text at all - a form
    never opens with a write-on-this-line box before a single field's own
    label - and a rule overlapping a bold text run is a section heading's
    own underline, since a bold field label is not a pattern this kind of
    form ever draws (its bold text is reserved for headings). A section
    banner is sometimes preceded by a divider stroke rather than following
    right on from one, though, on a page whose text is all OCR'd and
    carries no font weight to check at all - "FOR OFFICIAL USE ONLY" a few
    points below a bare horizontal rule with nothing at all overlapping
    the rule's own zone, so neither of the first two signals ever fires.
    A rule sitting just above a banner's own baseline, spanning close to
    that banner's own width, is caught by this third check instead.

    None of the three alone catches every heading a form might draw, but
    together only genuine headings are ever this close to a loose-line
    rule on this shape of form - a real answer blank never opens a page,
    is never itself bold, and is never immediately followed by a
    recognised section title.
    """
    is_topmost = bool(all_loose_rules) and rect[1] == max(r[1] for r in all_loose_rules)

    top, bottom = rect[1], rect[3]

    if is_topmost:
        for w in words:
            if not re.search(r"[A-Za-z0-9]{2,}", w["text"]):
                continue
            if w["top_pdf"] >= bottom or w["bottom_pdf"] <= top:
                continue
            if rect[0] - 1 <= w["x0"] and w["x1"] <= rect[2] + 1:
                return True

    for bx0, by0, bx1, by1 in bold_boxes or []:
        # Exporters do not always give a heading's rule and glyph run the
        # exact same width.  In particular, faux-bold text can overhang its
        # own underline by a few points.  Treat near-total horizontal
        # overlap as the same heading instead of requiring strict
        # containment, while keeping short answer rules beside a bold label
        # out of the match.
        overlap = max(0.0, min(rect[2], bx1) - max(rect[0], bx0))
        bold_width = max(0.01, bx1 - bx0)
        rule_width = max(0.01, rect[2] - rect[0])
        overlaps_vertically = not (by0 >= bottom or by1 <= top)
        sits_just_above = 0 <= top - by1 <= 8
        same_width_heading_rule = (
            overlaps_vertically
            and overlap / bold_width >= 0.9
            and overlap / rule_width >= 0.9
        )
        divider_spanning_heading = sits_just_above and overlap / bold_width >= 0.9
        if same_width_heading_rule or divider_spanning_heading:
            return True

    for baseline, _, title_x0, title_x1 in banners or []:
        if not (0 <= top - baseline <= 8):
            continue
        if rect[0] - 5 <= title_x0 and title_x1 <= rect[2] + 5:
            return True

    return False


def infer_missing_value_cells(
    rects: list[tuple[float, float, float, float]],
    words: list[dict],
    tolerance: float = 2.5,
) -> list[tuple[float, float, float, float]]:
    """Restore a value cell whose fragmented border was not reconstructed.

    Label/value tables sometimes export the first row's top and side rails
    as several tiny paths.  The label cell is still recovered, and the next
    complete row proves the value column's x bounds, but no closed rectangle
    remains for the first answer.  Infer it only from two vertically adjacent
    label-bearing cells with matching columns plus the lower row's value cell;
    that narrow pattern avoids inventing fields in ordinary data tables.
    """
    labelled = [rect for rect in rects if covered_by_label(rect, words)]
    additions: list[tuple[float, float, float, float]] = []

    for upper in labelled:
        for lower in labelled:
            same_label_column = (
                abs(upper[0] - lower[0]) <= tolerance
                and abs(upper[2] - lower[2]) <= tolerance
            )
            directly_below = abs(lower[3] - upper[1]) <= tolerance
            if not (same_label_column and directly_below):
                continue

            lower_values = [
                rect
                for rect in rects
                if abs(rect[1] - lower[1]) <= tolerance
                and abs(rect[3] - lower[3]) <= tolerance
                and 0 <= rect[0] - lower[2] <= tolerance * 2
                and rect[2] - rect[0] >= 38.0
                and not covered_by_label(rect, words)
            ]
            for value in lower_values:
                candidate = (value[0], upper[1], value[2], upper[3])
                if any(
                    abs(existing[0] - candidate[0]) <= tolerance
                    and abs(existing[1] - candidate[1]) <= tolerance
                    and abs(existing[2] - candidate[2]) <= tolerance
                    and abs(existing[3] - candidate[3]) <= tolerance
                    for existing in rects + additions
                ):
                    continue
                additions.append(candidate)

    return rects + additions


def infer_checkbox_above_run(
    rects: list[tuple[float, float, float, float]],
    words: list[dict],
    cfg: dict,
    tolerance: float = 2.0,
) -> list[tuple[float, float, float, float]]:
    """Infer a missing top checkbox cell from two complete cells below it."""
    cells = [
        rect
        for rect in rects
        if 10.0 <= rect[3] - rect[1] <= cfg["checkbox_max"]
        and 10.0 <= rect[2] - rect[0] <= cfg["checkbox_max"]
    ]
    additions: list[tuple[float, float, float, float]] = []
    for upper in cells:
        for lower in cells:
            same_column = abs(upper[0] - lower[0]) <= tolerance and abs(upper[2] - lower[2]) <= tolerance
            adjacent = abs(lower[3] - upper[1]) <= tolerance
            if not (same_column and adjacent):
                continue
            height = upper[3] - upper[1]
            candidate = (upper[0], upper[3], upper[2], upper[3] + height)
            has_row_label = any(
                w["x1"] <= candidate[0] + tolerance
                and candidate[0] - w["x1"] <= 160.0
                and w["top_pdf"] < candidate[3]
                and w["bottom_pdf"] > candidate[1]
                and re.search(r"[A-Za-z]{2,}", w["text"])
                for w in words
            )
            already_present = any(
                abs(r[0] - candidate[0]) <= tolerance
                and abs(r[1] - candidate[1]) <= tolerance
                and abs(r[2] - candidate[2]) <= tolerance
                and abs(r[3] - candidate[3]) <= tolerance
                for r in rects + additions
            )
            if has_row_label and not already_present:
                additions.append(candidate)
    return additions


def rules_from_text(words: list[dict], cfg: dict) -> list[tuple[float, float, float, float]]:
    """
    Boxes for forms ruled with underscores or dot leaders rather than drawn
    boxes. The rule is typed characters, not geometry, so it has to be found in
    the text rather than among the rectangles.

    The field sits on the rule and rises above it, which is where a person
    writing on paper would put their answer.
    """
    boxes: list[tuple[float, float, float, float]] = []

    for word in words:
        text = word["text"]
        if len(text) < cfg["rule_min_chars"]:
            continue

        if re.fullmatch(r"[_—–.…]{3,}", text):
            # A run of full stops is only a rule when long enough to write on.
            if text[0] in "." and len(text) < 6:
                continue
            x0 = word["x0"]
        else:
            # OCR often glues a dot leader onto the word before it, and
            # misreads the dots themselves further along as stray letters,
            # e.g. "by.....scceecsss...". The leader still always starts at
            # the first run of three or more literal dots; whatever the OCR
            # made of the rest of the line is the rule, not a real word.
            match = re.search(r"\.{3,}", text)
            if not match or match.start() == 0:
                continue
            span = word["x1"] - word["x0"]
            per_char = span / max(1, len(text))
            x0 = word["x0"] + match.start() * per_char

        baseline = word["top_pdf"]
        boxes.append((x0, baseline, word["x1"], baseline + cfg["rule_height"]))

    # Width is checked after merging, not here. A date written as
    # "____ / ____ / ________" is three short runs and one field.
    return boxes


def short_date_rules_from_text(
    words: list[dict], cfg: dict
) -> list[tuple[float, float, float, float]]:
    """Short underscore blanks inside strings such as ``__/__/2025``."""
    boxes: list[tuple[float, float, float, float]] = []
    for word in words:
        text = word["text"]
        if "_" not in text or "/" not in text:
            continue
        runs = list(re.finditer(r"_+", text))
        if not runs:
            continue
        span = word["x1"] - word["x0"]
        per_char = span / max(1, len(text))
        for run in runs:
            x0 = word["x0"] + run.start() * per_char
            # OCR sometimes reads a printed two-character month blank as a
            # single underscore.  Date segments still need room for two
            # digits, so enforce a two-character visual width.
            x1 = x0 + max(
                SHORT_DATE_MIN_WIDTH,
                max(2, run.end() - run.start()) * per_char,
            )
            boxes.append((x0, word["top_pdf"], x1, word["top_pdf"] + cfg["rule_height"]))
    return boxes


def merge_adjacent(rects: list[tuple[float, float, float, float]], gap: float = 12.0) -> list[tuple[float, float, float, float]]:
    """
    Join rules broken into pieces into one field.

    A date written as "____ / ____ / ________" is three rules and one answer, so
    the separators are jumped rather than treated as field boundaries.
    """
    if not rects:
        return []

    ordered = sorted(rects, key=lambda r: (-round(r[1], 1), r[0]))
    merged = [list(ordered[0])]

    for rect in ordered[1:]:
        last = merged[-1]
        same_line = abs(rect[1] - last[1]) <= 2.0
        # A rect from another row can still round to within 2.0 of last[1]
        # without the two ever having shared a row - two rows a few points
        # apart, close together on a crowded line of small print. Without a
        # lower bound here, that rect's own x0 being left of last[2] (it
        # never really followed last at all) still reads as "gap of -40",
        # which passes "<= gap" the same way a real, small gap would, and
        # silently swallows it into a field's bounds from a different row
        # entirely.
        adjacent = -0.5 <= rect[0] - last[2] <= gap
        if same_line and adjacent:
            last[2] = max(last[2], rect[2])
            last[3] = max(last[3], rect[3])
            continue
        merged.append(list(rect))

    return [tuple(r) for r in merged]


def merge_and_filter_rules(
    rules: list[tuple[float, float, float, float]], cfg: dict
) -> list[tuple[float, float, float, float]]:
    """
    Join adjacent rule pieces, then keep only the ones wide enough to write
    an answer on.

    A pair of strokes short enough to have needed merging at all is never
    decorative noise the way one lone short stroke elsewhere on the page
    might be - nothing draws two dashes side by side just for ornamentation
    - so a merged run earns a lower floor than a single untouched piece
    would, one still comfortably above a tick box or a stray sliver. This is
    shared by every caller that turns loose geometric strokes into rules -
    collect_rectangles and detect's own rule_set both need the identical
    merge and the identical floor, or a rect one accepts and the other
    doesn't ends up drawn as a field but excluded from the rule exemptions
    that field's own width depends on.
    """
    raw = rules
    merged = merge_adjacent(raw)
    raw_set = set(raw)
    min_width = cfg["rule_min_width"]
    kept = []
    for rect in merged:
        was_merged = rect not in raw_set
        floor = cfg["checkbox_max"] if was_merged else min_width
        if rect[2] - rect[0] >= floor:
            kept.append(rect)
    return kept


def dedupe(rects: Iterable[tuple[float, float, float, float]], tolerance: float) -> list[tuple[float, float, float, float]]:
    """
    Collapse rectangles that are really the same box.

    A box stroked and filled appears twice, and a box with a visible border is
    often two rectangles a hair apart. Nested rectangles within the tolerance
    are treated as one, keeping the outer.
    """
    ordered = sorted(rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True)
    kept: list[tuple[float, float, float, float]] = []

    for rect in ordered:
        duplicate = False
        for existing in kept:
            if (
                abs(rect[0] - existing[0]) <= tolerance
                and abs(rect[1] - existing[1]) <= tolerance
                and abs(rect[2] - existing[2]) <= tolerance
                and abs(rect[3] - existing[3]) <= tolerance
            ):
                duplicate = True
                break
            # Fully contained and nearly the same size: an inner border.
            if (
                rect[0] >= existing[0] - tolerance
                and rect[1] >= existing[1] - tolerance
                and rect[2] <= existing[2] + tolerance
                and rect[3] <= existing[3] + tolerance
            ):
                inner = (rect[2] - rect[0]) * (rect[3] - rect[1])
                outer = (existing[2] - existing[0]) * (existing[3] - existing[1])
                if outer > 0 and inner / outer > 0.75:
                    duplicate = True
                    break
        if not duplicate:
            kept.append(rect)

    return kept


def split_date_run_indices(
    boxes: list[tuple[float, float, float, float]], gap: float = 3.0, min_run: int = 2
) -> set[int]:
    """
    Indices of boxes that belong to a split date field: "DD MM YYYY" drawn as
    one small square per character.

    Those squares are checkbox-sized, so `classify` calls them tick boxes on
    size alone, but a real tick box always has its label sitting well clear
    of it, wide enough for a word like "Golf" to fit. A run of several
    same-row boxes sitting almost flush against each other, near enough that
    no label could fit between them, is a split field instead.

    Two flush cells are already enough: a date is sometimes drawn as three
    short grids side by side rather than one long one - two cells for the
    day, two for the month, four for the year - and a real tick box is
    never flush against another tick box regardless of how many sit in the
    row, so there is no run length this could mistake for a genuine
    checkbox chain the way there might be for some looser adjacency test.
    """
    by_row: dict[float, list[int]] = {}
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        by_row.setdefault(round(y0, 1), []).append(i)

    marked: set[int] = set()
    for indices in by_row.values():
        indices.sort(key=lambda i: boxes[i][0])
        run = [indices[0]]
        for i in indices[1:]:
            prev_x1 = boxes[run[-1]][2]
            if boxes[i][0] - prev_x1 <= gap:
                run.append(i)
                continue
            if len(run) >= min_run:
                marked.update(run)
            run = [i]
        if len(run) >= min_run:
            marked.update(run)
    return marked


def segment_cell_indices(
    classified: list[tuple[tuple[float, float, float, float], str]],
    all_rects: list[tuple[float, float, float, float]],
    gap: float = 1.0,
    min_width: float = 30.0,
) -> set[int]:
    """
    Indices of checkbox-sized rects that are really one segment of a wider
    multi-part field, such as a country-code cell in front of a phone
    number - not a run of same-sized cells like a split date, but a chain of
    flush cells, at least one of them plainly too wide to be a tick box.

    A real tick box's label is ordinary text, never another drawn rectangle,
    so it always leaves a visible gap - room for a word like "Golf" - before
    anything else on its row. A checkbox-sized cell chained flush to a
    neighbour far too wide to be another tick box is instead one piece of a
    field someone chose to draw as adjacent boxes - and the chain is
    followed through cells too narrow to write on and too wide for a tick
    box, which classify as neither and would otherwise make two real
    segments either side of one look unconnected.

    The neighbour is looked up in every rectangle on the page, not just the
    ones that ended up classified as a field, for the same reason.
    """
    def row_key(r: tuple[float, float, float, float]) -> tuple[float, float]:
        return (round(r[1], 1), round(r[3], 1))

    rows: dict[tuple[float, float], list[tuple[float, float, float, float]]] = {}
    for r in all_rects:
        rows.setdefault(row_key(r), []).append(r)

    marked: set[int] = set()
    for i, (rect, kind) in enumerate(classified):
        if kind != "checkbox":
            continue
        row = rows.get(row_key(rect), [])
        row = sorted(row, key=lambda r: r[0])
        pos = row.index(rect)

        chain_has_wide_neighbour = False
        # Walk right, then left, through flush neighbours only.
        for step in (1, -1):
            j = pos
            while True:
                nxt = j + step
                if nxt < 0 or nxt >= len(row):
                    break
                prev_rect, next_rect = (row[j], row[nxt]) if step > 0 else (row[nxt], row[j])
                if not (-0.5 <= next_rect[0] - prev_rect[2] <= gap):
                    break
                if row[nxt][2] - row[nxt][0] >= min_width:
                    chain_has_wide_neighbour = True
                    break
                j = nxt

        if chain_has_wide_neighbour:
            marked.add(i)
    return marked


def covered_by_label(
    rect: tuple[float, float, float, float],
    words: list[dict],
    min_coverage: float = 0.3,
    min_width: float = 30.0,
) -> bool:
    """
    True when a rectangle is really a label sitting in a cell of its own,
    such as a table's header row, not a blank waiting to be filled.

    A geometric cell is only worth checking this way when it comes from real
    drawn boxes - a table header cell and a table data cell are drawn
    identically, so geometry alone can't tell them apart, but only the
    header one has its column title sitting entirely inside it. Requiring
    at least two real alphanumeric characters per word rules out the actual
    risk here - a misread border sliver or punctuation from an adjacent
    line producing a "word" that is really just noise - without also
    requiring multiple words, which would miss a single-word column header.

    A checkbox-sized cell is excluded outright: a split date field's single
    digit box is barely wider than one character, so a single misread
    letter - a "Y" hint OCR'd as "ry" - can cover most of its width and look
    exactly like a real label by that same test, at a size no genuine column
    header is ever drawn at. Above that floor a short real label can still
    fall just under a stricter ratio than this - "Fax Number" only clears
    about a third of its own cell's width - so the floor stays this low
    deliberately, one a misread sliver only reaches by being wide enough to
    already be well past checkbox-sized in the first place.
    """
    width = rect[2] - rect[0]
    if width <= 0 or width < min_width:
        return False

    top, bottom = rect[1], rect[3]
    inside = [
        w
        for w in words
        if w["x0"] >= rect[0] - 1
        and w["x1"] <= rect[2] + 1
        and w["top_pdf"] >= top - 1
        and w["bottom_pdf"] <= bottom + 1
        and re.search(r"[A-Za-z0-9]{2,}", w["text"])
        # OCR occasionally hallucinates a two-letter token spanning an
        # entire empty field ("PT" across a 479-point address box).  Real
        # printed labels never have character spacing remotely this large.
        and (w["x1"] - w["x0"])
        / max(1, len(re.findall(r"[A-Za-z0-9]", w["text"])))
        <= 18.0
    ]
    if not inside:
        return False

    covered = sum(w["x1"] - w["x0"] for w in inside)
    return covered / width >= min_coverage


def _header_sibling_and_confirmed(
    rects: list[tuple[float, float, float, float]],
    words: list[dict],
    size_tolerance: float = 1.0,
) -> tuple[set[tuple[float, float, float, float]], set[tuple[float, float, float, float]]]:
    """
    Header cells whose own column title fails OCR outright - not garbled,
    just never read at all - because it is white print on a dark fill, a
    contrast neither OCR pass is built to read.

    `covered_by_label` alone leaves such a cell fillable, since it has no
    text to work with. But a table header row is drawn as a strip of cells
    that are all the same height, and turning the whole row into a match
    the moment any one of them clears `covered_by_label` risks reaching
    past the table into unrelated rows the same height happens to recur in
    - a signature grid's own captions, for instance, drawn as tall boxes
    that are never the same height as their own labels' text row.

    So the match here is narrower: a header cell is only inferred from a
    same-row neighbour that is flush against it (no gap for a whole other
    cell to have fit between them) AND identical in both width and height,
    not merely the same height - the two title cells in this row usually
    are, since a title's own cell width isn't tied to what it says the way
    a caption or answer field's width is elsewhere on the page.

    Returns both the inferred cells and the label-bearing cells a sibling
    match actually confirmed as real column headers - the second is what a
    caller needs to find the table's own column boundaries, not just which
    of its cells to exclude.
    """
    covered: set[tuple[float, float, float, float]] = set()
    confirmed_headers: set[tuple[float, float, float, float]] = set()
    labelled = [r for r in rects if covered_by_label(r, words)]

    # A header cell is sometimes drawn twice at once - a tall outer rect
    # spanning the merged cell as printed, and a shorter inner one for just
    # its own label strip, left behind by whatever built the table's grid.
    # covered_by_label already found the outer one directly, title text and
    # all; the inner one shares its title but is too short for that same
    # text to fit inside its own narrower bounds, so it never clears the
    # check on its own. No sibling match is needed here the way it is for a
    # header with genuinely unreadable text - the outer rect already proved
    # itself a label by direct evidence, so anything sitting inside it is
    # covered by that same evidence too.
    #
    # Matched by shared column bounds, not containment alone - containment
    # by itself would just as readily catch a real field nested inside a
    # much bigger labelled rect that happens to have covered_by_label true
    # for its own unrelated reason, a whole "Hobbies" caption strip sitting
    # over a full row of real tick boxes, say. A genuine outer/inner pair of
    # the same cell keeps the same left and right edge - only its own
    # height differs - so the match stays scoped to that shape and nothing
    # wider.
    for rect in rects:
        if rect in labelled:
            continue
        for outer in labelled:
            if outer == rect:
                continue
            same_columns = abs(outer[0] - rect[0]) <= 1 and abs(outer[2] - rect[2]) <= 1
            contained_height = rect[1] >= outer[1] - 1 and rect[3] <= outer[3] + 1
            if same_columns and contained_height:
                covered.add(rect)
                break

    for rect in rects:
        if rect in labelled:
            continue
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        for other in labelled:
            ow, oh = other[2] - other[0], other[3] - other[1]
            if abs(w - ow) > size_tolerance or abs(h - oh) > size_tolerance:
                continue
            if abs(other[1] - rect[1]) > 1 or abs(other[3] - rect[3]) > 1:
                continue
            flush_right = 0 <= other[0] - rect[2] <= 1
            flush_left = 0 <= rect[0] - other[2] <= 1
            if flush_right or flush_left:
                covered.add(rect)
                confirmed_headers.add(other)
                break

    # Flush siblings confirm each other, so a header row of 3+ cells only
    # ever has its interior members added above - the two end cells never
    # see a same-size neighbour on both sides to be added by. Any labelled
    # cell adjacent to something already in confirmed_headers belongs to
    # the same row and is a header too.
    changed = True
    while changed:
        changed = False
        for rect in labelled:
            if rect in confirmed_headers:
                continue
            for header in list(confirmed_headers):
                if abs(header[1] - rect[1]) > 1 or abs(header[3] - rect[3]) > 1:
                    continue
                flush_right = 0 <= rect[0] - header[2] <= 1
                flush_left = 0 <= header[0] - rect[2] <= 1
                if flush_right or flush_left:
                    confirmed_headers.add(rect)
                    changed = True
                    break

    # A header cell that a sibling match has actually confirmed can still
    # hide a second rectangle inside its own bounds - a stray sub-cell from
    # elsewhere in the table's column grid landing on the header row, wider
    # than a tick box so `segment_cell_indices` won't catch it, but with no
    # title of its own for `covered_by_label` to find. Unlike matching by
    # size or position alone, this is safe precisely because it is scoped to
    # rects a sibling has already confirmed - a caption cell elsewhere on
    # the page (a signature box's neighbour, say) is never in that set, so
    # its own genuinely fillable interior is never reached by this step.
    for rect in rects:
        if rect in labelled or rect in covered:
            continue
        for header in confirmed_headers:
            contained = (
                rect[0] >= header[0] - 1
                and rect[1] >= header[1] - 1
                and rect[2] <= header[2] + 1
                and rect[3] <= header[3] + 1
            )
            if contained:
                covered.add(rect)
                break

    return covered, confirmed_headers


def header_sibling_rects(
    rects: list[tuple[float, float, float, float]],
    words: list[dict],
    size_tolerance: float = 1.0,
) -> set[tuple[float, float, float, float]]:
    covered, _ = _header_sibling_and_confirmed(rects, words, size_tolerance)
    return covered


def table_column_edges(
    rects: list[tuple[float, float, float, float]], words: list[dict]
) -> set[float]:
    """
    Interior x-boundaries of a genuine multi-column table, as proven by a
    confirmed header row - the vertical lines between "Name on Card" and
    "Name of Custodian", for instance.

    `header_sibling_rects` already finds these header cells the safe way,
    by requiring a same-row, same-size, flush neighbour that itself carries
    real label text. What is wanted here isn't which cells are headers but
    where their shared edges fall, so a later merge across an ordinary row
    can tell "this x-position is a real column boundary, proven by a header
    row above" from "this x-position is just where a form's export tool
    happened to cut the fill into pieces."
    """
    inferred, confirmed = _header_sibling_and_confirmed(rects, words)
    edges: set[float] = set()
    # Include unreadable header cells inferred from their confirmed siblings.
    # Their shared edge is just as structural as the edges of headers whose
    # text was extracted successfully.  Omitting it lets merge_row_runs join
    # the first two permission columns (for example Input and Authorize) into
    # one wide, overlapping widget.
    for rect in confirmed | inferred:
        edges.add(round(rect[0], 1))
        edges.add(round(rect[2], 1))
    return edges


def repeated_row_boundaries(
    rects: list[tuple[float, float, float, float]],
    tolerance: float = 1.25,
    min_rows: int = 3,
) -> set[float]:
    """Vertical cell boundaries repeated across several distinct table rows."""
    hits: dict[float, set[tuple[float, float]]] = {}
    for left in rects:
        for right in rects:
            if left is right:
                continue
            same_row = abs(left[1] - right[1]) <= tolerance and abs(left[3] - right[3]) <= tolerance
            flush = 0 <= right[0] - left[2] <= tolerance
            if same_row and flush:
                edge = round((left[2] + right[0]) / 2.0, 1)
                hits.setdefault(edge, set()).add((round(left[1], 1), round(left[3], 1)))
    return {edge for edge, rows in hits.items() if len(rows) >= min_rows}


def merge_row_runs(
    rects: list[tuple[float, float, float, float]],
    colours: dict[tuple[float, float, float, float], tuple],
    column_edges: set[float],
    gap: float = 1.0,
) -> list[tuple[float, float, float, float]]:
    """
    Collapse a run of flush, same-height, same-fill rectangles on one row
    into a single rectangle spanning the whole run.

    Some export tools cut what was always meant to be one continuous answer
    line - "Address", "Phone Number" - into several abutting filled
    rectangles that read as one uninterrupted bar on the page, with no
    stroke or colour change marking any division. Left alone, each piece
    becomes its own field, breaking a single answer into several boxes that
    don't match what the form actually shows. Only a real table's column
    boundaries, proven by a header row through `table_column_edges`, are
    left uncrossed - crossing any other shared edge is safe because nothing
    in the source distinguishes it from the rest of the run.
    """
    by_row: dict[tuple[float, float], list[tuple[float, float, float, float]]] = {}
    others: list[tuple[float, float, float, float]] = []

    for rect in rects:
        colour = colours.get(rect)
        if colour is None:
            others.append(rect)
            continue
        by_row.setdefault((round(rect[1], 1), round(rect[3], 1), colour), []).append(rect)

    merged: list[tuple[float, float, float, float]] = list(others)
    for row in by_row.values():
        row.sort(key=lambda r: r[0])
        run = [row[0]]
        for rect in row[1:]:
            last = run[-1]
            flush = -0.5 <= rect[0] - last[2] <= gap
            crosses_column = round(last[2], 1) in column_edges
            if flush and not crosses_column:
                run.append(rect)
                continue
            merged.append((run[0][0], run[0][1], run[-1][2], run[-1][3]))
            run = [rect]
        merged.append((run[0][0], run[0][1], run[-1][2], run[-1][3]))

    return merged


def drop_containers(
    classified: list[tuple[tuple[float, float, float, float], str]], min_contained: int = 2
) -> list[tuple[tuple[float, float, float, float], str]]:
    """
    Remove a rectangle that turns out to be a frame drawn around a whole
    labelled section, not a field of its own.

    A large box classifies the same way a real signature or multiline field
    does - big enough, tall enough - so the only thing telling them apart is
    what's inside. A real field is empty; a section frame has other already-
    classified fields sitting entirely inside it.
    """
    boxes = [rect for rect, _ in classified]
    keep = []
    for i, (rect, kind) in enumerate(classified):
        contained = sum(
            1
            for j, other in enumerate(boxes)
            if j != i
            and other[0] >= rect[0] - 1
            and other[1] >= rect[1] - 1
            and other[2] <= rect[2] + 1
            and other[3] <= rect[3] + 1
        )
        if contained < min_contained:
            keep.append((rect, kind))
    return keep


def restorable_closed_fields(
    candidates: set[tuple[float, float, float, float]],
    words: list[dict],
    sibling_headers: set[tuple[float, float, float, float]],
    cfg: dict,
) -> set[tuple[float, float, float, float]]:
    """Empty, closed, single-line boxes that container cleanup must retain."""
    return {
        rect
        for rect in candidates
        if rect not in sibling_headers
        and rect[3] - rect[1] <= cfg["max_text_height"]
        and not covered_by_label(rect, words, min_width=15.0)
    }


def drop_fields_crossing_closed_columns(
    classified: list[tuple[tuple[float, float, float, float], str]],
    closed_rects: set[tuple[float, float, float, float]],
) -> list[tuple[tuple[float, float, float, float], str]]:
    """Drop a loose rule that cuts across two genuine side-by-side fields."""
    kept = []
    for rect, kind in classified:
        if rect in closed_rects:
            kept.append((rect, kind))
            continue
        supports = []
        for closed in closed_rects:
            horizontal = max(0.0, min(rect[2], closed[2]) - max(rect[0], closed[0]))
            vertical = max(0.0, min(rect[3], closed[3]) - max(rect[1], closed[1]))
            min_height = max(0.01, min(rect[3] - rect[1], closed[3] - closed[1]))
            if horizontal >= 5.0 and vertical / min_height >= 0.5:
                supports.append(closed)
        crosses_columns = any(
            left[2] <= right[0] + 2 or right[2] <= left[0] + 2
            for left in supports
            for right in supports
            if left != right
        )
        if not crosses_columns:
            kept.append((rect, kind))
    return kept


def drop_option_row_overlays(
    classified: list[tuple[tuple[float, float, float, float], str]],
) -> list[tuple[tuple[float, float, float, float], str]]:
    """Keep an option row's checkbox, not a wide field spanning its label."""
    checkboxes = [rect for rect, kind in classified if kind == "checkbox"]
    kept = []
    for rect, kind in classified:
        if kind == "checkbox" or rect[2] - rect[0] < 150.0:
            kept.append((rect, kind))
            continue
        overlays_checkbox = any(
            rect[0] <= checkbox[0]
            and checkbox[2] <= rect[2]
            and max(0.0, min(rect[3], checkbox[3]) - max(rect[1], checkbox[1]))
            / max(0.01, min(rect[3] - rect[1], checkbox[3] - checkbox[1]))
            >= 0.5
            for checkbox in checkboxes
        )
        if not overlays_checkbox:
            kept.append((rect, kind))
    return kept


def drop_fields_inside_printed_words(
    classified: list[tuple[tuple[float, float, float, float], str]],
    words: list[dict],
    closed_rects: set[tuple[float, float, float, float]],
) -> list[tuple[tuple[float, float, float, float], str]]:
    """Drop loose geometry embedded inside printed text, commonly a logo."""
    kept = []
    for rect, kind in classified:
        if rect in closed_rects:
            kept.append((rect, kind))
            continue
        rect_width = max(0.01, rect[2] - rect[0])
        rect_height = max(0.01, rect[3] - rect[1])
        inside_word = any(
            re.search(r"[A-Za-z0-9]{2,}", word["text"])
            and max(0.0, min(rect[2], word["x1"]) - max(rect[0], word["x0"]))
            / rect_width
            >= 0.8
            and max(
                0.0,
                min(rect[3], word["bottom_pdf"])
                - max(rect[1], word["top_pdf"]),
            )
            / rect_height
            >= 0.7
            for word in words
        )
        if not inside_word:
            kept.append((rect, kind))
    return kept


def drop_fields_overlapping_short_dates(
    classified: list[tuple[tuple[float, float, float, float], str]],
    short_dates: list[tuple[float, float, float, float]],
) -> list[tuple[tuple[float, float, float, float], str]]:
    """Prefer precise underscore-run dates over a larger overlapping field."""
    kept = []
    inferred: list[tuple[tuple[float, float, float, float], str]] = []
    for rect, kind in classified:
        if rect in short_dates:
            kept.append((rect, kind))
            continue
        obscures_short_date = any(
            rect[2] - rect[0] > short[2] - short[0] + 4
            and max(0.0, min(rect[2], short[2]) - max(rect[0], short[0]))
            / max(0.01, short[2] - short[0])
            >= 0.5
            and max(0.0, min(rect[3], short[3]) - max(rect[1], short[1]))
            / max(0.01, short[3] - short[1])
            >= 0.5
            for short in short_dates
        )
        if obscures_short_date:
            # OCR occasionally sees only the right-hand blank in
            # ``Date __ / __ / 2025`` while geometry sees one broad box over
            # both blanks.  Removing that broad false widget is correct, but
            # its left edge still gives us the missing two-digit day field.
            # Recover it when the precise short blank is clearly the right
            # half of a two-cell date run.
            for short in short_dates:
                short_width = short[2] - short[0]
                rect_width = rect[2] - rect[0]
                same_row = (
                    max(0.0, min(rect[3], short[3]) - max(rect[1], short[1]))
                    / max(0.01, short[3] - short[1])
                    >= 0.8
                )
                if (
                    same_row
                    and 2.0 * short_width <= rect_width <= 3.0 * short_width
                    and short[0] > rect[0] + short_width
                    and abs(rect[2] - short[2]) <= 3
                ):
                    inferred.append(
                        ((rect[0], short[1], rect[0] + short_width, short[3]), "date")
                    )
                    break
        if not obscures_short_date:
            kept.append((rect, kind))
    for item in inferred:
        if item not in kept:
            kept.append(item)
        if item[0] not in short_dates:
            short_dates.append(item[0])
    return kept


def classify(
    rect: tuple[float, float, float, float],
    cfg: dict,
    is_rule: bool = False,
    is_closed_box: bool = False,
) -> str | None:
    """
    Decide what sort of field a rectangle should become, or None to skip.

    A plain rectangle this narrow is usually a stray sliver worth ignoring,
    but two other kinds of geometry already proved themselves a real place
    to write by a different, narrower test, and are exempt from the width
    floor built to keep decorative slivers out of ordinary rectangles:
    a rule - a stroke someone drew under a blank, or a typed dot leader,
    either way something a person on paper already writes short answers
    on, "DD" or "MM" beside a date's slashes for instance - and a box
    closed on all four of its own sides, an even stronger signal since
    nothing decorative is ever drawn as a fully enclosed rectangle only
    slightly narrower than the usual floor, an "Other" box beside a row
    of checkboxes for instance. A rule is never a tick box - it's read off
    a stroke or a dot leader's own width, nothing square about either -
    but a closed box still can be, so only the width floor is skipped for
    one and not the checkbox test itself.
    """
    x0, y0, x1, y1 = rect
    width, height = x1 - x0, y1 - y0

    if width <= 0 or height <= 0:
        return None

    # Tick boxes: small and roughly square.
    if (
        not is_rule
        and cfg["checkbox_min"] <= width <= cfg["checkbox_max"]
        and cfg["checkbox_min"] <= height <= cfg["checkbox_max"]
    ):
        shorter, longer = sorted((width, height))
        if longer > 0 and shorter / longer >= cfg["checkbox_squareness"]:
            return "checkbox"

    if not is_rule and not is_closed_box and width < cfg["min_text_width"]:
        return None
    if height < cfg["min_text_height"]:
        return None

    # A page border or a section banner is not an input.
    if width > 900 or height > 400:
        return None

    if width * height >= cfg["signature_min_area"] and height >= cfg["multiline_height"]:
        return "signature"

    if height > cfg["multiline_height"]:
        return "multiline"

    return "text"


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def extract_words_deduped(page) -> list[dict]:
    """
    Words, with overprinted duplicates removed.

    Faux bold is often done by drawing the same string twice a fraction of a
    point apart. The two copies interleave at character level, so the word comes
    out as "GGoollff" unless the duplicates are dropped before words are
    assembled.
    """
    buckets: dict[tuple, list[dict]] = {}
    chars = []

    for char in page.chars:
        # Bucket loosely, then compare properly inside the bucket. A rounding
        # grid alone misses pairs that straddle a boundary.
        key = (char["text"], round(char["top"] / 3.0))
        near = buckets.setdefault(key, [])

        # The offset must be a fraction of the glyph, not a whole glyph, or
        # the second l of "Full" looks like an overprint of the first.
        width = max(0.5, float(char.get("x1", 0)) - float(char.get("x0", 0)))
        threshold = min(0.9, max(0.2, width * 0.4))

        if any(
            abs(char["x0"] - other["x0"]) < threshold
            and abs(char["top"] - other["top"]) < 0.9
            for other in near
        ):
            continue

        near.append(char)
        chars.append(char)

    if not chars:
        return []

    return plumber_extract_words(chars, use_text_flow=False, keep_blank_chars=False)


def bold_word_boxes(page) -> list[tuple[float, float, float, float]]:
    """
    Bounding boxes of bold text runs on the page, in PDF-native bottom-up
    coordinates, one per contiguous run of bold characters.

    A section heading is reliably bold even when it isn't styled in ALL
    CAPS the way most of a form's other headings are - "Other Contact
    Details" sits in ordinary title case but is still drawn with a bold
    font, the one thing that still tells it apart from a genuine field
    label nearby. Matched on the font name containing "Bold" - real bold
    fonts are named this way close to universally - which is enough here
    since this is only ever used to break a tie the width/position checks
    already narrowed down to a handful of candidates, not to find headings
    on its own.
    """
    height = page.height
    runs: list[tuple[float, float, float, float]] = []
    current: list[dict] = []

    def flush():
        if not current:
            return
        x0 = min(c["x0"] for c in current)
        x1 = max(c["x1"] for c in current)
        top = min(c["top"] for c in current)
        bottom = max(c["bottom"] for c in current)
        runs.append((x0, height - bottom, x1, height - top))

    for char in sorted(page.chars, key=lambda c: (round(c["top"], 1), c["x0"])):
        is_bold = "bold" in char.get("fontname", "").lower()
        if is_bold and current and abs(char["top"] - current[-1]["top"]) <= 1 and char["x0"] - current[-1]["x1"] <= 20:
            current.append(char)
        elif is_bold:
            flush()
            current = [char]
        else:
            flush()
            current = []
    flush()

    return runs


def ocr_words(
    page,
    resolution: int = OCR_RESOLUTION,
    psm: int | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """
    Recover words on a page with no text layer by rasterizing and reading it
    with Tesseract.

    Some forms are scanned, and some just lose their text layer to a lossy
    PDF compressor that turns every glyph into a tiny image. Either way there
    is nothing for `extract_words_deduped` to read, so the page is rendered
    to an image and OCR'd instead. Tesseract's pixel boxes, top-left origin,
    are converted to the same PDF-point, top-down shape pdfplumber's word
    dicts use, so the rest of the pipeline cannot tell the difference.

    Tesseract's automatic page segmentation (the default) occasionally drops
    a whole line outright - typically one crowded with a dense dot leader -
    with no trace of it in the output at any position, not just a garbled
    read. A single-block segmentation (`psm=6`) reads those lines fine but
    is worse elsewhere, so it is a second pass to merge in, not a
    replacement.

    A `bbox` (left, top, right, bottom, in PDF points) restricts the OCR to
    one region of the page - a signature line sitting in a font pdfplumber
    can't decode, for instance, can be the only thing missing from an
    otherwise complete text layer, with no image or curve count to flag the
    page as worth a full pass. Cropping keeps checking for that cheap enough
    to run on every real-text page rather than only the ones already known
    to need OCR.
    """
    if pytesseract is None:
        return []

    try:
        target = page.crop(bbox) if bbox is not None else page
        image = target.to_image(resolution=resolution).original
        config = f"--psm {psm}" if psm is not None else ""
        data = pytesseract.image_to_data(image, config=config, output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    scale = 72.0 / resolution
    x_offset, y_offset = (bbox[0], bbox[1]) if bbox is not None else (0.0, 0.0)
    words: list[dict] = []
    for i, raw_text in enumerate(data.get("text", [])):
        text = raw_text.strip()
        if not text:
            continue
        left, top = data["left"][i], data["top"][i]
        width, height = data["width"][i], data["height"][i]
        words.append(
            {
                "text": text,
                "x0": left * scale + x_offset,
                "x1": (left + width) * scale + x_offset,
                "top": top * scale + y_offset,
                "bottom": (top + height) * scale + y_offset,
            }
        )
    return words


def merge_missing_words(base: list[dict], extra: list[dict]) -> list[dict]:
    """
    Add words from a second source, skipping any that land on a word the
    first source already has.

    Two passes over the same page cover the same ground almost everywhere,
    and keeping both duplicates every word they agree on - which breaks
    anything that reads a line as one string, like a section banner's title
    or a dot leader's label. Only what the first source missed is worth
    adding from the second.
    """
    def overlaps(word: dict, others: list[dict]) -> bool:
        return any(
            word["x0"] < other["x1"]
            and word["x1"] > other["x0"]
            and word["top"] < other["bottom"]
            and word["bottom"] > other["top"]
            for other in others
        )

    return base + [w for w in extra if not overlaps(w, base)]


def find_sections(words: list[dict]) -> list[tuple[float, str, float, float]]:
    """
    Section banners, as (baseline, title, x0, x1) tuples ordered down the
    page.

    Printed forms announce a section with a short line in capitals, often on a
    coloured bar. Anything below that line belongs to it, until the next one.
    The title's own x-range is carried along too, so a caller can tell the
    bar itself - which always contains its title - from some other field
    that merely sits on the same row without being part of it.
    """
    rows: dict[float, list[dict]] = {}
    for word in words:
        key = round(word["bottom_pdf"] / 4.0)
        rows.setdefault(key, []).append(word)

    sections: list[tuple[float, str, float, float]] = []

    for group in rows.values():
        group.sort(key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in group).strip()

        if not text or len(text) > 80:
            continue
        # A single word standing alone on its own line is a field's own
        # label just as often as it is a section title - "BRANCH" reads
        # exactly like "DETAILS" would - and mistaking it for one hides
        # the very field it labels, along with anything else sharing its
        # line. A real banner is close to always a short phrase, so this
        # loses the rare single-word title but keeps a field's own label
        # from disappearing along with its input box.
        if len(group) < 2:
            continue
        letters = re.sub(r"[^A-Za-z]", "", text)
        if len(letters) < 4:
            continue
        if ":" in text:
            continue
        upper = re.sub(r"[^A-Z]", "", text)
        if len(upper) / len(letters) < 0.85:
            continue

        title = clean_label(re.sub(r"^\s*\d{1,2}\s*[\.\)]?\s*", "", text), 60)
        if title:
            sections.append((
                max(w["bottom_pdf"] for w in group),
                title.title(),
                min(w["x0"] for w in group),
                max(w["x1"] for w in group),
            ))

    sections.sort(key=lambda item: -item[0])
    return sections


def section_for(box: Box, sections: list[tuple[float, str, float, float]]) -> str:
    """
    The nearest section banner above this box.

    Nearest, not highest. Taking the first match down the page would file the
    whole form under its title.
    """
    above = [item for item in sections if item[0] >= box.y1 - 2]
    if not above:
        return ""
    return min(above, key=lambda item: item[0])[1]


def find_label(box: Box, words: list[dict], cfg: dict) -> str:
    """
    The wording that belongs to a box.

    Printed forms put the label to the left of the box on the same line, and
    fall back to sitting above it when the box spans the full width.
    """
    if not words:
        return ""

    mid_y = (box.y0 + box.y1) / 2
    band = max(4.0, box.height * 0.6)

    left = [
        w
        for w in words
        if not is_rule(w["text"])
        and w["x1"] <= box.x0 + 1
        and box.x0 - w["x1"] <= cfg["label_search_left"]
        and abs(((w["top_pdf"] + w["bottom_pdf"]) / 2) - mid_y) <= band
    ]

    if left:
        left.sort(key=lambda w: w["x1"], reverse=True)
        return assemble_label(left, cfg)

    above = [
        w
        for w in words
        if not is_rule(w["text"])
        and 0 <= w["bottom_pdf"] - box.y1 <= cfg["label_search_above"]
        and w["x1"] > box.x0 - 10
        and w["x0"] < box.x1 + 10
    ]

    if above:
        # Nearest line above, read left to right.
        nearest = min(w["bottom_pdf"] for w in above)
        row = [w for w in above if abs(w["bottom_pdf"] - nearest) <= 4]
        # Nearest to the box's left edge first, so a wide box under a full row
        # of wording takes the start of that row rather than all of it.
        row.sort(key=lambda w: abs(w["x0"] - box.x0))
        row = row[: cfg["label_max_words"]]
        row.sort(key=lambda w: w["x0"])
        return clean_label(" ".join(w["text"] for w in row), cfg["label_max_chars"])

    return ""


def assemble_label(words_right_to_left: list[dict], cfg: dict) -> str:
    """
    Walk leftwards from the box, collecting words until the gap widens.

    Capped, because a box at the end of a long row would otherwise swallow the
    entire row as its label.
    """
    picked = [words_right_to_left[0]]
    length = len(words_right_to_left[0]["text"])

    for word in words_right_to_left[1:]:
        previous = picked[-1]
        if previous["x0"] - word["x1"] > cfg["label_word_gap"]:
            break
        if len(picked) >= cfg["label_max_words"]:
            break
        if length + len(word["text"]) + 1 > cfg["label_max_chars"]:
            break
        picked.append(word)
        length += len(word["text"]) + 1

    picked.sort(key=lambda w: w["x0"])
    return clean_label(" ".join(w["text"] for w in picked), cfg["label_max_chars"])


def is_rule(text: str) -> bool:
    """Underscore runs, dot leaders and stray separators are not label words."""
    return bool(re.fullmatch(r"[_—–.…/|\-]{2,}", text.strip()))


def clean_label(text: str, max_chars: int = 80) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^\(?\s*(?:[ivxlcdm]+|\d{1,2})\s*[\.\)]\s*", "", text, flags=re.I)
    text = re.sub(r"[\s_.…/|-]{2,}.*$", "", text)
    text = text.strip(" :.…_-")
    if len(text) > max_chars:
        # Trim on a word boundary rather than mid word.
        text = text[:max_chars].rsplit(" ", 1)[0].strip(" :.,-")
    return text if 1 < len(text) <= 80 else ""


def infer_kind(label: str, current: str) -> str:
    if current in ("checkbox", "signature"):
        return current
    lowered = label.lower()
    for pattern, kind in TYPE_RULES:
        if re.search(pattern, lowered):
            if kind == "address":
                return "multiline" if current == "multiline" else "text"
            if kind == "signature":
                return "signature"
            return current if current == "multiline" else kind
    return current


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:48]


def prettify(name: str) -> str:
    words = [w for w in name.split("_") if w]
    return " ".join(w.upper() if w in ACRONYMS else w.capitalize() for w in words)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect(path: str, pages: set[int] | None, cfg: dict, group_mode: str = "section") -> Result:
    result = Result()
    used: dict[str, int] = {}

    with pdfplumber.open(path) as pdf:
        result.page_count = len(pdf.pages)

        for index, page in enumerate(pdf.pages, start=1):
            if pages and index not in pages:
                continue

            raw_words = extract_words_deduped(page)
            date_hint_words: list[dict] = []
            ocr_used = False
            # A lossy compressor can rasterize most of a page's text into
            # per-glyph images while leaving a stray heading or two as real
            # text, so "any real words at all" is not enough to trust the
            # text layer. Some tools flatten text to vector outlines instead
            # of images - no glyphs, no images, just curves - so images
            # alone also isn't enough. Either one heavily outnumbering the
            # words actually extracted means most of the page's text never
            # made it into raw_words, so OCR is run and merged in.
            if (len(page.images) + len(page.curves)) > len(raw_words) * 3:
                ocr_extra = ocr_words(page)
                if ocr_extra:
                    date_hint_words.extend(
                        w for w in ocr_extra if "_" in w["text"] and "/" in w["text"]
                    )
                    raw_words = merge_missing_words(raw_words, ocr_extra)
                    ocr_used = True
                # Automatic segmentation can drop a whole line - usually one
                # crowded with a dot leader - that a single-block pass reads
                # fine, so that pass runs too and fills in anything missed.
                # A blank field misread as a run of dashes is a bigger risk
                # from this pass than the words it's meant to recover, since
                # it invents a fake rule that splits one field into two -
                # real rule characters are already covered by the first
                # pass and by drawn geometry, so only label-shaped words are
                # taken from this one.
                ocr_psm6 = [w for w in ocr_words(page, psm=6) if re.search(r"[A-Za-z0-9]", w["text"])]
                if ocr_psm6:
                    date_hint_words.extend(
                        w for w in ocr_psm6 if "_" in w["text"] and "/" in w["text"]
                    )
                    raw_words = merge_missing_words(raw_words, ocr_psm6)
                    ocr_used = True
            else:
                # A page can pass the check above - real text everywhere it
                # looks like there should be - and still have one region
                # pdfplumber's text layer never captured, most often a
                # signature line set in a font it can't decode. Nothing
                # about the page as a whole flags it as needing OCR, so the
                # bottom margin, where a signature line almost always sits,
                # gets a small, cheap OCR pass on every real-text page
                # rather than only the ones already known to need one.
                margin_top = max(0.0, page.height - 100.0)
                margin_bbox = (0, margin_top, page.width, page.height)
                bottom_ocr = [
                    w
                    for w in ocr_words(page, bbox=margin_bbox)
                    if re.search(r"[A-Za-z0-9]", w["text"])
                ]
                if bottom_ocr:
                    raw_words = merge_missing_words(raw_words, bottom_ocr)
                    ocr_used = True
                # Automatic segmentation over this thin a crop tends to drop
                # a dot leader's dots entirely rather than garble them, so a
                # signature line's blank can be missing every trace of its
                # own rule even once the label beside it is found. The
                # single-block pass reads the dots as literal characters
                # here the same way it does on a full page.
                bottom_psm6 = [
                    w
                    for w in ocr_words(page, bbox=margin_bbox, psm=6)
                    if re.search(r"[A-Za-z0-9]", w["text"])
                ]
                if bottom_psm6:
                    raw_words = merge_missing_words(raw_words, bottom_psm6)
                    ocr_used = True
            if ocr_used:
                result.pages_ocred.append(index)
            elif not raw_words:
                result.pages_without_text.append(index)

            # pdfplumber reports word positions from the top of the page, while
            # annotations are placed from the bottom. Convert once, here.
            # Preserve OCR date patterns even when an overlapping, garbled
            # text-layer token caused merge_missing_words to reject them.
            raw_words.extend(date_hint_words)
            height = page.height
            words = []
            for word in raw_words:
                words.append(
                    {
                        "text": word["text"],
                        "x0": word["x0"],
                        "x1": word["x1"],
                        "top_pdf": height - word["bottom"],
                        "bottom_pdf": height - word["top"],
                    }
                )

            if (
                any("2025" in w["text"] for w in words)
                and not any("_" in w["text"] and "/" in w["text"] for w in words)
            ):
                for word in ocr_words(page):
                    if "_" not in word["text"] or "/" not in word["text"]:
                        continue
                    words.append(
                        {
                            "text": word["text"],
                            "x0": word["x0"],
                            "x1": word["x1"],
                            "top_pdf": height - word["bottom"],
                            "bottom_pdf": height - word["top"],
                        }
                    )

            banners = find_sections(words)
            sections = banners if group_mode == "section" else []

            short_date_rules = short_date_rules_from_text(words, cfg)
            rules = merge_adjacent(rules_from_text(words, cfg))
            rules = [r for r in rules if r[2] - r[0] >= cfg["rule_min_width"]]

            # A rule reconstructed from real drawn geometry - a bare
            # underline stroke, a run of tiny filled dashes - self-overlaps
            # the very same way a typed dot leader does whenever OCR
            # garbles the dots drawn along it into a fake word: nothing
            # visually distinguishes "SSCS" misread from a line of dots
            # from a real label, so this rule looks exactly like a header
            # cell by the same test and would otherwise be wrongly excluded
            # right alongside the ones `rules_from_text` already protects.
            #
            # Unlike a dot leader, though, a loose-line rule has no word of
            # its own it is expected to overlap - so the single topmost
            # one on the page, if it does, is a title's own underline
            # sitting right beneath that title's text at just the height a
            # genuine blank's field would occupy, decoration rather than a
            # real place to write, and is dropped before it ever becomes a
            # rule at all.
            _, loose_for_rules = rectangles_from_lines(page)
            all_loose_rules = rules_from_loose_lines(loose_for_rules, cfg["rule_height"])
            bold_boxes = bold_word_boxes(page)
            geometric_rules = merge_and_filter_rules(
                [r for r in all_loose_rules if not rule_under_heading(r, words, all_loose_rules, bold_boxes, banners)],
                cfg,
            )
            sliver_rects = [
                rect
                for rect in page.rects
                if rect.get("fill")
                and not rect.get("stroke")
                and (rect["x1"] - rect["x0"]) < 10
                and (rect["bottom"] - rect["top"]) < 2
            ]
            geometric_rules += rules_from_slivers(sliver_rects, cfg["rule_height"])

            rule_set = set(rules) | set(short_date_rules) | set(geometric_rules)

            # A box closed on all four sides is stronger evidence of an
            # intentional field than a single stroke is, the same
            # direction rule_set already trusts a stroke over bare
            # untested geometry - a narrow "Other" box beside a row of
            # checkboxes, say, drawn only wide enough for its own answer
            # and nothing more. Rebuilt here from the same sources
            # collect_rectangles itself draws from, since what matters is
            # only which ones closed on their own, not anything the
            # verticals-splitting or rule-merging steps do afterwards.
            closed_curve_rects, _ = curve_rects_and_lines(page)
            closed_from_lines, _ = rectangles_from_lines(page)
            closed_box_set = set(closed_curve_rects) | set(closed_from_lines) | {
                (rect["x0"], rect["y0"], rect["x1"], rect["y1"])
                for rect in page.rects
                # A table is sometimes ruled with thin filled slivers doing
                # the job a stroke would elsewhere - a divider between two
                # cells, not a box of its own - and is exactly as
                # untrustworthy geometry as the slivers collect_rectangles
                # already sets aside for a run rather than trusting
                # outright. Real closed boxes are never this thin on
                # either side.
                if (rect["x1"] - rect["x0"]) >= 10 and (rect["bottom"] - rect["top"]) >= 10
            }

            collected_rects = collect_rectangles(page, cfg)

            # A run such as DD MM YYYY is commonly drawn as one closed outer
            # rectangle with internal vertical dividers.  collect_rectangles
            # correctly turns that run into individual cells, but those
            # children are not present in closed_box_set because no child has
            # four independently drawn sides.  They still inherit the strong
            # closed-field evidence of their parent grid; without that, an OCR
            # hallucination over the empty year cells can discard the whole
            # YYYY portion after it has already been split correctly.
            enclosed_grid_cells = {
                rect
                for rect in collected_rects
                if any(
                    parent != rect
                    and parent[0] <= rect[0] + 1
                    and rect[2] <= parent[2] + 1
                    and abs(parent[1] - rect[1]) <= 2
                    and abs(parent[3] - rect[3]) <= 2
                    for parent in closed_box_set
                )
            }
            closed_box_set.update(enclosed_grid_cells)
            initial_closed_rects = set(collected_rects) & closed_box_set
            rects = dedupe(
                collected_rects + rules + short_date_rules,
                cfg["dedupe_tolerance"],
            )

            # Some export tools cut what was always one continuous answer
            # line into several abutting same-colour rectangles, with no
            # stroke or shade marking any division - only a real table's
            # column boundaries, proven by a header row here while the
            # geometry is still unmerged, are worth keeping separate.
            column_edges = table_column_edges(rects, words) | repeated_row_boundaries(rects)
            colours: dict[tuple[float, float, float, float], tuple] = {}
            for rect in page.rects:
                box = (rect["x0"], rect["y0"], rect["x1"], rect["y1"])
                colour = rect.get("non_stroking_color")
                if rect.get("fill") and not rect.get("stroke") and isinstance(colour, tuple):
                    colours[box] = colour
            rects = merge_row_runs(rects, colours, column_edges)
            rects_with_inferred_values = infer_missing_value_cells(rects, words)
            inferred_value_rects = [r for r in rects_with_inferred_values if r not in rects]
            rects = rects_with_inferred_values
            inferred_checkbox_rects = infer_checkbox_above_run(rects, words, cfg)
            rects.extend(inferred_checkbox_rects)

            # A section banner's own background bar is real geometry, not a
            # blank to fill - the title is printed inside it, not beside it.
            # A bar is never taller than about one line of text, so an
            # unrelated box tall enough to span a banner's baseline too, an
            # official stamp square sitting right below "OFFICIAL USE ONLY"
            # for instance, is never itself the bar on height alone. Height
            # alone still isn't enough, though - a genuine separate field
            # can sit on that exact row beside the title without being part
            # of the bar, a blank box to the right of "CUSTOMER DETAILS" for
            # instance - so the bar's own title also has to actually fall
            # inside the rect's x-range, the way it always does for a real
            # background strip drawn to hold that title.
            rects = [
                rect
                for rect in rects
                if not (
                    rect[3] - rect[1] <= cfg["multiline_height"]
                    and any(
                        rect[1] <= baseline <= rect[3]
                        and rect[0] <= title_x0
                        and title_x1 <= rect[2]
                        for baseline, _, title_x0, title_x1 in banners
                    )
                )
            ]

            # A running footer bar sits in the same colour and shape as a
            # section banner but carries no title, so the banner check above
            # can't see it - only its position gives it away: pinned to the
            # bottom margin of every page, wide enough to span the content
            # column, with nothing that looks like a label anywhere near it.
            footer_margin = 50.0
            rects = [
                rect
                for rect in rects
                if not (rect[1] <= footer_margin and rect[2] - rect[0] > 300)
            ]

            # collect_rectangles rebuilds its own loose-line rules
            # independently of the ones already checked above for sitting
            # under a heading, so the same check runs again here against
            # its output - scoped to rects that aren't a closed box (which
            # has no business overlapping a heading this way) and aren't a
            # rules_from_text rule (which legitimately overlaps its own
            # dot leader's word already). Both draw from the very same
            # rectangles_from_lines(page) call, so "topmost on the page"
            # means the same thing in both places.
            rects = [
                rect
                for rect in rects
                if rect in closed_box_set
                or rect in set(rules)
                or not rule_under_heading(rect, words, all_loose_rules, bold_boxes, banners)
            ]

            # A table header cell is drawn identically to a data cell below
            # it, so only its column title being fully inside gives it away.
            # Checked only for geometric cells, never for a rule derived from
            # text - that rule's rect always overlaps the very word it came
            # from (a dot leader glued to its own label), which would look
            # exactly like this and wrongly remove every one of them.
            geometric_rects = [rect for rect in rects if rect not in rule_set]
            sibling_headers = header_sibling_rects(geometric_rects, words)
            candidate_closed_rects = initial_closed_rects
            rects = [
                rect
                for rect in rects
                if rect in rule_set
                or (
                    not covered_by_label(
                        rect,
                        words,
                        # A closed table cell narrower than the usual floor
                        # is still a real one, not decorative geometry a
                        # misread character could impersonate - "USD" or
                        # "ZWG" beside an account grid, say - so it earns
                        # the same lower floor a genuinely closed box
                        # already gets everywhere else this session's
                        # fixes touch. A rect with no box behind it at all
                        # keeps the ordinary, stricter floor.
                        min_width=15.0 if rect in closed_box_set else 30.0,
                    )
                    and rect not in sibling_headers
                )
            ]

            # A geometric rule earns its way into rule_set purely by shape -
            # a stroke, a run of dashes - with no relationship to any
            # particular word the way a text-derived rule always has to its
            # own dot leader, so nothing stops one from landing under a
            # section banner it has nothing to do with, "BRANCH/FRONT
            # OFFICE USE ONLY" for instance, sitting on the very rule meant
            # for the answer beneath it. A text-derived rule is never
            # dropped here - its self-overlap with its own label is
            # expected and already exempted above - only a bare geometric
            # one whose zone happens to contain a banner's own title.
            text_rule_set = set(rules) | set(short_date_rules)
            rects = [
                rect
                for rect in rects
                if rect in text_rule_set
                or not any(
                    rect[1] <= baseline <= rect[3] and rect[0] <= title_x0 and title_x1 <= rect[2]
                    for baseline, _, title_x0, title_x1 in banners
                )
            ]

            # A section underline can be reconstructed through more than one
            # geometry path.  Even if one path classifies it as a rule worth
            # preserving, a near-total overlap with bold text proves that it
            # is the heading's decoration, not an answer field.
            rects = [
                rect
                for rect in rects
                if rect in closed_box_set
                or not any(
                    max(0.0, min(rect[2], bx1) - max(rect[0], bx0))
                    / max(0.01, rect[2] - rect[0])
                    >= 0.9
                    and max(0.0, min(rect[3], by1) - max(rect[1], by0)) > 0
                    for bx0, by0, bx1, by1 in bold_boxes
                )
            ]

            classified: list[tuple[tuple[float, float, float, float], str]] = []
            for rect in rects:
                kind = classify(rect, cfg, is_rule=rect in rule_set, is_closed_box=rect in closed_box_set)
                if kind is not None:
                    classified.append((rect, kind))

            classified = drop_containers(classified)

            classified_rects = {rect for rect, _ in classified}
            for rect in restorable_closed_fields(
                candidate_closed_rects, words, sibling_headers, cfg
            ):
                if rect in classified_rects:
                    continue
                kind = classify(rect, cfg, is_rule=False, is_closed_box=True)
                if kind is not None:
                    classified.append((rect, kind))
                    classified_rects.add(rect)

            # Embedded date blanks such as __/__/2025 are trusted textual
            # date evidence.  Their very short runs can be swallowed by
            # generic container/header cleanup, so restore each run as its
            # own date field while leaving the printed slashes/year intact.
            for rect in short_date_rules:
                if rect not in classified_rects:
                    classified.append((rect, "date"))
                    classified_rects.add(rect)

            # The inferred cell encloses the fragmented border pieces that
            # caused it to be missed in the first place, so the generic
            # container cleanup can discard it.  Restore it after that pass;
            # its neighbouring label/value rows are the stronger evidence.
            for rect in inferred_value_rects + inferred_checkbox_rects:
                if rect in classified_rects:
                    continue
                kind = classify(rect, cfg, is_rule=False, is_closed_box=True)
                if kind is not None:
                    classified.append((rect, kind))

            classified = drop_fields_crossing_closed_columns(
                classified,
                candidate_closed_rects
                | {rect for rect, kind in classified if kind == "checkbox"},
            )
            classified = drop_option_row_overlays(classified)
            printed_overlap_words = words
            if ocr_used:
                top_ocr = ocr_words(
                    page,
                    bbox=(0.0, 0.0, page.width, min(120.0, page.height)),
                )
                printed_overlap_words = words + [
                    {
                        "text": word["text"],
                        "x0": word["x0"],
                        "x1": word["x1"],
                        "top_pdf": height - word["bottom"],
                        "bottom_pdf": height - word["top"],
                    }
                    for word in top_ocr
                ]
            classified = drop_fields_inside_printed_words(
                classified, printed_overlap_words, candidate_closed_rects
            )
            classified = drop_fields_overlapping_short_dates(
                classified, short_date_rules
            )

            checkbox_rects = [rect for rect, kind in classified if kind == "checkbox"]
            date_cells = split_date_run_indices(checkbox_rects)
            date_cell_rects = {checkbox_rects[i] for i in date_cells}

            segment_cells = segment_cell_indices(classified, rects)
            segment_cell_rects = {classified[i][0] for i in segment_cells}

            page_boxes: list[Box] = []
            for rect, kind in classified:
                if rect in short_date_rules:
                    kind = "date"
                elif rect in date_cell_rects:
                    kind = "date"
                elif rect in segment_cell_rects:
                    kind = "text"
                page_boxes.append(
                    Box(
                        page=index,
                        x0=rect[0],
                        y0=rect[1],
                        x1=rect[2],
                        y1=rect[3],
                        kind=kind,
                        max_length=2 if rect in short_date_rules else 0,
                    )
                )

            # Reading order: down the page, then across.
            page_boxes.sort(key=lambda b: (-round(b.y1, 1), b.x0))

            for position, box in enumerate(page_boxes, start=1):
                box.label = find_label(box, words, cfg)
                box.kind = infer_kind(box.label, box.kind)

                if group_mode == "section":
                    box.group = section_for(box, sections) or f"Page {index}"
                elif group_mode == "page":
                    box.group = f"Page {index}"

                base = slugify(box.label) if box.label else ""
                if not base:
                    box.labelled = False
                    base = f"p{index}_{box.kind}_{position:02d}"
                    box.label = prettify(base)

                # Confidence is intentionally conservative on OCR pages. It
                # is an operational review signal, not a claim of statistical
                # probability: unlabelled OCR geometry deserves inspection;
                # labelled vector fields are normally safe to auto-accept.
                box.confidence = 0.9 if box.labelled and not ocr_used else 0.75
                if not box.labelled:
                    box.confidence = 0.45 if not ocr_used else 0.35
                if box.kind in {"checkbox", "date", "signature"}:
                    box.confidence = min(0.98, box.confidence + 0.03)

                name = base
                if name in used:
                    used[name] += 1
                    name = f"{base}_{used[name]}"
                else:
                    used[name] = 1
                box.name = name

            result.boxes.extend(page_boxes)
            # OCR-heavy PDFs can retain a full rendered page plus pdfminer
            # layout caches for every page processed.  Release each page
            # before moving on so multi-page scans do not exhaust memory.
            page.close()
            gc.collect()

    return result


# ---------------------------------------------------------------------------
# Writing the AcroForm
# ---------------------------------------------------------------------------


def blank_text_appearance(
    pdf: pikepdf.Pdf,
    width: float,
    height: float,
    border: bool,
    fill_background: bool = True,
) -> pikepdf.Object:
    """
    A normal appearance stream for an empty text field.

    NeedAppearances asks the viewer to draw the field itself once typed
    into, but the outline a field has before that depends on the viewer
    also drawing /MK on request, which not all of them do. A blank stream
    with the border painted directly avoids depending on that, so the box
    is visible everywhere from the moment the form opens, not just after
    NeedAppearances is honoured.

    A field placed over print - a "D" or "Y" hint under a split date cell,
    for instance - sits on transparent ground otherwise, so what was
    printed there stays visible behind whatever gets typed. Filling the
    field white first covers it, the same as a paper form's answer covering
    the hint printed beneath the line.
    """
    content = (
        f"q 1 1 1 rg 0 0 {width:g} {height:g} re f Q".encode("latin-1")
        if fill_background
        else b""
    )
    if border:
        # Inset by half the line width so the stroke sits inside the box,
        # matching how a Border Style dictionary paints it.
        inset = 0.5
        content += (
            f" q 0.55 0.6 0.66 RG 1 w {inset:g} {inset:g} {width - 2 * inset:g} "
            f"{height - 2 * inset:g} re S Q"
        ).encode("latin-1")

    stream = pdf.make_stream(content)
    stream.Type = Name.XObject
    stream.Subtype = Name.Form
    stream.BBox = Array([0, 0, width, height])
    return pdf.make_indirect(stream)


def checkbox_appearance(pdf: pikepdf.Pdf, width: float, height: float, checked: bool) -> pikepdf.Object:
    """
    A normal appearance stream for one state of a tick box.

    Viewers that do not build their own appearance for a button field, which
    is most of them outside Acrobat itself, show nothing at all for a state
    with none defined, so both the on and off states need a stream even
    though the off one draws nothing.
    """
    content = b""
    if checked:
        stroke = max(1.2, min(width, height) * 0.12)
        content = (
            f"q 0 0.35 0 RG {stroke:g} w 1 J 1 j "
            f"{width * 0.18:g} {height * 0.52:g} m "
            f"{width * 0.40:g} {height * 0.28:g} l "
            f"{width * 0.82:g} {height * 0.78:g} l S Q"
        ).encode("latin-1")

    stream = pdf.make_stream(content)
    stream.Type = Name.XObject
    stream.Subtype = Name.Form
    stream.BBox = Array([0, 0, width, height])
    return pdf.make_indirect(stream)


def build(path: str, out_path: str, boxes: list[Box], font_size: float, borders: bool) -> None:
    """
    Write the AcroForm.

    Where boxes carry a group, a non terminal parent field is created for it and
    the widgets become its kids. That is the standard way to express structure
    in a PDF form, and readers that understand it, including PDF Form Builder,
    recover the sections from it.
    """
    pdf = pikepdf.open(path)

    # Preserve fields already present in partially fillable PDFs.  Replacing
    # /AcroForm outright loses values, actions and signatures, while adding a
    # second widget over an existing one makes both fields unreliable.
    existing_acroform = pdf.Root.get("/AcroForm")
    existing_fields = (
        list(existing_acroform.get("/Fields", [])) if existing_acroform else []
    )
    existing_names: set[str] = set()

    def collect_field_names(nodes) -> None:
        for node in nodes:
            name = node.get("/T")
            if name is not None:
                existing_names.add(str(name))
            collect_field_names(node.get("/Kids", []))

    collect_field_names(existing_fields)

    existing_widgets: dict[int, list[tuple[float, float, float, float]]] = {}
    for page_index, existing_page in enumerate(pdf.pages, start=1):
        for annot in existing_page.get("/Annots", []):
            if annot.get("/Subtype") != Name.Widget or "/Rect" not in annot:
                continue
            existing_widgets.setdefault(page_index, []).append(
                tuple(float(value) for value in annot.Rect)
            )

    def overlaps_existing(box: Box) -> bool:
        for rect in existing_widgets.get(box.page, []):
            intersection = max(0.0, min(box.x1, rect[2]) - max(box.x0, rect[0])) * max(
                0.0, min(box.y1, rect[3]) - max(box.y0, rect[1])
            )
            if intersection / max(0.01, min(box.area, (rect[2] - rect[0]) * (rect[3] - rect[1]))) >= 0.6:
                return True
        return False

    boxes = [box for box in boxes if not overlaps_existing(box)]

    helvetica = pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.Type1,
            BaseFont=Name.Helvetica,
            Encoding=Name.WinAnsiEncoding,
        )
    )
    dingbats = pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.Type1,
            BaseFont=Name.ZapfDingbats,
        )
    )

    fields = Array(existing_fields)
    parents: dict[str, pikepdf.Object] = {}

    def parent_for(group: str):
        if not group:
            return None
        if group not in parents:
            node = pdf.make_indirect(Dictionary(T=String(group), Kids=Array()))
            parents[group] = node
            fields.append(node)
        return parents[group]

    by_page: dict[int, list[Box]] = {}
    for box in boxes:
        by_page.setdefault(box.page, []).append(box)

    for page_number, page_boxes in by_page.items():
        page = pdf.pages[page_number - 1]
        # Use the annotation array's row-major order as the keyboard tab
        # sequence. page_boxes is already sorted top-to-bottom then left-to-
        # right, giving generated forms a predictable accessible order.
        page.Tabs = Name.R

        # Annotation coordinates are relative to the MediaBox origin, which is
        # not always zero.
        media = [float(v) for v in page.mediabox]
        offset_x, offset_y = media[0], media[1]

        # Printed D/M/Y guide letters remain visible in browser viewers that
        # render form widgets as transparent HTML overlays.  Cover those
        # glyphs in the page content itself, then redraw the original cell
        # borders.  Seed the row from labels OCR read as D D / M M / Y Y and
        # include every adjacent date cell on that same baseline.
        guide_seeds = [
            box
            for box in page_boxes
            if box.kind == "date"
            and re.fullmatch(r"(?:[DMY]\s*){1,4}", box.label.strip(), re.I)
        ]
        guide_boxes = [
            box
            for box in page_boxes
            if box.kind == "date"
            and box.width <= 26
            and box.height <= 26
            and any(abs((box.y0 + box.y1) - (seed.y0 + seed.y1)) <= 3 for seed in guide_seeds)
        ]
        if guide_boxes:
            commands = ["q"]
            for box in guide_boxes:
                commands.append(
                    f"1 1 1 rg {box.x0 + offset_x:g} {box.y0 + offset_y:g} "
                    f"{box.width:g} {box.height:g} re f "
                    f"0.05 0.1 0.35 RG 1 w {box.x0 + offset_x + 0.5:g} "
                    f"{box.y0 + offset_y + 0.5:g} {max(0, box.width - 1):g} "
                    f"{max(0, box.height - 1):g} re S"
                )
            commands.append("Q")
            overlay = pdf.make_stream("\n".join(commands).encode("latin-1"))
            if "/Contents" not in page:
                page.Contents = overlay
            elif isinstance(page.Contents, pikepdf.Array):
                page.Contents.append(overlay)
            else:
                page.Contents = pikepdf.Array([page.Contents, overlay])

        if "/Annots" not in page:
            page.Annots = pdf.make_indirect(Array())
        annots = page.Annots

        for box in page_boxes:
            date_pair = box.kind == "date" and box.max_length == 2
            split_date_cell = (
                box.kind == "date"
                and not date_pair
                and box.width <= 26
                and box.height <= 26
            )
            rect = Array(
                [
                    box.x0 + offset_x,
                    box.y0 + offset_y,
                    box.x1 + offset_x,
                    box.y1 + offset_y,
                ]
            )

            widget = Dictionary(
                Type=Name.Annot,
                Subtype=Name.Widget,
                Rect=rect,
                T=String(box.name),
                TU=String(box.label or box.name),
                F=4,  # Print.
                P=page.obj,
            )

            # Field names are document-wide identifiers.  Keep existing
            # names untouched and deterministically suffix only new ones.
            candidate_name = box.name
            suffix = 2
            while candidate_name in existing_names:
                candidate_name = f"{box.name}_{suffix}"
                suffix += 1
            existing_names.add(candidate_name)
            widget.T = String(candidate_name)

            if box.kind == "checkbox":
                widget.FT = Name.Btn
                widget.V = Name("/Off")
                widget.AS = Name("/Off")
                widget.AP = Dictionary(
                    N=Dictionary(
                        Off=checkbox_appearance(pdf, box.width, box.height, checked=False),
                        Yes=checkbox_appearance(pdf, box.width, box.height, checked=True),
                    )
                )
            else:
                widget.FT = Name.Tx
                field_font_size = font_size
                if (split_date_cell or date_pair) and not field_font_size:
                    # Auto-size uses nearly the full cell height in several
                    # viewers, leaving date digits pressed against the top
                    # border.  A fixed, modest size stays visually centred.
                    field_font_size = min(7.0, box.height * 0.5)
                widget.DA = String(f"/Helv {field_font_size:g} Tf 0 g")
                if split_date_cell or date_pair:
                    widget.Q = 1  # Centre the single digit horizontally.
                    widget.MaxLen = box.max_length or 1
                if box.kind == "multiline":
                    widget.Ff = 1 << 12
                elif box.kind == "signature":
                    # Kept as text so it can be typed in any viewer. A real
                    # signature field would need a certificate to be useful.
                    widget.Ff = 1 << 12
                widget.AP = Dictionary(
                    N=blank_text_appearance(
                        pdf,
                        box.width,
                        box.height,
                        borders and not date_pair,
                        fill_background=not date_pair,
                    )
                )

            # NeedAppearances tells a compliant viewer to throw away the /AP
            # stream and build its own from /DA and /MK, so a background
            # painted only inside /AP - the white fill over a printed D/M/Y
            # hint, the field's own outline - never survives in exactly the
            # viewers most likely to honour NeedAppearances properly. /MK's
            # /BG is what those same viewers use for the regenerated one.
            if box.kind != "checkbox" and not split_date_cell and not date_pair:
                mk = widget.get("/MK", Dictionary())
                mk.BG = Array([1, 1, 1])
                widget.MK = mk

            if borders and not split_date_cell and not date_pair:
                mk = widget.get("/MK", Dictionary())
                mk.BC = Array([0.55, 0.6, 0.66])
                widget.MK = mk
                widget.BS = Dictionary(W=1, S=Name.S)
            else:
                widget.BS = Dictionary(W=0, S=Name.S)

            parent = parent_for(box.group)
            if parent is not None:
                widget.Parent = parent

            reference = pdf.make_indirect(widget)
            annots.append(reference)

            if parent is not None:
                parent.Kids.append(reference)
            else:
                fields.append(reference)

    if existing_acroform:
        acroform = existing_acroform
        acroform.Fields = fields
        resources = acroform.get("/DR", Dictionary())
        fonts = resources.get("/Font", Dictionary())
        if "/Helv" not in fonts:
            fonts.Helv = helvetica
        if "/ZaDb" not in fonts:
            fonts.ZaDb = dingbats
        resources.Font = fonts
        acroform.DR = resources
        if "/DA" not in acroform:
            acroform.DA = String(f"/Helv {font_size:g} Tf 0 g")
        acroform.NeedAppearances = False
    else:
        acroform = pdf.make_indirect(Dictionary(
            Fields=fields,
            DA=String(f"/Helv {font_size:g} Tf 0 g"),
            DR=Dictionary(Font=Dictionary(Helv=helvetica, ZaDb=dingbats)),
            # Keep the supplied widget appearances authoritative.  Setting
            # this true makes some browser viewers discard the vector tick
            # and substitute their platform-default X for checked boxes.
            NeedAppearances=False,
        ))
        pdf.Root.AcroForm = acroform

    # Low-level field-tree edits can leave qpdf's cached mapping stale.  Force
    # it to rebuild before saving, then ask it to repair safe structural
    # inconsistencies where the installed pikepdf version supports this API.
    try:
        form = pdf.acroform
        form.invalidate_cache()
        form.validate(repair=True)
    except (AttributeError, TypeError):
        pass

    pdf.save(out_path)
    pdf.close()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def write_report(path: str, boxes: list[Box]) -> None:
    rows = [asdict(b) for b in boxes]

    if path.lower().endswith(".json"):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2)
        return

    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "page", "name", "label", "kind", "x0", "y0", "x1", "y1",
                "group", "max_length",
                "confidence",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in writer.fieldnames})


def summarise(result: Result, verbose: bool) -> None:
    boxes = result.boxes
    counts: dict[str, int] = {}
    for box in boxes:
        counts[box.kind] = counts.get(box.kind, 0) + 1

    print(f"{len(boxes)} fields across {result.page_count} pages")
    for kind in sorted(counts):
        print(f"  {counts[kind]:4d}  {kind}")

    unlabelled = sum(1 for b in boxes if not b.labelled)
    if unlabelled:
        print(f"\n{unlabelled} field(s) could not be given a label from the page text.")

    if result.pages_ocred:
        pages = ", ".join(str(p) for p in result.pages_ocred)
        print(
            f"Page(s) {pages} had no text layer and were read with OCR instead.\n"
            "Labels on these pages may contain the occasional misread word."
        )

    if result.pages_without_text:
        pages = ", ".join(str(p) for p in result.pages_without_text)
        print(
            f"Page(s) {pages} have no text layer, so their boxes are typeable but\n"
            "generically named. Either the page is a scan too faint for OCR, or\n"
            "OCR is unavailable (pytesseract/Tesseract not installed)."
        )

    if verbose:
        print()
        current = None
        for box in boxes:
            if box.page != current:
                current = box.page
                print(f"--- page {box.page} ---")
            group = f"[{box.group}] " if box.group else ""
            print(f"  {box.kind:<9} {box.name:<34} {group}{box.label}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_pages(spec: str | None) -> set[int] | None:
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), int(end) + 1))
        else:
            pages.add(int(part))
    return pages or None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add fillable form fields to a printed PDF form.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="source PDF")
    parser.add_argument("-o", "--output", help="where to write the fillable PDF")
    parser.add_argument("--pages", help="limit to pages, e.g. 1-3,5")
    parser.add_argument("--report", help="also write the detected fields to a .csv or .json file")
    parser.add_argument("--dry-run", action="store_true", help="detect and report without writing a PDF")
    parser.add_argument("--verbose", "-v", action="store_true", help="list every field found")
    parser.add_argument("--font-size", type=float, default=0, help="0 means auto fit to the box height")
    parser.add_argument("--no-borders", action="store_true", help="do not outline the fields")
    parser.add_argument("--min-width", type=float, default=DEFAULTS["min_text_width"],
                        help="ignore boxes narrower than this, in points")
    parser.add_argument("--min-height", type=float, default=DEFAULTS["min_text_height"],
                        help="ignore boxes shorter than this, in points")
    parser.add_argument("--group-by", choices=("section", "page", "none"), default="section",
                        help="how to group fields: by detected section heading, by page, or not at all")
    parser.add_argument("--rule-height", type=float, default=DEFAULTS["rule_height"],
                        help="height of a field placed on an underscore or dotted rule, in points")

    args = parser.parse_args(argv)

    if not args.dry_run and not args.output:
        parser.error("either --output or --dry-run is required")

    cfg = dict(DEFAULTS)
    cfg["min_text_width"] = args.min_width
    cfg["min_text_height"] = args.min_height
    cfg["rule_height"] = args.rule_height

    result = detect(args.input, parse_pages(args.pages), cfg, args.group_by)

    if not result.boxes:
        print("No fillable boxes were found.")
        print(
            "Boxes, underscore rules and dot leaders were all checked. If the\n"
            "form uses thin drawn lines, try lowering --min-height. If the page\n"
            "has no text layer, it is a scan or its text became outlines."
        )
        return 1

    summarise(result, args.verbose)

    if args.report:
        write_report(args.report, result.boxes)
        print(f"\nReport written to {args.report}")

    if not args.dry_run:
        build(args.input, args.output, result.boxes, args.font_size or 0, not args.no_borders)
        print(f"\nFillable PDF written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
