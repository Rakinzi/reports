# PDF Fillable Module - Production Readiness

## Supported contract

The converter creates standard AcroForm widgets from visible boxes, ruled
lines, segmented date cells, signatures and checkboxes in vector PDFs and
image-only scans. Existing AcroForms are preserved by default. Set
`augment_existing=true` only when an operator intentionally wants a partially
fillable form scanned for additional fields.

The module rejects encrypted PDFs, XFA forms, digitally signed PDFs, malformed
files, documents over 50 MB, documents over 100 pages, and pages exceeding the
configured safe dimensions. Automatic detection is probabilistic: fields below
0.70 confidence must be reviewed before customer distribution.

## Security controls

- Uploads are streamed to randomized files outside the web root.
- Extension, PDF signature, parser validity, size, page count and page geometry
  are checked independently.
- Conversion concurrency is bounded and requests have a three-minute timeout.
- Output is written atomically and structurally validated before download.
- PDFs containing JavaScript, attachments, actions or multimedia are rejected
  before preview. Deep content-disarm-and-reconstruct belongs in an isolated
  production worker because rewriting hostile active content materially
  increases parser memory and attack surface.
- Temporary source and result files are deleted after the response.
- Production deployment must additionally provide authentication, per-user
  quotas, rate limiting, malware scanning, isolated worker containers and
  request-size enforcement at the reverse proxy.

## Accessibility and compatibility

Generated fields include unique names, alternate descriptions, printable
widget flags, explicit appearances and row-major keyboard tab order. Release
testing must cover current Adobe Acrobat Reader, Chrome, Edge, Firefox and
macOS Preview because PDF viewers do not render every AcroForm feature alike.

## Benchmark gate

Maintain a private, licensed corpus covering vector forms, raster scans,
rotated pages, tables, dates, checkboxes, partial forms, multilingual pages,
faint scans and malformed inputs. Store expected ranges in JSON and run:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark_pdf_fillable.py \
  tests/pdf_corpus --expectations tests/pdf_corpus/expectations.json
```

A commercial release should define target field precision and recall from
human-labelled ground truth. The structural benchmark included here catches
regressions but does not substitute for that labelled evaluation.

## Dependency licensing snapshot

- pikepdf: MPL-2.0. Commercial combination is allowed; modifications made to
  pikepdf itself carry source-disclosure obligations under that license.
- Tesseract and official trained data: Apache-2.0.
- pdfplumber: MIT.
- Pillow: HPND.
- OpenCV: Apache-2.0 for current 4.x releases.

Retain dependency notices in distributed builds and have counsel verify the
exact locked dependency graph before sale. This document is engineering
guidance, not legal advice.
