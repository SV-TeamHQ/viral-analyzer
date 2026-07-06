# Phase C Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `/niche-discovery` Phase C (`discovery_score.py`) — fix the scoring formula's micro/macro equalization (4d) and dead cross-hashtag weight (4c), add an absolute-engagement floor (4b), raise the follower floor to 10K with slim-reveal, and surface language (Fix 5) + engagement-anomaly (4a) flags in the shortlist.

**Architecture:** All scoring changes live in `scripts/discovery_score.py`. A gate-vs-flag distinction runs through the design: objective floors (4b abs engagement, follower count) drop candidates; relevance signals (language, >100% engagement) are flagged for the user's pick-time decision. Cohort statistics are computed over 4b-survivors before the soft follower gate, so below-floor candidates still score fairly. Phase B is untouched (separate Spec B).

**Tech Stack:** Python 3.10+ (modern type hints), `statistics.median`, `langdetect` (new, lazy-imported), `viral_core.scoring.outlier_score`, pytest.

## Global Constraints

- **Python 3.10+**, modern union type hints (`int | float`, `tuple[float, dict]`).
- **`viral_core` bootstrap** unchanged (already at top of `discovery_score.py`).
- **Ground-truth metrics from scraped data only.** `_avg_engagement` parses `latestPosts[]`; no invented numbers.
- **Real-shape fixtures in tests** — profile dicts must mirror `apify/instagram-profile-scraper` output (`followersCount`, `latestPosts[].likesCount/commentsCount/caption`). No invented field names.
- **TDD:** every code task writes the failing test first, runs it red, implements, runs it green, commits.
- **`compute_final_score` existing test stays green:** `test_compute_final_score_weights` (max_tags=3, followers=1000) must still pass after 4c/4d — the micro-tier cap (0.10) equals the old flat cap, and multi-hashtag keeps the 0.4/0.4/0.2 weights. Verify as a regression check in Task 1.
- **Backward compat:** the three new scored-output fields (`detected_language`, `engagement_anomaly`, `below_follower_floor`) are additive; consumers that ignore them are unaffected.
- **Spec of record:** `docs/superpowers/specs/2026-07-06-phase-c-hardening-design.md`.
- **Line endings:** repo normalizes LF↔CRLF on Windows; commit warnings expected and ignored.

---

## File Structure

**Modify:**
- `scripts/discovery_score.py` — constants, `_eng_cap`, `compute_final_score` (Task 1); `caption_language` (Task 2); `score_handles` + `main` + CLI defaults (Task 3).
- `tests/test_discovery_score.py` — new tests for 4c/4d (Task 1), language (Task 2), 4a/4b/slim-reveal/default (Task 3); intentional updates to three existing `score_handles` tests (Task 3).
- `requirements.txt` — add `langdetect>=1.0.9` (Task 2).
- `skills/niche-discovery/SKILL.md` — Phase C `--min-followers 10000` default + shortlist signal presentation (Task 4).

**Reuse unchanged:** `qualifies()` (≥2 hashtags OR top-20% engagement), `_avg_engagement`, `_eng_rate`, `_eng_abs`, `outlier_score`.

---

## Task 1: `compute_final_score` — follower-tiered caps (4d) + cross-hashtag redistribution (4c)

**Files:**
- Modify: `scripts/discovery_score.py` (add constants near the existing `W_*` block; add `_eng_cap`; revise `compute_final_score`)
- Test: `tests/test_discovery_score.py` (append new tests; existing direct-call tests stay green)

**Interfaces:**
- Consumes: `viral_core.scoring.outlier_score` (unchanged).
- Produces: `_eng_cap(followers: int) -> float`; revised `compute_final_score` whose `eng_norm` uses `_eng_cap` and whose weights depend on `max_tags < 2`. Same return shape `(float, dict)`, so `score_handles` (Task 3) calls it unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_discovery_score.py`:

```python
from scripts.discovery_score import _eng_cap, W_ENG_NOCROSS, W_CROSS_NOCROSS, W_OUTLIER_NOCROSS


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: FAIL — `ImportError: cannot import name '_eng_cap'` (and the score assertions would fail on the old flat 0.10 cap / old weights).

- [ ] **Step 3: Add constants + `_eng_cap`**

In `scripts/discovery_score.py`, replace the existing `W_*` block (lines 16–18):

```python
W_ENG = 0.4
W_CROSS = 0.4
W_OUTLIER = 0.2
```

