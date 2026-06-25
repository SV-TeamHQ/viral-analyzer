# Instagram Competitor Research Automation — Build Plan

## What This System Does

An automated Instagram competitor research pipeline that:
1. Takes a list of competitor Instagram handles
2. Scrapes their recent posts (past 7 days) via Apify
3. Downloads each video/image, extracts frames, transcribes audio
4. Uses AI to visually analyze each post and break down why it performed
5. Generates a ranked HTML report with hooks, formats, transcripts, outlier scores, and "why it worked" breakdowns

**Runtime:** ~7 minutes per run
**Cost:** ~$0.13–0.15 per run (Apify free tier gives $5/month = ~33 free runs/month)
**Output:** An HTML report ranking the top 15 posts from your niche, ready to inform your content strategy

---

## Architecture Overview

```
ig-competitor-research/
├── config/
│   └── competitors.json          ← Competitor handles + metadata
├── scripts/
│   ├── scrape_instagram.py       ← Phase 1: Apify API call
│   ├── rank_and_select.py        ← Phase 2: Rank posts, pick top 15
│   ├── download_media.py         ← Phase 3a: Download video/images
│   ├── extract_frames.py         ← Phase 3b: FFmpeg frame extraction
│   ├── transcribe_audio.py       ← Phase 3c: Whisper transcription
│   ├── analyze_post.py           ← Phase 3d: AI analysis per post
│   ├── generate_report.py        ← Phase 4: Build HTML report
│   └── utils.py                  ← Shared helpers (paths, logging, etc.)
├── output/
│   └── reports/                  ← Generated HTML reports (timestamped)
├── temp/                         ← Working directory for downloads/frames
├── requirements.txt              ← Python dependencies
├── .env                          ← API keys (Apify token)
└── README.md                     ← Setup instructions
```

---

## Prerequisites & Dependencies

### System Dependencies

| Tool | Purpose | Install (Windows) |
|------|---------|-------------------|
| **Python 3.10+** | Runtime | Already installed |
| **FFmpeg** | Extract video frames + audio | `winget install ffmpeg` or download from https://ffmpeg.org/download.html — add to PATH |
| **FFprobe** | Media metadata (bundled with FFmpeg) | Comes with FFmpeg |

### Python Dependencies (`requirements.txt`)

```
requests>=2.31.0
openai-whisper>=20231117
apify-client>=1.7.0
python-dotenv>=1.0.0
jinja2>=3.1.0
Pillow>=10.0.0
```

### Accounts

| Service | Purpose | Setup |
|---------|---------|-------|
| **Apify** | Instagram scraping | 1. Sign up at apify.com  2. Go to Settings → API & Integrations  3. Copy your API token  4. Paste into `.env` as `APIFY_TOKEN=your_token_here` |
| **OpenAI** (optional) | Alternative to local Whisper — use API for faster transcription | Only if local Whisper is too slow; set `OPENAI_API_KEY` in `.env` |

### `.env` File

```
APIFY_TOKEN=your_apify_api_token_here
# Optional: for API-based transcription instead of local Whisper
# OPENAI_API_KEY=your_openai_key_here
# Optional: for AI analysis (if not using Claude Code sub-agents)
# ANTHROPIC_API_KEY=your_anthropic_key_here
```

---

## Apify Actor Recommendation

### Primary: `apify/instagram-scraper` (Official)

- **Actor ID:** `apify/instagram-scraper`
- **Why:** Official actor, well-maintained, handles profile scraping, returns full post data (likes, comments, captions, media URLs, timestamps)
- **Cost:** ~$0.15 for ~57 posts across 5 handles
- **Free tier:** $5/month free credits = ~33 runs/month (more than enough for weekly runs)

### Alternative: `shu8hern/instagram-scraper`

- Cheaper per result, community-maintained
- Same data output, slightly different input schema
- Good fallback if the official actor changes pricing

### Apify Input Schema (for `apify/instagram-scraper`)

```json
{
  "directUrls": [
    "https://www.instagram.com/handle1/",
    "https://www.instagram.com/handle2/",
    "https://www.instagram.com/handle3/"
  ],
  "resultsType": "posts",
  "resultsLimit": 10,
  "searchType": "user",
  "maxRequestRetries": 3,
  "addParentData": true
}
```

