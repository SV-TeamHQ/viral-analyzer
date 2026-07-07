import base64
import json
import os
import pytest
from pathlib import Path

from scripts.generate_report import (
    encode_frame, build_summary, render_report, generate_report, get_thumbnail,
)


def test_writes_research_json_into_run_dir(tmp_path):
    analyses = json.loads(Path("tests/fixtures/sample_analyses.json").read_text())
    analyses_path = tmp_path / "analyses.json"
    analyses_path.write_text(json.dumps(analyses))
    patterns_path = tmp_path / "patterns.json"
    patterns_path.write_text(Path("tests/fixtures/sample_patterns.json").read_text())

    out = generate_report(
        input_path=str(analyses_path),
        output_dir=str(tmp_path / "out"),
        summary_path=None,
        patterns_path=str(patterns_path),
        pdf=False,
    )
    run_dir = Path(out).parent
    research = json.loads((run_dir / "research.json").read_text())
    assert research["stage"] == "research"
    assert research["run_dir"] == str(run_dir)
    assert research["patterns"]["summary"]
    assert research["patterns"]["hook_types"][0]["name"] == "Contrarian claim"
    assert Path(research["report"]["html"]).exists()


def test_falls_back_when_no_patterns(tmp_path):
    analyses = [{"id": "C1", "handle": "alice", "likes": 10, "comments": 1,
                 "views": 100, "outlier_score": 2.0, "caption": "c",
                 "analyzed": True, "visual_format": "talking head",
                 "why_it_worked": "x"}]
    analyses_path = tmp_path / "analyses.json"
    analyses_path.write_text(json.dumps(analyses))
    out = generate_report(
        input_path=str(analyses_path),
        output_dir=str(tmp_path / "out"),
        summary_path=None,
        patterns_path=None,
        pdf=False,
    )
    run_dir = Path(out).parent
    research = json.loads((run_dir / "research.json").read_text())
    # patterns block may be absent, but research.json still written
    assert research["stage"] == "research"


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


class TestGetThumbnail:
    def test_uses_first_frame_when_present(self, tmp_path):
        frame = tmp_path / "frame.jpg"
        frame.write_bytes(b"\xff\xd8\xff\xe0framebytes")
        a = {"id": "A1", "frames": [str(frame)]}
        uri = get_thumbnail(a, media_dir=str(tmp_path / "media"))
        assert uri and uri.startswith("data:image/jpeg;base64,")

    def test_falls_back_to_downloaded_cover_when_no_frames(self, tmp_path):
        # Bug 2: a post with frames: [] should still thumbnail from temp/media/{id}.jpg
        media = tmp_path / "media"
        media.mkdir()
        (media / "A1.jpg").write_bytes(b"\xff\xd8\xff\xe0coverbytes")
        a = {"id": "A1", "frames": []}
        uri = get_thumbnail(a, media_dir=str(media))
        assert uri and uri.startswith("data:image/jpeg;base64,")
        assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8\xff\xe0coverbytes"

    def test_returns_none_when_no_frame_and_no_cover(self, tmp_path):
        a = {"id": "NOPE", "frames": []}
        assert get_thumbnail(a, media_dir=str(tmp_path / "media")) is None

    def test_video_cover_not_misencoded_as_jpeg(self, tmp_path):
        # A video post saves as .mp4; it must not be base64-encoded as a broken
        # jpeg data URI. Only image-type covers qualify as a static thumbnail.
        media = tmp_path / "media"
        media.mkdir()
        (media / "V1.mp4").write_bytes(b"\x00\x00\x00\x20ftypmp42")
        a = {"id": "V1", "frames": []}
        assert get_thumbnail(a, media_dir=str(media)) is None


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

    def test_includes_light_print_stylesheet_for_pdf(self):
        html = render_report(ANALYSES, "S", "2026-06-26", "templates/report.html.j2")
        assert "@media print" in html
        # light theme overrides for the PDF (print media), not the dark screen theme
        assert "#ffffff" in html
        assert "break-inside: avoid" in html


