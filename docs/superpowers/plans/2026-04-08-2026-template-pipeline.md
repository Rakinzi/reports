# 2026 Template Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated 2026 PPTX generation pipeline that handles the new 8-slide template format and two new report clients (dicomm, ecosure already exists).

**Architecture:** `generate_report()` in `generator.py` dispatches to `generate_report_2026()` when a 2026 template exists for the report name. The 2026 pipeline shares GA4 scraping helpers with the 2025 pipeline but has its own slide-filling logic matching the new template structure.

**Tech Stack:** Python, python-pptx, Gemini (`gemini-2.5-flash`), existing Playwright scraping helpers.

---

## File Map

| File | Change |
|---|---|
| `src/reports/schemas.py` | Add `"dicomm"` to `ReportName` literal |
| `src/reports/generator.py` | Add `TEMPLATES_2026`, `GA4_PROPERTIES` entry for dicomm, `generate_report_2026()`, dispatch logic in `generate_report()` |
| `frontend/src/routes/+page.svelte` | Add `{ value: 'dicomm', label: 'Dicomm McCann' }` to `REPORT_OPTIONS` |

---

### Task 1: Add `dicomm` to schemas and frontend report options

**Files:**
- Modify: `src/reports/schemas.py`
- Modify: `frontend/src/routes/+page.svelte`

- [ ] **Step 1: Add `dicomm` to the `ReportName` literal in `schemas.py`**

Open `src/reports/schemas.py`. Change:

```python
ReportName = Literal[
    "econet",
    "econet_ai",
    "infraco",
    "ecocash",
    "ecosure",
    "zimplats",
    "cancer_serve",
]
```

To:

```python
ReportName = Literal[
    "econet",
    "econet_ai",
    "infraco",
    "ecocash",
    "ecosure",
    "zimplats",
    "cancer_serve",
    "dicomm",
]
```

- [ ] **Step 2: Add Dicomm to the frontend report options**

Open `frontend/src/routes/+page.svelte`. Find the `REPORT_OPTIONS` array (around line 44). Add the new entry:

```typescript
const REPORT_OPTIONS = [
    { value: 'econet_ai', label: 'Econet AI' },
    { value: 'econet', label: 'Econet' },
    { value: 'infraco', label: 'Infraco' },
    { value: 'ecocash', label: 'EcoCash' },
    { value: 'ecosure', label: 'Ecosure' },
    { value: 'zimplats', label: 'Zimplats' },
    { value: 'cancer_serve', label: 'Cancer Serve' },
    { value: 'dicomm', label: 'Dicomm McCann' },
];
```

- [ ] **Step 3: Commit**

```bash
git add src/reports/schemas.py frontend/src/routes/+page.svelte
git commit -m "feat: add dicomm as a report client"
```

---

### Task 2: Add 2026 template map and GA4 property for dicomm

**Files:**
- Modify: `src/reports/generator.py`

- [ ] **Step 1: Add `TEMPLATES_2026` dict and dicomm GA4 property**

Open `src/reports/generator.py`. After the existing `TEMPLATES` dict (around line 55), add:

```python
TEMPLATES_2026 = {
    "econet":       "new/Econet February Website Report - Copy.pptx",
    "econet_ai":    "new/Econet AI March Website Report.pptx",
    "infraco":      "new/Econet Infraco March Website Report.pptx",
    "ecocash":      "new/EcoCash March Website Report.pptx",
    "ecosure":      "new/Ecosure January 2026 Website Report (1).pptx",
    "zimplats":     "new/Zimplats March Website Report.pptx",
    "cancer_serve": "new/Cancerserve March Website Report.pptx",
    "dicomm":       "new/Dicomm March Website Report.pptx",
}
```

- [ ] **Step 2: Add dicomm to `GA4_PROPERTIES`**

Find the `GA4_PROPERTIES` dict (around line 45). Add:

```python
GA4_PROPERTIES = {
    "cancer_serve": "454873082",
    "econet_ai":    "511212348",
    "infraco":      "516617515",
    "zimplats":     "385365994",
    "ecocash":      "386950925",
    "econet":       "386649040",
    "ecosure":      "384507667",
    "dicomm":       "382296904",
}
```

