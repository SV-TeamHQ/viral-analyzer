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

1. Python deps: `python -c "import requests, apify_client, pytrends"`. If missing,
   `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.
2. `APIFY_TOKEN` in `${CLAUDE_PROJECT_DIR}/.env` (required for Phases B + C).
3. Reddit is optional: `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` enable Phase A's
   Reddit signal. Absent -> Phase A runs on Google Trends only.

## Entry

Ask: "Do you have a niche in mind, or should I discover trending niches for you?"

- **Fast path** — user types a niche: skip Phase A; seed Phase B with it. A niche
  is required here (the scripts no longer fabricate a default).
- **Discovery path** — ask for a broad category seed (e.g. "AI", "fitness") —
  required for Google Trends. Run Phase A, present top 10 niches, user picks 1-3.

> **Reddit signal:** if the user chose discovery AND `REDDIT_CLIENT_ID`/`SECRET`
> are absent, warn them: "Phase A will run on Google Trends only — add Reddit
> creds to `.env` for richer niche signals." The script prints this too.

## Phase A — Trend signals

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_pull_trends.py" \
  --seed "<broad category, e.g. AI>" \
  --output "${CLAUDE_PROJECT_DIR}/temp/niches.json"
```
A non-empty seed is required. Present top 10; user picks 1-3.

## Phase B — Hashtag -> handle discovery

**Research hashtag volumes, then confirm, then scrape.** This avoids burning
Apify calls on dead/off-topic hashtags.

1. **Research** — pick a seed hashtag for the niche (a curated one from
   `hashtags_for_niche()`, or one the user suggests) and pull real Instagram
   volumes + related hashtags:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_hashtag_research.py" \
     --seed "<seedhashtag>" --top-n 10
   ```
   Prints `<hashtag> <volume> (seed|related)` lines, ranked by volume. Present
   the list and let the user pick/edit a confirmed set.

2. **Fallback** (research empty/failed, no token, or tiny niche) — use the
   offline generator to preview candidates:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_handles.py" \
     --preview-hashtags --niche "<niche>"
   ```
   Curated niches (e.g. "AI tools", "fitness") return vetted hashtags from
   `${CLAUDE_PLUGIN_ROOT}/config/hashtag_seeds.json`; others are generated.

3. **Scrape** — pass the confirmed hashtag set through `--hashtags` so the
   user's choices (not the generated defaults) drive the scrape:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_handles.py" \
     --hashtags "#aitools,#chatgpt,#aiproductivity" \
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
