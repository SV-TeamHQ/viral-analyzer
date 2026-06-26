# viral-analyzer — IG Competitor Research

A Claude Code plugin that runs an Instagram competitor research pipeline: scrape
competitors' recent posts via Apify, rank them by an engagement **outlier score**,
download media, extract frames/audio, transcribe, analyze why each top post
performed, and generate a ranked HTML report.

Trigger it in Claude Code with **`/competitor-research`** (alias `/ig-research`),
or natural language like *"research my Instagram competitors."*

---

## What it does

5 phases, each an independently-testable Python script under `scripts/`:

| Phase | Script | Output |
|-------|--------|--------|
| 1 — Scrape | `scrape_instagram.py` | `temp/raw_posts.json` |
| 2 — Rank & Select | `rank_and_select.py` | `temp/selected_posts.json` |
| 3a — Download media | `download_media.py` | `temp/media/` |
| 3b — Extract frames + audio | `extract_frames.py` | `temp/frames/`, `temp/audio/` |
| 3c — Transcribe | `transcribe_audio.py` | `temp/transcripts/` |
| 3d — Analyze | `post-analyzer` sub-agents + `merge_analyses.py` | `temp/analyses.json` |
| 4 — Report | `generate_report.py` | `output/reports/IG-Competitor-Research_{date}.html` |

Phase 3d is done by Claude sub-agents in-conversation (vision over the extracted
frames) — not an API call — so there's no extra LLM cost beyond your Claude session.

---

## Prerequisites

| Tool | Why | Install |
|------|-----|---------|
| **Python 3.10+** | pipeline runtime | — |
| **FFmpeg + FFprobe** | frame + audio extraction (Phase 3b) | `winget install ffmpeg` (Windows) / `brew install ffmpeg` (macOS) |
| **Apify account + token** | Instagram scraping (Phase 1) | apify.com → Settings → API & Integrations → copy token |

Then install Python deps:

```bash
pip install -r requirements.txt
```

> `openai-whisper` (Phase 3c) pulls in PyTorch (~2 GB). The pipeline imports cleanly
> without it; you only need it installed when you actually run transcription.

---

## Install the plugin

This repo is both a single-plugin marketplace and the plugin itself. Pick one:

### Option A — from this repo as a marketplace (for your team)

Push this repo to a git host (e.g. `your-org/viral-analyzer`), then each teammate:

```bash
# in Claude Code:
/plugin marketplace add your-org/viral-analyzer
/plugin install viral-analyzer@viral-analyzer
```

For a local test before publishing:

```bash
/plugin marketplace add ./path/to/viral-analyzer
/plugin install viral-analyzer@viral-analyzer
```

### Option B — load in place for one session (no install)

```bash
claude --plugin-dir ./viral-analyzer
```

### Option C — as a project-scoped skills-directory plugin

Copy/symlink this repo into your project at `.claude/skills/viral-analyzer/`. It loads
as `viral-analyzer@skills-dir` after you accept the workspace trust dialog.

---

## Configure your competitors

The plugin ships a template at `config/competitors.json` (placeholder handles). On the
first run, the skill copies it into your project at `config/competitors.json` — **edit
that copy** with real handles:

```json
{
  "competitors": [
    { "handle": "real_handle_1", "niche": "AI tools" },
    { "handle": "real_handle_2", "niche": "AI tools" }
  ],
  "posts_per_handle": 10,
  "lookback_days": 7
}
```

Put your Apify token in `.env` (in your project root, where you run Claude Code):

```
APIFY_TOKEN=your_apify_api_token_here
```

---

## How outputs are stored

When run as a plugin, all working data and reports are written under your **project
directory** (`${CLAUDE_PROJECT_DIR}`), not inside the plugin (the plugin's install
directory is ephemeral and replaced on update):

- `temp/` — downloads, frames, audio, transcripts, per-post analyses (scratch; recreated each run)
- `output/reports/` — the final HTML reports (kept)

Both are gitignored in this repo.

---

## Run it

In Claude Code, from your project root:

```
/competitor-research
```

Or just describe what you want ("research my IG competitors and make a report").

---

## Develop / test

Each script is independently runnable and unit-tested:

```bash
python -m pytest            # 52 tests across all phases
python scripts/scrape_instagram.py --help
```

The pipeline is "Instagram first, pluggable": adding a platform means a new
`scrape_<platform>.py` with the same normalize → rank → download interface.

---

## Notes

- **Instagram CDN URLs expire within hours** — the pipeline always downloads media
  immediately after scraping (Phases 1 → 3a back-to-back).
- **Versioning:** `plugin.json` pins `version: 0.1.0`. For a team iterating fast, remove
  the `version` field so every commit ships a new version (git-SHA-based); otherwise bump
  the version on each release and teammates run `/plugin update`.
- **Marketplace owner:** `.claude-plugin/marketplace.json` uses the placeholder
  `"Your Team"` — replace it with your team/org name before sharing.
