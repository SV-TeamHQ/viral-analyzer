---
name: competitor-research
description: Runs the Instagram competitor research pipeline — scrape competitor posts via Apify, rank by engagement outlier score, download media, extract frames/audio, transcribe, analyze why each top post performed, and generate a ranked HTML report. Use when the user wants to research what's working in an Instagram niche, analyze competitors' top-performing posts, or generate a competitor research report. Triggered by "/competitor-research" or "/ig-research", or natural language like "research my Instagram competitors" or "what's working in my niche".
---

# Instagram Competitor Research

Orchestrates a 5-phase Python pipeline that turns a list of competitor Instagram
handles into a ranked HTML report explaining why their top posts performed.

## Path conventions (important)

This skill ships as a Claude Code plugin, so it must not assume a working directory.
Two substitution variables are used throughout (Claude Code fills these in):

- **`${CLAUDE_PLUGIN_ROOT}`** — where the plugin's bundled code lives (scripts, templates,
  the competitors template). Treat it as **read-only**; it changes on plugin updates.
- **`${CLAUDE_PROJECT_DIR}`** — the user's project. All working data, outputs, the user's
  competitor list, and `.env` live here.

Set these in your head before running anything:
- Scripts → `${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`
- Working data → `${CLAUDE_PROJECT_DIR}/temp/...`
- Reports → `${CLAUDE_PROJECT_DIR}/output/reports/...`
- User config → `${CLAUDE_PROJECT_DIR}/config/competitors.json`
- Secrets → `${CLAUDE_PROJECT_DIR}/.env` (read by `python-dotenv` from the CWD)

## First-run setup

Before the first run, ensure prerequisites are met. Run these checks and stop with a
clear instruction if any fail:

1. **Python deps** — `python -c "import requests, jinja2, apify_client"` (and `whisper`
   before Phase 3c). If missing, tell the user to run
   `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.
2. **ffmpeg/ffprobe** — `ffmpeg -version` and `ffprobe -version`. If missing, instruct the
   user to install FFmpeg.
3. **`APIFY_TOKEN`** — check `${CLAUDE_PROJECT_DIR}/.env` (or the environment). If absent,
   tell the user to create `${CLAUDE_PROJECT_DIR}/.env` with `APIFY_TOKEN=...`.
4. **Competitor list** — if `${CLAUDE_PROJECT_DIR}/config/competitors.json` does NOT exist,
   copy the template: `${CLAUDE_PLUGIN_ROOT}/config/competitors.json` →
   `${CLAUDE_PROJECT_DIR}/config/competitors.json`, then tell the user to replace the
   `example_handle_*` placeholders with real handles before continuing.

Do not proceed until the user has real handles configured.

## Pipeline Phases

Run each phase in order. Every script accepts explicit paths via CLI flags, so pass the
`${CLAUDE_PROJECT_DIR}`-rooted paths explicitly rather than relying on defaults.

### Phase 1 — Scrape ✅
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/scrape_instagram.py" \
  --config "${CLAUDE_PROJECT_DIR}/config/competitors.json" \
  --output "${CLAUDE_PROJECT_DIR}/temp/raw_posts.json"
```
Scrapes recent posts for each handle via Apify's **`api-ninja/instagram-scraper`**
(uses Instagram's private API — reliable; do **not** swap to `apify/instagram-scraper`,
which is blocked on post-detail requests). Default lookback is **365 days** in the
template; most accounts don't post weekly, so a 7-day window often returns 0 posts.

### Phase 2 — Rank & Select ✅
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/rank_and_select.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/raw_posts.json" \
  --output "${CLAUDE_PROJECT_DIR}/temp/selected_posts.json" \
  --top-per-handle 10
