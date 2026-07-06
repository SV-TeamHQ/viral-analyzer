# Phase C Hardening — Design Spec

**Date:** 2026-07-06
**Status:** Approved (pending user review of written spec)
**Scope:** Harden `/niche-discovery` Phase C (`discovery_score.py`) — fix the scoring formula's micro-account bias and dead cross-hashtag weight, raise the follower floor with a slim-reveal, and add language + engagement-anomaly signal flags to the shortlist. All changes are Phase C-local and correct regardless of what Phase B returns.

**Out of scope:** the Phase B pool-quality root cause (recent-feed micro-bias, `sections` input, top-posts actor) is **Spec B** — a separate brainstorm. This spec (Spec A) deliberately does not touch Phase B; it makes the *current* Phase C output honest and pickable, and every fix here stays correct once Spec B improves the candidate pool.

---

## Overview

The 2026-07-06 discovery-quality-report identified that Phase C's scoring compounds Phase B's micro-account bias: soft caps equalize micro- and macro-accounts (a 723% engagement artifact scored 0.8), the 40% cross-hashtag weight is dead weight in every run (single-hashtag candidate pools), and there is no absolute-engagement floor. Separately, the recurring off-market-creator gap (a Telugu creator passing every gate) has no language signal at all.

This spec fixes those. It introduces a **gate-vs-flag distinction** that runs through the whole design:

- **Objective quality floors → drop.** A dead account (avg <100 engagement) or a tiny account (<10K followers by default) is a non-judgment call, consistent with the existing `--min-followers` gate. Near-zero false-positive risk.
- **Relevance/judgment signals → flag.** Caption language and >100% engagement have real false-positive risk (bilingual creators; genuinely-viral accounts where likes legitimately exceed followers). These are surfaced in the shortlist for the user to decide at pick time — nothing is auto-rejected on these axes.

One refinement to the follower gate: rather than a hard 10K floor returning empty results on a micro-biased pool, the gate is **soft with reveal-on-slim** — if fewer than 5 candidates clear it, the sub-10K candidates are re-added (flagged) so the user has a visible menu instead of a dead end.

### Key decisions

- **4a (engagement >100%): flag, don't alter the score or drop.** Keep raw `engagement_rate`; set `engagement_anomaly = eng_rate > 1.0`; surface ⚠ in the shortlist.
- **4b (absolute engagement floor): hard drop.** `MIN_ABS_ENGAGEMENT = 100`; candidates with avg `(likes + comments) < 100` are removed in Pass 1.
- **4c (cross-hashtag weight redistribution).** When `max_tags < 2`, effective weights `W_ENG=0.7, W_CROSS=0.0, W_OUTLIER=0.3`; otherwise the existing `0.4 / 0.4 / 0.2`. No dropping.
- **4d (follower-tiered engagement caps).** `eng_cap = 0.10` (<10K), `0.08` (10K–100K), `0.05` (100K+); `eng_norm = min(eng_rate / eng_cap, 1.0)`. No dropping.
- **Default `--min-followers` raised 1,000 → 10,000**, with slim-reveal: if the qualifying set is `< SLIM_THRESHOLD (5)`, sub-10K candidates are appended, each flagged `below_follower_floor: true`.
- **Fix 5 (language): flag.** Detect caption language via `langdetect`; surface ISO code in the shortlist. No target-language input, no auto-rejection.
- **Cohort statistics are computed over everyone passing the 4b floor**, before the follower gate, so below-floor candidates still get a fair score for display. The follower gate affects *revelation*, not *scoring*.

---

## Architecture

All changes are inside `scripts/discovery_score.py` (and its tests). No change to Phase A, Phase B, the skill's Phase A/B orchestration, the data contract downstream of `temp/scored_handles.json`, or `config/competitors.json`. The skill's Phase C command gains `--min-followers 10000` as the default invocation and the shortlist presentation gains three signal columns.

### Scoring flow (revised `score_handles`)

```
Pass 1 — enrich every candidate via profile scrape (unchanged)
   compute followers, avg_likes, avg_comments from latestPosts[] (unchanged)
   ▼
Hard floor — 4b: drop candidates with avg(likes+comments) < MIN_ABS_ENGAGEMENT (100)
   ▼
Cohort stats — computed over everyone who passed 4b
   median_abs, top20_rate  (unchanged definitions)
   ▼
Score everyone — compute_final_score with:
     4d: follower-tiered eng_cap
     4c: redistributed weights if max_tags < 2
   attach language (Fix 5) + engagement_anomaly (4a) fields
   ▼
Soft follower gate — partition by min_followers (default 10000):
     above_floor = scored with followers >= min_followers
     below_floor = scored with followers <  min_followers  (flag below_follower_floor=True)
   if len(above_floor) >= SLIM_THRESHOLD (5): return above_floor
   else: return above_floor + below_floor   (below flagged, so the user can relax the gate manually)
   ▼ truncate to top_n, sorted by final_score
```

