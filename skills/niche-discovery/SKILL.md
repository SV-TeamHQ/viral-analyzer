---
name: niche-discovery
description: Discovers trending niches, maps them to Instagram hashtags, extracts and scores creator handles, and writes a ranked shortlist to config/competitors.json. Solves the cold-start problem before /competitor-research. Triggered by "/niche-discovery" or natural language like "find me creators in the X niche", "discover trending niches", or "who should I research on Instagram".
---

# Niche & Creator Discovery

Stage 0 of the viral-analyzer chain. Ends by writing `config/competitors.json`,
which `/competitor-research` reads — no changes to that pipeline.

## Path conventions

- `${CLAUDE_PLUGIN_ROOT}` — read-only plugin code (scripts).
- `${CLAUDE_PROJECT_DIR}` — user project (working data, config, .env, output).

Scripts -> `${CLAUDE_PLUGIN_ROOT}/scripts/discovery_*.py`
Working data -> `${CLAUDE_PROJECT_DIR}/temp/...`
Config -> `${CLAUDE_PROJECT_DIR}/config/competitors.json`
Provenance -> `${CLAUDE_PROJECT_DIR}/output/runs/{ts}/discovery.json`

## First-run setup

1. Python deps: `python -c "import requests, apify_client"`. If missing,
   `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.
2. `APIFY_TOKEN` in `${CLAUDE_PROJECT_DIR}/.env` (required for Phases A, B + C).

## Entry

Ask in two steps.

**Step 1 — niche label** (always; tags the whole run and is written to
`config/competitors.json`):
"What niche are you researching?" (e.g. "home gym", "AI tools", "fitness").

**Step 2 — optional seed creator** (routes Phase B):
"Got a creator in this niche to start from? Paste an Instagram handle
(e.g. `cristiano`), or skip to browse by hashtag."

- **Seed handle given → profile-first Phase B** (bias-free established-peer
  discovery via Instagram's related-accounts graph).
- **Skip → hashtag Phase B** (the existing Phase A → hashtag path).

Capture both: `niche_label` (Step 1) and `seed_handle` (Step 2, may be empty).

## Phase A — IG-native niche discovery

One analytics-actor call on a seed hashtag returns its related hashtags with
real IG volume — those related hashtags *are* the niche candidates. The niche
you pick is already an IG hashtag, so there is no topic→hashtag translation.

Seeded:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_explore_niches.py" \
  --seed "#homegym" \
  --output "${CLAUDE_PROJECT_DIR}/temp/niches.json"
```

Unseeded (pick a category):
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_explore_niches.py" \
  --category fitness \
  --output "${CLAUDE_PROJECT_DIR}/temp/niches.json"
```

Present the volume-ranked niches from `temp/niches.json` (e.g. `homegym 7.6m ·
homeworkout 1.4m · garagegym 580k`). User picks 1–3.

**Optional drill-down:** if the top-level niches feel too broad, re-run Phase A
with one of the picks as the seed (`--seed "#homegym"`) to surface finer
sub-niches before Phase B.

If Phase A returns nothing (analytics actor failed / rate-limited / no token),
fall back to the fast path: the user types a niche → `hashtags_for_niche()`
offline → straight to Phase B. Discovery never hard-fails.

## Phase B (profile-first) — Seed -> related creators

When the user gave a seed handle in Step 2, run the profile-first path instead
of the hashtag path. One scrape of the seed returns its `relatedProfiles`
(Instagram's "similar accounts" — established peers, not whoever posted in
the last 10 minutes).

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_profiles.py" \
  --seed "<handle>" \
  --niche "<niche_label>" \
  --output "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json"
```

The candidate JSON is the same contract the hashtag path writes, so Phase C
consumes it unchanged. Candidates carry no hashtags (Phase C's single-hashtag
weighting from the Phase C hardening handles that).

**If the script exits non-zero** (it prints a cause-named message), the cluster
is thin or the seed was invalid/private. Surface the cause and offer the user
three choices — do not silently switch strategies:
1. **Proceed** with the thin pool (the candidate JSON was still written).
2. **Try a different seed** handle.
3. **Fall back to the hashtag path** for `<niche_label>` (continue to the
   "Phase B — Hashtag" section below).

On a non-thin success, skip straight to Phase C.

## Phase B — Hashtag -> handle discovery

**Confirm the hashtag set, then scrape.** The picked Phase A niches are already
volume-confirmed IG hashtags (the analytics-actor volumes came straight from
Phase A), so there is no separate research step — just hand them through.

1. **Confirm** — show the user the picked Phase A niches (e.g. `#homegym,
   #homeworkout, #garagegym`) and let them edit the set. These tokens, `#`-prefixed,
   are the `--hashtags` value below.

2. **Fallback** (Phase A returned nothing / no token / tiny niche) — use the
   offline generator to preview candidates:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_handles.py" \
     --preview-hashtags --niche "<niche>"
   ```
   Curated niches (e.g. "AI tools", "fitness") return vetted hashtags from
   `${CLAUDE_PLUGIN_ROOT}/config/hashtag_seeds.json`; others are generated.

3. **Scrape** — pass the confirmed hashtag set (the picked Phase A niches,
   `#`-prefixed) through `--hashtags` so the user's choices drive the scrape:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_handles.py" \
     --hashtags "#homegym,#homeworkout,#garagegym" \
     --output "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json"
   ```
   (Omit `--hashtags` to fall back to per-niche generation from `--niches`.)

Note: the actor returns posts as Instagram `owner.id` (no username); Phase C
resolves each id to a real username before writing `competitors.json`.

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

## Shortlist + write config

Ask: "Replace existing competitors or add?" (default: replace).

Write `config/competitors.json` (preserve `posts_per_handle`, `lookback_days` if
replacing; keep their existing values otherwise):
```json
{
  "competitors": [{"handle": "...", "niche": "..."}],
  "posts_per_handle": 10,
  "lookback_days": 365
}
```

Then write the provenance record to `${CLAUDE_PROJECT_DIR}/output/runs/{ts}/discovery.json`:
```json
{
  "stage": "discovery",
  "created_at": "<iso>",
  "niche_seed": "<seed or typed niche>",
  "niches_explored": ["..."],
  "selected_creators": [{"handle": "...", "final_score": 0.0, "niche": "..."}],
  "config_written_to": "config/competitors.json"
}
```

Offer to run `/competitor-research` next.
