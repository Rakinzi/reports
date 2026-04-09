"""
generator_2026.py — Generation pipeline for 2026 PPTX template format.

Completely separate from the old pipeline in generator.py.
Called by app.py when the requested report name is in TEMPLATES_2026.
"""
from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path

import lxml.etree as etree
from google import genai
from playwright.sync_api import sync_playwright
from pptx import Presentation
from pptx.oxml.ns import qn

from .charts import generate_country_bar_chart
from .logging_utils import configure_logging
from .runtime import (
    get_output_dir,
    get_screenshots_dir,
    get_templates_dir,
    load_runtime_environment,
)

# Re-use browser/navigation helpers from the old module — they are pure utilities
# with no dependency on the old pipeline's data model.
from .generator import (
    _ensure_expected_ga4_property,
    _fill_text_run,
    _goto_ga4_section,
    _launch_persistent_context,
    _replace_image_in_slide,
    _scrape_home_metrics,
    _scrape_snapshot_metrics,
    _set_date_range,
    _switch_ga4_property_via_search,
    _generate_recommendations,
    _get_previous_month_data,
)

logger = configure_logging()

TEMPLATES_DIR = get_templates_dir()
OUTPUT_DIR = get_output_dir()
SCREENSHOTS_DIR = get_screenshots_dir()

# ---------------------------------------------------------------------------
# Template + property maps — 2026 format only
# ---------------------------------------------------------------------------

GA4_PROPERTIES_2026: dict[str, str] = {
    "cancer_serve": "454873082",
    "econet_ai":    "511212348",
    "infraco":      "516617515",
    "zimplats":     "385365994",
    "ecocash":      "386950925",
    "econet":       "386649040",
    "ecosure":      "384507667",
    "dicomm":       "382296904",
}

TEMPLATES_2026: dict[str, str] = {
    "econet":       "new/Econet February Website Report - Copy.pptx",
    "econet_ai":    "new/Econet AI March Website Report.pptx",
    "infraco":      "new/Econet Infraco March Website Report.pptx",
    "ecocash":      "new/EcoCash March Website Report.pptx",
    "ecosure":      "new/Ecosure January 2026 Website Report (1).pptx",
    "zimplats":     "new/Zimplats March Website Report.pptx",
    "cancer_serve": "new/Cancerserve March Website Report.pptx",
    "dicomm":       "new/Dicomm March Website Report.pptx",
}

# 7-slide variants skip Slide 6 (Search Performance)
SEVEN_SLIDE_REPORTS = {"zimplats", "dicomm"}

# Google Search Console site URLs — used to build the performance report URL
GSC_URLS: dict[str, str] = {
    "econet":       "https://www.econet.co.zw/",
    "econet_ai":    "https://econetai.co.zw/",
    "infraco":      "https://infraco.co.zw/",
    "ecocash":      "https://www.ecocash.co.zw/",
    "ecosure":      "https://www.ecosure.co.zw/",
    "cancer_serve": "https://www.cancerserve.org/",
    "dicomm":       "https://www.dicomm.co.zw/",
}


# ---------------------------------------------------------------------------
# Gemini text generators
# ---------------------------------------------------------------------------

def _gemini_para(raw: str) -> str:
    """Paraphrase raw text via Gemini, returning the same approximate length."""
    load_runtime_environment()
    word_count = len(raw.split())
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            f"Paraphrase the following for a professional PowerPoint report. "
            f"Keep all numbers, percentages, and proper nouns exactly as they are. "
            f"Use clear, formal business English. No em dashes, bullets, or markdown. "
            f"Output must be approximately {word_count} words — do not shorten or expand. "
            f"Output one plain paragraph only.\n\n" + raw
        ),
    )
    return resp.text.strip()


def _write_para_with_highlights(para, text: str, bold_words: set[str] | None = None) -> None:
    """Replace paragraph content with text, bolding numbers/percentages and any extra bold_words."""
    import lxml.etree as etree

    if not para.runs:
        return

    # Save formatting from first run
    first_rpr = para.runs[0]._r.find(qn("a:rPr"))
    base_rpr = deepcopy(first_rpr) if first_rpr is not None else None

    # Remove all existing runs (keep pPr)
    for child in list(para._p):
        if child.tag != qn("a:pPr"):
            para._p.remove(child)

    # Build pattern: numbers/percentages + any extra words (e.g. country names)
    num_pat = r"\d[\d,]*(?:\.\d+)?(?:%|K|M|s|ms)?|\d+(?:\.\d+)?%"
    if bold_words:
        # Sort longest first to avoid partial matches (e.g. "South Africa" before "South")
        escaped = [re.escape(w) for w in sorted(bold_words, key=len, reverse=True)]
        token_pattern = re.compile(f"({'|'.join(escaped)}|{num_pat})")
    else:
        token_pattern = re.compile(f"({num_pat})")

    segments = []
    last = 0
    for m in token_pattern.finditer(text):
        if m.start() > last:
            segments.append((text[last:m.start()], False))
        segments.append((m.group(), True))
        last = m.end()
    if last < len(text):
        segments.append((text[last:], False))

    for seg_text, bold in segments:
        r = etree.SubElement(para._p, qn("a:r"))
        if base_rpr is not None:
            rpr = deepcopy(base_rpr)
            if bold:
                rpr.set("b", "1")
            else:
                rpr.attrib.pop("b", None)
            r.insert(0, rpr)
        t = etree.SubElement(r, qn("a:t"))
        t.text = seg_text


def _exec_summary_texts(report_name: str, home_metrics: dict, snapshot_metrics: dict) -> dict:
    """Slide 2 — KPI values + narratives for para 0 and para 2."""
    active_users = home_metrics.get("Active users", "N/A")
    new_users = home_metrics.get("New users", "N/A")
    brand = report_name.replace("_", " ").title()

    # GA4 already returns shorthand like "27K" — use as-is, only convert if raw number
    try:
        s = str(active_users).strip().replace(",", "")
        if s.upper().endswith("K"):
            active_users_short = s
        else:
            n = int(float(s))
            active_users_short = f"{n // 1000}K" if n >= 1000 else str(n)
    except (ValueError, TypeError):
        active_users_short = str(active_users)

    def _parse_num(val: str) -> int:
        s = str(val).strip().replace(",", "")
        if s.upper().endswith("K"):
            return int(float(s[:-1]) * 1000)
        return int(float(s))

    try:
        nu = _parse_num(new_users)
        au = _parse_num(active_users)
        new_pct = f"{round(nu / au * 100)}%" if au > 0 else "N/A"
    except (ValueError, TypeError, ZeroDivisionError):
        new_pct = "N/A"

    # Subtitle — same word count as template
    raw_subtitle = f"Performance Overview: {new_pct} of users are first-time visitors"

    # Para 0 — active users + new visitors count + new visitor %
    raw_para0 = (
        f"The {brand} website delivered solid overall performance during the period under review, "
        f"attracting {active_users} active users, of which {new_users} ({new_pct}) were new visitors. "
        f"This strong proportion of first-time users reflects effective audience acquisition "
        f"and sustained brand visibility across digital channels."
    )

    # Para 2 — closing insight (no CTR dependency)
    raw_para2 = (
        f"The combination of high new-user acquisition signals continued external interest "
        f"and strong discoverability. Overall, the website demonstrates a stable digital footprint "
        f"driven by strong awareness metrics. The next optimisation focus can centre on improving "
        f"engagement depth and converting this large influx of new visitors into repeat users "
        f"and long-term brand loyalty."
    )

    return {
        "active_users_short": active_users_short,
        "new_pct": new_pct,
        "subtitle": _gemini_para(raw_subtitle),
        "para0": _gemini_para(raw_para0),
        "para2": _gemini_para(raw_para2),
    }