```
Selects up to **10 posts per handle** and re-ranks by outlier score. `--top-per-handle`
is a *ceiling* — if `temp/raw_posts.json` contains fewer than 10 posts for a handle (i.e.
Phase 1 scraped fewer), fewer are selected. If the report comes back light, **re-run from
Phase 1** and/or raise `posts_per_handle` in `config/competitors.json` — do not just bump
this flag, it cannot add posts that were never scraped.

### Phase 3a — Download Media ✅
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/download_media.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/selected_posts.json" \
  --output-dir "${CLAUDE_PROJECT_DIR}/temp/media"
```

### Phase 3b — Extract Frames & Audio ✅
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/extract_frames.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/selected_posts.json" \
  --frames-dir "${CLAUDE_PROJECT_DIR}/temp/frames" \
  --audio-dir "${CLAUDE_PROJECT_DIR}/temp/audio" \
  --num-frames 4
```

### Phase 3c — Transcribe Audio ✅
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/transcribe_audio.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/selected_posts.json" \
  --transcripts-dir "${CLAUDE_PROJECT_DIR}/temp/transcripts" \
  --model base
```
Requires `openai-whisper` installed.

### Phase 3d — Analyze Posts ✅

Analyze each post with **Claude sub-agents** (in-conversation, using vision on the
extracted frames). This is orchestration, not a single script:

1. Read `${CLAUDE_PROJECT_DIR}/temp/selected_posts.json` (fully enriched with `frames`,
   `transcript`, `hook`, metrics).
2. **Fan out** the `post-analyzer` sub-agent (see `agents/post-analyzer.md`) — spawn up to
   **5 in parallel per batch** via the Agent tool (e.g. 50 posts = 10 sequential batches,
   since Phase 2 selects up to 10 per handle). Wait for each batch to finish before
   spawning the next.
3. Each sub-agent reads its post's frame JPEGs (vision) + transcript + metrics and writes
   `${CLAUDE_PROJECT_DIR}/temp/analyses/{id}.json`.
4. Merge the per-post files (re-applies ground-truth metrics; placeholders for gaps):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/merge_analyses.py" \
     --input "${CLAUDE_PROJECT_DIR}/temp/selected_posts.json" \
     --analyses-dir "${CLAUDE_PROJECT_DIR}/temp/analyses" \
     --output "${CLAUDE_PROJECT_DIR}/temp/analyses.json"
   ```

If fewer than ~3 posts analyze successfully, warn the user that the report may not be
representative before continuing.

### Phase 4 — Generate Report ✅
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_report.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/analyses.json" \
  --output-dir "${CLAUDE_PROJECT_DIR}/output/reports" \
  --summary "${CLAUDE_PROJECT_DIR}/temp/niche_summary.txt"
```
The `--summary` file is optional: if absent (or `--summary ""`), the report uses a
data-driven fallback summary. The HTML report (full frame images rendered with
`object-fit: contain`) is written to `${CLAUDE_PROJECT_DIR}/output/reports/IG-Competitor-Research_{date}.html`.

By default a **PDF** is also rendered from that HTML (`--pdf`, disable with `--no-pdf`)
into `IG-Competitor-Research_{date}.pdf` via headless Chromium. Requires Playwright:
`pip install playwright && playwright install chromium`. If Playwright isn't installed,
the PDF step is skipped (non-fatal) and the HTML is still produced. To render a PDF from
an existing HTML file directly: `python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_pdf.py" --html <report.html>`.

## Orchestration

Run phases 1 → 4 end-to-end. All phases are implemented. After the Phase 3d analysis +
merge, optionally spawn a sub-agent to draft an AI niche summary and write it to
`${CLAUDE_PROJECT_DIR}/temp/niche_summary.txt` before Phase 4.

After a successful run, you may offer to clean up `${CLAUDE_PROJECT_DIR}/temp/` (it is
recreated on the next run). Keep `${CLAUDE_PROJECT_DIR}/output/reports/`.

## Notes
- Instagram CDN URLs expire within hours — always run Phase 3a immediately after Phase 1.
- All scripts are independently runnable and tested (`python -m pytest`).
- Architecture is "Instagram first, pluggable": a new platform = a new
  `scrape_<platform>.py` with the same normalize→rank→download interface.
