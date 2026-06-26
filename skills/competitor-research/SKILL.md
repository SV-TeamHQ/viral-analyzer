---
name: competitor-research
description: Runs the Instagram competitor research pipeline — scrape competitor posts via Apify, rank by engagement outlier score, download media, extract frames/audio, analyze why each top post performed, and generate a ranked HTML report. Use when the user wants to research what's working in an Instagram niche, analyze competitors' top-performing posts, or generate a competitor research report. Triggered by "/competitor-research" or "/ig-research", or natural language like "research my Instagram competitors" or "what's working in my niche".
---

# Instagram Competitor Research

Orchestrates a 5-phase Python pipeline that turns a list of competitor Instagram
handles into a ranked HTML report explaining why their top posts performed.

## Prerequisites

- **Python 3.10+** with `requirements.txt` installed (`pip install -r requirements.txt`)
- **FFmpeg + FFprobe** on PATH (frame + audio extraction)
- **`APIFY_TOKEN`** set in `.env` (Instagram scraping)
- Real competitor handles in `config/competitors.json` (replace the placeholders)

## Pipeline Phases

Each phase is an independently-testable Python script in `scripts/`. Run them in
order from the repo root. Each consumes the previous phase's output under `temp/`.

### Phase 1 — Scrape ✅
```bash
python scripts/scrape_instagram.py --config config/competitors.json --output temp/raw_posts.json
```
Scrapes recent posts (default last 7 days) for each handle via Apify's
`apify/instagram-scraper`. Output: `temp/raw_posts.json` (normalized posts).

### Phase 2 — Rank & Select ✅
```bash
python scripts/rank_and_select.py --input temp/raw_posts.json --output temp/selected_posts.json --top-per-handle 3
```
Selects top posts per handle and ranks by **outlier score** (`engagement /
account median`). Output: `temp/selected_posts.json`.

### Phase 3a — Download Media ✅
```bash
python scripts/download_media.py --input temp/selected_posts.json --output-dir temp/media
```
Downloads each post's video/image/carousel. Writes `local_media_path` back onto
each post (None if the CDN URL failed).

### Phase 3b — Extract Frames & Audio ✅
```bash
python scripts/extract_frames.py --input temp/selected_posts.json --frames-dir temp/frames --audio-dir temp/audio --num-frames 4
```
For videos: extracts N evenly-spaced JPEG frames + a mono 16 kHz wav. For
images/carousels: reuses the downloaded file as the single frame. Writes `frames`
and `audio_path` back onto each post.

### Phase 3c — Transcribe Audio ✅
```bash
python scripts/transcribe_audio.py --input temp/selected_posts.json --transcripts-dir temp/transcripts --model base
```
Runs local Whisper (`base` model, loaded once per batch) over each post's audio,
writing `temp/transcripts/{id}.txt` and adding `transcript` + `hook` (first
segment) fields. Posts with no audio get empty strings. Requires `openai-whisper`
installed (guarded import — pipeline runs without it until this phase executes).

### Phase 3d — Analyze Posts ⏳ *(not yet implemented)*
Planned: spawn up to 5 `post-analyzer` sub-agents in parallel (batches of 5),
each reading one post's frames (Claude vision) + transcript + engagement metrics
and writing structured JSON to `temp/analyses/{id}.json`. Merge into
`temp/analyses.json`. See `agents/post-analyzer.md`.

### Phase 4 — Generate Report ⏳ *(not yet implemented)*
Planned: `scripts/generate_report.py` — Jinja2 HTML report with a niche summary
and ranked post cards (base64 frame thumbnails), written to
`output/reports/IG-Competitor-Research_{YYYY-MM-DD}.html`.

## Orchestration

Run phases 1 → 3c sequentially now (3d/4 are pending). Stop and report which
phases are not yet implemented rather than skipping silently. When all phases
exist, run the full sequence end-to-end.

### Status legend
- ✅ implemented & tested
- ⏳ scaffolded / pending — do not attempt to run

## Notes
- Instagram CDN URLs expire within hours — always download immediately after scraping.
- All scripts are independently runnable and tested (`python -m pytest`).
- Architecture is "Instagram first, pluggable": a new platform = a new
  `scrape_<platform>.py` with the same normalize→rank→download interface.
