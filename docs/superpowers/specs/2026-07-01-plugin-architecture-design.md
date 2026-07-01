# Viral-Analyzer Plugin Architecture — Design Spec

**Date:** 2026-07-01
**Status:** Approved (pending user review of written spec)
**Approach:** Chained-stages architecture over a shared `viral_core` package, with durable run artifacts and an additive report redesign. Integrates the previously-approved `/niche-discovery` pipeline as stage 0 and establishes conventions for future stages.

---

## Overview

The viral-analyzer plugin grows from a single standalone pipeline (`/competitor-research`) into a **chain of stage-skills**: each stage consumes the previous stage's output, shares common logic through a small `viral_core` package, and writes durable artifacts so the chain survives cleanup and re-runs.

The immediate work has two parts:

1. **Architecture refactor** — introduce `viral_core`, durable run artifacts, and stage conventions.
2. **Niche-discovery integration** — land the `/niche-discovery` pipeline (per `2026-06-30-niche-discovery-design.md`) as stage 0, reusing `viral_core`.
3. **Report redesign** — an additive, cross-post "Niche Patterns" synthesis layer and a richer per-post spoken-hook block.

Future stages (content-ideation, hook-testing, posting-strategy) are **out of scope** to design here — only the conventions that let them slot in.

### Key decisions

- **Chained stages, one end-to-end flow.** `/niche-discovery` → `/competitor-research` → (future stages). Each stage is its own skill + command; no master orchestrator in this spec.
- **Durable stage artifacts.** Each stage writes a versioned record to `output/runs/{date}_{HHMM}/`. Throwaway intermediates stay in `temp/`. The chain's handoffs never live in disposable storage.
- **Two handoff seams, by nature of the data.** Discovery → research hands off *config* (`config/competitors.json` — which creators). Research → future stages hands off *data* (`output/runs/{ts}/research.json` — analyzed posts).
- **Shared `viral_core` package.** Apify client, scoring formula, config/env IO, and run-path logic live in one place. Scripts import it via a 2-line `sys.path` bootstrap — no build step, no `pip install -e`.
- **Flat scripts, stage-prefixed names going forward.** Existing scripts keep their names so the shipped `competitor-research` paths don't break; new scripts use a `discovery_*` prefix. Future stages follow the same convention.
- **Report redesign is strictly additive.** One new top section (prose summary + pattern statistics + expandable hook playbook) and one new per-post block (spoken hook). Nothing in the current card is removed.

---

## End-to-end flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 0 — DISCOVERY          /niche-discovery                       │
│  "I don't know who to research yet"                                  │
└─────────────────────────────────────────────────────────────────────┘
   /niche-discovery  (or "find me creators in the X niche")
        │  Skill asks: known niche, or discover trending ones?
        ├─ FAST PATH: user types a niche → skip Phase A
        └─ DISCOVERY PATH: user says "discover"
              │
              ▼  discovery_pull_trends.py     (Google Trends + Reddit)
                 temp/niches.json → user picks 1–3 niches
              ▼  discovery_handles.py         (Apify hashtag scrape)
                 temp/candidate_handles.json
              ▼  discovery_score.py           (Apify profile scrape + scoring)
                 temp/scored_handles.json → top 10 presented
        │
   User picks 3–5 handles; "replace" vs "add" (default replace)
        │
        ▼  Skill writes → config/competitors.json            ◄── DURABLE HANDOFF #1
                          └─ output/runs/{ts}/discovery.json   (audit record)

═══════════════════════════════════════════════════════════════════════
   (chain survives — competitors.json is durable; temp/ may be wiped)
═══════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1 — RESEARCH           /competitor-research   (existing)      │
│  "Tell me why their top posts performed"                             │
└─────────────────────────────────────────────────────────────────────┘
   /competitor-research
        ▼  Reads config/competitors.json
        Phase 1  scrape_instagram.py     → temp/raw_posts.json
        Phase 2  rank_and_select.py      → temp/selected_posts.json   (uses viral_core.scoring)
        Phase 3a download_media.py       → temp/media/
        Phase 3b extract_frames.py       → temp/frames/, temp/audio/
        Phase 3c transcribe_audio.py     → temp/transcripts/
        Phase 3d post-analyzer agents    → temp/analyses/{id}.json    (expanded schema)
                  merge_analyses.py      → temp/analyses.json
        Phase 3e pattern-synthesizer     → patterns block (NEW)
        Phase 4  generate_report.py      → report .html + .pdf (redesigned)
        ▼  Skill writes → output/runs/{ts}/research.json      ◄── DURABLE HANDOFF #2
                          └─ report .html/.pdf (inside the same run dir)