def _site_overview_paras(report_name: str, home_metrics: dict, snapshot_metrics: dict) -> tuple[str, str, str, str]:
    """Slide 3 — subtitle + three narrative paragraphs, each same token count as template."""
    active_users = home_metrics.get("Active users", "N/A")
    new_users = home_metrics.get("New users", "N/A")
    engagement = home_metrics.get("Average engagement time per active user", "N/A")
    brand = report_name.replace("_", " ").title()

    def _parse_num(val: str) -> int:
        s = str(val).strip().replace(",", "")
        if s.upper().endswith("K"):
            return int(float(s[:-1]) * 1000)
        return int(float(s))

    try:
        au = _parse_num(active_users)
        nu = _parse_num(new_users)
        new_pct = f"{round(nu / au * 100, 1)}%"
    except (ValueError, TypeError, ZeroDivisionError):
        new_pct = "N/A"

    # Subtitle — "User Engagement Metrics: 34K Strong Active User Baseline"
    raw_subtitle = f"User Engagement Metrics: {active_users} Strong Active User Baseline"

    raw_para0 = (
        f"The reporting period reflects solid and encouraging performance for the {brand} website, "
        f"with a total of {active_users} active users recorded during the period. "
        f"Of these, {new_users} users ({new_pct}) were new visitors, highlighting continued strong "
        f"brand discovery and the effectiveness of current reach and awareness initiatives."
    )

    raw_para2 = (
        f"The consistently high proportion of new users suggests that marketing efforts, "
        f"search visibility, and broader brand exposure are successfully attracting first-time "
        f"audiences to the platform. This level of new user acquisition indicates that the website "
        f"remains highly discoverable and competitive within its category."
    )

    raw_para4 = (
        f"The average engagement time of {engagement} demonstrates moderate but meaningful interaction. "
        f"While slightly below longer-form corporate engagement benchmarks, this duration suggests "
        f"that users are spending enough time to review key information rather than exiting immediately."
    )

    return (
        _gemini_para(raw_subtitle),
        _gemini_para(raw_para0),
        _gemini_para(raw_para2),
        _gemini_para(raw_para4),
    )


def _geo_paras(countries_data: list[dict]) -> tuple[str, str, str, str]:
    """Slide 4 — returns 4 Gemini-paraphrased narrative paragraphs from real country data."""
    total_users = sum(r["users"] for r in countries_data) or 1
    sorted_rows = sorted(countries_data, key=lambda r: r["users"], reverse=True)
    top = sorted_rows[0]
    top_pct = round(top["users"] / total_users * 100, 2)

    secondary = sorted_rows[1:5]

    def _pct_val(s: str) -> float:
        try:
            return float(s.strip().rstrip("%"))
        except ValueError:
            return 0.0

    high_intent = [r for r in sorted_rows[1:] if _pct_val(r["engagement_rate"]) > 50]

    raw0 = (
        f"Geographic performance shows {top['country']} as the dominant market, "
        f"contributing {top['users']:,} users ({top_pct}% of total traffic) "
        f"with a {top['engagement_rate']} engagement rate and "
        f"{top['engaged_sessions_per_user']} engaged sessions per user, "
        f"delivering strong volume with steady interaction."
    )

    if secondary:
        sec_parts = [
            f"{r['country']} ({r['users']:,} users) records a {r['engagement_rate']} engagement rate"
            for r in secondary[:2]
        ]
        raw1 = (
            f"{sec_parts[0]}"
            + (f", while {sec_parts[1]}" if len(sec_parts) > 1 else "")
            + ", indicating stronger visit quality despite lower traffic volumes."
        )
    else:
        raw1 = f"Secondary markets are emerging and represent an opportunity for targeted regional campaigns."

    if high_intent:
        hi_parts = [f"{r['country']} ({r['engagement_rate']})" for r in high_intent[:4]]
        raw2 = (
            f"Notably, smaller markets such as {', '.join(hi_parts)} "
            f"demonstrate the strongest engagement efficiency, suggesting high-intent audiences."
        )
    else:
        raw2 = (
            f"Several international markets demonstrate strong engagement efficiency, "
            f"suggesting high-intent audiences with potential conversion value."
        )

    raw3 = (
        f"Overall, {top['country']} drives scale, while select international markets "
        f"show strong engagement depth and potential conversion value."
    )

    return (
        _gemini_para(raw0),
        _gemini_para(raw1),
        _gemini_para(raw2),
        _gemini_para(raw3),
    )


_PAGE_COMPLIANCE_KEYWORDS = (
    "terms and conditions", "ts and cs", "t&c", "privacy policy",
    "terms of service", "disclaimer", "legal", "cookie policy",
)
_PAGE_SUPPORT_KEYWORDS = (
    "contact us", "contact", "support", "help", "faq", "customer experience",
    "customer service", "feedback",
)
_PAGE_HOME_KEYWORDS = (
    "home", "homepage", "index", "main",
)


def _classify_page(title: str) -> str:
    """Classify a page by its title keywords. Returns: 'home', 'compliance', 'support', 'product'."""
    # Classify against the FULL title — brand suffix pattern varies by client:
    # "Devices - Econet Wireless Zimbabwe" (page first) OR
    # "Econet Wireless Zimbabwe - Contact Us" (brand first)
    # So search the whole string for keywords, not just one side.
    t = title.lower()

    if any(kw in t for kw in _PAGE_HOME_KEYWORDS):
        return "home"
    if any(kw in t for kw in _PAGE_COMPLIANCE_KEYWORDS):
        return "compliance"
    if any(kw in t for kw in _PAGE_SUPPORT_KEYWORDS):
        return "support"

    # If no descriptors found and no " - " separator → pure brand name = homepage
    if " - " not in t and "–" not in t and "|" not in t:
        return "home"

    return "product"


