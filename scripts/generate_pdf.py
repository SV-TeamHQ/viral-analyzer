import argparse
import os
from pathlib import Path


def _get_sync_playwright():
    """Return playwright.sync_api.sync_playwright, or None if Playwright isn't installed.

    Kept separate so it's trivial to monkeypatch in tests and so the module imports
    cleanly without Playwright present.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


def render_pdf(html_path: str, pdf_path: str) -> str | None:
    """Render an HTML file to PDF via headless Chromium.

    Returns the pdf path on success, or None if Playwright/Chromium isn't available
    (non-fatal — callers should still have the HTML).
    """
    sync_playwright = _get_sync_playwright()
    if sync_playwright is None:
        print(
            "  Playwright not installed — skipping PDF. "
            "Install: pip install playwright && playwright install chromium"
        )
        return None

    os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
    url = Path(html_path).resolve().as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="load")
        page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
        )
        browser.close()

    return pdf_path if os.path.exists(pdf_path) else None


def main(html_path: str, pdf_path: str | None = None) -> None:
    if pdf_path is None:
        pdf_path = str(Path(html_path).with_suffix(".pdf"))
    result = render_pdf(html_path, pdf_path)
    if result:
        print(f"Wrote PDF -> {result}")
    else:
        print("No PDF generated (see message above).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render an HTML report to PDF via Chromium")
    parser.add_argument("--html", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    main(args.html, args.output)