with:

```python
W_ENG = 0.4
W_CROSS = 0.4
W_OUTLIER = 0.2

# 4d — follower-tiered engagement caps (replaces the flat 0.10 normalization).
ENG_CAP_MICRO = 0.10   # < 10K followers
ENG_CAP_MID = 0.08     # 10K-100K
ENG_CAP_MACRO = 0.05   # 100K+

# 4c — effective weights when cross-hashtag is structurally impossible (max_tags < 2).
W_ENG_NOCROSS = 0.7
W_CROSS_NOCROSS = 0.0
W_OUTLIER_NOCROSS = 0.3
```

Add the helper immediately above `compute_final_score`:

```python
def _eng_cap(followers: int) -> float:
    """4d: engagement-rate cap by follower tier. Larger accounts saturate at a
    lower rate so a 100K/5% creator isn't equalized with a 1K/10% creator."""
    if followers >= 100_000:
        return ENG_CAP_MACRO
    if followers >= 10_000:
        return ENG_CAP_MID
    return ENG_CAP_MICRO
```

- [ ] **Step 4: Revise `compute_final_score`**

Replace the body of `compute_final_score` (current lines 29–46) with:

```python
def compute_final_score(c: dict, max_tags: int, median_engagement: float,
                        sample_top_engagement: float) -> tuple[float, dict]:
    followers = c.get("followers") or 1
    eng_rate = (c.get("avg_likes", 0) + c.get("avg_comments", 0)) / followers
    cross = len(c.get("hashtags", []))
    cross_norm = min(cross / max_tags, 1.0) if max_tags else 0.0
    outlier_pot = outlier_score(sample_top_engagement, median_engagement) if median_engagement else 0.0
    eng_norm = min(eng_rate / _eng_cap(followers), 1.0)        # 4d
    out_norm = min(outlier_pot / 5.0, 1.0)
    if max_tags < 2:                                            # 4c
        w_eng, w_cross, w_out = W_ENG_NOCROSS, W_CROSS_NOCROSS, W_OUTLIER_NOCROSS
    else:
        w_eng, w_cross, w_out = W_ENG, W_CROSS, W_OUTLIER
    final = round(w_eng * eng_norm + w_cross * cross_norm + w_out * out_norm, 3)
    return final, {
        "engagement_rate": round(eng_rate, 4),
        "cross_hashtag_count": cross,
        "outlier_potential": round(outlier_pot, 2),
        "followers": followers,
    }
```

- [ ] **Step 5: Run the discovery_score tests (new + regression)**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: PASS for the 4 new tests AND the existing `test_compute_final_score_weights` / `test_qualifies_by_cross_hashtag` (regression — micro tier + multi-hashtag preserve old math). The three existing `score_handles`-level tests may now behave differently due to the not-yet-changed 10K default — they are updated in Task 3; if any fail here, leave them for Task 3 (do not edit them in this task).

- [ ] **Step 6: Commit**

```bash
git add scripts/discovery_score.py tests/test_discovery_score.py
git commit -m "feat: follower-tiered engagement caps (4d) + cross-hashtag weight redistribution (4c)"
```

---

## Task 2: `caption_language` helper + `langdetect` dependency (Fix 5)

**Files:**
- Modify: `scripts/discovery_score.py` (add `caption_language`)
- Modify: `requirements.txt` (add `langdetect>=1.0.9`)
- Test: `tests/test_discovery_score.py` (append language tests)

**Interfaces:**
- Produces: `caption_language(prof: dict, max_captions: int = 5) -> str` — modal ISO code across `prof["latestPosts"][].caption`, or `"unknown"` when captions are absent / `langdetect` missing / all detections raise. Lazy-imports `langdetect` so the module loads without it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_discovery_score.py`:

```python
import types


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
```

(Add `import sys` at the top of the test file if not already present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: FAIL — `NameError: name 'caption_language' is not defined`.

- [ ] **Step 3: Add `langdetect` to requirements.txt**

Append one line to `requirements.txt` (after `playwright>=1.40.0`):

```
langdetect>=1.0.9
```

- [ ] **Step 4: Implement `caption_language`**

In `scripts/discovery_score.py`, add this function immediately after `_avg_engagement` (before `score_handles`):

```python
def caption_language(prof: dict, max_captions: int = 5) -> str:
    """Fix 5: modal ISO language code across recent captions; 'unknown' if none
    are present, langdetect isn't installed, or every detection raises.
    langdetect is imported lazily so this module loads without it."""
    captions = [p.get("caption", "") for p in (prof.get("latestPosts") or [])
                if p.get("caption")]
    if not captions:
        return "unknown"
    try:
        from langdetect import detect
    except ImportError:
        return "unknown"
    from collections import Counter
    langs = []
    for cap in captions[:max_captions]:
        try:
            langs.append(detect(cap))
        except Exception:
            pass
    return Counter(langs).most_common(1)[0][0] if langs else "unknown"
