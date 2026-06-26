---
description: Run the Instagram competitor research pipeline (scrape → rank → download → frames → analyze → report)
argument-hint: [--top-per-handle N | --lookback-days N]
---

Invoke the `competitor-research` skill to run the full Instagram competitor
research pipeline. Optional arguments:

- `--top-per-handle N` — top posts per handle to select (default 3)
- `--lookback-days N` — only consider posts from the last N days (default 7)

Passes `$ARGUMENTS` through to the skill's orchestration. Alias: `/ig-research`.