def _short_title(title: str) -> str:
    """Return a clean short label: strip brand suffix from either side, normalise T&C variants."""
    _TC_VARIANTS = ("terms and conditions", "ts and cs", "terms & conditions", "terms of service")

    t_lower = title.lower()

    # Normalise T&C first (before stripping brand name)
    for variant in _TC_VARIANTS:
        if variant in t_lower:
            idx = t_lower.find(variant)
            product = title[:idx].strip().rstrip("–-– ").strip()
            # Also strip brand suffix from product part if present
            if " - " in product:
                product = product.rsplit(" - ", 1)[0].strip()
            if product:
                return f"{product} Terms & Conditions"
            return "Terms & Conditions"

    # Strip brand: try both "Page - Brand" and "Brand - Page" patterns.
    # Heuristic: the shorter segment after splitting on " - " is usually the page name.
    if " - " in title:
        parts = title.split(" - ", 1)
        left, right = parts[0].strip(), parts[1].strip()
        # Pick the more descriptive (usually shorter) part as the page label
        label = left if len(left) <= len(right) else right
        return label

    return title


def _page_perf_paras(pages_data: list[dict], site_total_views: int = 0) -> tuple[str, str, str, str]:
    """Slide 5 — heading + 3 Gemini-paraphrased narrative paragraphs from real page data."""
    if not pages_data:
        return ("", "", "", "")

    # Use the real site-wide total if available, else fall back to sum of top 10
    total_views = site_total_views if site_total_views > 0 else (sum(p["views"] for p in pages_data) or 1)

    # Annotate each page with its classification and clean label
    for p in pages_data:
        p["_type"] = _classify_page(p["title"])
        raw_label = _short_title(p["title"])
        # Home pages always get a friendly label regardless of brand name
        p["_label"] = "Homepage" if p["_type"] == "home" else raw_label

    top = pages_data[0]
    top_pct = round(top["views"] / total_views * 100, 1)

    # Homepage — find it regardless of position
    homepage = next((p for p in pages_data if p["_type"] == "home"), None)

    # Product pages — high commercial intent
    product_pages = [p for p in pages_data if p["_type"] == "product"]

    # Compliance pages (T&Cs etc.)
    compliance_pages = [p for p in pages_data if p["_type"] == "compliance"]

    # Support pages
    support_pages = [p for p in pages_data if p["_type"] == "support"]

    # --- Heading ---
    if homepage and homepage != top:
        raw_heading = (
            f"The {top['_label']} and {homepage['_label']} pages drive the most meaningful engagement."
        )
    else:
        second = pages_data[1] if len(pages_data) > 1 else None
        raw_heading = (
            f"The {top['_label']}"
            + (f" and {second['_label']}" if second else "")
            + " pages drive the most meaningful engagement."
        )

    # --- Para 1: top page + homepage context ---
    # "Homepage" already implies "page" — avoid "The Homepage page"
    top_label_display = top['_label'] if top['_label'] != "Homepage" else "Homepage"
    page_suffix = "" if top['_label'] == "Homepage" else " page"
    raw_para1 = (
        f"The {top_label_display}{page_suffix} drives the highest traffic, accounting for "
        f"{top_pct}% of total views ({top['views']:,} views) with {top['views_per_user']} views per active user "
        f"and an average engagement time of {top['avg_engagement_time']}. "
    )
    if top["_type"] == "compliance":
        raw_para1 += (
            "As a compliance or legal page, this high volume reflects strong paid media efforts "
            "directing users to read terms before proceeding, though lower repeat visits are expected."
        )
    elif homepage and homepage != top:
        h_pct = round(homepage["views"] / total_views * 100, 1)
        raw_para1 += (
            f"The Homepage remains a key entry point with {homepage['views']:,} views ({h_pct}% of total), "
            f"reinforcing its role as the central navigation hub."
        )
    else:
        raw_para1 += "This strong volume reflects effective discoverability and user interest in the content."

    # --- Para 2: product pages with browsing depth ---
    if product_pages:
        deep = sorted(product_pages, key=lambda p: float(p["views_per_user"]), reverse=True)[:3]
        deep_parts = [f"{p['_label']} ({p['views_per_user']} views per user)" for p in deep]
        raw_para2 = (
            f"Product-driven pages such as {', '.join(deep_parts)} demonstrate stronger browsing intent, "
            f"indicating commercial interest and higher engagement quality from users actively exploring offerings."
        )
    elif compliance_pages:
        c_parts = [f"{p['_label']} ({round(p['views']/total_views*100,1)}% of views)" for p in compliance_pages[:2]]
        raw_para2 = (
            f"Compliance pages including {' and '.join(c_parts)} generate substantial traffic, "
            f"typically driven by campaign landing requirements rather than organic browsing intent."
        )
    else:
        second = pages_data[1] if len(pages_data) > 1 else None
        if second:
            s_pct = round(second["views"] / total_views * 100, 1)
            raw_para2 = (
                f"The {second['_label']} page accounts for {s_pct}% of total views "
                f"with {second['views_per_user']} views per user, contributing steady secondary traffic."
            )
        else:
            raw_para2 = "Secondary pages contribute consistent traffic volumes across the site."

    # --- Para 3: support / low-depth pages or overall observation ---
    if support_pages:
        s_parts = [p["_label"] for p in support_pages[:2]]
        raw_para3 = (
            f"Support-oriented pages such as {' and '.join(s_parts)} contribute steady traffic "
            f"but are not primary drivers of repeat interaction or deep browsing behaviour."
        )
    elif compliance_pages and product_pages:
        c_views = sum(p["views"] for p in compliance_pages)
        c_pct = round(c_views / total_views * 100, 1)
        best_product = max(product_pages, key=lambda p: float(p["views_per_user"]))
        raw_para3 = (
            f"Compliance pages collectively account for {c_pct}% of total views, driven primarily "
            f"by campaign traffic rather than organic intent. In contrast, product pages such as "
            f"{best_product['_label']} ({best_product['views_per_user']} views per user) show "
            f"stronger browsing depth, signalling genuine commercial interest worth nurturing."
        )
    else:
        raw_para3 = (
            f"Overall, the site demonstrates a healthy page distribution with clear entry points "
            f"and consistent user flow across key content areas."
        )

    return (
        _gemini_para(raw_heading),
        _gemini_para(raw_para1),
        _gemini_para(raw_para2),
        _gemini_para(raw_para3),
    )


# ---------------------------------------------------------------------------
# GSC capture helper
# ---------------------------------------------------------------------------