- [ ] **Step 3: Commit**

```bash
git add src/reports/generator.py
git commit -m "feat: add 2026 template map and dicomm GA4 property"
```

---

### Task 3: Add Gemini helpers for 2026 slides

**Files:**
- Modify: `src/reports/generator.py`

These are new Gemini paraphrase functions specific to the 2026 slide layout.

- [ ] **Step 1: Add `_generate_exec_summary_texts()` for Slide 2**

Add this function after `_generate_slide5_text()` in `generator.py`:

```python
def _generate_exec_summary_texts(report_name: str, home_metrics: dict, snapshot_metrics: dict, search_metrics: dict) -> dict:
    """Generate Slide 2 Executive Summary KPI values and narrative paragraphs."""
    load_runtime_environment()
    active_users = home_metrics.get("Active users", "N/A")
    new_users = home_metrics.get("New users", "N/A")
    ctr = search_metrics.get("ctr", "N/A")
    brand = report_name.replace("_", " ").title()

    # Format active_users as shorthand e.g. 34000 -> "34K"
    try:
        n = int(str(active_users).replace(",", ""))
        active_users_short = f"{n // 1000}K" if n >= 1000 else str(n)
    except (ValueError, TypeError):
        active_users_short = str(active_users)

    # Compute new visitor %
    try:
        nu = int(str(new_users).replace(",", ""))
        au = int(str(active_users).replace(",", ""))
        new_pct = f"{round(nu / au * 100)}%" if au > 0 else "N/A"
    except (ValueError, TypeError, ZeroDivisionError):
        new_pct = "N/A"

    raw_narrative = (
        f"The {brand} website delivered performance during the period under review, "
        f"attracting {active_users} active users, with {new_pct} being new visitors. "
        f"From a search performance perspective, the platform achieved a {ctr} click-through rate (CTR). "
        f"The combination of high new-user acquisition and steady CTR performance signals continued external interest."
    )

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def para(text: str) -> str:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                "Paraphrase the following for a professional PowerPoint report. "
                "Keep all numbers exactly as they are. Use clear, formal business English. "
                "No em dashes, bullets, or markdown. Output one plain paragraph only.\n\n" + text
            ),
        )
        return resp.text.strip()

    return {
        "active_users_short": active_users_short,
        "new_pct": new_pct,
        "ctr": str(ctr),
        "narrative": para(raw_narrative),
    }
```

- [ ] **Step 2: Add `_generate_geo_text()` for Slide 4**

```python
def _generate_geo_text(countries: dict) -> str:
    """Generate Slide 4 geographic narrative from country data."""
    load_runtime_environment()
    top5 = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]
    total = sum(countries.values()) or 1
    top_country, top_n = top5[0] if top5 else ("N/A", 0)
    top_pct = round(top_n / total * 100, 2)

    raw = (
        f"Geographic performance shows {top_country} as the dominant market, "
        f"contributing {top_n} users ({top_pct}% of total traffic). "
        + ", ".join(f"{c} ({n} users)" for c, n in top5[1:]) + " follow."
    )

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            "Paraphrase the following for a professional PowerPoint report. "
            "Keep all country names and numbers exactly as they are. "
            "Use clear, formal business English. No em dashes, bullets, or markdown. "
            "Output one plain paragraph only.\n\n" + raw
        ),
    )
    return resp.text.strip()
```

- [ ] **Step 3: Add `_generate_page_perf_text()` for Slide 5**

```python
def _generate_page_perf_text(page_views: dict) -> str:
    """Generate Slide 5 page performance insight text."""
    load_runtime_environment()
    top3 = sorted(page_views.items(), key=lambda x: x[1], reverse=True)[:3]
    total = sum(page_views.values()) or 1

    parts = []
    for name, views in top3:
        pct = round(views / total * 100, 1)
        parts.append(f"{name} ({pct}% of total views)")

    raw = "The top pages driving traffic are: " + ", ".join(parts) + "."

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            "Paraphrase the following for a professional PowerPoint report. "
            "Keep all numbers exactly as they are. Use clear, formal business English. "
            "No em dashes, bullets, or markdown. Output one plain paragraph only.\n\n" + raw
        ),
    )
    return resp.text.strip()
```