═══════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 2+ — FUTURE (not built; architecture supports them)           │
└─────────────────────────────────────────────────────────────────────┘
   /content-ideation    reads runs/{ts}/research.json → runs/{ts}/ideation.json
   /hook-testing        reads runs/{ts}/ideation.json → runs/{ts}/hooks.json
   /posting-strategy    reads runs/{ts}/research.json → runs/{ts}/strategy.json
        ...each a new skill + stage-prefixed scripts, importing viral_core...
```

---

## Plugin structure (target)

```
viral-analyzer/
├── viral_core/                         ← NEW: shared package
│   ├── __init__.py                        # re-exports public surface
│   ├── apify_client.py                    # one Apify actor-runner
│   ├── scoring.py                         # outlier_score() extracted from rank_and_select
│   ├── config_io.py                       # competitors.json load/save + .env loading
│   └── paths.py                           # run-dir resolution
│
├── scripts/                            ← flat; stage-prefixed names for new scripts
│   ├── scrape_instagram.py                # existing — light refactor (viral_core)
│   ├── rank_and_select.py                  # existing — scoring extracted to viral_core
│   ├── download_media.py                   # existing, unchanged
│   ├── extract_frames.py                   # existing, unchanged
│   ├── transcribe_audio.py                 # existing, unchanged
│   ├── merge_analyses.py                   # existing — passes spoken_hook through
│   ├── generate_report.py                  # existing — writes run dir, renders new sections
│   ├── generate_pdf.py                     # existing, unchanged
│   ├── discovery_pull_trends.py            # NEW — Phase A
│   ├── discovery_handles.py                # NEW — Phase B
│   └── discovery_score.py                  # NEW — Phase C
│
├── skills/
│   ├── competitor-research/SKILL.md        # existing — updated paths, emits research.json
│   └── niche-discovery/SKILL.md            # NEW — stage 0 orchestration
├── commands/
│   ├── competitor-research.md              # existing
│   └── niche-discovery.md                  # NEW
├── agents/
│   ├── post-analyzer.md                    # existing — expanded output schema
│   └── pattern-synthesizer.md              # NEW — cross-post pattern synthesis
│
├── config/
│   └── competitors.json                    # discovery→research handoff (unchanged seam)
│
├── output/
│   └── runs/{YYYY-MM-DD}_{HHMM}/           ← NEW: durable per-run record
│       ├── discovery.json                     # provenance: how handles were chosen
│       ├── research.json                      # analyzed posts + patterns (research→future handoff)
│       └── IG-Competitor-Research_{...}.html / .pdf
│   └── reports/                            # deprecated; report moves into runs/
│
├── temp/                                # throwaway: raw_posts, frames, audio, transcripts, media
├── templates/report.html.j2             # existing — additive changes only
├── tests/                               # existing + viral_core tests + discovery tests
└── requirements.txt                     # + pytrends, praw (from niche-discovery spec)
```

### Naming convention (going forward)

- Existing scripts keep their names (do not break shipped `competitor-research` paths).
- New niche-discovery scripts use the `discovery_*` prefix.
- Future stages use their own prefix (e.g. `ideation_*`, `hooks_*`).
- If a tree structure is ever desired, it is a cheap later refactor once conventions are set.

---

## The `viral_core` package

### Import mechanism

Each script opens with a 2-line bootstrap that puts the plugin root on `sys.path`, then imports normally. No build step, no editable install:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from viral_core.apify_client import run_actor
```

`parents[1]` resolves to the plugin root whether the script lives in `scripts/` today or any sibling location later.

### Modules

