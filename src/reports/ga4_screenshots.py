"""Capture complete GA4 tables inside their scrolling report panels."""

from io import BytesIO
from pathlib import Path

from PIL import Image


def capture_ga4_table(
    page, path: Path, *, max_data_rows: int = 10, last_column: str | None = None,
) -> Path:
    """Save the table header, total, and complete data rows as one image.

    GA4 clips its table at the panel's scroll boundary. A screenshot of the
    table element therefore cuts the last row even though that row exists in
    the DOM. Playwright scrolls each row into view before capturing it.
    """
    table = page.locator("table.adv-table").first
    table.wait_for(state="visible", timeout=10000)
    table_box = table.bounding_box()
    if not table_box:
        raise RuntimeError("GA4 table has no visible bounds")

    headers = table.locator("thead").first
    rows = table.locator("tbody tr")
    row_count = rows.count()
    if row_count == 0:
        raise RuntimeError("GA4 table has no rows")

    # The table can span the entire report panel while its actual columns do
    # not. Use the right edge of the last visible header to remove empty space.
    visible_headers = [
        (" ".join(header.inner_text().lower().split()), box)
        for header in table.locator("thead th").all()
        if header.inner_text().strip() and (box := header.bounding_box())
        and box["x"] + box["width"] <= table_box["x"] + table_box["width"] + 1
    ]
    target = " ".join(last_column.lower().split()) if last_column else None
    matching = [box for label, box in visible_headers if target and target in label]
    if target and not matching:
        raise RuntimeError(f"GA4 table is missing the '{last_column}' column")
    selected = matching or [box for _, box in visible_headers]
    right_edge = max(
        (box["x"] + box["width"] for box in selected),
        default=table_box["x"] + table_box["width"],
    )
    content_width = min(table_box["width"], right_edge - table_box["x"] + 8)

    page.mouse.move(0, 0)
    parts = [Image.open(BytesIO(headers.screenshot())).convert("RGB")]
    data_rows = 0
    for index in range(row_count):
        row = rows.nth(index)
        label = row.inner_text().strip()
        if not label:
            continue
        is_total = label.lower().startswith("total")
        if not is_total and data_rows >= max_data_rows:
            break
        parts.append(Image.open(BytesIO(row.screenshot())).convert("RGB"))
        if not is_total:
            data_rows += 1

    if len(parts) == 1:
        raise RuntimeError("GA4 table rows were empty")

    scale = parts[0].width / table_box["width"]
    width = min(min(part.width for part in parts), round(content_width * scale))
    result = Image.new("RGB", (width, sum(part.height for part in parts)), "white")
    y = 0
    for part in parts:
        cropped = part.crop((0, 0, width, part.height))
        result.paste(cropped, (0, y))
        y += part.height
    result.save(path)
    return path