---

## Components

All edits in `scripts/discovery_score.py` unless noted.

### New constants

```python
MIN_ABS_ENGAGEMENT = 100        # 4b — avg likes+comments floor
SLIM_THRESHOLD = 5              # below-floor candidates revealed when above-floor count < this
# Follower-tiered engagement caps (4d)
ENG_CAP_MICRO = 0.10            # < 10K followers
ENG_CAP_MID   = 0.08            # 10K–100K
ENG_CAP_MACRO = 0.05            # 100K+
# Effective weights when cross-hashtag is structurally impossible (4c)
W_ENG_NOCROSS, W_CROSS_NOCROSS, W_OUTLIER_NOCROSS = 0.7, 0.0, 0.3
```

Existing `W_ENG = 0.4`, `W_CROSS = 0.4`, `W_OUTLIER = 0.2` stay as the multi-hashtag weights.

### `caption_language(prof, max_captions=5) -> str` (new, Fix 5)

```python
def caption_language(prof: dict, max_captions: int = 5) -> str:
    """Modal ISO language code across recent captions; 'unknown' if none/detection fails.
    langdetect is imported lazily so the module loads without it installed."""
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

### `compute_final_score` (revised — 4c + 4d)

```python
def _eng_cap(followers: int) -> float:
    if followers >= 100_000:
        return ENG_CAP_MACRO
    if followers >= 10_000:
        return ENG_CAP_MID
    return ENG_CAP_MICRO

def compute_final_score(c, max_tags, median_engagement, sample_top_engagement):
    followers = c.get("followers") or 1
    eng_rate = (c.get("avg_likes", 0) + c.get("avg_comments", 0)) / followers
    cross = len(c.get("hashtags", []))
    cross_norm = min(cross / max_tags, 1.0) if max_tags else 0.0
    outlier_pot = outlier_score(sample_top_engagement, median_engagement) if median_engagement else 0.0

    eng_norm = min(eng_rate / _eng_cap(followers), 1.0)          # 4d
    out_norm = min(outlier_pot / 5.0, 1.0)

    if max_tags < 2:                                               # 4c
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

### `score_handles` (revised — 4b hard floor, signal flags, soft follower gate)

Signature gains a `slim_threshold` parameter; `min_followers` default rises to `10000`:

```python
def score_handles(candidates, token, top_n=10, min_followers=10_000, slim_threshold=SLIM_THRESHOLD):
    max_tags = max((len(c.get("hashtags", [])) for c in candidates), default=1) or 1

    # Pass 1 — enrich (the run_actor profile-scrape + latestPosts parsing is
    # UNCHANGED from the current code; only the lines below are added/changed)
    enriched = []
    for c in candidates:
        # ... existing run_actor(PROFILE_ACTOR, {"usernames":[c["handle"]]}) + _avg_engagement ...
        c["followers"] = prof.get("followersCount", 0) or 0
        c["avg_likes"], c["avg_comments"] = _avg_engagement(prof)
        if (c["avg_likes"] + c["avg_comments"]) < MIN_ABS_ENGAGEMENT:   # 4b hard floor
            continue
        c["detected_language"] = caption_language(prof)                 # Fix 5
        enriched.append(c)
    if not enriched:
        return []

    # Cohort stats over 4b-survivors
    median_abs = median(_eng_abs(c) for c in enriched)
    rates_sorted = sorted(_eng_rate(c) for c in enriched)
    top20_rate = rates_sorted[max(1, len(rates_sorted) - max(1, len(rates_sorted)//5)) - 1] if rates_sorted else 1.0

    # Score everyone, attach signal flags
    scored = []
    for c in enriched:
        if not qualifies(c, min_tags=2, top20_eng_rate=top20_rate):
            continue
        final, parts = compute_final_score(c, max_tags, median_abs, _eng_abs(c))
        scored.append({
            "handle": c["handle"], "niche": c.get("niche", ""),
            "final_score": final, **parts,
            "detected_language": c.get("detected_language", "unknown"),
            "engagement_anomaly": parts["engagement_rate"] > 1.0,        # 4a
        })

    scored.sort(key=lambda d: d["final_score"], reverse=True)
    above = [d for d in scored if d["followers"] >= min_followers]
    below = [d for d in scored if d["followers"] <  min_followers]
    for d in below:
        d["below_follower_floor"] = True
    for d in above:
        d["below_follower_floor"] = False

    if len(above) >= slim_threshold:
        return above[:top_n]
    return (above + below)[:top_n]    # reveal below-floor so the user can relax the gate
```

