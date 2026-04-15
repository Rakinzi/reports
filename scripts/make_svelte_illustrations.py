"""
Converts raw SVG JSON files fetched from undraw.co into themed Svelte 5 components.

Usage:
    cd /Users/rakinzisilver/Documents/GitHub/reports
    python scripts/make_svelte_illustrations.py
"""

import json
import re
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend"
OUT_DIR = FRONTEND / "src/lib/illustrations"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def clean_svg(raw: str) -> str:
    """Strip unDraw metadata attrs, fixed dimensions, and add our class prop."""
    # Remove unDraw-specific attributes
    for attr in ['class="injected-svg"', 'role="img"', 'scrapped="true"']:
        raw = raw.replace(f' {attr}', '')
    raw = re.sub(r'\s+artist="[^"]*"', '', raw)
    raw = re.sub(r'\s+copyright="[^"]*"', '', raw)
    raw = re.sub(r'\s+source="[^"]*"', '', raw)
    # Remove fixed width/height — sizing done via CSS class
    raw = re.sub(r'\s+width="[^"]*"', '', raw)
    raw = re.sub(r'\s+height="[^"]*"', '', raw)
    # Add our class prop and aria-hidden to opening <svg tag
    raw = raw.replace('<svg ', '<svg class={className} aria-hidden="true" ', 1)
    return raw.strip()


def write_component(name: str, svg_html: str) -> None:
    cleaned = clean_svg(svg_html)
    content = (
        '<script lang="ts">\n'
        "\tlet { class: className = '' }: { class?: string } = $props();\n"
        '</script>\n\n'
        + cleaned
        + '\n'
    )
    out_path = OUT_DIR / f"{name}.svelte"
    out_path.write_text(content, encoding="utf-8")
    print(f"  ✓ {out_path.relative_to(FRONTEND)}")


def main():
    print("Creating Svelte illustration components...\n")

    # svgs-p1.txt: JSON object with noData, document, auth
    p1_path = FRONTEND / "svgs-p1.txt"
    if p1_path.exists():
        data = json.loads(json.loads(p1_path.read_text(encoding="utf-8")))
        if data.get("noData"):
            write_component("NoData", data["noData"])
        if data.get("document"):
            write_component("Document", data["document"])
        if data.get("auth"):
            write_component("Auth", data["auth"])
        p1_path.unlink()
        print(f"  🗑  Removed svgs-p1.txt")
    else:
        print("  ✗ svgs-p1.txt not found")

    # three-svgs.txt: JSON string of JSON object with settings, onboarding, analytics
    three_path = FRONTEND / "three-svgs.txt"
    if three_path.exists():
        raw = three_path.read_text(encoding="utf-8")
        data = json.loads(json.loads(raw))
        if data.get("settings"):
            write_component("Setup", data["settings"])
        if data.get("onboarding"):
            write_component("Session", data["onboarding"])
        if data.get("analytics"):
            write_component("Analytics", data["analytics"])
        three_path.unlink()
        print(f"  🗑  Removed three-svgs.txt")
    else:
        print("  ✗ three-svgs.txt not found")

    print(f"\nDone. Components in frontend/src/lib/illustrations/")
    print("\nComponents created:")
    for f in sorted(OUT_DIR.glob("*.svelte")):
        lines = f.read_text().count('\n')
        print(f"  {f.name} ({lines} lines)")


if __name__ == "__main__":
    main()