- [ ] **Step 4: Add `_generate_search_perf_text()` for Slide 6**

```python
def _generate_search_perf_text(search_metrics: dict) -> str:
    """Generate Slide 6 search performance narrative."""
    load_runtime_environment()
    impressions = search_metrics.get("impressions", "N/A")
    clicks = search_metrics.get("clicks", "N/A")
    ctr = search_metrics.get("ctr", "N/A")
    position = search_metrics.get("position", "N/A")

    raw = (
        f"With {impressions} impressions, the brand maintains substantial presence in search results. "
        f"The site generated {clicks} clicks, reflecting meaningful traffic acquisition. "
        f"The {ctr} click-through rate (CTR) suggests moderate conversion of impressions into clicks. "
        f"An average position of {position} places the website on the first page of search results."
    )

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            "Paraphrase the following for a professional PowerPoint report. "
            "Keep all numbers exactly as they are. Use clear, formal business English. "
            "No em dashes, bullets, or markdown. Output one plain paragraph only.\n\n" + raw
        ),
    )
    return resp.text.strip()
```

- [ ] **Step 5: Commit**

```bash
git add src/reports/generator.py
git commit -m "feat: add Gemini text generators for 2026 slides 2/4/5/6"
```

---

### Task 4: Add `_fill_text_run()` helper and implement `generate_report_2026()`

**Files:**
- Modify: `src/reports/generator.py`

- [ ] **Step 1: Add `_fill_text_run()` helper**

This helper replaces all text in a paragraph while preserving the first run's font formatting. Add it near the other paragraph helpers:

```python
def _fill_text_run(para, new_text: str) -> None:
    """Replace a paragraph's text with new_text, preserving the first run's rPr formatting."""
    from pptx.oxml.ns import qn
    from copy import deepcopy
    import lxml.etree as etree

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
```

- [ ] **Step 2: Implement `generate_report_2026()`**

Add this function before `generate_report()`:

