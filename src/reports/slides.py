"""
PPTX → PNG slide rendering and structured field extraction.

Rendering uses LibreOffice headless (soffice) which must be installed on the system.
Each slide is saved as slide_0.png, slide_1.png, etc. in a report-specific directory.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

from pptx import Presentation

from .logging_utils import configure_logging
from .runtime import get_slides_dir

logger = configure_logging()


def _find_libreoffice() -> str | None:
    """Return the path to the soffice binary, or None if not found."""
    for candidate in ["soffice", "/usr/bin/soffice", "/usr/local/bin/soffice",
                       "/Applications/LibreOffice.app/Contents/MacOS/soffice"]:
        if shutil.which(candidate):
            return candidate
    return None


def render_pdf(report_id: int, pptx_path: Path) -> Path:
    """
    Convert a PPTX to a single PDF using LibreOffice headless.
    Returns the path to the generated PDF file.
    Raises RuntimeError if LibreOffice is not installed.
    """
    soffice = _find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice is not installed. Install it to enable slide preview. "
            "On macOS: brew install --cask libreoffice"
        )

    slides_dir = get_slides_dir() / str(report_id)
    slides_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(slides_dir), str(pptx_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice PDF conversion failed: {result.stderr}")

    # LibreOffice outputs <stem>.pdf — rename to canonical preview.pdf
    lo_output = slides_dir / f"{pptx_path.stem}.pdf"
    canonical = slides_dir / "preview.pdf"
    if lo_output.exists() and lo_output != canonical:
        lo_output.rename(canonical)

    logger.info("Rendered PDF for report_id=%s to %s", report_id, canonical)
    return canonical


def render_slides(report_id: int, pptx_path: Path) -> Path:
    """
    Convert a PPTX to PNG images using LibreOffice headless.
    Returns the directory containing slide_0.png, slide_1.png, etc.
    Raises RuntimeError if LibreOffice is not installed.
    """
    soffice = _find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice is not installed. Install it to enable slide preview. "
            "On macOS: brew install --cask libreoffice"
        )

    slides_dir = get_slides_dir() / str(report_id)
    slides_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "png", "--outdir", str(slides_dir), str(pptx_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")

    # LibreOffice names outputs: <stem>.png (single) or <stem>1.png, <stem>2.png (multi)
    # Rename to canonical slide_0.png, slide_1.png, ...
    stem = pptx_path.stem
    pngs = sorted(slides_dir.glob(f"{stem}*.png"))
    for i, png in enumerate(pngs):
        target = slides_dir / f"slide_{i}.png"
        if png != target:
            png.rename(target)

    logger.info("Rendered %d slides for report_id=%s to %s", len(pngs), report_id, slides_dir)
    return slides_dir


def extract_slide_fields(pptx_path: Path) -> list[dict]:
    """
    Extract editable text fields from each slide.
    Returns a list of slide dicts:
      [{ "slide_index": 0, "fields": [{ "field_id": "s0_shape0_para0", "label": "...", "value": "..." }] }]
    """
    prs = Presentation(str(pptx_path))
    result = []

    for slide_idx, slide in enumerate(prs.slides):
        fields = []
        shapes_with_text = [s for s in slide.shapes if s.has_text_frame]
        for shape_idx, shape in enumerate(shapes_with_text):
            for para_idx, para in enumerate(shape.text_frame.paragraphs):
                text = para.text.strip()
                if not text:
                    continue

                field_id = f"s{slide_idx}_shape{shape_idx}_para{para_idx}"
                label = _label_for_field(slide_idx, shape.name, text)
                if label:
                    fields.append({
                        "field_id": field_id,
                        "label": label,
                        "value": text,
                        "slide_index": slide_idx,
                        "shape_name": shape.name,
                        "para_index": para_idx,
                    })

        result.append({"slide_index": slide_idx, "fields": fields})
    return result


def _label_for_field(slide_idx: int, shape_name: str, text: str) -> str | None:
    """Return a human-readable label for a text field, or None if it should not be editable."""
    if len(text) < 3:
        return None

    # Slide 1 — date
    if slide_idx == 0 and re.match(r"^[A-Za-z]+,?\s*\d{4}$", text):
        return "Report Month"

    # Slide 2 — executive summary
    if slide_idx == 1:
        if re.match(r"^\d+K?$", text):
            return "Active Users (short)"
        if re.match(r"^\d+%$", text) and len(text) <= 5:
            return "New Visitors %"
        if re.match(r"^\d+\.\d+%$", text):
            return "CTR"
        if len(text) > 60:
            return "Executive Summary Paragraph"

    # Slide 3 — site overview
    if slide_idx == 2:
        if "total active users" in text.lower():
            return "Active Users Label"
        if "new users" in text.lower():
            return "New Users Label"
        if "engagement" in text.lower():
            return "Engagement Time Label"
        if len(text) > 60:
            return "Site Overview Paragraph"
        if re.match(r"^[\d,]+$", text):
            return "Stat Value"

    # Slide 4 — geographic
    if slide_idx == 3 and len(text) > 40:
        return "Geographic Performance Paragraph"

    # Slide 5 — page performance
    if slide_idx == 4 and len(text) > 40:
        return "Page Performance Insight"

    # Slide 6 — search performance
    if slide_idx == 5 and len(text) > 40:
        return "Search Performance Paragraph"

    # Recommendations slide (index 6 for 8-slide, 5 for 7-slide)
    if slide_idx in (5, 6) and re.match(r"^\d\.", text):
        return f"Recommendation {text[0]}"

    return None


def apply_field_edits(pptx_path: Path, edits: dict[str, str], output_path: Path) -> None:
    """
    Re-open the PPTX, apply field edits (field_id -> new_text), and save to output_path.
    edits keys match the field_id format: "s{slide_idx}_shape{shape_idx}_para{para_idx}"
    """
    prs = Presentation(str(pptx_path))

    for field_id, new_text in edits.items():
        m = re.match(r"^s(\d+)_shape(\d+)_para(\d+)$", field_id)
        if not m:
            logger.warning("Unrecognised field_id format: %s", field_id)
            continue
        slide_idx, shape_idx, para_idx = int(m.group(1)), int(m.group(2)), int(m.group(3))

        if slide_idx >= len(prs.slides):
            continue
        slide = prs.slides[slide_idx]
        shapes_with_text = [s for s in slide.shapes if s.has_text_frame]
        if shape_idx >= len(shapes_with_text):
            continue
        shape = shapes_with_text[shape_idx]
        if para_idx >= len(shape.text_frame.paragraphs):
            continue
        para = shape.text_frame.paragraphs[para_idx]
        _fill_para(para, new_text)

    prs.save(str(output_path))


def _fill_para(para, new_text: str) -> None:
    """Replace paragraph text preserving first run's rPr formatting."""
    from copy import deepcopy
    import lxml.etree as etree
    from pptx.oxml.ns import qn

    if not para.runs:
        return
    first_rpr = para.runs[0]._r.find(qn("a:rPr"))
    saved_rpr = deepcopy(first_rpr) if first_rpr is not None else None
    for child in list(para._p):
        if child.tag != qn("a:pPr"):
            para._p.remove(child)
    new_r = etree.SubElement(para._p, qn("a:r"))
    if saved_rpr is not None:
        new_r.insert(0, saved_rpr)
    new_t = etree.SubElement(new_r, qn("a:t"))
    new_t.text = new_text
