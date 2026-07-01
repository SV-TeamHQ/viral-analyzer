import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_hashtag_research import parse_volume, research_hashtags


def test_parse_volume_units():
    assert parse_volume("7.62 m") == 7_620_000
    assert parse_volume("598.34 k") == 598_340
    assert parse_volume("2.5 b") == 2_500_000_000
    assert parse_volume("12345") == 12345
    assert parse_volume(None) == 0
    assert parse_volume("") == 0

def test_research_hashtags_ranks_by_volume_and_includes_seed(monkeypatch):
    # Real probed shape from apify/instagram-hashtag-analytics-scraper.
    probed = [{
        "name": "webscraping",
        "postsCount": 2_574_000,
        "related": [
            {"hash": "#software", "info": "7.62 m"},
            {"hash": "#dataanalytics", "info": "1.4 m"},
            {"hash": "#opensource", "info": "575.54 k"},
        ],
        "frequent": [],
        "url": "https://www.instagram.com/explore/tags/webscraping",
        "id": "webscraping",
    }]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_hashtag_research.run_actor", return_value=probed):
        out = research_hashtags("webscraping", "tok", top_n=10)

    # Seed is included with its postsCount as volume.
    by_tag = {h["hashtag"]: h for h in out}
    assert by_tag["#webscraping"]["volume"] == 2_574_000
    assert by_tag["#webscraping"]["source"] == "seed"
    assert by_tag["#software"]["volume"] == 7_620_000
    assert by_tag["#software"]["source"] == "related"
    # Ranked descending by volume (#software 7.62m > #webscraping 2.57m > #dataanalytics 1.4m)
    vols = [h["volume"] for h in out]
    assert vols == sorted(vols, reverse=True)
    assert out[0]["hashtag"] == "#software"

def test_research_hashtags_top_n_truncates(monkeypatch):
    probed = [{
        "name": "x", "postsCount": 100,
        "related": [{"hash": f"#r{i}", "info": str(i * 1000)} for i in range(1, 6)],
        "frequent": [], "url": "", "id": "x",
    }]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_hashtag_research.run_actor", return_value=probed):
        out = research_hashtags("x", "tok", top_n=3)
    assert len(out) == 3

def test_research_hashtags_empty_when_actor_returns_nothing(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_hashtag_research.run_actor", return_value=[]):
        assert research_hashtags("x", "tok") == []
