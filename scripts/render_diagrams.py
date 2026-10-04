"""Render docs/diagrams/*.mmd to SVG and PNG with Mermaid in headless Chromium (Playwright, requirements-dev).

Usage: .venv/bin/python scripts/render_diagrams.py [name ...]
Mermaid is loaded from a CDN here because this is a documentation tool, not part of the app (the app itself never
uses a CDN). PNGs are rendered at 2x for the report.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

DIR = pathlib.Path(__file__).resolve().parent.parent / "docs" / "diagrams"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
PAGE = f"""<!doctype html><html><head><meta charset="utf-8"><script src="{MERMAID}"></script>
<style>body{{margin:0;background:#fff;font-family:Arial,Helvetica,sans-serif}}#out{{display:inline-block;padding:16px}}</style>
</head><body><div id="out"></div><script>
mermaid.initialize({{startOnLoad:false, theme:"neutral", securityLevel:"strict",
  fontFamily:"Arial, Helvetica, sans-serif", flowchart:{{htmlLabels:true, curve:"basis"}},
  sequence:{{mirrorActors:false}}}});
</script></body></html>"""


def main(names):
    sources = sorted(DIR.glob("*.mmd"))
    if names:
        sources = [s for s in sources if s.stem in names or s.name in names]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2, viewport={"width": 1600, "height": 1200})
        page.set_content(PAGE, wait_until="networkidle")
        for src in sources:
            svg = page.evaluate("""async ([id, code]) => {
                const {svg} = await mermaid.render(id, code);
                const out = document.getElementById('out');
                out.innerHTML = svg;
                // Mermaid makes the SVG responsive (width 100%, max-width natural); draw it at its natural size.
                const el = out.querySelector('svg');
                el.style.width = el.style.maxWidth; el.style.maxWidth = 'none';
                return svg; }""", [f"d_{src.stem}", src.read_text()])
            (DIR / f"{src.stem}.svg").write_text(svg)
            page.locator("#out").screenshot(path=str(DIR / f"{src.stem}.png"))
            print("rendered", src.stem)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
