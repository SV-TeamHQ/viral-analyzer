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

## Prerequisites & dependencies

Each teammate needs to set these up once on their own machine.

### 1. System dependencies

| Tool | Why | Min. version | Install |
|------|-----|--------------|---------|
| **Python** | pipeline runtime | 3.10+ | [python.org](https://www.python.org/downloads/) — ensure `python` and `pip` are on your PATH |
| **FFmpeg** (+ ffprobe) | extract video frames + audio (Phase 3b) | any recent | Windows: `winget install ffmpeg` · macOS: `brew install ffmpeg` · Linux (Debian/Ubuntu): `sudo apt install ffmpeg` |

Verify:
```bash
python --version      # >= 3.10
ffmpeg -version
ffprobe -version
```

### 2. Python dependencies

From the repo (or plugin) root:

```bash
pip install -r requirements.txt
```

What you get and why:

| Package | Purpose | Phase |
|---------|---------|-------|
| `requests` | download media from Instagram CDN | 3a |
| `apify-client` | run the Instagram scraper actor on Apify | 1 |
| `python-dotenv` | load `APIFY_TOKEN` from `.env` | 1 |
| `openai-whisper` | local speech-to-text transcription (**pulls in PyTorch ~2 GB**) | 3c |
| `jinja2` | render the HTML report | 4 |
| `Pillow` | image handling | 4 |
| `pytest` | run the test suite (dev only) | — |

> **Heavy dep note:** `openai-whisper` transitively installs **PyTorch (~2 GB)**. The
> pipeline imports cleanly without it — you only need it when you actually run Phase 3c
> (transcription). If you want a minimal install first, do everything *except* whisper:
> ```bash
> pip install requests apify-client python-dotenv jinja2 Pillow pytest
> pip install openai-whisper   # add this when you're ready to transcribe
> ```
> Whisper also needs a CUDA-capable GPU for best speed but runs on CPU (slower). On first
> run it downloads the `base` model (~74 MB) automatically.

### 3. Accounts & secrets

| Service | Why | How to get it |
|---------|-----|---------------|
| **Apify** | Instagram scraping (Phase 1) | Sign up at [apify.com](https://apify.com) → **Settings → API & Integrations** → copy your API token. The free tier ($5/mo credit) covers ~33 runs/month. |

Put the token in `.env` in your **project root** (where you launch Claude Code), not in
the plugin:
```
APIFY_TOKEN=your_apify_api_token_here
```

That's the only required secret. There is **no per-run LLM cost** — Phase 3d analysis runs
as Claude sub-agents inside your existing Claude Code session, so it's covered by your
Claude subscription (no separate `ANTHROPIC_API_KEY` needed).

### Quick setup checklist (for a teammate)

```bash
# 1. system deps
winget install ffmpeg          # or: brew install ffmpeg  /  sudo apt install ffmpeg

# 2. python deps
pip install -r requirements.txt

# 3. secrets — create .env in your project root
echo "APIFY_TOKEN=your_token_here" > .env

# 4. (in Claude Code) install the plugin, then run it
#    /plugin marketplace add your-org/viral-analyzer
#    /plugin install viral-analyzer@viral-analyzer
#    /competitor-research
```

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
