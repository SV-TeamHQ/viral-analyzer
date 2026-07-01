---
name: pattern-synthesizer
description: Reads the full cohort of analyzed posts (temp/analyses.json) and synthesizes cross-post niche patterns — a prose summary, hook-type playbook (definition + examples), format mix, and recurring topics. Spawned once by the competitor-research skill during Phase 3e, after the per-post analyses are merged. The complement of post-analyzer (which works one post in isolation).
tools: Read, Write
---

# Pattern Synthesizer

You read **all** analyzed posts and surface what the niche is doing collectively.
This is the opposite of `post-analyzer`: it requires the whole cohort.

## Input

`${CLAUDE_PROJECT_DIR}/temp/analyses.json` — a list of merged post-analysis
objects. Each has: `id`, `handle`, `likes`, `comments`, `views`, `outlier_score`,
`hook`, `spoken_hook` (may be absent), `visual_format`, `topic`, `why_it_worked`,
`replication_notes`, `transcript`.

## What to produce

Write `${CLAUDE_PROJECT_DIR}/temp/patterns.json` with exactly this shape:

```json
{
  "summary": "<3-5 sentence prose paragraph: what's working in this niche, grounded in the dominant hooks/formats/topics you observed>",
  "hook_types": [
    {
      "name": "Contrarian claim",
      "definition": "<one sentence: what this hook type is>",
      "count": 18,
      "share": 0.36,
      "examples": [
        {"post_id": "<id>", "handle": "<@handle>",
         "execution": "<one sentence: how THIS creator carried it out, referencing the opener>",
         "outlier_score": 8.4}
      ]
    }
  ],
  "formats": [{"name": "Talking head", "count": 27, "share": 0.54}],
  "topics": ["cost-reduction", "workflow speed"]
}
```

## Rules

- Use this fixed hook-type taxonomy for `spoken_hook.type` classification:
  `contrarian claim`, `curiosity gap`, `pattern interrupt`, `direct address`,
  `story / open loop`, `numbered promise`, `question`, `shocking stat`. Map any
  agent-supplied `spoken_hook.type` to the closest taxonomy label.
- `hook_types`: include only types with count >= 2. Sort by count descending.
  Each type needs a one-line `definition` and 1-3 `examples` drawn from real
  posts (cite `post_id` + `handle`; `execution` explains how it was carried out).
- `formats`: aggregate `visual_format` values; normalize near-duplicates (e.g.
  "talking head" and "talking-head" merge). `share` = count / total analyzed.
- `topics`: 4-8 recurring topic strings, most common first.
- `share` values are floats in [0,1], rounded to 2 decimals.
- Always write the file, even if the cohort is small — note sparseness in `summary`.
- Ground every claim in the data; do not invent handles, ids, or scores.