def _capture_gsc(context, report_name: str, start_date: str, end_date: str, out_dir: Path) -> tuple[dict, dict]:
    """Open GSC, select the correct property, set custom date range, scrape metrics + screenshot."""
    from datetime import datetime as _dt
    from urllib.parse import quote as _quote

    start_dt = _dt.strptime(start_date, "%b %d, %Y")
    end_dt   = _dt.strptime(end_date,   "%b %d, %Y")
    gsc_site = GSC_URLS[report_name]

    # Format dates for the GSC date picker inputs: "3/1/2026"
    start_picker = start_dt.strftime("%-m/%-d/%Y")
    end_picker   = end_dt.strftime("%-m/%-d/%Y")

    search_metrics: dict = {}
    screenshots: dict = {}

    gsc_page = context.new_page()

    # 1. Go to GSC performance page for this property directly via URL
    gsc_page.goto(
        "https://search.google.com/search-console/performance/search-analytics"
        f"?resource_id={_quote(gsc_site, safe='')}",
        wait_until="domcontentloaded", timeout=30000,
    )
    gsc_page.wait_for_selector("text=Total clicks", state="attached", timeout=20000)
    gsc_page.wait_for_timeout(1000)

    # 2. Click the property selector pill to confirm/switch property
    try:
        gsc_page.locator('div[jscontroller="Jdbz6e"]').click()
        gsc_page.wait_for_timeout(800)

        # Use the active combobox input — exact=True to avoid matching "Inspect any URL in..."
        prop_input = gsc_page.get_by_role("combobox", name=gsc_site, exact=True)
        prop_input.click(click_count=3)
        prop_input.fill(gsc_site)
        gsc_page.wait_for_timeout(800)

        # Click the matching result that appears in the dropdown list
        gsc_page.locator(f'[data-initialvalue="{gsc_site}"]').first.click()
        gsc_page.wait_for_timeout(2000)
        gsc_page.wait_for_selector("text=Total clicks", state="attached", timeout=10000)
    except Exception as e:
        logger.warning("[2026] GSC property selector failed (continuing): %s", e)

    # 3. Set custom date range.
    #    Some GSC instances show "Custom" directly in the toolbar; others hide it under "More".
    #    Both open the same "Date range" modal with YYYY-MM-DD inputs.
    try:
        start_val = start_dt.strftime("%Y-%m-%d")
        end_val   = end_dt.strftime("%Y-%m-%d")

        # Try clicking "Custom" directly first; fall back to "More time ranges" → "Custom"
        try:
            gsc_page.locator('button[role="radio"]').filter(has_text="Custom").click(timeout=3000)
        except Exception:
            gsc_page.get_by_role("button", name="More time ranges").click(timeout=5000)
            gsc_page.wait_for_timeout(500)
            # Two "Custom" labels exist (Filter + Compare tabs) — click the Filter one
            gsc_page.get_by_label("Filter", exact=True).get_by_text("Custom", exact=True).click(timeout=5000)

        gsc_page.wait_for_timeout(600)

        # Fill the date inputs inside the modal.
        # The inputs have class "qdOxv-fmcmS-wGMbrd" and use aria-labelledby.
        # Wait for them to appear, then fill by order (start=0, end=1).
        gsc_page.wait_for_selector("input.qdOxv-fmcmS-wGMbrd", timeout=8000)
        date_inputs = gsc_page.locator("input.qdOxv-fmcmS-wGMbrd")

        date_inputs.nth(0).click(click_count=3)
        date_inputs.nth(0).fill(start_val)
        gsc_page.wait_for_timeout(200)
        date_inputs.nth(1).click(click_count=3)
        date_inputs.nth(1).fill(end_val)
        gsc_page.wait_for_timeout(200)

        # Click Apply — page reloads with new date range
        gsc_page.get_by_role("button", name="Apply").click()
        gsc_page.wait_for_timeout(5000)
    except Exception as e:
        logger.warning("[2026] GSC date picker failed, reloading with URL date params: %s", e)
        # Fallback: open a fresh page with date params baked into URL
        try:
            gsc_page.close()
        except Exception:
            pass
        gsc_page = context.new_page()
        gsc_page.goto(
            "https://search.google.com/search-console/performance/search-analytics"
            f"?resource_id={_quote(gsc_site, safe='')}"
            f"&start_date={start_dt.strftime('%Y%m%d')}"
            f"&end_date={end_dt.strftime('%Y%m%d')}",
            wait_until="domcontentloaded", timeout=30000,
        )
        gsc_page.wait_for_selector("text=Total clicks", state="attached", timeout=15000)
        gsc_page.wait_for_timeout(2000)

    # 5. Scrape metrics
    body_text = gsc_page.locator("body").inner_text()
    lines = [l.strip() for l in body_text.splitlines()]

    def _next_val_after(label: str) -> str:
        for i, line in enumerate(lines):
            if line.lower() == label.lower():
                for j in range(i + 1, min(i + 4, len(lines))):
                    if lines[j]:
                        return lines[j]
        return "N/A"

    search_metrics = {
        "impressions":  _next_val_after("Total impressions"),
        "clicks":       _next_val_after("Total clicks"),
        "ctr":          _next_val_after("Average CTR"),
        "avg_position": _next_val_after("Average position"),
    }

    # 6. Screenshot: metric cards + chart section
    try:
        gsc_page.mouse.move(0, 0)
        gsc_page.wait_for_timeout(500)
        path = out_dir / "search_console.png"

        gsc_page.evaluate("window.scrollTo(0, 0)")
        gsc_page.wait_for_timeout(500)

        clip = gsc_page.evaluate("""() => {
            // Find any leaf or near-leaf element whose trimmed text is 'Total clicks'
            const all = Array.from(document.querySelectorAll('*'));
            const label = all.find(el =>
                el.textContent.trim() === 'Total clicks' &&
                el.getBoundingClientRect().width > 0
            );
            if (!label) return null;
            const vw = window.innerWidth;
            let el = label;
            for (let i = 0; i < 20; i++) {
                el = el.parentElement;
                if (!el) break;
                const r = el.getBoundingClientRect();
                if (r.width >= vw * 0.6 && r.height >= 400) {
                    return { x: r.x, y: r.y, width: r.width, height: r.height };
                }
            }
            return null;
        }""")

        if clip and clip["height"] > 50:
            gsc_page.screenshot(path=str(path), clip=clip)
        else:
            # Fallback: screenshot just the top portion of the viewport
            gsc_page.screenshot(path=str(path), clip={"x": 0, "y": 150, "width": 1400, "height": 550})

        screenshots["search_screenshot"] = path
    except Exception:
        pass

    gsc_page.close()
    return search_metrics, screenshots


# ---------------------------------------------------------------------------
# GA4 capture — 2026 pipeline only
# ---------------------------------------------------------------------------