```

- [ ] **Step 5: Run the language tests**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: the 4 new language tests PASS; earlier tests unaffected.

- [ ] **Step 6: Commit**

```bash
git add scripts/discovery_score.py requirements.txt tests/test_discovery_score.py
git commit -m "feat: caption language detection (Fix 5) + langdetect dep"
```

---

## Task 3: `score_handles` — 4b floor, 4a flag, language attach, slim-reveal, 10K default

**Files:**
- Modify: `scripts/discovery_score.py` (constants; `score_handles`; `main`; CLI `--min-followers` default)
- Test: `tests/test_discovery_score.py` (new tests; intentional updates to three existing `score_handles` tests)

**Interfaces:**
- Consumes: Task 1's `compute_final_score`; Task 2's `caption_language`.
- Produces: revised `score_handles(candidates, token, top_n=10, min_followers=10_000, slim_threshold=5)`; scored-output dict gains `detected_language`, `engagement_anomaly` (bool), `below_follower_floor` (bool). `main(..., min_followers=10_000)`; CLI `--min-followers` default `10000`.

- [ ] **Step 1: Update the three existing `score_handles` tests to be intentional about the new defaults**

In `tests/test_discovery_score.py`:

(a) `test_score_handles_computes_engagement_from_latest_posts` — pass `min_followers=1000` explicitly (to test the scoring path, not the slim-reveal) and raise `real_b`'s engagement above the new 4b floor. Replace its `profiles` block with:

```python
    profiles = {
        # avg 115 engagement (>= MIN_ABS_ENGAGEMENT), 5K followers (>= 1K floor)
        "id_a": _profile("real_a", 5000, [(80, 10), (120, 20)]),
        # avg 120 engagement (>= MIN_ABS_ENGAGEMENT), 2K followers (>= 1K floor)
        "id_b": _profile("real_b", 2000, [(100, 20)]),
    }
```

and change the call to `score_handles(candidates, "tok", top_n=10, min_followers=1000)`. The existing assertions (`real_a` resolved, `id_a` absent, `engagement_rate == round((100+15)/5000, 4)`, sorted) remain and still hold.

(b) `test_min_followers_gate_drops_tiny_accounts` — give `small` enough engagement to clear 4b so the test still exercises the *follower* gate (not 4b). Replace its `profiles` block with:

```python
    profiles = {
        # 14 followers but 250 avg engagement -> clears 4b, dropped by follower gate
        "small": _profile("small", 14, [(200, 50)]),
        "big": _profile("big", 50000, [(500, 50)]),
    }
```

Keep the call `score_handles(candidates, "tok", top_n=10, min_followers=1000)` and the existing assertions (`small` absent, `big` present, all `followers >= 1000`).

(c) `test_outlier_potential_nonzero_with_real_profile_data` — pass `min_followers=100` explicitly to isolate the cohort-stats behavior from the new 10K default. Change the call to `score_handles(candidates, "tok", top_n=10, min_followers=100)`. (`id_c` at 50 avg engagement is now dropped by 4b — that's fine; the assertion is `any(outlier_potential > 0)`, satisfied by `id_a`.)

- [ ] **Step 2: Write the new failing tests**

Append to `tests/test_discovery_score.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: FAIL — new tests reference not-yet-existing fields (`below_follower_floor`, `engagement_anomaly`) and the 10K default / 4b floor aren't in place.

- [ ] **Step 4: Add the new constants**

In `scripts/discovery_score.py`, just below the `W_OUTLIER_NOCROSS` line added in Task 1, add:

```python
# Phase C hardening (Spec A) — objective floors + slim-reveal
MIN_ABS_ENGAGEMENT = 100     # 4b: drop candidates whose avg (likes+comments) < this
SLIM_THRESHOLD = 5           # reveal below-floor candidates when fewer than this clear the gate
```

