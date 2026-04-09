"""Debug: open GSC, click More → Custom, dump modal HTML."""
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright
from urllib.parse import quote
from src.reports.generator import _launch_persistent_context

GSC_URL = "https://search.google.com/search-console/performance/search-analytics?resource_id=" + quote("https://www.econet.co.zw/", safe="")

with sync_playwright() as p:
    ctx = _launch_persistent_context(p, headless=False)
    page = ctx.new_page()
    page.goto(GSC_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("text=Total clicks", timeout=20000)
    page.wait_for_timeout(1000)

    # Click More time ranges
    page.get_by_role("button", name="More time ranges").click()
    page.wait_for_timeout(1000)

    # Click Custom (Filter tab)
    page.get_by_label("Filter", exact=True).get_by_text("Custom", exact=True).click()
    page.wait_for_timeout(1000)

    # Dump modal HTML
    out = Path("artifacts/screenshots/econet/gsc_modal.html")
    out.write_text(page.content())
    print(f"Dumped modal HTML to {out}")

    ctx.close()
