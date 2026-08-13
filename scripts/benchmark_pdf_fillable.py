#!/usr/bin/env python3
"""Benchmark automatic form conversion against a directory of PDF fixtures."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from reports.pdf_fillable_service import FillablePdfError, convert_pdf_to_fillable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path, help="directory containing PDF fixtures")
    parser.add_argument("--expectations", type=Path, help="JSON keyed by fixture filename")
    parser.add_argument("--report", type=Path, default=Path("artifacts/pdf-fillable-benchmark.json"))
    args = parser.parse_args()

    expectations = json.loads(args.expectations.read_text()) if args.expectations else {}
    rows = []
    passed = True
    with tempfile.TemporaryDirectory(prefix="pdf-fillable-benchmark-") as temporary:
        for source in sorted(args.corpus.glob("*.pdf")):
            started = time.monotonic()
            row = {"file": source.name}
            try:
                result = convert_pdf_to_fillable(source, Path(temporary) / source.name)
                row.update(
                    status="ok",
                    seconds=round(time.monotonic() - started, 3),
                    pages=result.page_count,
                    fields=result.total_fields,
                    new_fields=result.detected_fields,
                    low_confidence=result.low_confidence_fields,
                    mean_confidence=round(result.mean_confidence, 3),
                    ocr_pages=list(result.ocr_pages),
                )
                expected = expectations.get(source.name, {})
                checks = {
                    "min_fields": row["fields"] >= expected.get("min_fields", 0),
                    "max_fields": row["fields"] <= expected.get("max_fields", sys.maxsize),
                    "max_low_confidence": row["low_confidence"]
                    <= expected.get("max_low_confidence", sys.maxsize),
                }
                row["checks"] = checks
                passed &= all(checks.values())
            except FillablePdfError as exc:
                row.update(status="error", seconds=round(time.monotonic() - started, 3), error=str(exc))
                passed = False
            rows.append(row)

    summary = {
        "passed": passed,
        "documents": len(rows),
        "successful": sum(row["status"] == "ok" for row in rows),
        "results": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