def capture_2026(
    report_name: str,
    start_date: str,
    end_date: str,
    _stage_callback=None,
) -> tuple[dict[str, Path], dict, dict, dict]:
    """Navigate GA4, capture all screenshots and metrics needed for the 2026 pipeline.

    Returns: (screenshots, home_metrics, snapshot_metrics, page_views)
    """
    def _stage(msg: str):
        if _stage_callback:
            _stage_callback(msg)

    screenshots: dict[str, Path] = {}
    out_dir = SCREENSHOTS_DIR / report_name
    out_dir.mkdir(parents=True, exist_ok=True)

    home_metrics: dict = {}
    snapshot_metrics: dict = {}
    page_views: dict = {}
    pages_data: list[dict] = []  # rich per-page rows: {title, views, active_users, views_per_user, avg_engagement_time}
    site_total_views: int = 0   # total views across ALL pages (from GA4 Total row)
    countries_data: list[dict] = []  # rich per-country rows: {country, users, engagement_rate, engaged_sessions_per_user}
    search_metrics: dict = {}   # GSC metrics: impressions, clicks, ctr, avg_position

    with sync_playwright() as p:
        context = _launch_persistent_context(p, headless=False)
        try:
            page = context.new_page()
            page.bring_to_front()

            # --- Switch to correct GA4 property ---
            _stage("Switching GA4 property...")
            page = _switch_ga4_property_via_search(page, report_name)

            # --- Home page: set date range + scrape metrics ---
            _stage("Capturing GA4 home metrics...")
            page = _goto_ga4_section(page, report_name, "/home")
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            except Exception:
                pass
            _set_date_range(page, start_date, end_date)
            home_metrics = _scrape_home_metrics(page)

            # --- Home line chart screenshot (Slide 3) ---
            try:
                chart_el = page.locator("ga-card.card_0 ga-tab-chart")
                chart_el.wait_for(state="visible", timeout=10000)
                page.mouse.move(0, 0)
                page.mouse.click(0, 0)
                page.wait_for_timeout(800)
                path = out_dir / "home_chart.png"
                chart_el.screenshot(path=str(path))
                screenshots["home_chart"] = path
            except Exception:
                pass

            # --- Navigate to Reports Snapshot via the confirmed button ---
            _stage("Capturing GA4 snapshot metrics...")
            _ensure_expected_ga4_property(page, report_name)
            page.locator("span.view-link-text", has_text="View reports snapshot").click()
            page.wait_for_timeout(4000)
            _ensure_expected_ga4_property(page, report_name)

            # Set date range on snapshot page
            _set_date_range(page, start_date, end_date)
            page.wait_for_timeout(3000)

            snapshot_metrics = _scrape_snapshot_metrics(page)

            # --- Snapshot KPI card screenshot (Slide 1) ---
            try:
                card_el = page.locator("ga-card[data-guidedhelpid='summary']").first
                card_el.wait_for(state="visible", timeout=10000)
                page.mouse.move(0, 0)
                page.mouse.click(0, 0)
                page.wait_for_timeout(800)
                path = out_dir / "snapshot_card.png"
                card_el.screenshot(path=str(path))
                screenshots["snapshot_card"] = path
            except Exception:
                pass

            # --- Countries table: screenshot + scrape rich data (Slide 4) ---
            _stage("Capturing countries data...")
            try:
                page.get_by_text("View countries").click()
                page.wait_for_timeout(4000)
                _ensure_expected_ga4_property(page, report_name)
                row_num_col = page.locator("th.cdk-column-__row_index__").first
                end_col = page.locator("th.cdk-column-DEFAULT-engagedSessionsPerUser").first
                row_num_col.wait_for(state="visible", timeout=10000)
                page.keyboard.press("End")
                page.wait_for_timeout(1000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1000)
                start_box = row_num_col.bounding_box()
                end_box = end_col.bounding_box()
                table_box = page.locator("table.adv-table").bounding_box()
                clip = {
                    "x": start_box["x"],
                    "y": table_box["y"],
                    "width": (end_box["x"] + end_box["width"]) - start_box["x"],
                    "height": table_box["height"],
                }
                path = out_dir / "countries_table.png"
                page.screenshot(path=str(path), clip=clip, full_page=True)
                screenshots["countries_table"] = path

                # Scrape rich country data from table rows
                # GA4 table inner_text rows: "N\tCountry\tActive Users\tNew Users\tEngaged Sessions\tEngagement Rate\tEng.Sessions/User\tAvg Eng Time"
                import re as _re
                body = page.locator("body").inner_text()
                # Rows format (leading tab + index):
                # "\t1\tZimbabwe\t21,735 (80.66%)\t19,675 (79.45%)\t15,135 (80.46%)\t47.98%\t0.70\t..."
                for line in body.splitlines():
                    m = _re.match(
                        r"^\t\d+\t(.+?)\t([\d,]+)\s*\([^)]+\)\t([\d,]+)\s*\([^)]+\)\t([\d,]+)\s*\([^)]+\)\t([\d.]+%)\t([\d.]+)",
                        line,
                    )
                    if m:
                        countries_data.append({
                            "country": m.group(1).strip(),
                            "users": int(m.group(2).replace(",", "")),
                            "new_users": int(m.group(3).replace(",", "")),
                            "engaged_sessions": int(m.group(4).replace(",", "")),
                            "engagement_rate": m.group(5),
                            "engaged_sessions_per_user": m.group(6),
                        })

                page.go_back()
                page.wait_for_timeout(3000)
                _ensure_expected_ga4_property(page, report_name)
            except Exception:
                pass

            # --- Pages and screens: screenshot + scrape page views (Slide 5) ---
            _stage("Capturing pages & screens data...")
            try:
                page.get_by_role("button", name="View pages and screens", exact=True).click()
                page.wait_for_timeout(4000)
                _ensure_expected_ga4_property(page, report_name)
                row_num_col = page.locator("th.cdk-column-__row_index__").first
                end_col = page.locator("th.cdk-column-DEFAULT-userEngagementDurationPerUser").first
                row_num_col.wait_for(state="visible", timeout=10000)
                page.keyboard.press("End")
                page.wait_for_timeout(1000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1000)
                start_box = row_num_col.bounding_box()
                end_box = end_col.bounding_box()
                table_box = page.locator("table.adv-table").bounding_box()
                clip = {
                    "x": start_box["x"],
                    "y": table_box["y"],
                    "width": (end_box["x"] + end_box["width"]) - start_box["x"],
                    "height": table_box["height"],
                }
                path = out_dir / "pages_table.png"
                page.screenshot(path=str(path), clip=clip, full_page=True)
                screenshots["pages_table"] = path

                body = page.locator("body").inner_text()
                import re as _re
                # Scrape total views from the "Total" summary row first:
                # "\tTotal\t58,165\n100% of total\t..."
                total_m = _re.search(r"\tTotal\t([\d,]+)\n", body)
                if total_m:
                    site_total_views = int(total_m.group(1).replace(",", ""))
                # Row format: "\t1\tPage Title\t9,053 (15.56%)\t5,913 (21.94%)\t1.53\t32s\t..."
                for line in body.splitlines():
                    m = _re.match(
                        r"^\t\d+\t(.+?)\t([\d,]+)\s*\([^)]+\)\t([\d,]+)\s*\([^)]+\)\t([\d.]+)\t(\S+)",
                        line,
                    )
                    if m and len(pages_data) < 10:
                        title = m.group(1).strip()
                        pages_data.append({
                            "title": title,
                            "views": int(m.group(2).replace(",", "")),
                            "active_users": int(m.group(3).replace(",", "")),
                            "views_per_user": m.group(4),
                            "avg_engagement_time": m.group(5),
                        })
                        # Keep simple page_views dict for backward compat
                        if len(page_views) < 4:
                            page_views[title] = int(m.group(2).replace(",", ""))
            except Exception:
                pass

            # --- Google Search Console: scrape metrics + screenshot (Slide 6) ---
            if report_name not in SEVEN_SLIDE_REPORTS and report_name in GSC_URLS:
                _stage("Capturing Google Search Console data...")
                try:
                    search_metrics, gsc_screenshots = _capture_gsc(
                        context, report_name, start_date, end_date, out_dir
                    )
                    screenshots.update(gsc_screenshots)
                except Exception as e:
                    logger.warning("[2026] GSC capture failed for %s: %s", report_name, e)

        finally:
            try:
                context.close()
            except Exception:
                pass

    return screenshots, home_metrics, snapshot_metrics, page_views, pages_data, site_total_views, countries_data, search_metrics


