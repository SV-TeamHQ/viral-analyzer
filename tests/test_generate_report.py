import base64
import json
import os
import pytest

from scripts.generate_report import (
    encode_frame, build_summary, render_report, generate_report,
)


ANALYSES = [
    {"id": "A1", "handle": "creator1", "url": "https://ig/p/A1", "likes": 100,
     "comments": 5, "views": 1000, "outlier_score": 5.0, "caption": "c1",
     "analyzed": True, "hook": "hook1", "visual_format": "Talking Head",
     "format_breakdown": "fb", "topic": "t", "why_it_worked": "w",
     "replication_notes": "r", "transcript": "tr", "frames": []},
    {"id": "A2", "handle": "creator2", "url": "https://ig/p/A2", "likes": 50,
     "comments": 2, "views": 500, "outlier_score": 2.0, "caption": "c2",
     "analyzed": False, "why_it_worked": "Analysis unavailable.", "frames": []},
]


class TestEncodeFrame:
    def test_returns_data_uri(self, tmp_path):
        img = tmp_path / "f.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0fakejpg")
        uri = encode_frame(str(img))
        assert uri.startswith("data:image/jpeg;base64,")
        encoded = uri.split(",", 1)[1]
        assert base64.b64decode(encoded) == b"\xff\xd8\xff\xe0fakejpg"

    def test_returns_none_when_missing(self, tmp_path):
        assert encode_frame(str(tmp_path / "nope.jpg")) is None


class TestBuildSummary:
    def test_includes_counts_and_top_format(self):
        summary = build_summary(ANALYSES)
        assert "2" in summary               # post count
        assert "creator1" in summary or "creator2" in summary
        assert "Talking Head" in summary    # top visual_format


class TestRenderReport:
    def test_renders_handles_and_summary(self, tmp_path):
        html = render_report(ANALYSES, "SUMMARY TEXT", "2026-06-26",
                             "templates/report.html.j2")
        assert "SUMMARY TEXT" in html
        assert "creator1" in html
        assert "2026-06-26" in html
        assert "hook1" in html


class TestGenerateReport:
    def test_writes_dated_html_file(self, tmp_path):
        analyses_file = tmp_path / "analyses.json"
        analyses_file.write_text(json.dumps(ANALYSES))
        out_dir = tmp_path / "reports"
        path = generate_report(str(analyses_file), str(out_dir), summary_path=None,
                               date_str="2026-06-26")
        assert path.endswith("IG-Competitor-Research_2026-06-26.html")
        assert os.path.exists(path)
        assert "creator1" in open(path, encoding="utf-8").read()

    def test_pdf_flag_invokes_render_pdf(self, tmp_path, monkeypatch):
        analyses_file = tmp_path / "analyses.json"
        analyses_file.write_text(json.dumps(ANALYSES))
        called = {}

        def fake_render(html, pdf):
            called["html"] = html
            called["pdf"] = pdf
            return pdf
        monkeypatch.setattr("scripts.generate_pdf.render_pdf", fake_render)

        generate_report(str(analyses_file), str(tmp_path / "reports"), summary_path=None,
                        date_str="2026-06-29", pdf=True)
        assert called["html"].endswith("IG-Competitor-Research_2026-06-29.html")
        assert called["pdf"].endswith("IG-Competitor-Research_2026-06-29.pdf")

    def test_pdf_off_does_not_invoke_render_pdf(self, tmp_path, monkeypatch):
        analyses_file = tmp_path / "analyses.json"
        analyses_file.write_text(json.dumps(ANALYSES))

        def boom(html, pdf):
            raise AssertionError("render_pdf should not be called when pdf=False")
        monkeypatch.setattr("scripts.generate_pdf.render_pdf", boom)

        generate_report(str(analyses_file), str(tmp_path / "reports"), summary_path=None,
                        date_str="2026-06-29", pdf=False)
