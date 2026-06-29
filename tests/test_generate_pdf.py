import os
from unittest.mock import patch, MagicMock

from scripts.generate_pdf import render_pdf, _get_sync_playwright


class TestRenderPdf:
    def test_returns_none_when_playwright_missing(self, tmp_path):
        with patch("scripts.generate_pdf._get_sync_playwright", return_value=None):
            result = render_pdf(str(tmp_path / "in.html"), str(tmp_path / "out.pdf"))
        assert result is None

    def test_renders_pdf_via_chromium(self, tmp_path):
        html = tmp_path / "in.html"
        html.write_text("<html><body><h1>hi</h1></body></html>")

        page = MagicMock()

        def fake_pdf(**kwargs):
            with open(kwargs["path"], "wb") as f:
                f.write(b"%PDF-1.4")
        page.pdf.side_effect = fake_pdf

        browser = MagicMock()
        browser.new_page.return_value = page
        ctx_p = MagicMock()
        ctx_p.chromium.launch.return_value = browser
        cm = MagicMock()
        cm.__enter__.return_value = ctx_p

        out_path = tmp_path / "out.pdf"
        with patch("scripts.generate_pdf._get_sync_playwright", return_value=lambda: cm):
            result = render_pdf(str(html), str(out_path))

        assert result == str(out_path)
        assert os.path.exists(result)
        # loaded the HTML via a file:// URI
        goto_url = page.goto.call_args.args[0]
        assert goto_url.startswith("file://")
        # print backgrounds so the dark theme renders faithfully
        assert page.pdf.call_args.kwargs.get("print_background") is True
        assert page.pdf.call_args.kwargs.get("path") == str(out_path)

    def test_writes_into_nested_output_dir(self, tmp_path):
        html = tmp_path / "in.html"
        html.write_text("<html></html>")
        page = MagicMock()

        def fake_pdf(**kwargs):
            os.makedirs(os.path.dirname(kwargs["path"]), exist_ok=True)
            with open(kwargs["path"], "wb") as f:
                f.write(b"%PDF")
        page.pdf.side_effect = fake_pdf
        browser = MagicMock()
        browser.new_page.return_value = page
        ctx_p = MagicMock()
        ctx_p.chromium.launch.return_value = browser
        cm = MagicMock()
        cm.__enter__.return_value = ctx_p

        nested = tmp_path / "deep" / "reports" / "out.pdf"
        with patch("scripts.generate_pdf._get_sync_playwright", return_value=lambda: cm):
            result = render_pdf(str(html), str(nested))
        assert result == str(nested)


class TestGetSyncPlaywright:
    def test_returns_callable(self):
        # playwright is not installed in this env -> should be None, not raise
        result = _get_sync_playwright()
        assert result is None or callable(result)
