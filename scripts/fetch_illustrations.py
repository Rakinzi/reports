"""
One-off developer script to fetch unDraw SVG illustrations from undraw.co.
Saves raw SVGs to illustrations_tmp/ for review before converting to Svelte components.

Usage:
    cd /Users/rakinzisilver/Documents/GitHub/reports
    python scripts/fetch_illustrations.py
"""

import re
from pathlib import Path
from playwright.sync_api import sync_playwright

SEARCHES = [
    ("no data", "no-data"),
    ("setup", "setup"),
    ("authentication", "auth"),
    ("browser stats", "session"),
    ("online document", "document"),
]

OUT_DIR = Path(__file__).parent.parent / "illustrations_tmp"
OUT_DIR.mkdir(exist_ok=True)


def fetch_illustration(page, search_term: str, filename: str) -> bool:
    print(f"\n[{filename}] Searching for: '{search_term}'")

    # Clear search and type new term
    search_box = page.locator('input[type="search"], input[placeholder*="search" i], input[placeholder*="Search" i]').first
    search_box.click()
    search_box.select_text()
    search_box.fill(search_term)
    page.wait_for_timeout(2000)

    # Click the first illustration card
    cards = page.locator('[class*="card"], [class*="illustration"], [class*="item"]').all()
    if not cards:
        print(f"  [!] No cards found for '{search_term}'")
        return False

    cards[0].click()
    page.wait_for_timeout(2000)

    # Try to grab SVG from the modal/overlay
    svg_html = None
    for selector in [
        '.modal svg',
        '[class*="modal"] svg',
        '[class*="dialog"] svg',
        '[class*="overlay"] svg',
        '[class*="detail"] svg',
        'dialog svg',
    ]:
        try:
            el = page.locator(selector).first
            if el.count() > 0:
                svg_html = el.evaluate("el => el.outerHTML")
                if svg_html and len(svg_html) > 100:
                    break
        except Exception:
            continue

    if not svg_html:
        # Fallback: grab largest SVG on the page
        try:
            svgs = page.locator('svg').all()
            best = max(svgs, key=lambda s: len(s.evaluate("el => el.outerHTML")), default=None)
            if best:
                svg_html = best.evaluate("el => el.outerHTML")
        except Exception:
            pass

    if not svg_html or len(svg_html) < 100:
        print(f"  [!] Could not extract SVG for '{search_term}'")
        # Close any open modal
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return False

    out_path = OUT_DIR / f"{filename}.svg"
    out_path.write_text(svg_html, encoding="utf-8")
    print(f"  [✓] Saved {len(svg_html)} chars → {out_path}")

    # Close modal
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    return True


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        print("Navigating to undraw.co...")
        page.goto("https://undraw.co/illustrations", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        results = {}
        for search_term, filename in SEARCHES:
            results[filename] = fetch_illustration(page, search_term, filename)

        browser.close()

    print("\n\n=== Results ===")
    for filename, ok in results.items():
        status = "✓" if ok else "✗ FAILED"
        print(f"  {status}  {filename}.svg")

    print(f"\nSVGs saved to: {OUT_DIR}")
    print("\nNext steps:")
    print("  1. Review SVGs in illustrations_tmp/")
    print("  2. For each SVG, replace the accent color hex with 'currentColor'")
    print("  3. Run: python scripts/make_svelte_illustrations.py")


if __name__ == "__main__":
    main()
