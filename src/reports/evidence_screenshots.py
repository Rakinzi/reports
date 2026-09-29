"""Live browser captures for SEO and SiteCheck evidence slides."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlsplit

from PIL import Image


def capture_google_results(page, query: str, output: Path, *, web_only: bool = False) -> Path:
    search_url = f"https://www.google.com/search?q={quote(query)}"
    if web_only:
        search_url += "&udm=14"
    for attempt in range(3):
        try:
            page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            break
        except Exception as exc:
            if "ERR_NETWORK_CHANGED" not in str(exc) or attempt == 2:
                raise
            # Transient network changes can interrupt a single navigation.
            # Reset the page and retry the same query before treating the
            # required search evidence as unavailable.
            page.wait_for_timeout(1000 * (attempt + 1))
            try:
                page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
            except Exception:
                pass
    if "/sorry/" in page.url:
        raise RuntimeError("Google requested a verification challenge")
    page.locator("#search").wait_for(state="visible", timeout=20000)
    # Google can show a visible search container while its result cards are
    # still skeleton placeholders. Require an actual linked result before
    # taking the evidence screenshot.
    page.locator("#search a:has(h3)").first.wait_for(state="visible", timeout=30000)
    page.wait_for_timeout(1200)
    if not web_only:
        for label in ("Your business on Google", "Thinking a little longer"):
            loading_panel = page.get_by_text(label, exact=True).first
            if loading_panel.count() and loading_panel.is_visible():
                return capture_google_results(page, query, output, web_only=True)
        places = page.get_by_text("Places", exact=True).first
        if places.count():
            box = places.bounding_box()
            if box and box["y"] < 760:
                return capture_google_results(page, query, output, web_only=True)
    viewport = page.viewport_size or {"width": 1920, "height": 1080}
    page.screenshot(
        path=str(output),
        clip={
            "x": 100,
            "y": 0,
            "width": min(1120, viewport["width"] - 100),
            "height": min(760, viewport["height"]),
        },
        timeout=30000,
        animations="disabled",
    )
    links = page.locator("#search a:has(h3)").evaluate_all(
        """elements => elements.map(a => ({
            title: a.querySelector('h3')?.innerText?.trim() || '',
            url: a.href || ''
        }))"""
    )
    results = []
    seen = set()
    for link in links:
        title = link.get("title", "").strip()
        address = urljoin(page.url, link.get("url", ""))
        parsed = urlsplit(address)
        if parsed.hostname and parsed.hostname.endswith("google.com") and parsed.path == "/url":
            address = parse_qs(parsed.query).get("q", [address])[0]
            parsed = urlsplit(address)
        domain = (parsed.hostname or "").removeprefix("www.")
        if not title or not domain or domain.endswith("google.com") or address in seen:
            continue
        seen.add(address)
        results.append({"title": title, "url": address, "domain": domain})
        if len(results) == 5:
            break
    if not results:
        raise RuntimeError("Google returned no identifiable search results")
    output.with_suffix(".json").write_text(
        json.dumps({"query": query, "results": results}, indent=2), encoding="utf-8"
    )
    return output


def capture_sitecheck(page, site_url: str, output: Path) -> Path:
    host = urlsplit(site_url).netloc
    if not host:
        raise ValueError(f"Invalid site URL: {site_url}")
    page.goto(
        f"https://sitecheck.sucuri.net/results/https/{host}",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.get_by_role("heading", name=re.compile(re.escape(host), re.I)).first.wait_for(
        state="visible", timeout=30000
    )
    for button_name in ("Decline", "Close modal"):
        button = page.get_by_role("button", name=button_name)
        if button.count() and button.first.is_visible():
            try:
                button.first.click(timeout=2000)
            except Exception:
                pass
            break
    panel = page.locator("div.w-full.p-6.bg-white.rounded-2xl").filter(
        has_text=re.compile("Malware|Blacklist", re.I)
    ).first
    panel.wait_for(state="visible", timeout=30000)
    panel_text = panel.inner_text()
    panel.screenshot(path=str(output), timeout=30000, animations="disabled")
    with Image.open(output) as screenshot:
        screenshot.crop((0, 0, screenshot.width, min(420, screenshot.height))).save(output)
    output.with_suffix(".json").write_text(
        json.dumps({"panel_text": panel_text}, indent=2), encoding="utf-8"
    )
    return output