def test_patterns_section_renders(tmp_path):
    from scripts.generate_report import render_report
    analyses = json.loads(Path("tests/fixtures/sample_analyses.json").read_text())
    patterns = json.loads(Path("tests/fixtures/sample_patterns.json").read_text())
    html = render_report(analyses, "SUM", "2026-07-01",
                         "templates/report.html.j2", patterns=patterns)
    assert "Niche Patterns" in html
    assert "Contrarian claim" in html          # hook type name
    assert "Talking head" in html              # format name
    assert "cost-reduction" in html            # topic


def test_spoken_hook_block_renders(tmp_path):
    from scripts.generate_report import render_report
    analyses = json.loads(Path("tests/fixtures/sample_analyses.json").read_text())
    html = render_report(analyses, "SUM", "2026-07-01",
                         "templates/report.html.j2", patterns=None)
    assert "SPOKEN HOOK" in html
    assert "contrarian claim" in html
    assert "0:00-0:03" in html


def test_card_renders_without_spoken_hook():
    from scripts.generate_report import render_report
    analyses = [{"id": "C1", "handle": "alice", "likes": 1, "comments": 0,
                 "views": 10, "outlier_score": 1.0, "caption": "", "analyzed": True,
                 "hook": "hi", "visual_format": "image", "why_it_worked": "w"}]
    html = render_report(analyses, "SUM", "2026-07-01",
                         "templates/report.html.j2", patterns=None)
    assert "SPOKEN HOOK" not in html   # graceful absence
    assert "Why It Worked" in html or "Why It" in html


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

    def test_real_run_filename_is_timestamp_versioned(self, tmp_path):
        # no date_str passed (a real run) -> filename is run-versioned so same-day
        # re-runs don't overwrite each other: IG-Competitor-Research_YYYY-MM-DD_HHMM.html
        import re
        analyses_file = tmp_path / "analyses.json"
        analyses_file.write_text(json.dumps(ANALYSES))
        path = generate_report(str(analyses_file), str(tmp_path / "reports"), summary_path=None)
        name = os.path.basename(path)
        assert re.match(r"IG-Competitor-Research_\d{4}-\d{2}-\d{2}_\d{4}\.html$", name), name

    def test_patterns_summary_wins_over_stale_summary_file(self, tmp_path):
        # Bug 1: a leftover temp/niche_summary.txt from a previous run (different
        # niche) must NOT override a valid patterns.summary. patterns is the
        # authoritative synthesis; the text file is only a manual fallback.
        analyses_file = tmp_path / "analyses.json"
        analyses_file.write_text(json.dumps(ANALYSES))
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps(
            {"summary": "PATTERNS-AUTHORITATIVE-SUMMARY",
             "hook_types": [], "formats": [], "topics": []}))
        stale_summary = tmp_path / "niche_summary.txt"
        stale_summary.write_text("STALE-SUMMARY-FROM-ANOTHER-NICHE")

        out = generate_report(str(analyses_file), str(tmp_path / "out"),
                              summary_path=str(stale_summary),
                              patterns_path=str(patterns_file),
                              date_str="2026-07-06", pdf=False)
        html = open(out, encoding="utf-8").read()
        assert "PATTERNS-AUTHORITATIVE-SUMMARY" in html
        assert "STALE-SUMMARY-FROM-ANOTHER-NICHE" not in html

    def test_text_summary_used_when_no_patterns_summary(self, tmp_path):
        # The text file is still honored as a fallback when patterns has no summary.
        analyses_file = tmp_path / "analyses.json"
        analyses_file.write_text(json.dumps(ANALYSES))
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps({"hook_types": []}))  # no "summary"
        summary_file = tmp_path / "niche_summary.txt"
        summary_file.write_text("MANUAL-FALLBACK-SUMMARY")

        out = generate_report(str(analyses_file), str(tmp_path / "out"),
                              summary_path=str(summary_file),
                              patterns_path=str(patterns_file),
                              date_str="2026-07-06", pdf=False)
        html = open(out, encoding="utf-8").read()
        assert "MANUAL-FALLBACK-SUMMARY" in html