# ---------------------------------------------------------------------------
# PPTX builder helpers
# ---------------------------------------------------------------------------

def _performance_month(date_range: str) -> str:
    """Extract 'Month,YYYY' from date_range e.g. '1 February 2026 - 28 February 2026' -> 'February,2026'"""
    match = re.search(r"[A-Za-z]+ \d{4}", date_range)
    return match.group(0).replace(" ", ",") if match else ""


def _build_slide1(slide, performance_month: str, screenshots: dict) -> None:
    """Replace date text and KPI card screenshot on Slide 1."""
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            if re.match(r"^[A-Za-z]+,?\s*\d{4}$", para.text.strip()):
                _fill_text_run(para, performance_month)

    if "snapshot_card" in screenshots:
        _replace_image_in_slide(slide, screenshots["snapshot_card"], shape_name="Picture 9")


def _build_slide2(slide, home_metrics: dict, snapshot_metrics: dict, report_name: str, search_metrics: dict | None = None) -> None:
    """Replace KPI stat boxes and narrative on Slide 2 (Executive Summary)."""
    exec_texts = _exec_summary_texts(report_name, home_metrics, snapshot_metrics)
    ctr = (search_metrics or {}).get("ctr", "N/A")
    impressions = (search_metrics or {}).get("impressions", "N/A")
    avg_position = (search_metrics or {}).get("avg_position", "N/A")

    raw_para1 = (
        f"From a search visibility perspective, the website recorded {impressions} impressions "
        f"with a {ctr} click-through rate and an average search position of {avg_position}, "
        f"reflecting strong organic discoverability and continued relevance in search results."
    )
    para1_text = _gemini_para(raw_para1) if ctr != "N/A" else ""

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            # KPI boxes — replace value only, keep font
            if re.match(r"^\d+K?$", text):
                _fill_text_run(para, exec_texts["active_users_short"])
            elif text.endswith("%") and "." not in text and len(text) <= 5:
                _fill_text_run(para, exec_texts["new_pct"])
            # Subtitle line
            elif text.lower().startswith("performance overview:"):
                _fill_text_run(para, exec_texts["subtitle"])
            # Para 0 — attracting / first-time users
            elif any(kw in text.lower() for kw in ("first-time users", "under review", "attracting")):
                _write_para_with_highlights(para, exec_texts["para0"])
            # Para 1 — CTR / search visibility (from GSC)
            elif para1_text and any(kw in text.lower() for kw in ("click-through", "search visibility", "organic", "ctr", "impressions")):
                _write_para_with_highlights(para, para1_text)
            # Para 2 — closing insight
            elif any(kw in text.lower() for kw in ("combination of high", "discoverability", "brand loyalty")):
                _write_para_with_highlights(para, exec_texts["para2"])


def _build_slide3(slide, home_metrics: dict, snapshot_metrics: dict, report_name: str, screenshots: dict) -> None:
    """Replace stat values, subtitle, narratives, and chart on Slide 3 (Site Overview)."""
    active_users = home_metrics.get("Active users", "N/A")
    new_users = home_metrics.get("New users", "N/A")
    engagement = home_metrics.get("Average engagement time per active user", "N/A")

    def _parse_num(val: str) -> int:
        s = str(val).strip().replace(",", "")
        if s.upper().endswith("K"):
            return int(float(s[:-1]) * 1000)
        return int(float(s))

    try:
        au = _parse_num(active_users)
        nu = _parse_num(new_users)
        new_pct = f"{round(nu / au * 100, 1)}%"
    except (ValueError, TypeError, ZeroDivisionError):
        new_pct = "N/A"

    subtitle, para0, para2, para4 = _site_overview_paras(report_name, home_metrics, snapshot_metrics)

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()

            # Subtitle — Gemini paraphrase, same tokens
            if "user engagement metrics" in text.lower():
                _fill_text_run(para, subtitle)

            # object 6 — Total Active Users value
            elif shape.name == "object 6" and re.match(r"^[\d,]+$", text):
                _fill_text_run(para, str(active_users))

            # object 10 — New Users value + (%) label
            elif shape.name == "object 10" and re.match(r"^[\d,]+$", text):
                _fill_text_run(para, str(new_users))
            elif shape.name == "object 10" and re.match(r"^\([\d.]+%\)$", text):
                _fill_text_run(para, f"({new_pct})")

            # object 14 — Avg Engagement Time value
            elif shape.name == "object 14" and re.match(r"^[\d]+\w+$", text):
                _fill_text_run(para, str(engagement))

            # Narrative paragraphs — Gemini paraphrase with highlights
            elif any(kw in text.lower() for kw in ("reflects solid", "active users recorded", "encouraging performance")):
                _write_para_with_highlights(para, para0)
            elif any(kw in text.lower() for kw in ("consistently high proportion", "search visibility", "first-time audiences")):
                _write_para_with_highlights(para, para2)
            elif any(kw in text.lower() for kw in ("average engagement time", "engagement benchmarks", "exiting immediately")):
                _write_para_with_highlights(para, para4)

    # Reuse the snapshot_card screenshot from slide 1 at Picture 18's original dimensions
    if "snapshot_card" in screenshots:
        _replace_image_in_slide(slide, screenshots["snapshot_card"], shape_name="Picture 18")


