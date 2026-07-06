import sys, pathlib, types
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_score import compute_final_score, qualifies, score_handles, caption_language
from scripts.discovery_score import _eng_cap, W_ENG_NOCROSS, W_CROSS_NOCROSS, W_OUTLIER_NOCROSS


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


def _profile(username, followers, posts):
    """Real apify/instagram-profile-scraper item shape."""
    return {"username": username, "followersCount": followers,
            "latestPosts": [{"likesCount": l, "commentsCount": c} for (l, c) in posts]}


def test_score_handles_computes_engagement_from_latest_posts(monkeypatch):
    # Candidates arrive as owner IDs from Phase B; Phase C resolves username.
    candidates = [
        {"handle": "id_a", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"},
        {"handle": "id_b", "hashtags": ["#x"], "post_count": 1, "niche": "AI"},
    ]
    profiles = {
        # avg 115 engagement (>= MIN_ABS_ENGAGEMENT), 5K followers (>= 1K floor)
        "id_a": _profile("real_a", 5000, [(80, 10), (120, 20)]),
        # avg 120 engagement (>= MIN_ABS_ENGAGEMENT), 2K followers (>= 1K floor)
        "id_b": _profile("real_b", 2000, [(100, 20)]),
    }
    def fake_run(token, actor, run_input):
        return [profiles[run_input["usernames"][0]]]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor", side_effect=fake_run):
        out = score_handles(candidates, "tok", top_n=10, min_followers=1000)
    assert out[0]["final_score"] >= out[-1]["final_score"]
    # Issue 5: output handles are RESOLVED USERNAMES, not the input ids
    handles = {h["handle"] for h in out}
    assert "real_a" in handles
    assert "id_a" not in handles
    assert "niche" in out[0]
    # Issue 7: engagement was computed from latestPosts (not nonexistent avg fields)
    a = next(h for h in out if h["handle"] == "real_a")
    assert a["engagement_rate"] == round((100 + 15) / 5000, 4)  # avg(80+10),(120+20)=100,15


def test_min_followers_gate_drops_tiny_accounts(monkeypatch):
    # 6 above-floor candidates (>= slim_threshold) -> follower gate is strict,
    # so the below-floor "small" account is dropped (not slim-revealed).
    candidates = [
        {"handle": "small", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"},
    ] + [
        {"handle": f"big{i}", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"}
        for i in range(6)
    ]
    profiles = {
        # 14 followers but 250 avg engagement -> clears 4b, dropped by follower gate
        "small": _profile("small", 14, [(200, 50)]),
        **{f"big{i}": _profile(f"big{i}", 50_000, [(500, 50)]) for i in range(6)},
    }
    def fake_run(token, actor, run_input):
        return [profiles[run_input["usernames"][0]]]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor", side_effect=fake_run):
        out = score_handles(candidates, "tok", top_n=10, min_followers=1000)
    handles = {h["handle"] for h in out}
    assert "big0" in handles
    assert "small" not in handles
    assert all(h["followers"] >= 1000 for h in out)


def test_outlier_potential_nonzero_with_real_profile_data(monkeypatch):
    """Regression: candidates arrive WITHOUT pre-filled followers/engagement
    (as real Apify Phase B output does). The cohort median used by the
    outlier_potential component must be derived from REAL scraped data, not
    from the pre-scrape zeros that previously zeroed-out the component."""
    candidates = [
        {"handle": "id_a", "hashtags": ["#x", "#y", "#z"], "post_count": 5, "niche": "AI"},
        {"handle": "id_b", "hashtags": ["#x", "#y"], "post_count": 4, "niche": "AI"},
        {"handle": "id_c", "hashtags": ["#x"], "post_count": 3, "niche": "AI"},
    ]
    profiles = {
        "id_a": _profile("real_a", 1000, [(200, 50)]),    # 250 eng
        "id_b": _profile("real_b", 2000, [(100, 20)]),    # 120 eng
        "id_c": _profile("real_c", 500, [(40, 10)]),      # 50 eng
    }
    def fake_run(token, actor, run_input):
        return [profiles[run_input["usernames"][0]]]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor", side_effect=fake_run):
        out = score_handles(candidates, "tok", top_n=10, min_followers=100)
    assert any(h["outlier_potential"] > 0 for h in out), \
        f"outlier_potential all zero — cohort median not derived from scraped data: {out}"


def test_eng_cap_tiers():
    # 4d — follower-tiered engagement caps
    assert _eng_cap(0) == 0.10        # micro (<10K)
    assert _eng_cap(9_999) == 0.10
    assert _eng_cap(10_000) == 0.08   # mid (10K-100K)
    assert _eng_cap(99_999) == 0.08
    assert _eng_cap(100_000) == 0.05  # macro (100K+)


def test_compute_final_score_single_hashtag_uses_redistributed_weights():
    # 4c — when max_tags < 2, weights are 0.7/0.0/0.3 (cross signal impossible)
    c = {"handle": "a", "hashtags": ["#x"], "followers": 1000,
         "avg_likes": 100, "avg_comments": 0}   # eng_rate = 0.10 -> eng_norm = 1.0 (micro cap)
    # median=50, sample_top=100 -> outlier_pot = 100/50 = 2.0 -> out_norm = 0.4
    score, parts = compute_final_score(c, max_tags=1, median_engagement=50,
                                        sample_top_engagement=100)
    expected = round(0.7 * 1.0 + 0.0 + 0.3 * 0.4, 3)   # 0.82
    assert score == expected == 0.82


def test_compute_final_score_multi_hashtag_keeps_original_weights():
    # 4c regression — max_tags >= 2 keeps 0.4/0.4/0.2
    c = {"handle": "a", "hashtags": ["#x", "#y", "#z"], "followers": 1000,
         "avg_likes": 50, "avg_comments": 10}   # eng_rate = 0.06 -> eng_norm = 0.6
    score, parts = compute_final_score(c, max_tags=3, median_engagement=30,
                                        sample_top_engagement=93)
    # cross_norm = 3/3 = 1.0 ; outlier_pot = 93/30 = 3.1 -> out_norm = 0.62
    expected = round(0.4 * 0.6 + 0.4 * 1.0 + 0.2 * 0.62, 3)   # 0.764
    assert score == expected


def test_compute_final_score_macro_not_equalized_with_micro():
    # 4d — a 100K/5% account and a 5K/10% account both saturate eng_norm at 1.0,
    # so with identical other inputs they score equally (NOT penalized for size)
    big = {"handle": "big", "hashtags": ["#x"], "followers": 100_000,
           "avg_likes": 5000, "avg_comments": 0}     # eng_rate 0.05, cap 0.05 -> eng_norm 1.0
    small = {"handle": "small", "hashtags": ["#x"], "followers": 5_000,
             "avg_likes": 500, "avg_comments": 0}    # eng_rate 0.10, cap 0.10 -> eng_norm 1.0
    s_big, _ = compute_final_score(big, max_tags=1, median_engagement=100,
                                    sample_top_engagement=200)
    s_small, _ = compute_final_score(small, max_tags=1, median_engagement=100,
                                      sample_top_engagement=200)
    assert s_big == s_small   # equal eng_norm + equal outlier -> equal score


def _stub_langdetect(monkeypatch, detect_fn):
    mod = types.ModuleType("langdetect")
    mod.detect = detect_fn
    monkeypatch.setitem(sys.modules, "langdetect", mod)


def test_caption_language_english(monkeypatch):
    _stub_langdetect(monkeypatch, lambda text: "en")
    prof = {"latestPosts": [{"caption": "check out my new video"},
                            {"caption": "best tips for growth"}]}
    assert caption_language(prof) == "en"


def test_caption_language_modal_when_mixed(monkeypatch):
    returns = iter(["ar", "ar", "en"])
    _stub_langdetect(monkeypatch, lambda text: next(returns))
    prof = {"latestPosts": [{"caption": "a"}, {"caption": "b"}, {"caption": "c"}]}
    assert caption_language(prof) == "ar"


def test_caption_language_unknown_when_no_captions():
    assert caption_language({"latestPosts": []}) == "unknown"
    assert caption_language({}) == "unknown"


def test_caption_language_unknown_when_langdetect_missing(monkeypatch):
    # Setting sys.modules[name] = None makes `from langdetect import detect` raise ImportError
    monkeypatch.setitem(sys.modules, "langdetect", None)
    prof = {"latestPosts": [{"caption": "hello"}]}
    assert caption_language(prof) == "unknown"


def test_4b_drops_low_absolute_engagement(monkeypatch):
    # 50K followers (above any floor) but only 3 avg engagement -> dropped by 4b
    candidates = [{"handle": "ghost", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"}]
    profiles = {"ghost": _profile("ghost", 50_000, [(3, 0)])}
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor",
               side_effect=lambda *a, **k: [profiles[a[2]["usernames"][0]]]):
        out = score_handles(candidates, "tok", top_n=10, min_followers=1000)
    assert all(h["handle"] != "ghost" for h in out)


def test_4a_engagement_anomaly_flag(monkeypatch):
    # 2K followers, avg 30K likes -> eng_rate ~15 (>1.0) -> anomaly flagged, kept
    candidates = [{"handle": "viral", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"}]
    profiles = {"viral": _profile("viral", 2_000, [(30_000, 500)])}
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor",
               side_effect=lambda *a, **k: [profiles[a[2]["usernames"][0]]]):
        out = score_handles(candidates, "tok", top_n=10, min_followers=1000)
    assert any(h["handle"] == "viral" for h in out)
    v = next(h for h in out if h["handle"] == "viral")
    assert v["engagement_anomaly"] is True
    assert v["engagement_rate"] > 1.0


def test_slim_reveal_appends_below_floor_when_above_is_thin(monkeypatch):
    # 2 above-floor (>=10K) + 2 below-floor (<10K); above count < SLIM_THRESHOLD(5)
    candidates = [
        {"handle": f"h{i}", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"}
        for i in range(4)
    ]
    profiles = {
        "h0": _profile("h0", 20_000, [(500, 50)]),    # above floor
        "h1": _profile("h1", 15_000, [(400, 40)]),    # above floor
        "h2": _profile("h2", 3_000, [(300, 30)]),     # below floor
        "h3": _profile("h3", 2_000, [(200, 20)]),     # below floor
    }
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor",
               side_effect=lambda *a, **k: [profiles[a[2]["usernames"][0]]]):
        out = score_handles(candidates, "tok", top_n=10, min_followers=10_000)
    handles = {h["handle"]: h for h in out}
    assert handles["h0"]["below_follower_floor"] is False
    assert handles["h2"]["below_follower_floor"] is True   # revealed
    assert "h3" in handles                                 # revealed


def test_no_slim_reveal_when_above_floor_is_sufficient(monkeypatch):
    # 6 above-floor + 1 below-floor -> above >= SLIM_THRESHOLD -> below NOT revealed
    candidates = [
        {"handle": f"h{i}", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"}
        for i in range(7)
    ]
    profiles = {f"h{i}": _profile(f"h{i}", 20_000, [(500, 50)]) for i in range(6)}
    profiles["h6"] = _profile("h6", 3_000, [(300, 30)])     # below floor
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor",
               side_effect=lambda *a, **k: [profiles[a[2]["usernames"][0]]]):
        out = score_handles(candidates, "tok", top_n=10, min_followers=10_000)
    handles = {h["handle"] for h in out}
    assert "h6" not in handles
    assert all(h["below_follower_floor"] is False for h in out)


def test_default_min_followers_is_10000(monkeypatch):
    # 5K-follower candidate with solid engagement: under default 10K floor -> flagged
    candidates = [{"handle": "mid", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"}]
    profiles = {"mid": _profile("mid", 5_000, [(500, 50)])}
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor",
               side_effect=lambda *a, **k: [profiles[a[2]["usernames"][0]]]):
        out = score_handles(candidates, "tok", top_n=10)   # no min_followers -> default 10000
    assert any(h["handle"] == "mid" for h in out)          # revealed via slim
    assert out[0]["below_follower_floor"] is True
