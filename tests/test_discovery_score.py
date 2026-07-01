import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_score import compute_final_score, qualifies, score_handles


def test_qualifies_by_cross_hashtag():
    c = {"handle": "a", "hashtags": ["#x", "#y"], "post_count": 1,
         "followers": 1000, "avg_likes": 50, "avg_comments": 5}
    assert qualifies(c, min_tags=2, top20_eng_rate=1.0) is True

def test_compute_final_score_weights():
    c = {"handle": "a", "hashtags": ["#x", "#y", "#z"], "post_count": 1,
         "followers": 1000, "avg_likes": 50, "avg_comments": 10}
    # engagement_rate = (50+10)/1000 = 0.06 ; cross = 3/3 = 1.0
    score, parts = compute_final_score(c, max_tags=3, median_engagement=30, sample_top_engagement=93)
    assert 0.0 <= score <= 1.0
    assert parts["engagement_rate"] == 0.06
    assert parts["cross_hashtag_count"] == 3

def test_score_handles_returns_top_sorted(monkeypatch):
    candidates = [
        {"handle": "a", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"},
        {"handle": "b", "hashtags": ["#x"], "post_count": 1, "niche": "AI"},
    ]
    def fake_run(token, actor, run_input):
        return [{"followersCount": 1000, "avgLikes": 80, "avgComments": 10}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor", side_effect=fake_run):
        out = score_handles(candidates, "tok", top_n=10)
    assert out[0]["final_score"] >= out[-1]["final_score"]
    assert "handle" in out[0] and "niche" in out[0]


def test_outlier_potential_nonzero_with_real_profile_data(monkeypatch):
    """Regression: candidates arrive WITHOUT pre-filled followers/avg_likes
    (as real Apify Phase B output does). The cohort median used by the
    outlier_potential component must be derived from REAL scraped data, not
    from the pre-scrape zeros that previously zeroed-out the component.
    """
    candidates = [
        {"handle": "a", "hashtags": ["#x", "#y", "#z"], "post_count": 5, "niche": "AI"},
        {"handle": "b", "hashtags": ["#x", "#y"], "post_count": 4, "niche": "AI"},
        {"handle": "c", "hashtags": ["#x"], "post_count": 3, "niche": "AI"},
    ]

    profiles = {
        "a": {"followersCount": 1000, "avgLikes": 200, "avgComments": 50},   # 250 eng
        "b": {"followersCount": 2000, "avgLikes": 100, "avgComments": 20},   # 120 eng
        "c": {"followersCount": 500, "avgLikes": 40, "avgComments": 10},     # 50 eng
    }

    def fake_run(token, actor, run_input):
        username = run_input["usernames"][0]
        return [profiles[username]]

    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor", side_effect=fake_run):
        out = score_handles(candidates, "tok", top_n=10)

    # At least one scored handle must show a non-zero outlier_potential —
    # i.e. the cohort median was computed from real engagement counts.
    assert any(h["outlier_potential"] > 0 for h in out), \
        f"outlier_potential all zero — cohort median not derived from scraped data: {out}"