- [ ] **Step 5: Revise `score_handles`**

Replace the entire current `score_handles` function (lines 72–125) with:

```python
def score_handles(candidates: list[dict], token: str, top_n: int = 10,
                  min_followers: int = 10_000,
                  slim_threshold: int = SLIM_THRESHOLD) -> list[dict]:
    max_tags = max((len(c.get("hashtags", [])) for c in candidates), default=1) or 1

    # ----- Pass 1: enrich every candidate via profile scrape -----
    enriched: list[dict] = []
    for c in candidates:
        run_input = {"usernames": [c["handle"]]}
        try:
            items = run_actor(token, PROFILE_ACTOR, run_input)
        except Exception as e:
            print(f"WARN: profile scrape failed for {c['handle']}: {e}")
            continue
        if not items:
            continue
        prof = items[0]
        c["followers"] = prof.get("followersCount", 0) or 0
        c["avg_likes"], c["avg_comments"] = _avg_engagement(prof)
        c["detected_language"] = caption_language(prof)            # Fix 5
        # 4b: objective absolute-engagement floor (drop dead accounts)
        if (c["avg_likes"] + c["avg_comments"]) < MIN_ABS_ENGAGEMENT:
            continue
        username = prof.get("username")
        if username:
            c["handle"] = username  # resolve owner.id -> username
        enriched.append(c)

    if not enriched:
        return []

    # ----- Cohort statistics from REAL scraped data (computed over 4b-survivors) -----
    median_abs = median(_eng_abs(c) for c in enriched)
    rates_sorted = sorted(_eng_rate(c) for c in enriched)
    top20_idx = max(1, len(rates_sorted) - max(1, len(rates_sorted) // 5))
    top20_rate = rates_sorted[top20_idx - 1] if rates_sorted else 1.0

    # ----- Pass 2: qualify + score + attach signal flags -----
    scored = []
    for c in enriched:
        if not qualifies(c, min_tags=2, top20_eng_rate=top20_rate):
            continue
        final, parts = compute_final_score(c, max_tags, median_abs,
                                           sample_top_engagement=_eng_abs(c))
        scored.append({
            "handle": c["handle"], "niche": c.get("niche", ""),
            "final_score": final, **parts,
            "detected_language": c.get("detected_language", "unknown"),
            "engagement_anomaly": parts["engagement_rate"] > 1.0,   # 4a flag (no drop)
        })
    scored.sort(key=lambda d: d["final_score"], reverse=True)

    # ----- Soft follower gate: default strict, reveal below-floor on slim -----
    above = [d for d in scored if d["followers"] >= min_followers]
    below = [d for d in scored if d["followers"] < min_followers]
    for d in scored:
        d["below_follower_floor"] = d["followers"] < min_followers

    if len(above) >= slim_threshold:
        return above[:top_n]
    return (above + below)[:top_n]
```

- [ ] **Step 6: Update `main` default + CLI default to 10,000**

In `scripts/discovery_score.py`, change `main`'s signature default and the CLI default. Replace lines 128–152 with:

```python
def main(input_path: str, output_path: str, top_n: int, min_followers: int = 10_000) -> None:
    project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    with open(input_path) as f:
        candidates = json.load(f)
    scored = score_handles(candidates, token, top_n, min_followers=min_followers)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2)
    print(f"Wrote {len(scored)} scored handles -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score candidate handles (Phase C)")
    parser.add_argument("--input", default="temp/candidate_handles.json")
    parser.add_argument("--output", default="temp/scored_handles.json")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-followers", type=int, default=10_000,
                        help="prefer candidates at/above this follower count; "
                             "below-floor candidates are revealed when few clear it")
    args = parser.parse_args()
    main(args.input, args.output, args.top_n, min_followers=args.min_followers)
```

- [ ] **Step 7: Run the full discovery_score suite**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: PASS — all new tests + the three updated existing tests + the Task 1/2 tests green.

- [ ] **Step 8: Run the whole suite**

Run: `python -m pytest -q`
Expected: all green, no regressions.

- [ ] **Step 9: Commit**

```bash
git add scripts/discovery_score.py tests/test_discovery_score.py
git commit -m "feat: Phase C hardening — 4b floor, 4a flag, slim-reveal, 10K default"
```

---

## Task 4: Skill wiring — Phase C `--min-followers 10000` + shortlist signals