| Module | Responsibility | Public functions |
|---|---|---|
| `apify_client.py` | One Apify actor-runner used by every script that calls Apify: `scrape_instagram`, `discovery_handles`, `discovery_score`. Replaces per-script Apify setup boilerplate and standardizes retry/timeout. | `run_actor(actor_id, run_input, token) → list[dict]`, `wait_for_run(run_id, token)` |
| `scoring.py` | The outlier-score formula, extracted verbatim from `rank_and_select.py`. `discovery_score.py` imports it rather than duplicating. | `outlier_score(post_engagement, account_median) → float` |
| `config_io.py` | Centralizes `competitors.json` load/save and `.env` loading. Today every script re-implements this and depends on CWD; this removes that fragility. | `load_competitors(path) → dict`, `save_competitors(path, data)`, `load_env(project_dir)` |
| `paths.py` | Run-directory logic — the backbone of the durable-artifact convention. | `new_run_dir(output_root) → Path`, `latest_run(output_root) → Path \| None`, `run_artifact(run_dir, stage) → Path` |
| `__init__.py` | Re-exports the public surface so `from viral_core.paths import latest_run` works. | — |

---

## Durable run artifacts

A new directory per pipeline run holds every durable output for that run:

```
output/runs/{YYYY-MM-DD}_{HHMM}/
├── discovery.json          # stage 0 provenance (if discovery ran this session)
├── research.json           # stage 1 handoff to future stages
├── IG-Competitor-Research_{ts}.html
└── IG-Competitor-Research_{ts}.pdf
```

### Rules

- `temp/` holds **only throwaway intermediates** (raw scrape, frames, audio, transcripts, media). It may be wiped freely; the chain does not depend on it.
- The run dir holds **durable records and deliverables**. Downstream stages read from it.
- A downstream stage invoked without an explicit run reads `paths.latest_run(output_root)` (most recent run dir by name/timestamp). With an explicit `--run <dir>`, it reads that one — enabling re-analysis without re-scrape.
- The HTML/PDF report moves from `output/reports/` into the run dir so an entire run's outputs live together. The filename remains run-versioned (already the case today).

### Handoff #1 — discovery → research

The functional handoff is `config/competitors.json` (the existing seam — which creators to research). This is unchanged from the niche-discovery spec. `discovery.json` is an additional provenance record of how those handles were chosen.

### Handoff #2 — research → future stages

The functional handoff is `research.json` (analyzed posts + patterns). Future stages consume it without re-running the expensive Apify scrape.

---

## Data contracts

### `output/runs/{ts}/discovery.json`

Written by niche-discovery as a provenance/audit record. The functional handoff into competitor-research remains `config/competitors.json`.

```json
{
  "stage": "discovery",
  "created_at": "2026-07-01T09:14:00+08:00",
  "niche_seed": "AI video editors",
  "niches_explored": ["AI video editors", "AI coding assistants"],
  "selected_creators": [
    { "handle": "mrwhosetheboss", "final_score": 0.82, "niche": "AI video editors" }
  ],
  "config_written_to": "config/competitors.json"
}
```

### `output/runs/{ts}/research.json`

Written by competitor-research; consumed by future stages.

```json
{
  "stage": "research",
  "created_at": "2026-07-01T09:42:00+08:00",
  "run_dir": "output/runs/2026-07-01_0942",
  "config": "config/competitors.json",
  "posts": [ { "...": "one entry per analyzed post — see per-post object below" } ],
  "patterns": {
    "summary": "The AI-video-editor niche is rewarding contrarian, cost-focused hooks…",
    "hook_types": [
      {
        "name": "Contrarian claim",
        "definition": "Opens by challenging a common belief or naming an enemy (a tool, a cost, a workflow).",
        "count": 18,
        "share": 0.36,
        "examples": [
          {
            "post_id": "Cxyz123",
            "handle": "mrwhosetheboss",
            "execution": "Opens with 'replaced my entire video team' → timeline demo at 0:04.",
            "outlier_score": 8.4
          }
        ]
      }
    ],
    "formats": [
      { "name": "Talking head", "count": 27, "share": 0.54 },
      { "name": "Screen recording", "count": 14, "share": 0.28 },
      { "name": "Carousel", "count": 9, "share": 0.18 }
    ],
    "topics": ["cost-reduction", "workflow speed", "before/after demos", "tool comparison"]
  },
  "report": {
    "html": "IG-Competitor-Research_2026-07-01_0942.html",
    "pdf":  "IG-Competitor-Research_2026-07-01_0942.pdf"
  }
}
```

**Pattern-category depth (agreed):** `hook_types` carry full `definition + count + examples` (the expandable playbook). `formats` and `topics` are lighter — stat bars and a tag list respectively. (If richer treatment is later wanted for these, the schema extends without breaking consumers.)

### Per-post analysis object

Today's fields, plus three new hook fields. Existing fields and their meanings are unchanged.

