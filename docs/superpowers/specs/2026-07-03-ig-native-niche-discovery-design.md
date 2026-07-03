# IG-Native Niche Discovery — Design Spec

**Date:** 2026-07-03
**Status:** Approved (pending user review of written spec)
**Scope:** Replace Phase A's external trend sources (pytrends + Reddit) with a single IG-native operation built on the already-integrated `apify/instagram-hashtag-analytics-scraper`. Collapse Phase A and the hashtag-research step into one operation. Drop all non-Apify Phase A dependencies.

---

## Overview

Today, `/niche-discovery` Phase A pulls trend signals from **outside** Instagram — Google Trends (pytrends) and optionally Reddit (praw) — then maps the resulting topics *back* to IG hashtags. That translation step is the root of repeated failures: pytrends returns purchase-oriented search queries (the 2026-07-02 run found 7/10 results off-topic), and Reddit's API access has become hard to obtain. Every external source introduces a topic→hashtag translation gap and its own failure mode.

This spec makes Phase A **fully IG-native**: it discovers niches *inside* Instagram by reading the analytics actor's `related[]` hashtags (with real IG volume). The niche the user picks **is** an IG hashtag — there is no translation step. As a side effect, Phase A (niche discovery) and the existing hashtag-research step become the **same operation**: one analytics-actor call surfaces related hashtags that serve as both the niches to pick and the hashtags Phase B scrapes.

### Key decisions

- **IG-native, single actor.** Phase A uses `apify/instagram-hashtag-analytics-scraper` (already integrated, probed, live-tested in `discovery_hashtag_research.py`). No new actor.
- **Two entry modes, one code path.** Seeded (user has a niche/keyword/hashtag) and Unseeded (user picks a broad category). Both resolve to a seed hashtag and call the same function.
- **The niche is the hashtag.** Output niches are IG hashtags rendered as clean phrases (`#garagegym` → `"garage gym"`). They feed Phase B directly with no remapping.
- **Phase A and hashtag-research collapse into one step.** The flow becomes: analytics actor on seed → pick niches (= hashtags) → scrape. The separate pre-Phase-B hashtag-research step is absorbed.
- **Drop external deps.** `discovery_pull_trends.py`, `pytrends`, and `praw` are removed. Phase A's only external credential is `APIFY_TOKEN`.
- **Trending scraper deferred.** `agentx/instagram-trending-scraper` (true Explore-feed trending) is **not** integrated. It remains a documented future "true trending" power-up if category-driven discovery proves too narrow.

---

## Architecture

```
/niche-discovery entry
   │
   ├─ SEEDED    (user has a niche / keyword / hashtag)
   │     input → hashtags_for_niche() → seed hashtag  (e.g. "#homegym")
   │
   └─ UNSEEDED  (pure discovery — "show me options")
         user picks a broad category from a curated list
         (Fitness, Tech, Food, Finance, Beauty, Gaming, Travel, Business)
         category → its mega-hashtag  (e.g. "#fitness")
   │
   ▼  ONE analytics-actor call on that seed hashtag
   ▼  via discovery_hashtag_research.research_hashtags()
   ▼  returns related[] hashtags with real IG volume
   ▼
   present as niche candidates ranked by volume:
      "homegym 7.6m · homeworkout 1.4m · garagegym 580k …"
   ▼
   user picks 1–3
   ▼  (optional drill: re-run the actor on a pick for finer sub-niches)
   ▼
   picked hashtags feed straight into Phase B
      (discovery_handles.py --hashtags …)
```

### How it slots into the current system

- **Output contract unchanged.** `temp/niches.json` still holds `{niche, trend_score, sources}` objects; `discovery_handles.py` still reads `n["niche"]`. Downstream is untouched.
- **`discovery_hashtag_research.py` is reused as-is** (it already calls the analytics actor and parses `related[]` + volumes). The new script is a thin wrapper that reshapes its output into the niche contract.
- **`discovery_pull_trends.py` is removed.** Phase A no longer depends on any non-Apify service.

---

## Components

### New: `scripts/discovery_explore_niches.py`

The IG-native Phase A. A thin wrapper over the existing analytics-actor call.

