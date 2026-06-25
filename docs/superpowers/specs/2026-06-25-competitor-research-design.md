# Instagram Competitor Research — Design Spec

**Date:** 2026-06-25
**Status:** Approved
**Approach:** Skill-Orchestrated Python Pipeline (Approach A)

---

## Overview

A Claude Code plugin that automates Instagram competitor research. The skill orchestrates a pipeline of Python scripts to scrape competitor posts, rank them by engagement, download and process media, then uses Claude sub-agents to visually analyze why top posts performed. Output is a self-contained HTML report ranking the top 15 posts with hooks, formats, transcripts, and replication notes.

**Key decisions:**
- Claude Code plugin with skill + slash command (shareable with team)
- Instagram first, pluggable scraper interface for future platforms
- Claude in-conversation vision analysis via sub-agents (zero extra API cost)
- Local Whisper (base model) for audio transcription
- Research report only — no content generation

---

## Plugin Structure

```
viral-analyzer/
├── plugin.json                    # Plugin manifest (name, version, description)
├── skills/
│   └── competitor-research/
│       └── skill.md               # Orchestration instructions for Claude
├── agents/
│   └── post-analyzer.md           # Sub-agent for parallel post analysis
├── commands/
│   └── competitor-research.yaml   # Slash command definition
├── config/
│   └── competitors.json           # Default competitor handles
├── scripts/
│   ├── scrape_instagram.py        # Phase 1: Apify scraper
│   ├── rank_and_select.py         # Phase 2: Rank + outlier scoring
│   ├── download_media.py          # Phase 3a: Download video/images
│   ├── extract_frames.py          # Phase 3b: FFmpeg frame extraction
│   ├── transcribe_audio.py        # Phase 3c: Local Whisper transcription
│   └── generate_report.py         # Phase 4: Jinja2 HTML report
├── templates/
│   └── report.html                # Jinja2 report template
├── tests/
│   └── fixtures/
│       ├── sample_raw_posts.json  # Test data for ranking
│       └── sample_frames/         # Test frames for report generation
├── requirements.txt
└── .env.example                   # Template for API keys
```

### Invocation

- **Slash command:** `/competitor-research`
- **Natural language:** Skill triggers on phrases like "analyze my competitors", "run competitor research", "what's working on Instagram"

---

## Data Flow

```
Phase 1: SCRAPE          Phase 2: RANK           Phase 3: ANALYZE         Phase 4: REPORT
─────────────────        ──────────────          ─────────────────        ───────────────
competitors.json         raw_posts.json          selected_posts.json      analyses.json
       │                      │                        │                       │
  Apify API call         Sort by engagement      For each post:           Jinja2 template
       │                 Top 3 per handle         ├─ Download media              │
       v                 Outlier scoring          ├─ Extract frames        HTML report
  raw_posts.json              │                  ├─ Transcribe audio      (timestamped)
  (all posts,            selected_posts.json     └─ Claude sub-agent
   last 7 days)          (top 15, ranked)            analyzes visually
                                                       │
                                                  analyses.json
```

### Intermediate files

| File | Created by | Consumed by |
|------|-----------|-------------|
| `temp/raw_posts.json` | Phase 1 (scrape) | Phase 2 (rank) |
| `temp/selected_posts.json` | Phase 2 (rank) | Phase 3 (analyze) |
| `temp/media/{shortCode}.*` | Phase 3a (download) | Phase 3b (frames) |
| `temp/frames/{shortCode}/frame_01..04.jpg` | Phase 3b (frames) | Phase 3d (sub-agent) |
| `temp/audio/{shortCode}.wav` | Phase 3b (frames) | Phase 3c (transcribe) |
| `temp/transcripts/{id}.json` | Phase 3c (transcribe) | Phase 3d (sub-agent) |
| `temp/analyses/{shortCode}.json` | Phase 3d (sub-agent) | Phase 4 (report) |
| `output/reports/IG-Competitor-Research_{date}.html` | Phase 4 (report) | User |

---

## Scraper Interface (Pluggable)

Every scraper exposes the same function signature:

```python
def scrape(handles: list[dict], posts_per_handle: int, lookback_days: int) -> list[dict]
```

Returns normalized post dicts with a common schema:

```python
{
    "id": "ABC123",              # Platform-unique ID
    "platform": "instagram",
    "handle": "competitor1",
    "url": "https://...",
    "media_url": "https://...",  # Video or image URL
    "media_type": "video",       # "video", "image", or "carousel"
    "likes": 5432,
    "comments": 231,
    "views": 89000,              # None for images
    "caption": "...",
    "timestamp": "2026-06-20T...",
}
```

Instagram scraper uses `apify-client` to call the `apify/instagram-scraper` actor. Adding a new platform means creating a new `scrape_<platform>.py` with the same interface.

---

## Phase Details

### Phase 1: Scrape (scrape_instagram.py)

1. Read handles from `config/competitors.json`
2. Call Apify `apify/instagram-scraper` actor with `resultsType: "posts"` and `resultsLimit` per handle
3. Filter posts to only those within `lookback_days`
4. Normalize into the common post schema
5. Write to `temp/raw_posts.json`

### Phase 2: Rank & Select (rank_and_select.py)