```json
{
  "id": "Cxyz123",
  "handle": "mrwhosetheboss",
  "url": "https://instagram.com/p/Cxyz123/",
  "caption": "...",
  "likes": 124000,
  "comments": 3100,
  "views": 1200000,
  "outlier_score": 8.4,
  "analyzed": true,

  "hook": "This AI editor replaced my entire video team in a week.",
  "spoken_hook": {
    "text": "This AI editor replaced my entire video team in a week.",
    "type": "contrarian claim",
    "window": "0:00-0:03"
  },

  "visual_format": "talking head → screen recording",
  "format_breakdown": "Opens direct-to-camera, jump cuts every 1.5s, transitions to screen recording at 0:04.",
  "topic": "Cost-reduction via AI video editing replacing a team workflow.",
  "why_it_worked": "Polarizing contrarian hook drives saves; the 8.4x outlier score is driven by a relatable cost pain point and an immediate demo proving the claim.",
  "replication_notes": "Lead with a bold cost/team claim, cut to proof within 4 seconds, use on-screen text for the before/after.",
  "transcript": "..."
}
```

- `hook` is retained (the analytical opener, as today) for backward compatibility and for any consumer that only wants a string.
- `spoken_hook` is the new structured object: verbatim first ~3 seconds (`text`), a hook-type classification (`type`), and the time window it covers (`window`).
- `merge_analyses.py` passes `spoken_hook` through unchanged (the post-analyzer owns it; merge re-applies only ground-truth metrics, as today).

---

## Report redesign (additive)

The report template (`templates/report.html.j2`) gains exactly two new render targets. Nothing existing is removed or reordered.

### 1. Unified top section — prose + patterns

Replaces today's single-line auto-summary. One purple-bordered block containing:

- The prose "🔥 What's Working in the Niche" paragraph (today this is the optional `temp/niche_summary.txt`; it is now sourced from `patterns.summary`, which the `pattern-synthesizer` agent drafts).
- Pattern statistics, rendered beneath the prose:
  - **Top hook structures** — each type is a collapsible entry showing `definition`, `count (share%)`, and `examples[]` (handle + execution detail + outlier score). Rendered collapsed by default except the top type.
  - **Dominant formats** — ranked horizontal bars (name + share%).
  - **Recurring topics** — inline tag list.

### 2. Per-post spoken-hook block

Inserted on each card between the thumbnail and the Format field: a pink "▶ SPOKEN HOOK" element showing the verbatim `spoken_hook.text`, a chip with `spoken_hook.type`, and the `spoken_hook.window` timestamp. All existing card fields (metrics, thumbnail, Format, Format Breakdown, Topic, Why It Worked, Replication Notes, collapsible Transcript, original-post link) remain unchanged.

### Rendering details