**Key fields returned per post:**
- `shortCode` — unique post identifier
- `url` — direct link to the post
- `videoUrl` / `displayUrl` — media URL (video or image)
- `likesCount` — number of likes
- `commentsCount` — number of comments
- `caption` — post caption text
- `timestamp` — when it was posted
- `ownerUsername` — which competitor posted it
- `type` — "Video", "Image", "Sidecar" (carousel)
- `videoViewCount` — views (for videos)

---

## Phase-by-Phase Build Plan

### Phase 1: Scrape Competitor Posts

**File:** `scripts/scrape_instagram.py`

**What it does:**
1. Read competitor handles from `config/competitors.json`
2. Call Apify API to run the Instagram scraper actor
3. Wait for the run to complete (polling or webhook)
4. Download results as JSON
5. Save raw data to `temp/raw_posts.json`

**Config format (`config/competitors.json`):**
```json
{
  "competitors": [
    { "handle": "competitor1", "niche": "AI tools" },
    { "handle": "competitor2", "niche": "AI tools" },
    { "handle": "competitor3", "niche": "AI tools" },
    { "handle": "competitor4", "niche": "AI tools" },
    { "handle": "competitor5", "niche": "AI tools" }
  ],
  "posts_per_handle": 10,
  "lookback_days": 7
}
```

**Apify API call flow:**
```python
from apify_client import ApifyClient

client = ApifyClient(os.getenv("APIFY_TOKEN"))

run_input = {
    "directUrls": [f"https://www.instagram.com/{h['handle']}/" for h in competitors],
    "resultsType": "posts",
    "resultsLimit": posts_per_handle,
}

run = client.actor("apify/instagram-scraper").call(run_input=run_input)
items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
```

**Filter posts:** Only keep posts from the last 7 days (use `timestamp` field).

---

### Phase 2: Rank & Select Top Posts

**File:** `scripts/rank_and_select.py`

**What it does:**
1. Load raw posts from Phase 1
2. Group posts by competitor handle
3. Select top 3 posts per handle (by engagement = likes + comments)
4. Combine all selected posts (~15 total)
5. Re-rank the full list by engagement score (highest first)
6. Calculate **outlier score** for each post

**Outlier score formula:**
```
outlier_score = post_engagement / account_median_engagement
```

A post with an outlier score of 5.0x means it got 5x the account's typical engagement — it struck a nerve.

**Output:** `temp/selected_posts.json` — the top 15 posts ranked by engagement, with metadata.

---

### Phase 3: Analyze Each Post (The Heavy Lifting)

This phase has 4 sub-steps per post. In the original system, each post is analyzed by a parallel sub-agent. For a standalone build, process them sequentially or use Python's `concurrent.futures` for parallelism.

#### Phase 3a: Download Media

**File:** `scripts/download_media.py`

**What it does:**
- For each of the 15 selected posts:
  - If **video**: download the video file from `videoUrl`
  - If **image**: download the image from `displayUrl`
  - If **carousel**: download first image/video
- Save to `temp/media/{shortCode}.mp4` or `.jpg`

**Notes:**
- Instagram CDN URLs expire — download immediately after scraping
- Use `requests` with proper headers (User-Agent)
- If CDN URLs fail, try `yt-dlp` as fallback: `yt-dlp https://www.instagram.com/reel/{shortCode}/`

#### Phase 3b: Extract Frames (Videos Only)

**File:** `scripts/extract_frames.py`

**What it does:**
- For each video file, extract 3–5 key frames using FFmpeg
- Extract audio track for transcription

**FFmpeg commands:**
```bash
# Extract 4 frames evenly spaced through the video
ffmpeg -i input.mp4 -vf "select=not(mod(n\,{interval}))" -frames:v 4 -vsync vfn frame_%02d.jpg

# Extract audio for transcription
ffmpeg -i input.mp4 -vn -ac 1 -ar 16000 -b:a 64k audio.wav
```

**Output:**
- `temp/frames/{shortCode}/frame_01.jpg` ... `frame_04.jpg`
- `temp/audio/{shortCode}.wav`

#### Phase 3c: Transcribe Audio

**File:** `scripts/transcribe_audio.py`

**What it does:**
- For each audio file, run Whisper to get timestamped transcript
- Extract the **hook** (first sentence / first 3 seconds)

**Local Whisper:**
```python
import whisper

model = whisper.load_model("base")  # or "small" for better accuracy
result = model.transcribe("temp/audio/{shortCode}.wav")
transcript = result["text"]
segments = result["segments"]  # timestamped segments
hook = segments[0]["text"] if segments else ""
```