1. Load `temp/raw_posts.json`
2. Group by handle, select top 3 per handle by engagement (likes + comments)
3. Calculate outlier score: `post_engagement / account_median_engagement`
4. Re-rank combined list (top 15) by outlier score
5. Write to `temp/selected_posts.json`

### Phase 3a: Download Media (download_media.py)

- Download video from `media_url` for each selected post
- Save to `temp/media/{id}.mp4` or `.jpg`
- Fallback to `yt-dlp` if CDN URL fails
- 1-second delay between downloads

### Phase 3b: Extract Frames (extract_frames.py)

- For videos: extract 4 evenly-spaced frames via FFmpeg
- Extract audio track as WAV (16kHz mono) for transcription
- For images: copy to frames directory as-is
- Output: `temp/frames/{id}/frame_01..04.jpg` and `temp/audio/{id}.wav`

### Phase 3c: Transcribe Audio (transcribe_audio.py)

- Run local Whisper (base model) on each audio file
- Extract timestamped segments
- Identify the hook (first segment text)
- Write transcript + hook to `temp/transcripts/{id}.json`

### Phase 3d: AI Analysis (sub-agents)

- Skill spawns up to 5 `post-analyzer` sub-agents simultaneously (3 batches for 15 posts)
- Each sub-agent:
  - Reads frames from `temp/frames/{id}/`
  - Reads transcript from `temp/transcripts/{id}.json`
  - Receives metrics and outlier score
  - Analyzes using Claude's vision capabilities
  - Writes structured analysis to `temp/analyses/{id}.json`
- Skill waits for each batch to complete before spawning next

### Phase 4: Generate Report (generate_report.py)

1. Merge all `temp/analyses/{id}.json` into `temp/analyses.json`
2. Skill generates a niche summary paragraph (patterns across all 15 posts)
3. Render Jinja2 template with analyses + niche summary
4. Base64-encode frame images into HTML (self-contained report)
5. Write to `output/reports/IG-Competitor-Research_{YYYY-MM-DD}.html`

---

## Sub-Agent Analysis Output Schema

```json
{
    "shortCode": "ABC123",
    "handle": "@competitor1",
    "hook": "Every single pick runs the same engine...",
    "visual_format": "Talking Head Listicle",
    "format_breakdown": "Creator speaks to camera, text overlays appear at 3s intervals...",
    "topic": "AI coding tools comparison",
    "why_it_worked": "Strong controversy hook, timely topic...",
    "replication_notes": "Film talking head, overlay 5 tool logos...",
    "metrics": { "likes": 5432, "comments": 231, "views": 89000, "outlier_score": 4.2 },
    "transcript": "...",
    "post_url": "https://www.instagram.com/p/ABC123/",
    "posted_date": "2026-06-20"
}
```

---

## HTML Report Structure

1. **Header** — date, handles analyzed, total posts scraped
2. **Niche Summary** — AI-generated paragraph summarizing patterns (formats, topics, hooks)
3. **Ranked Post Cards** (ordered by outlier score):
   - Rank number, handle, metrics (likes, comments, views, outlier score)
   - Hook text
   - Visual format label
   - Format breakdown
   - Transcript (collapsible)
   - Why it worked analysis
   - Replication notes
   - Embedded frame images (base64)
   - Link to original post
4. Self-contained HTML with inline CSS, no external dependencies

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| Apify scrape fails | Exit with error, suggest checking API token |
| CDN URL expired (404) | Skip media download, mark post as "media unavailable" in report |
| FFmpeg/Whisper not installed | Fail fast at startup with install instructions |
| Sub-agent fails on a post | Log failure, continue with remaining posts, note in report |
| Stale temp files | Overwritten on next run |

Temp directory is cleaned up after successful report generation.

---

## Testing Strategy

- Each script independently runnable with test fixtures
- `tests/fixtures/sample_raw_posts.json` — test ranking without Apify
- `tests/fixtures/sample_frames/` — test report generation without full pipeline
- Scripts accept `--input` flag to use fixture data instead of pipeline output
- No unit test framework — scripts testable via direct invocation

---

## Configuration

### competitors.json

```json
{
    "competitors": [
        { "handle": "competitor1", "niche": "AI tools" },
        { "handle": "competitor2", "niche": "AI tools" }
    ],
    "posts_per_handle": 10,
    "lookback_days": 7
}
```

### .env.example

```
APIFY_TOKEN=your_apify_api_token_here
```

---

## Dependencies

### System

| Tool | Purpose |
|------|---------|
| Python 3.10+ | Runtime |
| FFmpeg | Frame/audio extraction |

### Python (requirements.txt)

```
requests>=2.31.0
openai-whisper>=20231117
apify-client>=1.7.0
python-dotenv>=1.0.0
jinja2>=3.1.0
Pillow>=10.0.0
```

---

## Cost & Performance

| Component | Cost |
|-----------|------|
| Apify scraping | ~$0.15 per run (free tier: $5/month) |
| FFmpeg | Free (local) |
| Whisper | Free (local) |
| Claude analysis | $0 (in-conversation) |
| **Total** | **~$0.15 per run** |

Estimated runtime: ~7 minutes per run.