`qualifies()` is unchanged (≥2 hashtags OR top-20% engagement). `main()` passes `min_followers` (default 10000) and the new default flows through. The CLI `--min-followers` default becomes `10000`.

### Dependency

`requirements.txt` — add `langdetect>=1.0.9`. Imported lazily inside `caption_language` so the module still loads if it's absent.

---

## Data contract

The scored-output dict (`temp/scored_handles.json`) gains three optional fields. All existing fields are unchanged; consumers that ignore the new fields are unaffected.

```json
{
  "handle": "sunnyame1ia",
  "niche": "makeuptutorial",
  "final_score": 0.62,
  "engagement_rate": 0.121,
  "followers": 8200,
  "cross_hashtag_count": 1,
  "outlier_potential": 1.4,
  "detected_language": "en",
  "engagement_anomaly": false,
  "below_follower_floor": true
}
```

`below_follower_floor` is always present (True/False). `detected_language` is `"unknown"` when captions are absent or langdetect unavailable. `engagement_anomaly` is True when raw `engagement_rate > 1.0`.

---

## Testing

TDD throughout, real-shape fixtures (the standing lesson from the 2026-07-01 bug arc). Extend `tests/test_discovery_score.py`. Existing tests that call `compute_final_score`/`qualifies` directly may need expected-value updates because of 4c/4d — update them with the new math, preserving their intent.

- **4a** — a profile whose computed `engagement_rate > 1.0` (e.g. 2K followers, 30K avg likes) → kept in output, `engagement_anomaly == True`.
- **4b** — a profile with avg `(likes+comments) < 100` → dropped (absent from output).
- **4c** — single-hashtag pool (`max_tags < 2`): assert `compute_final_score` equals `0.7*eng_norm + 0*cross + 0.3*out_norm` on a known input. Multi-hashtag pool: equals the original `0.4/0.4/0.2` formula.
- **4d** — `(100K followers, 5% eng)` and `(5K followers, 10% eng)` produce equal `eng_norm` (both saturate at 1.0 against their tier caps).
- **Fix 5** — mock `latestPosts` captions in English / Arabic / empty → `detected_language` returns `"en"` / `"ar"` / `"unknown"`. (Patch `langdetect.detect` so the test doesn't depend on the library's runtime behavior beyond import.)
- **Slim-reveal** — `score_handles(..., min_followers=10_000, slim_threshold=5)` with only 2 above-floor candidates → below-floor candidates appended with `below_follower_floor == True`; with ≥5 above-floor → no below-floor candidates returned.
- **Default floor** — `score_handles(candidates, token)` with no `min_followers` uses `10_000`.

---

## Skill wiring (`skills/niche-discovery/SKILL.md`, Phase C)

- The Phase C command passes `--min-followers 10000` (was 1000). Lowering it remains an escape hatch for micro-creator niches.
- The shortlist presentation shows three signals next to each candidate:
  `sunnyame1ia  0.62  8.2K  EN  ⚠below-floor` / `glamwithrida  0.56  1.5K  AR?  ⚠below-floor` / `viral_account  0.80  50K  EN  ⚠anomaly`
- Instruct Claude to surface these at pick time: the user recognizes their own target market's language from the codes (e.g. an English-market user skips `AR?`/`TL?`), and treats `⚠anomaly` and `⚠below-floor` as "consider, don't auto-pick." No target-language input is required — the codes are advisory.

---

## Error handling

- `langdetect` not installed / fails / empty captions → `caption_language` returns `"unknown"`; the candidate is kept and flagged `"unknown"`, not dropped (language is a flag, not a gate).
- Cohort stats over a single 4b-survivor → `median_abs` = that candidate's engagement (outlier_potential = 1.0, harmless); `top20_rate` index guard already handles small N.
- Below-floor reveal only triggers when above-floor is slim; if the entire pool is below-floor (typical today), the user gets the full below-floor shortlist flagged, not an empty result.

---

## Verification

1. **Unit suite:** `python -m pytest tests/test_discovery_score.py -v` — green, real-shape fixtures, all seven new/updated cases pass.
2. **Full suite:** `python -m pytest -q` — no regressions elsewhere.
3. **End-to-end manual run** (token required) on a beauty/fitness niche:
   - Confirm the shortlist surfaces `detected_language`, `⚠anomaly`, and `⚠below-floor` signals.
   - Confirm a run on today's micro-biased pool returns a flagged below-floor shortlist (not empty), and a run that finds ≥10K creators returns only above-floor.
4. **Negative check:** feed a candidate with avg engagement < 100 → confirm it's dropped; feed a 723%-engagement candidate → confirm it's kept with `engagement_anomaly == True` and the *score* isn't nonsensically inflated.
