import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_handles import hashtags_for_niche, build_frequency, discover_handles


def test_hashtags_for_niche():
    tags = hashtags_for_niche("AI video editors")
    assert all(t.startswith("#") for t in tags)
    assert 3 <= len(tags) <= 5

def test_build_frequency_cross_hashtag():
    posts = [
        {"user": {"username": "a"}, "__hashtag": "#ai"},
        {"user": {"username": "a"}, "__hashtag": "#video"},
        {"user": {"username": "b"}, "__hashtag": "#ai"},
    ]
    freq = build_frequency(posts)
    assert freq["a"]["post_count"] == 2
    assert set(freq["a"]["hashtags"]) == {"#ai", "#video"}
    assert freq["b"]["post_count"] == 1

def test_discover_handles_uses_run_actor(monkeypatch):
    def fake_run(token, actor, run_input):
        tag = run_input["hashtags"][0]
        return [{"user": {"username": "a"}}, {"user": {"username": "b"}}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_handles.run_actor", side_effect=fake_run) as ra:
        out = discover_handles(["AI video editors"], "tok")
    assert ra.call_count >= 1
    handles = {h["handle"] for h in out}
    assert {"a", "b"} <= handles
