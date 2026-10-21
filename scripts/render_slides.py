"""Render the m11-rdf slides to PDF.

Input:  site/slides/m11-elements-slides.html (hand-maintained source)
Output: site/ich-m11-elements-mapping-target.pdf (copied into docs/slides/ by build_site.py)

Needs Python Playwright with a Chromium browser and network access to Google
Fonts. Not part of the regular rebuild; run it after editing the slides.
Set PLAYWRIGHT_CHROMIUM to a browser executable to use one other than
Playwright's default (in the cloud workspace: the headless shell under
/opt/pw-browsers).
"""
import os

from playwright.sync_api import sync_playwright

from common import ROOT

SOURCE = ROOT / "site" / "slides" / "m11-elements-slides.html"
TARGET = ROOT / "site" / "ich-m11-elements-mapping-target.pdf"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM"))
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(SOURCE.as_uri(), wait_until="networkidle")
        page.wait_for_selector("body[data-ready='1']")
        loaded = page.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
        for family in ("Domine", "Nunito Sans"):
            if family not in loaded:
                raise RuntimeError(f"Font {family} did not load; the PDF would fall back to another face")
        pages = page.evaluate("document.querySelectorAll('section').length")
        page.pdf(path=str(TARGET), width="1920px", height="1080px", print_background=True, prefer_css_page_size=True)
        browser.close()
    print(f"OK: {pages} slides rendered to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
