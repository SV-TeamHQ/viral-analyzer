---
description: Run the Instagram competitor research pipeline (scrape → rank → download → frames → analyze → report)
argument-hint: [--top-per-handle N]
---

Invoke the `competitor-research` skill to run the full Instagram competitor
research pipeline. Optional argument:

- `--top-per-handle N` — top posts **per handle** to carry through to analysis and the
  report (default **10**). This is a *ceiling*: fewer posts are returned if the scrape
  yielded fewer for a handle. To get more posts, raise `posts_per_handle` in
  `config/competitors.json` and re-run from Phase 1 (scrape).

The lookback window comes from `lookback_days` in `config/competitors.json`
(default **365**), not a CLI flag.

Passes `$ARGUMENTS` through to the skill's orchestration. Alias: `/ig-research`.
