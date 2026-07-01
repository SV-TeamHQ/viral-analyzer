import json
import os
import pytest

from scripts.merge_analyses import load_analysis, merge_analyses


SELECTED = [
    {"id": "A1", "handle": "creator1", "url": "u1", "likes": 100, "comments": 5,
     "views": 1000, "outlier_score": 5.0, "caption": "c1"},
    {"id": "A2", "handle": "creator2", "url": "u2", "likes": 50, "comments": 2,
     "views": 500, "outlier_score": 2.0, "caption": "c2"},
]


class TestLoadAnalysis:
    def test_reads_json(self, tmp_path):
        f = tmp_path / "A1.json"
        f.write_text(json.dumps({"hook": "h", "why_it_worked": "w"}))
        result = load_analysis("A1", str(tmp_path))
        assert result["hook"] == "h"

    def test_returns_none_when_missing(self, tmp_path):
        assert load_analysis("NOPE", str(tmp_path)) is None


class TestMergeAnalyses:
    def test_merges_analysis_with_metadata(self, tmp_path):
        (tmp_path / "A1.json").write_text(json.dumps(
            {"hook": "h1", "visual_format": "fmt", "why_it_worked": "w1",
             "replication_notes": "r1"}))
        result = merge_analyses(SELECTED, str(tmp_path))
        a1 = result[0]
        assert a1["hook"] == "h1"
        assert a1["visual_format"] == "fmt"
        assert a1["likes"] == 100          # metadata merged in
        assert a1["handle"] == "creator1"
        assert a1["analyzed"] is True

    def test_missing_analysis_becomes_placeholder(self, tmp_path):
        # A2 has no analysis file
        result = merge_analyses(SELECTED, str(tmp_path))
        a2 = result[1]
        assert a2["analyzed"] is False
        assert a2["likes"] == 50            # metadata still present
        assert "unavailable" in a2["why_it_worked"].lower()

    def test_preserves_selected_order(self, tmp_path):
        result = merge_analyses(SELECTED, str(tmp_path))
        assert [p["id"] for p in result] == ["A1", "A2"]

    def test_metadata_overrides_stale_analysis_values(self, tmp_path):
        # agent wrote a wrong likes count; metadata must win
        (tmp_path / "A1.json").write_text(json.dumps(
            {"likes": 99999, "why_it_worked": "w"}))
        result = merge_analyses(SELECTED, str(tmp_path))
        assert result[0]["likes"] == 100

    def test_frames_carry_through(self, tmp_path):
        selected = [{"id": "A1", "handle": "c1", "url": "u", "likes": 1, "comments": 0,
                     "views": 10, "outlier_score": 1.0, "caption": "",
                     "frames": ["temp/frames/A1/frame_01.jpg"]}]
        result = merge_analyses(selected, str(tmp_path))
        assert result[0]["frames"] == ["temp/frames/A1/frame_01.jpg"]

    def test_spoken_hook_passes_through_merge(self, tmp_path):
        # post in selected_posts.json
        posts = [{"id": "C1", "handle": "alice", "url": "u", "likes": 5,
                  "comments": 1, "views": 10, "outlier_score": 1.0, "caption": "c"}]
        # agent analysis includes a spoken_hook
        analysis = {"shortCode": "C1", "handle": "agent-said", "why_it_worked": "x",
                    "spoken_hook": {"text": "Stop scrolling.", "type": "pattern interrupt",
                                    "window": "0:00-0:02"}}
        (tmp_path / "C1.json").write_text(json.dumps(analysis))
        merged = merge_analyses(posts, str(tmp_path))
        # agent-emitted field survives merge unchanged
        assert merged[0]["spoken_hook"] == analysis["spoken_hook"]
        # ground-truth handle still wins over the agent's
        assert merged[0]["handle"] == "alice"