```python
from viral_core.apify_client import run_actor  # used transitively via research_hashtags
from scripts.discovery_hashtag_research import research_hashtags

ANALYTICS_ACTOR = "apify/instagram-hashtag-analytics-scraper"

CATEGORIES = {
    "fitness": "#fitness", "tech": "#tech", "food": "#food",
    "finance": "#personalfinance", "beauty": "#makeup", "gaming": "#gaming",
    "travel": "#travel", "business": "#entrepreneur",
}


def explore_niches(seed_hashtag: str, token: str, top_n: int = 10) -> list[dict]:
    """IG-native Phase A. Calls the analytics actor on a seed hashtag and
    returns its related hashtags (with real volume) as niche candidates.

    Output matches the existing temp/niches.json contract:
        [{niche, trend_score, sources}]

    `niche` is the related hashtag token, #-stripped (e.g. 'homegym'). Real IG
    related hashtags are concatenated tokens with no separators (#dataanalytics,
    #opensource), so no word-splitting is attempted — the token is displayed
    as-is and re-prefixed with '#' at Phase B handoff (lossless round-trip).
    """
    ranked = research_hashtags(seed_hashtag, token, top_n=top_n)
    return [
        {
            "niche": h["hashtag"].lstrip("#"),
            "trend_score": h["volume"],
            "sources": ["instagram"],
        }
        for h in ranked
    ]


def main(seed=None, category=None, output_path="temp/niches.json", top_n=10):
    # Resolve the seed hashtag: from --seed directly, or from --category via
    # CATEGORIES. Load .env (parent.parent of output_path), read APIFY_TOKEN,
    # call explore_niches, write temp/niches.json. On empty result, print a
    # clear message and write [].
```

- **CLI:** `--seed "#homegym"` (seeded) **or** `--category fitness` (unseeded), `--top-n 10`, `--output temp/niches.json`.
- Loads `.env` via the `parent.parent` project-dir pattern used by the other discovery scripts, then reads `APIFY_TOKEN`.

### Existing, reused unchanged
- `scripts/discovery_hashtag_research.py` — `research_hashtags(seed, token, top_n)` + `parse_volume()`. Already tested with the real analytics-actor shape.
- `scripts/discovery_handles.py` — Phase B, including the `--hashtags` override (so user-confirmed niches drive scraping directly).
- `scripts/hashtags_for_niche()` (in `discovery_handles.py`) + `config/hashtag_seeds.json` — maps a typed niche/keyword to a seed hashtag for seeded mode.

### Removed
- `scripts/discovery_pull_trends.py`
- `tests/test_discovery_pull_trends.py`
- `pytrends>=4.9.0` and `praw>=7.7.0` from `requirements.txt`
- Reddit credential note from `.env.example` (Phase A no longer uses Reddit)

---

## Data contract

`temp/niches.json` (shape unchanged from today; only the values/source label change):

```json
[
  {"niche": "homegym", "trend_score": 7600000, "sources": ["instagram"]},
  {"niche": "homeworkout", "trend_score": 1400000, "sources": ["instagram"]},
  {"niche": "garagegym", "trend_score": 580000, "sources": ["instagram"]}
]
```

- `niche` — the related hashtag token, `#`-stripped (e.g. `"homegym"`). Real IG related hashtags are concatenated tokens without separators, so no word-splitting is attempted; the token is displayed as-is.
- `trend_score` — the related hashtag's parsed IG volume (an absolute count, e.g. 7,600,000). This is **popularity** (established volume), not rising/heat. Sufficient and arguably better for competitor research (stable niches with real creators).
- `sources` — `["instagram"]` (was `["google_trends"]` / `["reddit"]`).

Because Phase B accepts the picked niches directly via `--hashtags`, the niche tokens are re-prefixed with `#` at handoff (`"homegym"` → `#homegym`) — a trivial, lossless round-trip.

### Drill-down (optional, skill-orchestrated)

After the user picks a niche (e.g. `"garage gym"`), the skill may re-run `discovery_explore_niches.py --seed "#garagegym"` to surface finer sub-niches (`#garagegymtour`, `#powerslifting`, …) before Phase B. Same script, same call — just a narrower seed. Not required; the skill offers it when the top-level niches feel too broad.

---

## Entry modes

The skill branches at `/niche-discovery` entry:

- **Seeded** — *"Have a niche in mind?"* The user types a niche, keyword, or hashtag. `hashtags_for_niche(input)` resolves it to a seed hashtag (curated seed map first, string-generator fallback — the existing behavior).
- **Unseeded** — *"Want to browse trending categories?"* The skill presents the `CATEGORIES` list; the user picks one; its mega-hashtag is the seed.

Both modes then call `explore_niches(seed_hashtag, token)` and present the volume-ranked results. The only difference is how the seed hashtag is chosen.

---

## Error handling

Mirrors the existing graceful-degradation pattern (every external call wrapped, failures return `[]` + a visible message rather than crashing):

| Scenario | Behavior |
|---|---|
| Analytics-actor fails / rate-limited / Apify down | `research_hashtags` returns `[]` → `explore_niches` returns `[]` → script prints `"IG niche discovery unavailable: <reason>. Try a different seed/category or check APIFY_TOKEN."` and writes an empty `temp/niches.json`. |
| Empty/invalid seed or category | Same: `[]` + message. |
| No `APIFY_TOKEN` | `run_actor` raises `RuntimeError("APIFY_TOKEN not set")`; the skill surfaces it. |
| Discovery returns nothing | The skill falls back to the **fast path**: user types a niche directly → `hashtags_for_niche()` offline → Phase B. Discovery never hard-fails the run. |

---

## Testing

TDD throughout, with fixtures using the **real analytics-actor shape** (the lesson from the 2026-07-01 bug arc: invented fixture shapes give false confidence).

- **`tests/test_discovery_explore_niches.py`** (new) — mocks `research_hashtags` with the real probed shape (`[{hashtag, volume, source}]`), asserts:
  - niches ranked by parsed volume,
  - `niche` is the related hashtag token, `#`-stripped (e.g. `"homegym"`),
  - `sources == ["instagram"]`,
  - `top_n` truncation,
  - empty list on failure,
  - category → seed-hashtag resolution for unseeded mode.
- **`tests/test_discovery_hashtag_research.py`** — reused unchanged (covers `parse_volume` + `research_hashtags`).
- **`tests/test_discovery_integration.py`** — already covers the analytics actor's live shape; no new live test needed.
- **Removed:** `tests/test_discovery_pull_trends.py`.

---

## Skill rewiring (`skills/niche-discovery/SKILL.md`)

- Replace the Phase A `discovery_pull_trends.py` call with `discovery_explore_niches.py`.
- Entry branches: seeded (keyword/hashtag) vs unseeded (category list).
- After presenting volume-ranked niches: user picks 1–3 → optional drill-down → Phase B with `--hashtags` set to the picked niches (since they are already hashtags).
- First-run setup: drop the pytrends/praw dep check; `APIFY_TOKEN` is now the only external credential Phase A needs.

---

## Out of scope

- **`agentx/instagram-trending-scraper`** (true Explore-feed trending with topic labels) is **not** integrated. It remains a documented future power-up if category-driven discovery (Mode: unseeded) proves too narrow. Adding it later is additive — it would slot in as an alternative seed source, not require rework.
- The broader "relevance" gaps from the 2026-07-02 run analysis (audience/language filtering, content-style tags, consistency score, hollow Niche Patterns section) are **separate specs**; this one is scoped strictly to the IG-native Phase A swap.

---

## Verification

1. **Unit suite:** `python -m pytest tests/test_discovery_explore_niches.py tests/test_discovery_hashtag_research.py -v` — green, fixtures mirror the real analytics-actor shape.
2. **Full suite:** `python -m pytest -q` — no regressions; `test_discovery_pull_trends.py` removed cleanly.
3. **Live integration (token required):** `APIFY_TOKEN=... python -m pytest tests/test_discovery_integration.py -v` — confirms the analytics actor still returns the expected `postsCount` + `related[]` shape.
4. **End-to-end manual run** with a real token:
   - Seeded: `/niche-discovery` → type "home gym" → confirm the seed hashtag (`#homegym`) → confirm niches are volume-ranked IG hashtags → pick → Phase B scrapes real handles.
   - Unseeded: `/niche-discovery` → pick "Fitness" category → confirm related hashtags with volume → pick → drill (optional) → Phase B.
5. **Negative check:** run with a dead/invalid seed → confirm graceful `[]` + message + fast-path fallback, not a crash.
6. **Dep cleanup:** confirm `pip install -r requirements.txt` no longer pulls pytrends/praw, and that no remaining code imports them.