```python
def generate_report_2026(
    report_name: str,
    date_range: str,
    report_date: str,
    start_date: str,
    end_date: str,
) -> Path:
    """Generation pipeline for the 2026 8-slide template format."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Capture screenshots + scrape GA4 metrics (reuse existing helper)
    screenshots, home_metrics, snapshot_metrics, acquisition, page_views, weekly_active_users = capture_screenshots_and_metrics(
        report_name, start_date, end_date
    )

    countries = snapshot_metrics.get("countries", {})

    # search_metrics placeholder — scraping not yet implemented; use empty dict
    search_metrics: dict = {}

    # Step 2: Load template
    template_path = TEMPLATES_DIR / TEMPLATES_2026[report_name]
    prs = Presentation(str(template_path))
    slide_count = len(prs.slides)

    performance_month = _performance_month(date_range)

    # --- Slide 1: Replace date ---
    slide1 = prs.slides[0]
    for shape in slide1.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            # Match "Month,YYYY" or "Month, YYYY" patterns
            if re.match(r"^[A-Za-z]+,?\s*\d{4}$", text):
                _fill_text_run(para, performance_month.replace(" ", ","))

    # --- Slide 2: Executive Summary ---
    exec_texts = _generate_exec_summary_texts(report_name, home_metrics, snapshot_metrics, search_metrics)
    slide2 = prs.slides[1]
    active_users = home_metrics.get("Active users", "N/A")
    new_users = home_metrics.get("New users", "N/A")
    try:
        nu = int(str(new_users).replace(",", ""))
        au = int(str(active_users).replace(",", ""))
        new_pct = f"{round(nu / au * 100)}%"
    except (ValueError, TypeError, ZeroDivisionError):
        new_pct = "N/A"

    for shape in slide2.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            # KPI boxes: match by approximate value patterns
            if re.match(r"^\d+K?$", text):  # e.g. "34K" active users
                _fill_text_run(para, exec_texts["active_users_short"])
            elif text.endswith("%") and "." not in text and len(text) <= 5:  # e.g. "94%"
                _fill_text_run(para, exec_texts["new_pct"])
            elif re.match(r"^\d+\.\d+%$", text):  # e.g. "3.1%" CTR
                _fill_text_run(para, exec_texts["ctr"])
            # Narrative paragraphs
            elif "first-time users" in text.lower() or "under review" in text.lower() or "attracting" in text.lower():
                _fill_text_run(para, exec_texts["narrative"])

    # --- Slide 3: Site Overview ---
    active_users_raw = home_metrics.get("Active users", "N/A")
    new_users_raw = home_metrics.get("New users", "N/A")
    engagement = home_metrics.get("Average engagement time per active user", "N/A")
    try:
        au_int = int(str(active_users_raw).replace(",", ""))
        nu_int = int(str(new_users_raw).replace(",", ""))
        nu_pct = round(nu_int / au_int * 100, 1)
        new_users_label = f"{new_users_raw} ({nu_pct}%)"
    except (ValueError, TypeError, ZeroDivisionError):
        new_users_label = str(new_users_raw)

    slide3_para = _generate_slide3_paragraph(report_name, home_metrics, snapshot_metrics)
    slide3 = prs.slides[2]
    for shape in slide3.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if re.match(r"^[\d,]+$", text) and len(text) >= 3:  # stat number e.g. "34,000"
                # determine which stat by shape position — use shape name heuristic
                pass  # handled by shape-level below
            if "total active users" in text.lower():
                _fill_text_run(para, str(active_users_raw))
            elif "new users" in text.lower() and "%" in text:
                _fill_text_run(para, new_users_label)
            elif "avg engagement" in text.lower() or "engagement time" in text.lower():
                _fill_text_run(para, str(engagement))
            elif "reflects solid" in text.lower() or "new visitors" in text.lower() or "past month" in text.lower() or "attracted" in text.lower():
                _fill_text_run(para, slide3_para)

    # Replace stat number boxes on slide 3 by shape order
    stat_shapes = [
        s for s in slide3.shapes
        if s.has_text_frame and re.match(r"^[\d,]+$", s.text_frame.text.strip())
    ]
    stat_values = [str(active_users_raw), str(new_users_raw), str(engagement)]
    for i, shape in enumerate(stat_shapes[:3]):
        for para in shape.text_frame.paragraphs:
            if re.match(r"^[\d,]+", para.text.strip()):
                _fill_text_run(para, stat_values[i])

    # Line chart screenshot on slide 3
    if "home_chart" in screenshots:
        _replace_image_in_slide(slide3, screenshots["home_chart"], shape_name="Picture 18")

    # --- Slide 4: Geographic Performance ---
    if countries:
        top5 = dict(sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5])
        country_chart_path = SCREENSHOTS_DIR / report_name / "country_chart.png"
        generate_country_bar_chart(top5, str(country_chart_path))
        screenshots["country_chart"] = country_chart_path

    geo_text = _generate_geo_text(countries) if countries else ""
    slide4 = prs.slides[3]
    for shape in slide4.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if "dominant market" in text.lower() or "geographic performance" in text.lower() or "contributing" in text.lower():
                _fill_text_run(para, geo_text)

    if "country_chart" in screenshots:
        _replace_image_in_slide(slide4, screenshots["country_chart"], shape_name="Picture 10")

    # --- Slide 5: Page Performance ---
    page_perf_text = _generate_page_perf_text(page_views) if page_views else ""
    slide5 = prs.slides[4]
    for shape in slide5.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if "drives the highest traffic" in text.lower() or "overall insight" in text.lower() or "homepage" in text.lower():
                _fill_text_run(para, page_perf_text)

    if "pages_table" in screenshots:
        _replace_image_in_slide(slide5, screenshots["pages_table"], shape_name="Picture 13")

    # --- Slide 6: Search Performance (8-slide variants only) ---
    # slide_count == 8 means this slide exists; 7-slide variants skip it
    if slide_count == 8:
        search_text = _generate_search_perf_text(search_metrics) if search_metrics else ""
        slide6 = prs.slides[5]
        if search_text:
            for shape in slide6.shapes:
                if not shape.has_text_frame:
                    continue
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if "impressions" in text.lower() or "click-through rate" in text.lower():
                        _fill_text_run(para, search_text)
        if "search_screenshot" in screenshots:
            _replace_image_in_slide(slide6, screenshots["search_screenshot"], shape_name="Picture 10")

    # --- Recommendations slide (last before thank-you) ---
    rec_slide_idx = slide_count - 2  # second to last slide
    previous_data = _get_previous_month_data(report_name)
    current_stats = (
        f"Date range: {date_range}\nReport date: {report_date}\n"
        f"Active users: {home_metrics.get('Active users', 'N/A')}\n"
        f"New users: {home_metrics.get('New users', 'N/A')}\n"
        f"Channels: {snapshot_metrics.get('channels', {})}\n"
        f"Top country: {snapshot_metrics.get('top_country', 'N/A')}"
    )
    recommendations = _generate_recommendations(report_name, current_stats, previous_data, date_range)

    if recommendations and rec_slide_idx < slide_count:
        from copy import deepcopy
        import lxml.etree as _etree
        from pptx.oxml.ns import qn as _qn_rec
        rec_slide = prs.slides[rec_slide_idx]
        for shape in rec_slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                full_text = "".join(r.text for r in para.runs).strip()
                for i, rec in enumerate(recommendations, start=1):
                    if full_text.startswith(f"{i}."):
                        if para.runs:
                            first_rpr = para.runs[0]._r.find(_qn_rec("a:rPr"))
                            saved_rpr = deepcopy(first_rpr) if first_rpr is not None else None
                            for child in list(para._p):
                                if child.tag != _qn_rec("a:pPr"):
                                    para._p.remove(child)
                            new_r = _etree.SubElement(para._p, _qn_rec("a:r"))
                            if saved_rpr is not None:
                                new_r.insert(0, saved_rpr)
                            new_t = _etree.SubElement(new_r, _qn_rec("a:t"))
                            new_t.text = rec
                        break

    # Save output
    safe_name = report_name.replace("_", "-")
    output_path = OUTPUT_DIR / f"{safe_name}-{report_date.replace(' ', '-')}.pptx"
    prs.save(str(output_path))
    return output_path
```

