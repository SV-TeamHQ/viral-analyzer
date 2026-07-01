import json, sys, pathlib
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_pull_trends import pull_trends, merge_niches


def test_merge_boosts_niches_in_both_sources():
    trends = [("AI video editors", 87), ("AI coding assistants", 74)]
    reddit = [("AI video editors", 5), ("Notion templates", 3)]
    merged = merge_niches(trends, reddit)
    by_niche = {m["niche"]: m for m in merged}
    assert "google_trends" in by_niche["AI video editors"]["sources"]
    assert "reddit" in by_niche["AI video editors"]["sources"]
    # a niche in both should outrank a trends-only niche with a lower raw score
    assert by_niche["AI video editors"]["trend_score"] >= by_niche["AI coding assistants"]["trend_score"]


def test_pull_trends_pytrends_only(monkeypatch):
    import scripts.discovery_pull_trends as m
    monkeypatch.setattr(m, "_pytrends_niches", lambda seed: [("AI video editors", 87)])
    monkeypatch.setattr(m, "_reddit_niches", lambda seed: [])  # reddit unavailable
    out = pull_trends("AI", use_reddit=True)
    assert out[0]["niche"] == "AI video editors"
    assert out[0]["sources"] == ["google_trends"]


def test_pull_trends_empty_when_no_sources(monkeypatch):
    import scripts.discovery_pull_trends as m
    monkeypatch.setattr(m, "_pytrends_niches", lambda seed: [])
    monkeypatch.setattr(m, "_reddit_niches", lambda seed: [])
    assert pull_trends("AI", use_reddit=True) == []
