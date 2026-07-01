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

- **Fast path** — user types a niche: skip Phase A; seed Phase B with it.
- **Discovery path** — run Phase A, present top 10 niches, user picks 1-3.

## Phase A — Trend signals

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_pull_trends.py" \
  --seed "<optional broad category>" \
  --output "${CLAUDE_PROJECT_DIR}/temp/niches.json"
```
Present top 10; user picks 1-3.

## Phase B — Hashtag -> handle discovery

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_handles.py" \
  --niches "${CLAUDE_PROJECT_DIR}/temp/niches.json" \
  --output "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json"
```

## Phase C — Creator scoring

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_score.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json" \
  --output "${CLAUDE_PROJECT_DIR}/temp/scored_handles.json" \
  --top-n 10
```
Present the ranked table (rank, handle, score, eng rate, hashtags, followers).
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
