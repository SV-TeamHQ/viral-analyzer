import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.discovery_explore_niches import explore_niches, _resolve_seed, CATEGORIES


def test_explore_niches_reshapes_to_contract(monkeypatch):
    # real research_hashtags output shape: [{hashtag, volume, source}]
    ranked = [
        {"hashtag": "#homegym", "volume": 7600000, "source": "related"},
        {"hashtag": "#homeworkout", "volume": 1400000, "source": "related"},
    ]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=ranked):
        out = explore_niches("#fitness", "tok", top_n=10)
    assert out == [
        {"niche": "homegym", "trend_score": 7600000, "sources": ["instagram"]},
        {"niche": "homeworkout", "trend_score": 1400000, "sources": ["instagram"]},
    ]

def test_explore_niches_preserves_volume_order(monkeypatch):
    # research_hashtags already ranks by volume desc; explore_niches must preserve order
    ranked = [{"hashtag": "#a", "volume": 100, "source": "related"},
              {"hashtag": "#b", "volume": 50, "source": "related"}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=ranked):
        out = explore_niches("#x", "tok")
    assert [n["trend_score"] for n in out] == [100, 50]

def test_explore_niches_top_n_truncation(monkeypatch):
    ranked = [{"hashtag": f"#t{i}", "volume": i, "source": "related"} for i in range(20)]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=ranked):
        out = explore_niches("#x", "tok", top_n=5)
    assert len(out) == 5

def test_explore_niches_empty_on_failure(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=[]):
        assert explore_niches("#dead", "tok") == []

def test_resolve_seed_from_seed():
    assert _resolve_seed("homegym", None) == "#homegym"
    assert _resolve_seed("#homegym", None) == "#homegym"

def test_resolve_seed_from_category():
    assert _resolve_seed(None, "Fitness") == "#fitness"
    assert _resolve_seed(None, "AI") == "#ai"
    assert _resolve_seed(None, "health & wellness") == "#wellness"
    assert _resolve_seed(None, "apps") == "#apps"

def test_resolve_seed_unknown_category_raises():
    try:
        _resolve_seed(None, "nonexistent")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)

def test_resolve_seed_neither_returns_none():
    assert _resolve_seed(None, None) is None

def test_categories_has_17_entries():
    assert len(CATEGORIES) == 17
    for key in ("ai", "beauty", "apps", "fitness", "tech"):
        assert key in CATEGORIES