def _build_slide4(slide, countries_data: list[dict], screenshots: dict) -> None:
    """Replace country table screenshot and narrative on Slide 4 (Geographic Performance)."""
    if countries_data:
        sorted_rows = sorted(countries_data, key=lambda r: r["users"], reverse=True)
        top = sorted_rows[0]

        # Subtitle in object 2, para[1]
        raw_subtitle = f"{top['country']} Dominance with International Opportunity"
        subtitle = _gemini_para(raw_subtitle)

        # 4 narrative paragraphs from real data
        para0, para1, para2, para3 = _geo_paras(countries_data)
        narratives = [para0, para1, para2, para3]

        # Country names to bold in narratives
        country_names = {r["country"] for r in countries_data}

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue

            # Subtitle: object 2, para index 1
            if shape.name == "object 2":
                paras = shape.text_frame.paragraphs
                if len(paras) > 1:
                    _fill_text_run(paras[1], subtitle)

            # Narratives: object 6, non-empty paragraphs (even-indexed, odd ones are spacers)
            elif shape.name == "object 6":
                content_paras = [p for p in shape.text_frame.paragraphs if p.text.strip()]
                for i, para in enumerate(content_paras):
                    if i < len(narratives):
                        _write_para_with_highlights(para, narratives[i], bold_words=country_names)

    # Use the captured countries table screenshot from GA4
    if "countries_table" in screenshots:
        _replace_image_in_slide(slide, screenshots["countries_table"], shape_name="Picture 10")


def _build_slide5(slide, pages_data: list[dict], screenshots: dict, site_total_views: int = 0) -> None:
    """Replace pages table screenshot and narratives on Slide 5 (Page Performance)."""
    if pages_data:
        heading, para1, para2, para3 = _page_perf_paras(pages_data, site_total_views)
        # Collect clean page labels for bolding (classification already ran inside _page_perf_paras)
        page_names = {p.get("_label", p["title"].split(" - ")[0].strip()) for p in pages_data}

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue

            # object 3 — short heading line
            if shape.name == "object 3":
                content_paras = [p for p in shape.text_frame.paragraphs if p.text.strip()]
                if content_paras:
                    _fill_text_run(content_paras[0], heading)

            # object 7 — "Overall Insight:" label + 3 narrative paragraphs
            elif shape.name == "object 7":
                content_paras = [p for p in shape.text_frame.paragraphs if p.text.strip()]
                narratives = [para1, para2, para3]
                # para[0] is the "Overall Insight:" label — leave it, fill paras[1:]
                for i, para in enumerate(content_paras[1:]):
                    if i < len(narratives):
                        _write_para_with_highlights(para, narratives[i], bold_words=page_names)

    if "pages_table" in screenshots:
        _replace_image_in_slide(slide, screenshots["pages_table"], shape_name="Picture 13")


def _search_perf_paras(search_metrics: dict) -> tuple[str, str, str, str]:
    """Slide 6 — subtitle + 4 narrative paragraphs from real GSC data."""
    impressions = search_metrics.get("impressions", "N/A")
    clicks      = search_metrics.get("clicks", "N/A")
    ctr         = search_metrics.get("ctr", "N/A")
    position    = search_metrics.get("avg_position", "N/A")

    # Subtitle — dynamic based on CTR
    def _pct_val(s: str) -> float:
        try:
            return float(str(s).strip().rstrip("%"))
        except ValueError:
            return 0.0

    ctr_val = _pct_val(ctr)
    if ctr_val >= 5:
        subtitle_raw = f"Strong Search Visibility with {ctr} Click-Through Rate"
    elif ctr_val >= 3:
        subtitle_raw = f"Solid Foundation with Room for Visibility Improvement"
    else:
        subtitle_raw = f"Search Presence Established — CTR Optimisation Opportunity"

    raw_para0 = (
        f"With {impressions} impressions, the brand maintains substantial presence in search results, "
        f"indicating strong keyword coverage and consistent discoverability. "
        f"From this visibility, the site generated {clicks} clicks, "
        f"reflecting meaningful traffic acquisition directly from search engines."
    )

    raw_para1 = (
        f"The {ctr} click-through rate suggests "
        f"{'strong' if ctr_val >= 5 else 'moderate'} conversion of impressions into clicks. "
        f"{'This reflects compelling meta titles and descriptions that resonate with searcher intent.' if ctr_val >= 5 else 'There is room to optimise meta titles and descriptions to further improve click appeal and capture a larger share of search demand.'}"
    )

    raw_para2 = (
        f"An average position of {position} is "
        f"{'particularly encouraging, placing the website on the first page of search results for many queries. This reinforces strong SEO foundations and competitive ranking strength.' if _pct_val(position) <= 10 else 'an indication that the website is gaining search traction. Focused content and technical SEO efforts can improve ranking further toward the first page.'}"
    )

    raw_para3 = (
        f"Trend-wise, performance appears relatively stable throughout the period, "
        f"with normal fluctuations but no major declines, "
        f"indicating consistent search demand and sustained visibility."
    )

    return (
        _gemini_para(subtitle_raw),
        _gemini_para(raw_para0),
        _gemini_para(raw_para1),
        _gemini_para(raw_para2),
        # para3 kept short — same token count
        _gemini_para(raw_para3),
    )


def _build_slide6(slide, search_metrics: dict, screenshots: dict) -> None:
    """Replace search performance narrative on Slide 6 (8-slide variants only)."""
    if not search_metrics or all(v == "N/A" for v in search_metrics.values()):
        return

    subtitle, para0, para1, para2, para3 = _search_perf_paras(search_metrics)

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue

        # object 4 — subtitle
        if shape.name == "object 4":
            content_paras = [p for p in shape.text_frame.paragraphs if p.text.strip()]
            if content_paras:
                _fill_text_run(content_paras[0], subtitle)

        # object 5 — 4 narrative paragraphs (paras 0, 2, 3, 5 — odds are spacers)
        elif shape.name == "object 5":
            content_paras = [p for p in shape.text_frame.paragraphs if p.text.strip()]
            for i, para in enumerate(content_paras):
                narr = [para0, para1, para2, para3][i] if i < 4 else None
                if narr:
                    _write_para_with_highlights(para, narr)

    if "search_screenshot" in screenshots:
        _replace_image_in_slide(slide, screenshots["search_screenshot"], shape_name="Picture 10")


