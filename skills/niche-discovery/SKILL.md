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

Ask: "Have a niche in mind, or want to browse trending categories?"

- **Seeded** — user types a niche, keyword, or hashtag (e.g. "home gym", "#fitness",
  "AI tools"). Resolve it to a seed hashtag via `hashtags_for_niche()` and pass it
  to Phase A as `--seed`.
- **Unseeded** — user wants options. Present the 17 broad categories (Fitness, Tech,
  Food, Finance, Beauty, Gaming, Travel, Business, AI, Fashion, Health & Wellness,
  Photography, Real Estate, Pets, Music, Cars, Apps); the picked category becomes
  Phase A's `--category`.

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
  --min-followers 1000
```
`--min-followers` (default 1000) drops tiny accounts that would otherwise score
alongside established creators. Lower it to surface micro-creators. Present the
ranked table (rank, handle, score, eng rate, hashtags, followers). User picks 3-5.

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
