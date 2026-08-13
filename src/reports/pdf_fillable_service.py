"""Safe, document-level orchestration for automatic PDF form conversion."""

from __future__ import annotations

import shutil
import gc
from dataclasses import dataclass
from pathlib import Path

import pikepdf
from pikepdf import Name

from .pdf_make_fillable import DEFAULTS, Result, build, detect


class FillablePdfError(ValueError):
    """A user-actionable failure while inspecting or converting a PDF."""


@dataclass(frozen=True)
class PdfInspection:
    page_count: int
    existing_widgets: int
    has_xfa: bool
    has_signatures: bool
    has_active_content: bool


@dataclass(frozen=True)
class ConversionResult:
    output_path: Path
    detected_fields: int
    existing_fields: int
    page_count: int
    ocr_pages: tuple[int, ...]
    unlabelled_fields: int
    low_confidence_fields: int
    mean_confidence: float

    @property
    def total_fields(self) -> int:
        return self.detected_fields + self.existing_fields


def inspect_pdf(path: str | Path, *, max_pages: int = 100) -> PdfInspection:
    """Parse an uploaded file and reject unsupported or unreasonable input."""
    path = Path(path)
    try:
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise FillablePdfError("The uploaded file is not a valid PDF.")
        with pikepdf.open(path) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                raise FillablePdfError("The PDF has no pages.")
            if page_count > max_pages:
                raise FillablePdfError(
                    f"The PDF has {page_count} pages; the limit is {max_pages}."
                )
            acroform = pdf.Root.get("/AcroForm")
            has_xfa = bool(acroform and "/XFA" in acroform)
            has_signatures = False
            names = pdf.Root.get("/Names", {})
            has_active_content = bool(
                "/JavaScript" in names
                or "/EmbeddedFiles" in names
                or "/OpenAction" in pdf.Root
                or "/AA" in pdf.Root
            )
            widgets = sum(
                1
                for page in pdf.pages
                for annot in page.get("/Annots", [])
                if annot.get("/Subtype") == Name.Widget
            )
            for page in pdf.pages:
                width = float(page.MediaBox[2]) - float(page.MediaBox[0])
                height = float(page.MediaBox[3]) - float(page.MediaBox[1])
                if width <= 0 or height <= 0 or width > 2880 or height > 2880 or width * height > 2_000_000:
                    raise FillablePdfError("A PDF page exceeds the safe processing dimensions.")
                for annot in page.get("/Annots", []):
                    if annot.get("/FT") == Name.Sig:
                        has_signatures = True
                    if (
                        annot.get("/Subtype")
                        in {Name.FileAttachment, Name.Movie, Name.Sound, Name.Screen, Name("/3D")}
                        or "/A" in annot
                        or "/AA" in annot
                    ):
                        has_active_content = True
            return PdfInspection(
                page_count, widgets, has_xfa, has_signatures, has_active_content
            )
    except FillablePdfError:
        raise
    except pikepdf.PasswordError as exc:
        raise FillablePdfError("Password-protected PDFs are not supported.") from exc
    except pikepdf.PdfError as exc:
        raise FillablePdfError("The uploaded PDF is damaged or cannot be read.") from exc


