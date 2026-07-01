import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_handles import hashtags_for_niche, build_frequency, discover_handles


def test_hashtags_for_niche():
    tags = hashtags_for_niche("AI video editors")
    assert all(t.startswith("#") for t in tags)
    assert 3 <= len(tags) <= 5

def test_hashtags_for_niche_uses_curated_seeds():
    # Issue 6: a curated niche returns the vetted seed-map hashtags verbatim
    # (case-insensitive), not the string-generated ones.
    tags = hashtags_for_niche("AI tools")
    assert "#chatgpt" in tags
    assert "#aitools" in tags
    # a curated match must not contain the generator's "#aitoolstips" artifact
    assert all(not t.endswith("tips") for t in tags)

def test_build_frequency_uses_owner_id():
    # Real api-ninja hashtag pages return owner.id (no username field).
    posts = [
        {"owner": {"id": "111"}, "__hashtag": "#ai"},
        {"owner": {"id": "111"}, "__hashtag": "#video"},
        {"owner": {"id": "222"}, "__hashtag": "#ai"},
        {"__hashtag": "#ai"},  # missing owner -> gracefully skipped
    ]
    freq = build_frequency(posts)
    assert freq["111"]["post_count"] == 2
    assert set(freq["111"]["hashtags"]) == {"#ai", "#video"}
    assert freq["222"]["post_count"] == 1
    assert "handle" in freq["111"] and freq["111"]["handle"] == "111"

def test_discover_handles_uses_explore_tags_urls(monkeypatch):
    captured = []
    def fake_run(token, actor, run_input):
        captured.append(run_input)
        # real hashtag-post shape: owner.id only
        return [{"owner": {"id": "111"}, "shortcode": "abc"},
                {"owner": {"id": "222"}, "shortcode": "def"}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_handles.run_actor", side_effect=fake_run) as ra:
        out = discover_handles(["AI video editors"], "tok")
    assert ra.call_count >= 1
    # run_input MUST use the explore-tags URL form (Issue 4), not a 'hashtags' key
    for r in captured:
        assert "urls" in r
        assert all("explore/tags/" in u for u in r["urls"])
    handles = {h["handle"] for h in out}
    assert {"111", "222"} <= handles

def test_discover_handles_honors_explicit_hashtags_override(monkeypatch):
    # When the user confirms a hashtag set via research, those (and only those)
    # are scraped — per-niche generation is bypassed.
    scraped_tags = []
    def fake_run(token, actor, run_input):
        scraped_tags.append(run_input["urls"][0])
        return [{"owner": {"id": "999"}}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_handles.run_actor", side_effect=fake_run):
        out = discover_handles(["ignored niche"], "tok",
                               hashtags=["#aitools", "#chatgpt"])
    assert len(scraped_tags) == 2
    assert all("aitools" in t or "chatgpt" in t for t in scraped_tags)
    assert any(h["handle"] == "999" for h in out)