- [ ] **Step 3: Commit**

```bash
git add src/reports/generator.py
git commit -m "feat: implement generate_report_2026() pipeline"
```

---

### Task 5: Wire the dispatch in `generate_report()`

**Files:**
- Modify: `src/reports/generator.py`

- [ ] **Step 1: Add dispatch at the top of `generate_report()`**

Find `generate_report()` (around line 884). Add the dispatch as the first thing after the `UNSUPPORTED_REPORTS` check:

```python
def generate_report(
    report_name: str,
    date_range: str,
    report_date: str,
    start_date: str,
    end_date: str,
) -> Path:
    if report_name in UNSUPPORTED_REPORTS:
        raise NotImplementedError(
            f"'{report_name}' has a unique template structure and is not yet supported."
        )

    # Dispatch to 2026 pipeline if a new-format template exists for this report
    if report_name in TEMPLATES_2026:
        return generate_report_2026(
            report_name=report_name,
            date_range=date_range,
            report_date=report_date,
            start_date=start_date,
            end_date=end_date,
        )

    # ... rest of existing 2025 pipeline unchanged
```

- [ ] **Step 2: Remove `econet`, `econet_ai`, `infraco`, `ecocash`, `ecosure`, `zimplats`, `cancer_serve`, `dicomm` from `UNSUPPORTED_REPORTS` if present**

Check if `UNSUPPORTED_REPORTS` exists in the file:

```bash
grep -n "UNSUPPORTED_REPORTS" src/reports/generator.py
```

If any 2026 clients are listed there, remove them.

- [ ] **Step 3: Smoke test the dispatch wiring**

```bash
cd /Users/rakinzisilver/Documents/GitHub/reports
python3 -c "
from src.reports.generator import TEMPLATES_2026, generate_report
print('2026 template keys:', list(TEMPLATES_2026.keys()))
print('Dispatch wired OK')
"
```

Expected output:
```
2026 template keys: ['econet', 'econet_ai', 'infraco', 'ecocash', 'ecosure', 'zimplats', 'cancer_serve', 'dicomm']
Dispatch wired OK
```

- [ ] **Step 4: Commit**

```bash
git add src/reports/generator.py
git commit -m "feat: dispatch to 2026 pipeline when new template exists"
```