def _generate_recommendations_2026(
    report_name: str,
    home_metrics: dict,
    snapshot_metrics: dict,
    pages_data: list[dict],
    countries_data: list[dict],
    date_range: str,
) -> list[dict]:
    """Use Gemini to generate 3 structured recommendations, each with a title + 3 bullet points."""
    load_runtime_environment()
    brand = report_name.replace("_", " ").title()

    top_pages = ", ".join(
        f"{p.get('_label', p['title'].split(' - ')[0])} ({p['views']:,} views, {p['views_per_user']} views/user)"
        for p in pages_data[:5]
    ) if pages_data else "N/A"

    top_countries = ", ".join(
        f"{r['country']} ({r['users']:,} users, {r['engagement_rate']} engagement)"
        for r in sorted(countries_data, key=lambda x: x["users"], reverse=True)[:3]
    ) if countries_data else "N/A"

    channels = snapshot_metrics.get("channels", {})
    channels_str = ", ".join(f"{k}: {v}" for k, v in list(channels.items())[:5]) if channels else "N/A"

    prompt = (
        f"You are a digital analytics expert writing a monthly website performance report for {brand}.\n\n"
        f"Period: {date_range}\n"
        f"Active users: {home_metrics.get('Active users', 'N/A')}\n"
        f"New users: {home_metrics.get('New users', 'N/A')}\n"
        f"Avg engagement time: {home_metrics.get('Average engagement time per active user', 'N/A')}\n"
        f"Top acquisition channels: {channels_str}\n"
        f"Top pages: {top_pages}\n"
        f"Top countries: {top_countries}\n\n"
        "Write exactly 3 actionable recommendations to improve website performance.\n"
        "For each recommendation output:\n"
        "TITLE: <short action-oriented title (4-6 words)>\n"
        "- <bullet point 1>\n"
        "- <bullet point 2>\n"
        "- <bullet point 3>\n"
        "---\n"
        "Use formal business English. No markdown bold, no em dashes. Be specific to the data above."
    )

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = resp.text.strip()

    recs = []
    for block in text.split("---"):
        block = block.strip()
        if not block:
            continue
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        title = ""
        bullets = []
        for line in lines:
            if line.upper().startswith("TITLE:"):
                title = line[6:].strip()
            elif line.startswith("-"):
                bullets.append(line[1:].strip())
        if title and bullets:
            recs.append({"title": title, "bullets": bullets[:3]})
        if len(recs) == 3:
            break

    return recs


def _build_recommendations_slide(
    slide,
    report_name: str,
    home_metrics: dict,
    snapshot_metrics: dict,
    pages_data: list[dict],
    countries_data: list[dict],
    date_range: str,
    report_date: str,
) -> None:
    """Replace recommendations on slide 7 (object 7) with Gemini-generated content."""
    recs = _generate_recommendations_2026(
        report_name, home_metrics, snapshot_metrics, pages_data, countries_data, date_range
    )
    if not recs:
        return

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue

        # object 3 — subtitle: "Three Key Initiatives to Enhance Performance"
        if shape.name == "object 3":
            content_paras = [p for p in shape.text_frame.paragraphs if p.text.strip()]
            if content_paras:
                _fill_text_run(content_paras[0], "Three Key Initiatives to Enhance Performance")

        # object 7 — main content: replace paragraphs starting with "1.", "2.", "3."
        # Each rec title replaces the numbered heading; bullets replace the sub-paragraphs
        elif shape.name == "object 7":
            all_paras = shape.text_frame.paragraphs
            rec_idx = 0  # which recommendation we're filling
            bullet_idx = 0  # which bullet within that rec

            for para in all_paras:
                full_text = "".join(r.text for r in para.runs).strip()
                if not full_text:
                    continue

                # Numbered heading line — start a new recommendation
                if re.match(r"^\d+\.", full_text) and rec_idx < len(recs):
                    _fill_text_run(para, f"{rec_idx + 1}. {recs[rec_idx]['title']}")
                    bullet_idx = 0
                    continue

                # Bullet / sub-paragraph under the current recommendation
                if rec_idx < len(recs) and bullet_idx < len(recs[rec_idx]["bullets"]):
                    _fill_text_run(para, recs[rec_idx]["bullets"][bullet_idx])
                    bullet_idx += 1
                    # Move to next rec when bullets exhausted
                    if bullet_idx >= len(recs[rec_idx]["bullets"]):
                        rec_idx += 1
                        bullet_idx = 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report_2026(
    report_name: str,
    date_range: str,
    report_date: str,
    start_date: str,
    end_date: str,
    _stage_callback=None,
) -> Path:
    """Full 2026 pipeline: capture GA4 → fill PPTX → save."""
    def _stage(msg: str):
        if _stage_callback:
            _stage_callback(msg)
        logger.info("[2026] Stage: %s", msg)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Capture screenshots + metrics
    screenshots, home_metrics, snapshot_metrics, page_views, pages_data, site_total_views, countries_data, search_metrics = capture_2026(
        report_name, start_date, end_date, _stage_callback=_stage_callback
    )

    # Step 2: Load template
    template_path = TEMPLATES_DIR / TEMPLATES_2026[report_name]
    prs = Presentation(str(template_path))
    slide_count = len(prs.slides)
    is_7_slide = report_name in SEVEN_SLIDE_REPORTS

    perf_month = _performance_month(date_range)

    # Step 3: Build each slide
    _stage("Building slides...")
    logger.info("[2026] Building slides for %s (%d slides)", report_name, slide_count)

    _build_slide1(prs.slides[0], perf_month, screenshots)
    _build_slide2(prs.slides[1], home_metrics, snapshot_metrics, report_name, search_metrics)
    _build_slide3(prs.slides[2], home_metrics, snapshot_metrics, report_name, screenshots)
    _build_slide4(prs.slides[3], countries_data, screenshots)
    _build_slide5(prs.slides[4], pages_data, screenshots, site_total_views)

    if not is_7_slide and slide_count >= 8:
        _build_slide6(prs.slides[5], search_metrics, screenshots)

    rec_slide_idx = slide_count - 2
    _build_recommendations_slide(
        prs.slides[rec_slide_idx],
        report_name, home_metrics, snapshot_metrics,
        pages_data, countries_data, date_range, report_date,
    )

    # Step 4: Save
    safe_name = report_name.replace("_", "-")
    output_path = OUTPUT_DIR / f"{safe_name}-{report_date.replace(' ', '-')}.pptx"
    prs.save(str(output_path))
    logger.info("[2026] Saved report to %s", output_path)
    return output_path