- `build_summary()` in `generate_report.py` is replaced by reading the `patterns` block from `research.json` (the pattern-synthesizer's output).
- The template keeps the existing dark theme on screen and the light-theme `@media print` rules for PDF.
- Each hook-type example references a `post_id`; in the rendered report, examples can link/scroll to the corresponding card.

---

## New `pattern-synthesizer` agent

A new sub-agent (`agents/pattern-synthesizer.md`), the complement of `post-analyzer`:

- `post-analyzer` analyzes **one post in isolation** (safe to fan out 5-at-a-time).
- `pattern-synthesizer` reads **the whole cohort** (`temp/analyses.json`) and produces the cross-post `patterns` block.

**Input:** `temp/analyses.json` (the merged per-post analyses).

**Output:** the `patterns` object written into `research.json`:
- `summary` — a short prose paragraph on what's working in the niche.
- `hook_types[]` — each with `name`, `definition`, `count`, `share`, and `examples[]` (post_id, handle, execution, outlier_score). A fixed taxonomy of hook types is provided in the agent prompt (contrarian claim, curiosity gap, pattern interrupt, direct address, story/open loop, etc.) so classification is consistent.
- `formats[]` — name + count + share.
- `topics[]` — recurring topic strings.

**Runs once**, after the post-analyzer fan-out and merge complete, before `generate_report.py`. It reads `analyses.json`; it does not modify it.

---

## Changes to existing components

| Component | Change |
|---|---|
| `scripts/rank_and_select.py` | `outlier_score()` extracted into `viral_core.scoring`; script imports it. Same math. |
| `scripts/scrape_instagram.py` | Apify setup → `viral_core.apify_client.run_actor()`. `.env` → `viral_core.config_io.load_env()`. |
| `scripts/discovery_handles.py`, `discovery_score.py` (new) | Use `viral_core.apify_client` and `viral_core.scoring`. |
| All scripts | `.env` loaded via `viral_core.config_io.load_env()` (no CWD reliance). |
| `scripts/merge_analyses.py` | Pass `spoken_hook` through unchanged. |
| `scripts/generate_report.py` | Write into the run dir (`viral_core.paths`); read `patterns` + `spoken_hook`; render new template sections. `build_summary()` removed in favor of `patterns.summary`. |
| `skills/competitor-research/SKILL.md` | Update paths to run dir; add Phase 3e (pattern-synthesizer); emit `research.json`. |
| `templates/report.html.j2` | Additive: unified top section + spoken-hook block. |
| `agents/post-analyzer.md` | Expand output schema with `spoken_hook` object. |
| `requirements.txt` | Add `pytrends>=4.9.0`, `praw>=7.7.0` (per niche-discovery spec). |

---

## Niche-discovery integration (stage 0)

The previously-approved niche-discovery design (`2026-06-30-niche-discovery-design.md`) lands as-is, with these adjustments to fit the new architecture:

- Its three scripts are named `discovery_pull_trends.py`, `discovery_handles.py`, `discovery_score.py` (stage prefix).
- `discovery_handles.py` and `discovery_score.py` use `viral_core.apify_client` and `viral_core.scoring` instead of local reimplementations.
- The skill additionally writes `output/runs/{ts}/discovery.json` (provenance) alongside the functional handoff `config/competitors.json`.
- Its error-handling table, fallback chains, env vars (`REDDIT_CLIENT_ID/SECRET` optional), and cost estimates are unchanged from that spec.

---

## Error handling

Niche-discovery error handling is inherited verbatim from `2026-06-30-niche-discovery-design.md`. Architecture-level additions:

| Scenario | Behavior |
|---|---|
| `viral_core` import fails (bootstrap path wrong) | Script fails fast with a clear message naming the missing module and the expected plugin root. |
| Run dir cannot be created (permissions) | Stage fails with the resolved path; no silent fallback to `temp/`. |
| `pattern-synthesizer` fails or returns partial patterns | Report still renders. Missing `hook_types` render as "n/a"; if the `patterns` block is entirely absent, `generate_report` falls back to a minimal data-driven summary (counts of handles/formats from the posts) so the report never renders headerless. |
| `spoken_hook` absent on a post (e.g. silent reel with no transcript) | Card renders without the spoken-hook block; the existing `hook` field still shows. No error. |
| `latest_run()` finds no prior run (future stage invoked cold) | Stage tells the user to run `/competitor-research` first, naming the expected artifact path. |

---

## Testing strategy

- **`viral_core` unit tests** — each module independently: `outlier_score` math, `paths` run-dir resolution (new/latest/artifact), `config_io` round-trip, `apify_client` with mocked HTTP.
- **Script independence** — every script remains independently runnable with `--input/--output` flags and fixture data (existing pattern).
- **New fixtures** — `tests/fixtures/sample_analyses.json` (cohort) for pattern-synthesizer + report rendering tests; `tests/fixtures/sample_niches.json`, `sample_candidate_handles.json` (from niche-discovery spec).
- **Report rendering tests** — assert the new top section and spoken-hook block render given a fixture `patterns` + per-post object; assert existing fields still render.
- **Schema tests** — assert `research.json` and `discovery.json` conform to the contracts above (required keys, types).
- Existing tests (`python -m pytest`) continue to pass after the light refactor.

---

## Scope

**In scope:**
1. `viral_core` package (5 modules) + bootstrap import convention.
2. Durable run artifacts (`output/runs/{ts}/`) + `paths.py` helpers.
3. Niche-discovery integration as stage 0 (3 scripts + skill + command, reusing `viral_core`).
4. Light refactor of existing competitor-research scripts to use `viral_core`.
5. Report redesign: unified top section + spoken-hook block + `pattern-synthesizer` agent.
6. Data contracts (`discovery.json`, `research.json`, `patterns`, `spoken_hook`).

**Out of scope (conventions only, not designed):**
- Future stages (content-ideation, hook-testing, posting-strategy).
- A master `/viral-analyzer` orchestrator command.
- Moving scripts into a directory tree (flat + prefix is sufficient for now).