**Alternative — OpenAI Whisper API** (faster, costs money):
```python
from openai import OpenAI
client = OpenAI()
with open(audio_path, "rb") as f:
    result = client.audio.transcriptions.create(model="whisper-1", file=f)
```

#### Phase 3d: AI Analysis Per Post

**File:** `scripts/analyze_post.py`

**What it does:**
- For each post, send the frames + transcript + engagement data to an LLM
- Get back a structured analysis

**Input to AI:**
- Frame images (for visual format analysis)
- Transcript text
- Caption text
- Engagement metrics (likes, comments, views)
- Account info (follower count, typical engagement)

**Prompt template:**
```
Analyze this Instagram post and provide:

1. **Hook**: The opening hook (first 1-2 sentences or first 3 seconds)
2. **Visual Format**: What type of content is this? (talking head, listicle, carousel, text overlay, B-roll montage, screen recording, etc.)
3. **Format Breakdown**: Describe the visual structure — transitions, text placement, pacing
4. **Topic**: What specific topic/angle does this cover?
5. **Why It Worked**: Based on the engagement metrics (outlier score: {outlier}x), analyze why this post outperformed. Consider: hook strength, topic relevance, format choice, controversy, relatability, trend-riding
6. **Replication Notes**: How could someone in a similar niche recreate this format with their own topic?

Post data:
- Account: @{handle}
- Likes: {likes} | Comments: {comments} | Views: {views}
- Outlier Score: {outlier}x (vs account median)
- Caption: {caption}
- Transcript: {transcript}
```

**Output per post (structured JSON):**
```json
{
  "shortCode": "ABC123",
  "handle": "@competitor1",
  "hook": "Every single pick runs the same engine...",
  "visual_format": "Talking Head Listicle",
  "format_breakdown": "Creator speaks to camera with text overlays...",
  "topic": "AI coding tools comparison",
  "why_it_worked": "Strong controversy hook, timely topic...",
  "replication_notes": "Film talking head, overlay 5 tool logos...",
  "likes": 5432,
  "comments": 231,
  "views": 89000,
  "outlier_score": 4.2,
  "transcript": "...",
  "post_url": "https://www.instagram.com/p/ABC123/",
  "posted_date": "2026-06-20",
  "frames": ["frame_01.jpg", "frame_02.jpg"]
}
```

**AI provider options:**
- **Claude API** (`anthropic` Python SDK) — best for vision analysis of frames
- **OpenAI GPT-4o** — also handles vision well
- **Local LLM** — if you want zero API costs (but much slower)

---

### Phase 4: Generate HTML Report

**File:** `scripts/generate_report.py`

**What it does:**
1. Load all 15 post analyses from Phase 3
2. Render into a styled HTML report using Jinja2 template
3. Save to `output/reports/IG-Competitor-Research_{YYYY-MM-DD}.html`

**Report structure:**
```html
<h1>IG Competitor Research Report</h1>
<p>Generated: {date} | Handles analyzed: {count} | Posts scraped: {total}</p>

<h2>🔥 What's Working in the Niche</h2>
<p>{AI-generated summary of patterns across all 15 posts}</p>

<!-- For each post, ranked by outlier score -->
<div class="post-card">
  <div class="rank">#1</div>
  <div class="handle">@competitor1</div>
  <div class="metrics">
    <span>❤️ 5,432</span>
    <span>💬 231</span>
    <span>👁️ 89K</span>
    <span>⚡ 4.2x outlier</span>
  </div>
  <div class="hook">"Every single pick runs the same engine..."</div>
  <div class="format">Talking Head Listicle</div>
  <div class="breakdown">...</div>
  <div class="transcript">...</div>
  <div class="why-it-worked">...</div>
  <div class="replication-notes">...</div>
  <a href="https://instagram.com/p/ABC123/">View Original Post →</a>
</div>
```

**Include at the bottom:**
- Pattern summary: which formats dominated, which topics trended
- Recommended content ideas based on the research
- Engagement chart (if desired)

---

## Orchestration: How to Wire It All Together

### Option A: Single Python Script (Simplest)

Create a `main.py` that runs all phases sequentially:

```python
# main.py
import os
from scripts.scrape_instagram import scrape_competitors
from scripts.rank_and_select import rank_and_select
from scripts.download_media import download_all_media
from scripts.extract_frames import extract_all_frames
from scripts.transcribe_audio import transcribe_all
from scripts.analyze_post import analyze_all_posts
from scripts.generate_report import generate_report

def run():
    print("Phase 1: Scraping Instagram via Apify...")
    raw_posts = scrape_competitors()

    print("Phase 2: Ranking and selecting top posts...")
    selected = rank_and_select(raw_posts, top_per_handle=3)

    print("Phase 3a: Downloading media...")
    download_all_media(selected)

    print("Phase 3b: Extracting frames...")
    extract_all_frames(selected)

    print("Phase 3c: Transcribing audio...")
    transcribe_all(selected)

    print("Phase 3d: Analyzing posts with AI...")
    analyses = analyze_all_posts(selected)

    print("Phase 4: Generating HTML report...")
    report_path = generate_report(analyses)

    print(f"Done! Report saved to: {report_path}")

if __name__ == "__main__":
    run()
```

### Option B: Claude Code Skill (What He Did)

If you want to replicate his exact setup inside Claude Code:

1. Create a `skill.md` file in `.claude/skills/ig-competitor-research/`
2. The skill.md describes the automation and tells Claude how to orchestrate
3. Claude spawns sub-agents for parallel post analysis
4. Triggered by typing "IG competitor research" in Claude Code

### Option C: Cron / Scheduled (Weekly Automation)

Run `main.py` on a schedule:
- **Windows Task Scheduler**: Run every Monday at 9 AM
- **Or** use a simple batch file: `python main.py`

---

## Build Order (Recommended Sequence)

| Step | What to Build | Est. Time | Test By |
|------|---------------|-----------|---------|
| 1 | `config/competitors.json` + `.env` | 10 min | Verify handles are valid |
| 2 | `scripts/scrape_instagram.py` | 30 min | Run and check `temp/raw_posts.json` has data |
| 3 | `scripts/rank_and_select.py` | 20 min | Check `temp/selected_posts.json` has 15 ranked posts |
| 4 | `scripts/download_media.py` | 30 min | Check `temp/media/` has downloaded files |
| 5 | `scripts/extract_frames.py` | 20 min | Check `temp/frames/` has JPEGs per post |
| 6 | `scripts/transcribe_audio.py` | 30 min | Check transcripts are accurate |
| 7 | `scripts/analyze_post.py` | 45 min | Check JSON output has all fields populated |
| 8 | `scripts/generate_report.py` + Jinja2 template | 45 min | Open HTML in browser, verify it looks good |
| 9 | `main.py` orchestrator | 15 min | Full end-to-end run |
| 10 | Polish: error handling, retry logic, cleanup temp files | 30 min | Run twice, verify no stale data |

**Total estimated build time: ~4–5 hours**

---

## Key Implementation Notes

### Instagram CDN URLs Expire
Download media immediately after the Apify scrape completes. Don't store URLs for later — they expire within hours.

### Whisper Model Sizes
| Model | Size | Speed | Accuracy | RAM |
|-------|------|-------|----------|-----|
| `tiny` | 39 MB | Very fast | Low | ~1 GB |
| `base` | 74 MB | Fast | Good enough | ~1 GB |
| `small` | 244 MB | Medium | Better | ~2 GB |
| `medium` | 769 MB | Slow | Great | ~5 GB |

**Recommendation:** Start with `base` — fast enough and accurate for short Instagram videos (15–90 seconds).

### Rate Limiting & Error Handling
- Apify: respect their rate limits; the client library handles retries
- Instagram CDN: add 1-second delays between downloads
- Whisper: local, no rate limits
- AI analysis: if using Claude/OpenAI API, add retry with exponential backoff

### Cleanup
After generating the report, delete `temp/` contents to avoid disk bloat. Keep `output/reports/` for history.

### Cost Summary (Per Run)

| Component | Cost |
|-----------|------|
| Apify scraping | ~$0.15 (free tier) |
| FFmpeg | Free (local) |
| Whisper | Free (local) |
| AI analysis (15 posts) | ~$0.10–0.30 if using Claude/OpenAI API |
| **Total** | **~$0.25–0.45 per run** |

If run weekly: **~$1–2/month total.**

---

## Extending the System

Once the core is working, consider adding:

- **TikTok competitor research** — same flow, different Apify actor (`clockworks/tiktok-scraper`)
- **Auto-posting** — feed winning topics into a content generator → auto-schedule posts
- **Trend tracking over time** — store reports in a database, track which formats/topics trend up or down week over week
- **Slack/Discord notifications** — send the report summary to a channel when it completes
- **Multiple client support** — parameterize by client, each with their own competitor list
