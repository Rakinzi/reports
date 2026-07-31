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
    "checkbox_max": 24.0,
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


def collect_rectangles(page, cfg: dict) -> list[tuple[float, float, float, float]]:
    """
    Every rectangle on the page, in PDF coordinates with the origin at the
    bottom left.

    Boxes reach a page three ways: as a `re` operator, which pdfplumber reports
    in page.rects; as four separate line segments closing off a box, which it
    reports in page.lines; and as a single stroke drawn under a blank space for
    someone to write on, with no box at all. Forms mix these freely, sometimes
    on the same page, so all three are gathered here.
    """
    out: list[tuple[float, float, float, float]] = []

    for rect in page.rects:
        out.append((rect["x0"], rect["y0"], rect["x1"], rect["y1"]))

    closed, loose = rectangles_from_lines(page)
    out.extend(closed)

    loose_rules = rules_from_loose_lines(loose, cfg["rule_height"])
    out.extend(r for r in loose_rules if r[2] - r[0] >= cfg["rule_min_width"])
    return out


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
    """
    horizontals: list[dict] = []
    verticals: list[dict] = []

    for line in page.lines:
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
    """
    boxes: list[tuple[float, float, float, float]] = []
    for line in lines:
        x_low, x_high = sorted((line["x0"], line["x1"]))
        y = max(line["y0"], line["y1"])
        boxes.append((x_low, y, x_high, y + rule_height))
    return boxes


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
        if same_line and rect[0] - last[2] <= gap:
            last[2] = max(last[2], rect[2])
            last[3] = max(last[3], rect[3])
            continue
        merged.append(list(rect))

    return [tuple(r) for r in merged]


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
    boxes: list[tuple[float, float, float, float]], gap: float = 3.0, min_run: int = 4
) -> set[int]:
    """
    Indices of boxes that belong to a split date field: "DD MM YYYY" drawn as
    one small square per character.

    Those squares are checkbox-sized, so `classify` calls them tick boxes on
    size alone, but a real tick box always has its label sitting well clear
    of it, wide enough for a word like "Golf" to fit. A run of several
    same-row boxes sitting almost flush against each other, near enough that
    no label could fit between them, is a split field instead.
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


def classify(rect: tuple[float, float, float, float], cfg: dict) -> str | None:
    """Decide what sort of field a rectangle should become, or None to skip."""
    x0, y0, x1, y1 = rect
    width, height = x1 - x0, y1 - y0

    if width <= 0 or height <= 0:
        return None

    # Tick boxes: small and roughly square.
    if (
        cfg["checkbox_min"] <= width <= cfg["checkbox_max"]
        and cfg["checkbox_min"] <= height <= cfg["checkbox_max"]
    ):
        shorter, longer = sorted((width, height))
        if longer > 0 and shorter / longer >= cfg["checkbox_squareness"]:
            return "checkbox"

    if width < cfg["min_text_width"] or height < cfg["min_text_height"]:
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


def ocr_words(page, resolution: int = OCR_RESOLUTION) -> list[dict]:
    """
    Recover words on a page with no text layer by rasterizing and reading it
    with Tesseract.

    Some forms are scanned, and some just lose their text layer to a lossy
    PDF compressor that turns every glyph into a tiny image. Either way there
    is nothing for `extract_words_deduped` to read, so the page is rendered
    to an image and OCR'd instead. Tesseract's pixel boxes, top-left origin,
    are converted to the same PDF-point, top-down shape pdfplumber's word
    dicts use, so the rest of the pipeline cannot tell the difference.
    """
    if pytesseract is None:
        return []

    try:
        image = page.to_image(resolution=resolution).original
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    scale = 72.0 / resolution
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
                "x0": left * scale,
                "x1": (left + width) * scale,
                "top": top * scale,
                "bottom": (top + height) * scale,
            }
        )
    return words


def find_sections(words: list[dict]) -> list[tuple[float, str]]:
    """
    Section banners, as (baseline, title) pairs ordered down the page.

    Printed forms announce a section with a short line in capitals, often on a
    coloured bar. Anything below that line belongs to it, until the next one.
    """
    rows: dict[float, list[dict]] = {}
    for word in words:
        key = round(word["bottom_pdf"] / 4.0)
        rows.setdefault(key, []).append(word)

    sections: list[tuple[float, str]] = []

    for group in rows.values():
        group.sort(key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in group).strip()

        if not text or len(text) > 80:
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
            sections.append((max(w["bottom_pdf"] for w in group), title.title()))

    sections.sort(key=lambda item: -item[0])
    return sections


def section_for(box: Box, sections: list[tuple[float, str]]) -> str:
    """
    The nearest section banner above this box.

    Nearest, not highest. Taking the first match down the page would file the
    whole form under its title.
    """
    above = [(baseline, title) for baseline, title in sections if baseline >= box.y1 - 2]
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
            ocr_used = False
            if not raw_words:
                raw_words = ocr_words(page)
                ocr_used = bool(raw_words)
            if ocr_used:
                result.pages_ocred.append(index)
            elif not raw_words:
                result.pages_without_text.append(index)

            # pdfplumber reports word positions from the top of the page, while
            # annotations are placed from the bottom. Convert once, here.
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

            sections = find_sections(words) if group_mode == "section" else []

            rules = merge_adjacent(rules_from_text(words, cfg))
            rules = [r for r in rules if r[2] - r[0] >= cfg["rule_min_width"]]

            rects = dedupe(collect_rectangles(page, cfg) + rules, cfg["dedupe_tolerance"])

            classified: list[tuple[tuple[float, float, float, float], str]] = []
            for rect in rects:
                kind = classify(rect, cfg)
                if kind is not None:
                    classified.append((rect, kind))

            checkbox_rects = [rect for rect, kind in classified if kind == "checkbox"]
            date_cells = split_date_run_indices(checkbox_rects)
            date_cell_rects = {checkbox_rects[i] for i in date_cells}

            page_boxes: list[Box] = []
            for rect, kind in classified:
                if rect in date_cell_rects:
                    kind = "text"
                page_boxes.append(Box(page=index, x0=rect[0], y0=rect[1], x1=rect[2], y1=rect[3], kind=kind))

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

                name = base
                if name in used:
                    used[name] += 1
                    name = f"{base}_{used[name]}"
                else:
                    used[name] = 1
                box.name = name

            result.boxes.extend(page_boxes)

    return result


# ---------------------------------------------------------------------------
# Writing the AcroForm
# ---------------------------------------------------------------------------


def blank_text_appearance(pdf: pikepdf.Pdf, width: float, height: float, border: bool) -> pikepdf.Object:
    """
    A normal appearance stream for an empty text field.

    NeedAppearances asks the viewer to draw the field itself once typed
    into, but the outline a field has before that depends on the viewer
    also drawing /MK on request, which not all of them do. A blank stream
    with the border painted directly avoids depending on that, so the box
    is visible everywhere from the moment the form opens, not just after
    NeedAppearances is honoured.
    """
    content = b""
    if border:
        # Inset by half the line width so the stroke sits inside the box,
        # matching how a Border Style dictionary paints it.
        inset = 0.5
        content = (
            f"q 0.55 0.6 0.66 RG 1 w {inset:g} {inset:g} {width - 2 * inset:g} "
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
        size = min(width, height) * 0.8
        content = (
            f"q BT /ZaDb {size:g} Tf 0 g {width / 2 - size / 2.4:g} {height / 2 - size / 2.6:g} Td (4) Tj ET Q"
        ).encode("latin-1")

    stream = pdf.make_stream(content)
    stream.Type = Name.XObject
    stream.Subtype = Name.Form
    stream.BBox = Array([0, 0, width, height])
    stream.Resources = Dictionary(
        Font=Dictionary(
            ZaDb=pdf.make_indirect(
                Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.ZapfDingbats)
            )
        )
    )
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

    fields = Array()
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

        # Annotation coordinates are relative to the MediaBox origin, which is
        # not always zero.
        media = [float(v) for v in page.mediabox]
        offset_x, offset_y = media[0], media[1]

        if "/Annots" not in page:
            page.Annots = pdf.make_indirect(Array())
        annots = page.Annots

        for box in page_boxes:
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

            if box.kind == "checkbox":
                widget.FT = Name.Btn
                widget.V = Name("/Off")
                widget.AS = Name("/Off")
                widget.DA = String("/ZaDb 0 Tf 0 g")
                widget.MK = Dictionary(CA=String("4"))  # A tick, in ZapfDingbats.
                widget.AP = Dictionary(
                    N=Dictionary(
                        Off=checkbox_appearance(pdf, box.width, box.height, checked=False),
                        Yes=checkbox_appearance(pdf, box.width, box.height, checked=True),
                    )
                )
            else:
                widget.FT = Name.Tx
                widget.DA = String(f"/Helv {font_size:g} Tf 0 g")
                if box.kind == "multiline":
                    widget.Ff = 1 << 12
                elif box.kind == "signature":
                    # Kept as text so it can be typed in any viewer. A real
                    # signature field would need a certificate to be useful.
                    widget.Ff = 1 << 12
                widget.AP = Dictionary(N=blank_text_appearance(pdf, box.width, box.height, borders))

            if borders:
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

    pdf.Root.AcroForm = pdf.make_indirect(
        Dictionary(
            Fields=fields,
            DA=String(f"/Helv {font_size:g} Tf 0 g"),
            DR=Dictionary(Font=Dictionary(Helv=helvetica, ZaDb=dingbats)),
            # Viewers draw the field contents themselves. Without this, typed
            # text can stay invisible until the field is clicked into.
            NeedAppearances=True,
        )
    )

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
            fieldnames=["page", "name", "label", "kind", "x0", "y0", "x1", "y1", "group"],
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