def _validate_output(
    source: Path,
    output: Path,
    inspection: PdfInspection,
    expected_new_fields: int,
) -> None:
    """Fail closed if conversion damaged pages or produced invalid widgets."""
    # Open sequentially. Image-heavy PDFs can map sizeable object graphs even
    # when their compressed file is small; holding both copies at once creates
    # an avoidable memory spike in desktop builds.
    with pikepdf.open(source) as original:
        original_page_count = len(original.pages)
    with pikepdf.open(output) as converted:
        if original_page_count != len(converted.pages):
            raise FillablePdfError("Conversion changed the PDF page count.")

        widgets = []
        names: set[str] = set()
        for page in converted.pages:
            media = [float(value) for value in page.MediaBox]
            for annot in page.get("/Annots", []):
                if annot.get("/Subtype") != Name.Widget:
                    continue
                widgets.append(annot)
                rect = [float(value) for value in annot.Rect]
                if rect[2] <= rect[0] or rect[3] <= rect[1]:
                    raise FillablePdfError("Conversion produced an empty form field.")
                if (
                    rect[0] < media[0] - 1
                    or rect[1] < media[1] - 1
                    or rect[2] > media[2] + 1
                    or rect[3] > media[3] + 1
                ):
                    raise FillablePdfError("Conversion produced a field outside its page.")
                name = str(annot.get("/T", ""))
                if not inspection.existing_widgets and name and name in names:
                    raise FillablePdfError("Conversion produced duplicate form-field names.")
                names.add(name)

        # In a partially fillable PDF, detections under existing widgets are
        # deliberately skipped, so the only strict lower bound is preservation
        # of the existing widgets. A flat PDF should retain every detection.
        minimum = (
            inspection.existing_widgets
            if inspection.existing_widgets
            else expected_new_fields
        )
        if len(widgets) < minimum:
            raise FillablePdfError("Some form fields were lost while saving the PDF.")


def convert_pdf_to_fillable(
    source: str | Path,
    output: str | Path,
    *,
    max_pages: int = 100,
    augment_existing: bool = False,
) -> ConversionResult:
    """Convert vector PDFs and image-only scans into validated AcroForms.

    Existing AcroForm widgets are preserved. The detector handles vector
    boxes/rules directly and invokes OCR for scanned pages when Tesseract is
    installed. XFA is intentionally rejected because it is a different,
    unsupported form technology rather than an AcroForm variant.
    """
    source = Path(source)
    output = Path(output)
    inspection = inspect_pdf(source, max_pages=max_pages)
    gc.collect()
    if inspection.has_xfa:
        raise FillablePdfError(
            "This PDF uses XFA forms, which cannot be safely converted to AcroForm."
        )
    if inspection.has_signatures:
        raise FillablePdfError(
            "Digitally signed PDFs cannot be modified without invalidating their signatures."
        )
    if inspection.has_active_content:
        raise FillablePdfError(
            "PDFs containing JavaScript, attachments, actions, or multimedia are not accepted."
        )

    # Form conversion must be idempotent. Re-running visual detection over an
    # already interactive document can add duplicates and needlessly OCR every
    # page. Preserve and validate it byte-for-byte instead.
    if inspection.existing_widgets and not augment_existing:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.partial")
        temporary.unlink(missing_ok=True)
        try:
            shutil.copyfile(source, temporary)
            gc.collect()
            _validate_output(source, temporary, inspection, 0)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        return ConversionResult(
            output_path=output,
            detected_fields=0,
            existing_fields=inspection.existing_widgets,
            page_count=inspection.page_count,
            ocr_pages=(),
            unlabelled_fields=0,
            low_confidence_fields=0,
            mean_confidence=1.0,
        )

    detection: Result = detect(
        str(source), pages=None, cfg=dict(DEFAULTS), group_mode="section"
    )
    if not detection.boxes and not inspection.existing_widgets:
        raise FillablePdfError(
            "No writable boxes, lines, or checkboxes were detected. "
            "The scan may be too faint or OCR may be unavailable."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.partial")
    temporary.unlink(missing_ok=True)
    try:
        if detection.boxes:
            build(str(source), str(temporary), detection.boxes, font_size=0, borders=True)
        else:
            shutil.copyfile(source, temporary)
        gc.collect()
        _validate_output(source, temporary, inspection, len(detection.boxes))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    return ConversionResult(
        output_path=output,
        detected_fields=len(detection.boxes),
        existing_fields=inspection.existing_widgets,
        page_count=inspection.page_count,
        ocr_pages=tuple(detection.pages_ocred),
        unlabelled_fields=sum(not box.labelled for box in detection.boxes),
        low_confidence_fields=sum(box.confidence < 0.7 for box in detection.boxes),
        mean_confidence=(
            sum(box.confidence for box in detection.boxes) / len(detection.boxes)
            if detection.boxes
            else 1.0
        ),
    )