**Files:**
- Modify: `skills/niche-discovery/SKILL.md` (Phase C section only)

**Interfaces:**
- Consumes: Task 3's `--min-followers 10000` default and the three new shortlist fields.

- [ ] **Step 1: Read the current Phase C section**

Read `skills/niche-discovery/SKILL.md` and locate the `## Phase C — Creator scoring` section (it currently passes `--min-followers 1000`).

- [ ] **Step 2: Update the Phase C command + add signal-presentation guidance**

Replace the `## Phase C — Creator scoring` section's command block and trailing prose with:

```markdown
## Phase C — Creator scoring

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_score.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json" \
  --output "${CLAUDE_PROJECT_DIR}/temp/scored_handles.json" \
  --top-n 10 \
  --min-followers 10000
```
`--min-followers` (default 10,000) prefers established creators. When fewer than
~5 candidates clear it, Phase C reveals the next tier flagged `below_follower_floor`
so you still have a menu instead of an empty result. Lower the flag (e.g. `1000`)
for micro-creator niches.

Present the ranked table with three signals next to each candidate:
`handle  score  followers  LANG  flags` — e.g.
`sunnyame1ia  0.62  8.2K  EN  ⚠below-floor` · `glamwithrida  0.56  1.5K  AR?  ⚠below-floor` ·
`viral_account  0.80  50K  EN  ⚠anomaly`.

At pick time, surface these for the user's decision:
- **LANG** — the user recognizes their target market's language; skip codes that
  don't match (no target-language input is required — codes are advisory).
- **⚠anomaly** — `engagement_rate > 100%`; usually a viral post where likes
  exceeded followers. Consider, don't auto-pick.
- **⚠below-floor** — below the 10K follower preference; consider, don't auto-pick.

User picks 3-5.
```

Leave the rest of the skill (Phase A, Phase B, shortlist+write-config) untouched.

- [ ] **Step 3: Sanity-check**

Run: `python -c "import sys; sys.path.insert(0,'.'); import viral_core; print('ok')"` → `ok`.
Run: `python -m pytest -q` → all green (docs-only change).

- [ ] **Step 4: Commit**

```bash
git add skills/niche-discovery/SKILL.md
git commit -m "feat: skill surfaces Phase C signals (lang/anomaly/below-floor) + 10K default"
```

---

## Self-Review (completed during authoring)

**Spec coverage:**
- 4a (engagement >100% → flag, keep) → Task 3 `test_4a_engagement_anomaly_flag` + `engagement_anomaly` field.
- 4b (abs engagement floor → drop) → Task 3 `MIN_ABS_ENGAGEMENT` + `test_4b_drops_low_absolute_engagement`.
- 4c (cross-hashtag weight redistribution) → Task 1 `test_compute_final_score_single_hashtag_uses_redistributed_weights` + regression test.
- 4d (follower-tiered caps) → Task 1 `_eng_cap` + `test_eng_cap_tiers` + `test_compute_final_score_macro_not_equalized_with_micro`.
- Fix 5 (language flag) → Task 2 `caption_language` + 4 tests; Task 3 attaches field; Task 4 surfaces in shortlist.
- Slim-reveal + 10K default → Task 3 `test_slim_reveal_appends_below_floor_when_above_is_thin`, `test_no_slim_reveal_when_above_floor_is_sufficient`, `test_default_min_followers_is_10000`; Task 4 skill.
- Cohort stats over 4b-survivors, before follower gate → Task 3 (median/top20 computed on `enriched` after the 4b continue, before the follower partition).
- langdetect dep + lazy import → Task 2.
- No Phase B / Phase A / downstream contract changes → confirmed (only `discovery_score.py`, its tests, requirements, skill Phase C section).

**Placeholder scan:** none. Every code step shows complete code; tests are complete with concrete expected values.

**Type/name consistency:** `_eng_cap`, `caption_language`, `MIN_ABS_ENGAGEMENT`, `SLIM_THRESHOLD`, `W_ENG_NOCROSS`/`W_CROSS_NOCROSS`/`W_OUTLIER_NOCROSS`, `ENG_CAP_MICRO`/`ENG_CAP_MID`/`ENG_CAP_MACRO` match across the tasks that define and consume them. `compute_final_score` return shape `(float, dict)` unchanged; `score_handles` returns `list[dict]` with three additive fields. `--min-followers` default `10000` consistent in `score_handles`, `main`, CLI, and the skill.
