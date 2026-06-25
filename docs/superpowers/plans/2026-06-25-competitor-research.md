# Instagram Competitor Research — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that automates Instagram competitor research — scraping posts via Apify, ranking by engagement, analyzing with Claude vision sub-agents, and generating a ranked HTML report.

**Architecture:** Skill-Orchestrated Python Pipeline. Python scripts handle I/O-heavy work (scraping, downloading, frame extraction, transcription). Claude sub-agents handle visual analysis in-conversation. A skill.md file orchestrates the full pipeline, spawning sub-agents for parallel post analysis.

**Tech Stack:** Python 3.10+, apify-client, FFmpeg, openai-whisper, Jinja2, Pillow, pytest

## Global Constraints

- Python 3.10+ required (type hints use `list[dict]` syntax)
- FFmpeg must be installed and on PATH
- All scripts must be independently runnable with `--input` flag for test fixtures
- Normalized post schema: `id`, `platform`, `handle`, `url`, `media_url`, `media_type`, `likes`, `comments`, `views`, `caption`, `timestamp`
- Temp files go in `temp/`, reports go in `output/reports/`
- Each script reads from and writes to JSON files — no direct inter-script imports at runtime
- Plugin must be installable by team members via `claude plugin add`

---

### Task 1: Project Scaffold & Instagram Scraper (Phase 1)

**Files:**
- Create: `plugin.json`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `config/competitors.json`
- Create: `scripts/__init__.py`
- Create: `scripts/scrape_instagram.py`
- Create: `tests/__init__.py`
- Create: `tests/test_scrape_instagram.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: `config/competitors.json` (handle list), `APIFY_TOKEN` env var
- Produces: `temp/raw_posts.json` — list of normalized post dicts. Function `scrape(handles: list[dict], posts_per_handle: int, lookback_days: int) -> list[dict]` and CLI entry `main(config_path: str, output_path: str) -> None`

- [ ] **Step 1: Create project scaffold**

`.gitignore`:
```
__pycache__/
*.pyc
.env
temp/
output/
*.egg-info/
dist/
build/
```

`plugin.json`:
```json
{
  "name": "viral-analyzer",
  "version": "0.1.0",
  "description": "Instagram competitor research automation — scrape, rank, analyze, and report on competitor posts"
}
```

`.env.example`:
```
APIFY_TOKEN=your_apify_api_token_here
```

`requirements.txt`:
```
requests>=2.31.0
openai-whisper>=20231117
apify-client>=1.7.0
python-dotenv>=1.0.0
jinja2>=3.1.0
Pillow>=10.0.0
pytest>=7.0.0
```

`config/competitors.json`:
```json
{
  "competitors": [
    { "handle": "example_handle_1", "niche": "AI tools" },
    { "handle": "example_handle_2", "niche": "AI tools" }
  ],
  "posts_per_handle": 10,
  "lookback_days": 7
}
```

`scripts/__init__.py`: empty file
`tests/__init__.py`: empty file

- [ ] **Step 2: Write the failing tests for scrape_instagram.py**

Create `tests/fixtures/` directory.

`tests/test_scrape_instagram.py`:
```python
import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from scripts.scrape_instagram import scrape, normalize_post, filter_recent_posts


SAMPLE_APIFY_POST = {
    "shortCode": "ABC123",
    "url": "https://www.instagram.com/p/ABC123/",
    "videoUrl": "https://cdn.instagram.com/video.mp4",
    "displayUrl": "https://cdn.instagram.com/image.jpg",
    "likesCount": 5432,
    "commentsCount": 231,
    "videoViewCount": 89000,
    "caption": "Check out this AI tool",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "ownerUsername": "competitor1",
    "type": "Video",
}

SAMPLE_APIFY_IMAGE_POST = {
    "shortCode": "DEF456",
    "url": "https://www.instagram.com/p/DEF456/",
    "videoUrl": None,
    "displayUrl": "https://cdn.instagram.com/image2.jpg",
    "likesCount": 1200,
    "commentsCount": 45,
    "videoViewCount": None,
    "caption": "New feature drop",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "ownerUsername": "competitor2",
    "type": "Image",
}

OLD_POST = {
    **SAMPLE_APIFY_POST,
    "shortCode": "OLD999",
    "timestamp": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
}


class TestNormalizePost:
    def test_normalizes_video_post(self):
        result = normalize_post(SAMPLE_APIFY_POST)
        assert result["id"] == "ABC123"
        assert result["platform"] == "instagram"
        assert result["handle"] == "competitor1"
        assert result["media_url"] == "https://cdn.instagram.com/video.mp4"
        assert result["media_type"] == "video"
        assert result["likes"] == 5432
        assert result["comments"] == 231
        assert result["views"] == 89000
        assert result["caption"] == "Check out this AI tool"

    def test_normalizes_image_post(self):
        result = normalize_post(SAMPLE_APIFY_IMAGE_POST)
        assert result["media_url"] == "https://cdn.instagram.com/image2.jpg"
        assert result["media_type"] == "image"
        assert result["views"] is None

    def test_carousel_type(self):
        carousel = {**SAMPLE_APIFY_POST, "type": "Sidecar"}
        result = normalize_post(carousel)
        assert result["media_type"] == "carousel"


class TestFilterRecentPosts:
    def test_filters_old_posts(self):
        posts = [
            normalize_post(SAMPLE_APIFY_POST),
            normalize_post(OLD_POST),
        ]
        recent = filter_recent_posts(posts, lookback_days=7)
        assert len(recent) == 1
        assert recent[0]["id"] == "ABC123"

    def test_keeps_all_recent(self):
        posts = [
            normalize_post(SAMPLE_APIFY_POST),
            normalize_post(SAMPLE_APIFY_IMAGE_POST),
        ]
        recent = filter_recent_posts(posts, lookback_days=7)
        assert len(recent) == 2


class TestScrape:
    @patch("scripts.scrape_instagram.ApifyClient")
    def test_scrape_calls_apify_and_normalizes(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [SAMPLE_APIFY_POST, SAMPLE_APIFY_IMAGE_POST]
        mock_client.actor.return_value.call.return_value = {"defaultDatasetId": "ds123"}
        mock_client.dataset.return_value = mock_dataset

        handles = [{"handle": "competitor1", "niche": "AI tools"}]
        with patch.dict(os.environ, {"APIFY_TOKEN": "test_token"}):
            result = scrape(handles, posts_per_handle=10, lookback_days=7)

        assert len(result) == 2
        assert result[0]["platform"] == "instagram"
        assert result[0]["id"] == "ABC123"
        mock_client.actor.assert_called_once_with("apify/instagram-scraper")

    @patch("scripts.scrape_instagram.ApifyClient")
    def test_scrape_filters_old_posts(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [SAMPLE_APIFY_POST, OLD_POST]
        mock_client.actor.return_value.call.return_value = {"defaultDatasetId": "ds123"}
        mock_client.dataset.return_value = mock_dataset

        handles = [{"handle": "competitor1", "niche": "AI tools"}]
        with patch.dict(os.environ, {"APIFY_TOKEN": "test_token"}):
            result = scrape(handles, posts_per_handle=10, lookback_days=7)

        assert len(result) == 1
        assert result[0]["id"] == "ABC123"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_scrape_instagram.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.scrape_instagram'`

- [ ] **Step 4: Implement scrape_instagram.py**

`scripts/scrape_instagram.py`:
```python
import argparse
import json
import os
from datetime import datetime, timezone, timedelta

from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

TYPE_MAP = {
    "Video": "video",
    "Image": "image",
    "Sidecar": "carousel",
}


def normalize_post(raw: dict) -> dict:
    media_type = TYPE_MAP.get(raw.get("type", ""), "image")
    if media_type == "video":
        media_url = raw.get("videoUrl") or raw.get("displayUrl", "")
    else:
        media_url = raw.get("displayUrl", "")

    return {
        "id": raw["shortCode"],
        "platform": "instagram",
        "handle": raw["ownerUsername"],
        "url": raw["url"],
        "media_url": media_url,
        "media_type": media_type,
        "likes": raw.get("likesCount", 0),
        "comments": raw.get("commentsCount", 0),
        "views": raw.get("videoViewCount"),
        "caption": raw.get("caption", ""),
        "timestamp": raw["timestamp"],
    }


def filter_recent_posts(posts: list[dict], lookback_days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    recent = []
    for post in posts:
        post_time = datetime.fromisoformat(post["timestamp"])
        if post_time.tzinfo is None:
            post_time = post_time.replace(tzinfo=timezone.utc)
        if post_time >= cutoff:
            recent.append(post)
    return recent


def scrape(handles: list[dict], posts_per_handle: int, lookback_days: int) -> list[dict]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise ValueError("APIFY_TOKEN environment variable is not set")

    client = ApifyClient(token)

    direct_urls = [f"https://www.instagram.com/{h['handle']}/" for h in handles]
    run_input = {
        "directUrls": direct_urls,
        "resultsType": "posts",
        "resultsLimit": posts_per_handle,
        "searchType": "user",
        "maxRequestRetries": 3,
        "addParentData": True,
    }

    run = client.actor("apify/instagram-scraper").call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    posts = [normalize_post(item) for item in items]
    return filter_recent_posts(posts, lookback_days)


def main(config_path: str, output_path: str) -> None:
    with open(config_path) as f:
        config = json.load(f)

    posts = scrape(
        handles=config["competitors"],
        posts_per_handle=config.get("posts_per_handle", 10),
        lookback_days=config.get("lookback_days", 7),
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(posts, f, indent=2)

    print(f"Scraped {len(posts)} posts -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Instagram competitor posts via Apify")
    parser.add_argument("--config", default="config/competitors.json")
    parser.add_argument("--output", default="temp/raw_posts.json")
    args = parser.parse_args()
    main(args.config, args.output)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_scrape_instagram.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Install dependencies and commit**

```bash
pip install -r requirements.txt
git init
git add plugin.json .gitignore .env.example requirements.txt config/competitors.json scripts/__init__.py scripts/scrape_instagram.py tests/__init__.py tests/test_scrape_instagram.py
git commit -m "feat: add project scaffold and Instagram scraper (Phase 1)"
```

---

### Task 2: Rank & Select Top Posts (Phase 2)

**Files:**
- Create: `scripts/rank_and_select.py`
- Create: `tests/test_rank_and_select.py`
- Create: `tests/fixtures/sample_raw_posts.json`

**Interfaces:**
- Consumes: `temp/raw_posts.json` — list of normalized post dicts from Task 1
- Produces: `temp/selected_posts.json` — top 15 posts ranked by outlier score. Function `rank_and_select(posts: list[dict], top_per_handle: int) -> list[dict]` adds `outlier_score` field to each post. CLI entry `main(input_path: str, output_path: str, top_per_handle: int) -> None`

- [ ] **Step 1: Create test fixture**

`tests/fixtures/sample_raw_posts.json`:
```json
[
  {"id": "A1", "platform": "instagram", "handle": "creator1", "url": "https://instagram.com/p/A1/", "media_url": "https://cdn.example.com/a1.mp4", "media_type": "video", "likes": 5000, "comments": 200, "views": 80000, "caption": "Big hit post", "timestamp": "2026-06-20T10:00:00+00:00"},
  {"id": "A2", "platform": "instagram", "handle": "creator1", "url": "https://instagram.com/p/A2/", "media_url": "https://cdn.example.com/a2.mp4", "media_type": "video", "likes": 1000, "comments": 50, "views": 15000, "caption": "Average post", "timestamp": "2026-06-21T10:00:00+00:00"},
  {"id": "A3", "platform": "instagram", "handle": "creator1", "url": "https://instagram.com/p/A3/", "media_url": "https://cdn.example.com/a3.jpg", "media_type": "image", "likes": 800, "comments": 30, "views": null, "caption": "Low post", "timestamp": "2026-06-22T10:00:00+00:00"},
  {"id": "A4", "platform": "instagram", "handle": "creator1", "url": "https://instagram.com/p/A4/", "media_url": "https://cdn.example.com/a4.mp4", "media_type": "video", "likes": 500, "comments": 20, "views": 8000, "caption": "Lowest post", "timestamp": "2026-06-22T12:00:00+00:00"},
  {"id": "B1", "platform": "instagram", "handle": "creator2", "url": "https://instagram.com/p/B1/", "media_url": "https://cdn.example.com/b1.mp4", "media_type": "video", "likes": 3000, "comments": 150, "views": 50000, "caption": "Creator2 hit", "timestamp": "2026-06-20T10:00:00+00:00"},
  {"id": "B2", "platform": "instagram", "handle": "creator2", "url": "https://instagram.com/p/B2/", "media_url": "https://cdn.example.com/b2.mp4", "media_type": "video", "likes": 600, "comments": 25, "views": 10000, "caption": "Creator2 normal", "timestamp": "2026-06-21T10:00:00+00:00"},
  {"id": "B3", "platform": "instagram", "handle": "creator2", "url": "https://instagram.com/p/B3/", "media_url": "https://cdn.example.com/b3.jpg", "media_type": "image", "likes": 400, "comments": 15, "views": null, "caption": "Creator2 low", "timestamp": "2026-06-22T10:00:00+00:00"}
]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_rank_and_select.py`:
```python
import json
import os
import pytest

from scripts.rank_and_select import rank_and_select, calculate_outlier_score


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_sample_posts():
    with open(os.path.join(FIXTURES_DIR, "sample_raw_posts.json")) as f:
        return json.load(f)


class TestCalculateOutlierScore:
    def test_outlier_above_median(self):
        score = calculate_outlier_score(
            post_engagement=5200,
            account_median=1050,
        )
        assert round(score, 1) == 5.0

    def test_outlier_at_median(self):
        score = calculate_outlier_score(
            post_engagement=1000,
            account_median=1000,
        )
        assert score == 1.0

    def test_zero_median_returns_zero(self):
        score = calculate_outlier_score(
            post_engagement=500,
            account_median=0,
        )
        assert score == 0.0


class TestRankAndSelect:
    def test_selects_top_per_handle(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        creator1_posts = [p for p in result if p["handle"] == "creator1"]
        creator2_posts = [p for p in result if p["handle"] == "creator2"]
        assert len(creator1_posts) == 3
        assert len(creator2_posts) == 3

    def test_adds_outlier_score(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        for post in result:
            assert "outlier_score" in post
            assert isinstance(post["outlier_score"], float)

    def test_ranked_by_outlier_score_descending(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        scores = [p["outlier_score"] for p in result]
        assert scores == sorted(scores, reverse=True)

    def test_top_post_is_highest_outlier(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        assert result[0]["id"] == "A1"

    def test_limits_when_fewer_posts_than_top_per_handle(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=10)
        creator1_posts = [p for p in result if p["handle"] == "creator1"]
        assert len(creator1_posts) == 4
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_rank_and_select.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement rank_and_select.py**

`scripts/rank_and_select.py`:
```python
import argparse
import json
import os
from statistics import median


def calculate_outlier_score(post_engagement: int, account_median: float) -> float:
    if account_median == 0:
        return 0.0
    return round(post_engagement / account_median, 2)


def rank_and_select(posts: list[dict], top_per_handle: int) -> list[dict]:
    by_handle: dict[str, list[dict]] = {}
    for post in posts:
        by_handle.setdefault(post["handle"], []).append(post)

    account_medians: dict[str, float] = {}
    for handle, handle_posts in by_handle.items():
        engagements = [p["likes"] + p["comments"] for p in handle_posts]
        account_medians[handle] = median(engagements) if engagements else 0.0

    selected = []
    for handle, handle_posts in by_handle.items():
        sorted_posts = sorted(
            handle_posts,
            key=lambda p: p["likes"] + p["comments"],
            reverse=True,
        )
        selected.extend(sorted_posts[:top_per_handle])

    for post in selected:
        engagement = post["likes"] + post["comments"]
        post["outlier_score"] = calculate_outlier_score(
            engagement, account_medians[post["handle"]]
        )

    selected.sort(key=lambda p: p["outlier_score"], reverse=True)
    return selected


def main(input_path: str, output_path: str, top_per_handle: int) -> None:
    with open(input_path) as f:
        posts = json.load(f)

    selected = rank_and_select(posts, top_per_handle)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(selected, f, indent=2)

    print(f"Selected {len(selected)} posts -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rank and select top posts")
    parser.add_argument("--input", default="temp/raw_posts.json")
    parser.add_argument("--output", default="temp/selected_posts.json")
    parser.add_argument("--top-per-handle", type=int, default=3)
    args = parser.parse_args()
    main(args.input, args.output, args.top_per_handle)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_rank_and_select.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/rank_and_select.py tests/test_rank_and_select.py tests/fixtures/sample_raw_posts.json
git commit -m "feat: add post ranking and selection with outlier scoring (Phase 2)"
```

---

### Task 3: Download Media (Phase 3a)

**Files:**
- Create: `scripts/download_media.py`
- Create: `tests/test_download_media.py`

**Interfaces:**
- Consumes: `temp/selected_posts.json` — list of ranked posts with `media_url` and `media_type` fields
- Produces: `temp/media/{id}.mp4` or `temp/media/{id}.jpg` per post. Function `download_all_media(posts: list[dict], output_dir: str) -> list[dict]` returns posts with added `local_media_path` field (None if download failed). CLI entry `main(input_path: str, output_dir: str) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_download_media.py`:
```python
import os
import json
import pytest
from unittest.mock import patch, MagicMock

from scripts.download_media import download_single, download_all_media


SAMPLE_VIDEO_POST = {
    "id": "VID1",
    "media_url": "https://cdn.example.com/video.mp4",
    "media_type": "video",
    "handle": "creator1",
}

SAMPLE_IMAGE_POST = {
    "id": "IMG1",
    "media_url": "https://cdn.example.com/image.jpg",
    "media_type": "image",
    "handle": "creator1",
}


class TestDownloadSingle:
    @patch("scripts.download_media.requests.get")
    def test_downloads_video(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content = MagicMock(return_value=[b"video_data"])
        mock_get.return_value = mock_response

        path = download_single(SAMPLE_VIDEO_POST, str(tmp_path))
        assert path is not None
        assert path.endswith(".mp4")
        assert os.path.exists(path)

    @patch("scripts.download_media.requests.get")
    def test_downloads_image(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content = MagicMock(return_value=[b"image_data"])
        mock_get.return_value = mock_response

        path = download_single(SAMPLE_IMAGE_POST, str(tmp_path))
        assert path is not None
        assert path.endswith(".jpg")

    @patch("scripts.download_media.requests.get")
    def test_returns_none_on_404(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404")
        mock_get.return_value = mock_response

        path = download_single(SAMPLE_VIDEO_POST, str(tmp_path))
        assert path is None


class TestDownloadAllMedia:
    @patch("scripts.download_media.download_single")
    @patch("scripts.download_media.time.sleep")
    def test_adds_local_media_path(self, mock_sleep, mock_download):
        mock_download.return_value = "/tmp/media/VID1.mp4"
        posts = [SAMPLE_VIDEO_POST.copy()]

        result = download_all_media(posts, "/tmp/media")
        assert result[0]["local_media_path"] == "/tmp/media/VID1.mp4"

    @patch("scripts.download_media.download_single")
    @patch("scripts.download_media.time.sleep")
    def test_sets_none_on_failure(self, mock_sleep, mock_download):
        mock_download.return_value = None
        posts = [SAMPLE_VIDEO_POST.copy()]

        result = download_all_media(posts, "/tmp/media")
        assert result[0]["local_media_path"] is None

    @patch("scripts.download_media.download_single")
    @patch("scripts.download_media.time.sleep")
    def test_delays_between_downloads(self, mock_sleep, mock_download):
        mock_download.return_value = "/tmp/media/file.mp4"
        posts = [SAMPLE_VIDEO_POST.copy(), SAMPLE_IMAGE_POST.copy()]

        download_all_media(posts, "/tmp/media")
        assert mock_sleep.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_download_media.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement download_media.py**

`scripts/download_media.py`:
```python
import argparse
import json
import os
import time

import requests


EXTENSION_MAP = {
    "video": ".mp4",
    "image": ".jpg",
    "carousel": ".jpg",
}


def download_single(post: dict, output_dir: str) -> str | None:
    ext = EXTENSION_MAP.get(post["media_type"], ".jpg")
    output_path = os.path.join(output_dir, f"{post['id']}{ext}")

    try:
        response = requests.get(
            post["media_url"],
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
            timeout=30,
        )
        response.raise_for_status()
    except Exception:
        print(f"  Failed to download {post['id']}: media unavailable")
        return None

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return output_path


def download_all_media(posts: list[dict], output_dir: str) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for i, post in enumerate(posts):
        print(f"  Downloading {post['id']} ({post['media_type']})...")
        post = post.copy()
        post["local_media_path"] = download_single(post, output_dir)
        results.append(post)

        if i < len(posts) - 1:
            time.sleep(1)

    return results


def main(input_path: str, output_dir: str) -> None:
    with open(input_path) as f:
        posts = json.load(f)

    results = download_all_media(posts, output_dir)

    with open(input_path, "w") as f:
        json.dump(results, f, indent=2)

    downloaded = sum(1 for p in results if p["local_media_path"])
    print(f"Downloaded {downloaded}/{len(results)} media files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download media for selected posts")
    parser.add_argument("--input", default="temp/selected_posts.json")
    parser.add_argument("--output-dir", default="temp/media")
    args = parser.parse_args()
    main(args.input, args.output_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_download_media.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/download_media.py tests/test_download_media.py
git commit -m "feat: add media downloader with CDN failure handling (Phase 3a)"
```

---

### Task 4: Extract Frames & Audio (Phase 3b)

**Files:**
- Create: `scripts/extract_frames.py`
- Create: `tests/test_extract_frames.py`

**Interfaces:**
- Consumes: `temp/media/{id}.mp4` or `.jpg` files, posts with `local_media_path` and `media_type` fields
- Produces: `temp/frames/{id}/frame_01..04.jpg` and `temp/audio/{id}.wav`. Function `extract_all_frames(posts: list[dict], frames_dir: str, audio_dir: str) -> list[dict]` returns posts with added `frames_dir` and `audio_path` fields. CLI entry `main(input_path: str, frames_dir: str, audio_dir: str) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_frames.py`:
```python
import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

from scripts.extract_frames import (
    check_ffmpeg,
    get_video_duration,
    extract_frames_from_video,
    extract_audio_from_video,
    process_post,
)


class TestCheckFfmpeg:
    @patch("scripts.extract_frames.shutil.which")
    def test_raises_when_ffmpeg_missing(self, mock_which):
        mock_which.return_value = None
        with pytest.raises(RuntimeError, match="FFmpeg is not installed"):
            check_ffmpeg()

    @patch("scripts.extract_frames.shutil.which")
    def test_passes_when_ffmpeg_present(self, mock_which):
        mock_which.return_value = "/usr/bin/ffmpeg"
        check_ffmpeg()


class TestProcessPost:
    def test_copies_image_to_frames_dir(self, tmp_path):
        frames_dir = str(tmp_path / "frames")
        audio_dir = str(tmp_path / "audio")
        img_path = str(tmp_path / "IMG1.jpg")
        with open(img_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        post = {
            "id": "IMG1",
            "media_type": "image",
            "local_media_path": img_path,
        }

        result = process_post(post, frames_dir, audio_dir)
        assert result["frames_dir"] is not None
        assert result["audio_path"] is None
        assert os.path.exists(os.path.join(result["frames_dir"], "frame_01.jpg"))

    def test_skips_when_no_local_media(self, tmp_path):
        post = {
            "id": "MISS1",
            "media_type": "video",
            "local_media_path": None,
        }
        result = process_post(post, str(tmp_path / "frames"), str(tmp_path / "audio"))
        assert result["frames_dir"] is None
        assert result["audio_path"] is None

    @patch("scripts.extract_frames.extract_audio_from_video")
    @patch("scripts.extract_frames.extract_frames_from_video")
    @patch("scripts.extract_frames.get_video_duration")
    def test_processes_video(self, mock_duration, mock_frames, mock_audio, tmp_path):
        mock_duration.return_value = 30.0
        mock_frames.return_value = True
        mock_audio.return_value = True

        video_path = str(tmp_path / "VID1.mp4")
        with open(video_path, "wb") as f:
            f.write(b"\x00" * 100)

        post = {
            "id": "VID1",
            "media_type": "video",
            "local_media_path": video_path,
        }

        result = process_post(post, str(tmp_path / "frames"), str(tmp_path / "audio"))
        assert result["frames_dir"] is not None
        assert result["audio_path"] is not None
        mock_frames.assert_called_once()
        mock_audio.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract_frames.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement extract_frames.py**

`scripts/extract_frames.py`:
```python
import argparse
import json
import os
import shutil
import subprocess


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg is not installed or not on PATH. "
            "Install: winget install ffmpeg (Windows) or brew install ffmpeg (Mac)"
        )


def get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 30.0


def extract_frames_from_video(
    video_path: str, output_dir: str, num_frames: int = 4
) -> bool:
    os.makedirs(output_dir, exist_ok=True)
    duration = get_video_duration(video_path)
    interval = max(1, int(duration / (num_frames + 1)))

    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps=1/{interval}",
            "-frames:v", str(num_frames),
            "-vsync", "vfn",
            "-y",
            os.path.join(output_dir, "frame_%02d.jpg"),
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def extract_audio_from_video(video_path: str, output_path: str) -> bool:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
            "-y", output_path,
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def process_post(post: dict, frames_dir: str, audio_dir: str) -> dict:
    post = post.copy()
    post["frames_dir"] = None
    post["audio_path"] = None

    if not post.get("local_media_path"):
        return post

    post_frames_dir = os.path.join(frames_dir, post["id"])
    post_audio_path = os.path.join(audio_dir, f"{post['id']}.wav")

    if post["media_type"] == "image":
        os.makedirs(post_frames_dir, exist_ok=True)
        shutil.copy2(post["local_media_path"], os.path.join(post_frames_dir, "frame_01.jpg"))
        post["frames_dir"] = post_frames_dir
        return post

    if extract_frames_from_video(post["local_media_path"], post_frames_dir):
        post["frames_dir"] = post_frames_dir

    if extract_audio_from_video(post["local_media_path"], post_audio_path):
        post["audio_path"] = post_audio_path

    return post


def extract_all_frames(
    posts: list[dict], frames_dir: str, audio_dir: str
) -> list[dict]:
    check_ffmpeg()
    results = []
    for post in posts:
        print(f"  Extracting frames for {post['id']}...")
        results.append(process_post(post, frames_dir, audio_dir))
    return results


def main(input_path: str, frames_dir: str, audio_dir: str) -> None:
    with open(input_path) as f:
        posts = json.load(f)

    results = extract_all_frames(posts, frames_dir, audio_dir)

    with open(input_path, "w") as f:
        json.dump(results, f, indent=2)

    extracted = sum(1 for p in results if p["frames_dir"])
    print(f"Extracted frames for {extracted}/{len(results)} posts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract frames and audio from media")
    parser.add_argument("--input", default="temp/selected_posts.json")
    parser.add_argument("--frames-dir", default="temp/frames")
    parser.add_argument("--audio-dir", default="temp/audio")
    args = parser.parse_args()
    main(args.input, args.frames_dir, args.audio_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract_frames.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_frames.py tests/test_extract_frames.py
git commit -m "feat: add frame and audio extraction via FFmpeg (Phase 3b)"
```

---

### Task 5: Transcribe Audio (Phase 3c)

**Files:**
- Create: `scripts/transcribe_audio.py`
- Create: `tests/test_transcribe_audio.py`

**Interfaces:**
- Consumes: Posts with `audio_path` field pointing to WAV files in `temp/audio/`
- Produces: `temp/transcripts/{id}.json` per post containing `{"transcript": "...", "hook": "...", "segments": [...]}`. Function `transcribe_all(posts: list[dict], output_dir: str) -> list[dict]` returns posts with added `transcript_path` field. CLI entry `main(input_path: str, output_dir: str) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_transcribe_audio.py`:
```python
import json
import os
import pytest
from unittest.mock import patch, MagicMock

from scripts.transcribe_audio import transcribe_post, extract_hook


MOCK_WHISPER_RESULT = {
    "text": "Every single pick runs the same engine. Here are the top 5 AI tools you need.",
    "segments": [
        {"start": 0.0, "end": 2.5, "text": "Every single pick runs the same engine."},
        {"start": 2.5, "end": 6.0, "text": " Here are the top 5 AI tools you need."},
    ],
}


class TestExtractHook:
    def test_extracts_first_segment(self):
        hook = extract_hook(MOCK_WHISPER_RESULT["segments"])
        assert hook == "Every single pick runs the same engine."

    def test_empty_segments_returns_empty(self):
        hook = extract_hook([])
        assert hook == ""


class TestTranscribePost:
    @patch("scripts.transcribe_audio.whisper")
    def test_transcribes_and_saves(self, mock_whisper, tmp_path):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = MOCK_WHISPER_RESULT
        mock_whisper.load_model.return_value = mock_model

        audio_path = str(tmp_path / "TEST1.wav")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        post = {"id": "TEST1", "audio_path": audio_path}
        output_dir = str(tmp_path / "transcripts")

        result = transcribe_post(post, output_dir, mock_model)

        assert result["transcript_path"] is not None
        with open(result["transcript_path"]) as f:
            data = json.load(f)
        assert data["transcript"] == MOCK_WHISPER_RESULT["text"]
        assert data["hook"] == "Every single pick runs the same engine."

    def test_skips_when_no_audio(self, tmp_path):
        post = {"id": "NOAUDIO", "audio_path": None}
        result = transcribe_post(post, str(tmp_path), model=None)
        assert result["transcript_path"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_transcribe_audio.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement transcribe_audio.py**

`scripts/transcribe_audio.py`:
```python
import argparse
import json
import os

import whisper


def extract_hook(segments: list[dict]) -> str:
    if not segments:
        return ""
    return segments[0]["text"].strip()


def transcribe_post(post: dict, output_dir: str, model) -> dict:
    post = post.copy()
    post["transcript_path"] = None

    if not post.get("audio_path"):
        return post

    os.makedirs(output_dir, exist_ok=True)
    result = model.transcribe(post["audio_path"])

    transcript_data = {
        "transcript": result["text"],
        "hook": extract_hook(result.get("segments", [])),
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in result.get("segments", [])
        ],
    }

    output_path = os.path.join(output_dir, f"{post['id']}.json")
    with open(output_path, "w") as f:
        json.dump(transcript_data, f, indent=2)

    post["transcript_path"] = output_path
    return post


def transcribe_all(posts: list[dict], output_dir: str) -> list[dict]:
    model = whisper.load_model("base")
    results = []
    for post in posts:
        if post.get("audio_path"):
            print(f"  Transcribing {post['id']}...")
        results.append(transcribe_post(post, output_dir, model))
    return results


def main(input_path: str, output_dir: str) -> None:
    with open(input_path) as f:
        posts = json.load(f)

    results = transcribe_all(posts, output_dir)

    with open(input_path, "w") as f:
        json.dump(results, f, indent=2)

    transcribed = sum(1 for p in results if p["transcript_path"])
    print(f"Transcribed {transcribed}/{len(results)} posts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio with Whisper")
    parser.add_argument("--input", default="temp/selected_posts.json")
    parser.add_argument("--output-dir", default="temp/transcripts")
    args = parser.parse_args()
    main(args.input, args.output_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_transcribe_audio.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/transcribe_audio.py tests/test_transcribe_audio.py
git commit -m "feat: add Whisper audio transcription (Phase 3c)"
```

---

### Task 6: HTML Report Generator (Phase 4)

**Files:**
- Create: `scripts/generate_report.py`
- Create: `templates/report.html`
- Create: `tests/test_generate_report.py`
- Create: `tests/fixtures/sample_analyses.json`

**Interfaces:**
- Consumes: `temp/analyses.json` — merged list of post analysis dicts (from sub-agents), plus a `niche_summary` string. Each analysis has fields: `shortCode`, `handle`, `hook`, `visual_format`, `format_breakdown`, `topic`, `why_it_worked`, `replication_notes`, `metrics`, `transcript`, `post_url`, `posted_date`
- Produces: `output/reports/IG-Competitor-Research_{YYYY-MM-DD}.html`. Function `generate_report(analyses: list[dict], niche_summary: str, frames_dir: str, output_path: str) -> str` returns the output file path. CLI entry `main(input_path: str, niche_summary: str, frames_dir: str, output_dir: str) -> None`

- [ ] **Step 1: Create test fixture**

`tests/fixtures/sample_analyses.json`:
```json
[
  {
    "shortCode": "ABC123",
    "handle": "@creator1",
    "hook": "Every single pick runs the same engine...",
    "visual_format": "Talking Head Listicle",
    "format_breakdown": "Creator speaks to camera with text overlays at 3s intervals.",
    "topic": "AI coding tools comparison",
    "why_it_worked": "Strong controversy hook combined with timely topic.",
    "replication_notes": "Film talking head, overlay 5 tool logos, use numbered format.",
    "metrics": {"likes": 5432, "comments": 231, "views": 89000, "outlier_score": 4.2},
    "transcript": "Every single pick runs the same engine. Here are the top 5 tools.",
    "post_url": "https://www.instagram.com/p/ABC123/",
    "posted_date": "2026-06-20"
  },
  {
    "shortCode": "DEF456",
    "handle": "@creator2",
    "hook": "Stop using ChatGPT wrong...",
    "visual_format": "Screen Recording Tutorial",
    "format_breakdown": "Screen recording with voiceover, annotations highlight key areas.",
    "topic": "ChatGPT productivity tips",
    "why_it_worked": "Negative hook creates curiosity, practical value keeps viewers.",
    "replication_notes": "Record screen demo, use bold annotations, start with mistake everyone makes.",
    "metrics": {"likes": 3200, "comments": 180, "views": 65000, "outlier_score": 3.1},
    "transcript": "Stop using ChatGPT wrong. Here is what you should do instead.",
    "post_url": "https://www.instagram.com/p/DEF456/",
    "posted_date": "2026-06-21"
  }
]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_generate_report.py`:
```python
import json
import os
import pytest

from scripts.generate_report import generate_report, encode_frames_base64


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_sample_analyses():
    with open(os.path.join(FIXTURES_DIR, "sample_analyses.json")) as f:
        return json.load(f)


class TestEncodeFramesBase64:
    def test_encodes_jpeg(self, tmp_path):
        frames_dir = tmp_path / "frames" / "ABC123"
        frames_dir.mkdir(parents=True)
        (frames_dir / "frame_01.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)

        result = encode_frames_base64("ABC123", str(tmp_path / "frames"))
        assert len(result) == 1
        assert result[0].startswith("data:image/jpeg;base64,")

    def test_returns_empty_when_no_frames(self, tmp_path):
        result = encode_frames_base64("MISSING", str(tmp_path / "frames"))
        assert result == []


class TestGenerateReport:
    def test_creates_html_file(self, tmp_path):
        analyses = load_sample_analyses()
        output_path = str(tmp_path / "report.html")

        result = generate_report(
            analyses=analyses,
            niche_summary="AI tools content is dominating with talking head formats.",
            frames_dir=str(tmp_path / "frames"),
            output_path=output_path,
        )

        assert os.path.exists(result)
        with open(result) as f:
            html = f.read()
        assert "Competitor Research Report" in html
        assert "@creator1" in html
        assert "@creator2" in html
        assert "4.2x" in html
        assert "AI tools content is dominating" in html

    def test_posts_ordered_by_rank(self, tmp_path):
        analyses = load_sample_analyses()
        output_path = str(tmp_path / "report.html")

        generate_report(
            analyses=analyses,
            niche_summary="Summary",
            frames_dir=str(tmp_path / "frames"),
            output_path=output_path,
        )

        with open(output_path) as f:
            html = f.read()
        pos_creator1 = html.index("@creator1")
        pos_creator2 = html.index("@creator2")
        assert pos_creator1 < pos_creator2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Create Jinja2 template**

`templates/report.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IG Competitor Research Report — {{ date }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0a; color: #e0e0e0; line-height: 1.6; padding: 2rem; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { font-size: 1.8rem; margin-bottom: 0.5rem; color: #fff; }
        .meta { color: #888; margin-bottom: 2rem; font-size: 0.9rem; }
        .summary { background: #1a1a2e; border-left: 4px solid #e94560; padding: 1.5rem; border-radius: 0 8px 8px 0; margin-bottom: 2rem; }
        .summary h2 { color: #e94560; font-size: 1.2rem; margin-bottom: 0.75rem; }
        .post-card { background: #16213e; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #1a1a3e; }
        .post-header { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
        .rank { font-size: 1.5rem; font-weight: 700; color: #e94560; min-width: 2.5rem; }
        .handle { font-weight: 600; color: #a8d8ea; }
        .metrics { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; font-size: 0.85rem; }
        .metric { background: #0f3460; padding: 0.3rem 0.7rem; border-radius: 20px; }
        .outlier { background: #e94560; color: #fff; font-weight: 600; }
        .hook { font-size: 1.1rem; font-style: italic; color: #fff; margin-bottom: 1rem; padding: 0.75rem; background: #0f3460; border-radius: 8px; }
        .section { margin-bottom: 0.75rem; }
        .section-label { font-weight: 600; color: #a8d8ea; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .section-content { color: #ccc; }
        .frames { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
        .frames img { height: 120px; border-radius: 6px; object-fit: cover; }
        .transcript-toggle { cursor: pointer; color: #e94560; font-size: 0.85rem; text-decoration: underline; }
        .transcript-content { display: none; margin-top: 0.5rem; padding: 0.75rem; background: #0a0a1a; border-radius: 6px; font-size: 0.85rem; color: #999; }
        .post-link { display: inline-block; margin-top: 0.75rem; color: #e94560; text-decoration: none; font-size: 0.9rem; }
        .post-link:hover { text-decoration: underline; }
        .format-badge { display: inline-block; background: #533483; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.8rem; color: #fff; margin-bottom: 0.75rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>IG Competitor Research Report</h1>
        <p class="meta">Generated: {{ date }} | Handles analyzed: {{ handle_count }} | Posts analyzed: {{ post_count }}</p>

        <div class="summary">
            <h2>What's Working in the Niche</h2>
            <p>{{ niche_summary }}</p>
        </div>

        {% for post in posts %}
        <div class="post-card">
            <div class="post-header">
                <span class="rank">#{{ loop.index }}</span>
                <span class="handle">{{ post.handle }}</span>
            </div>

            <div class="metrics">
                <span class="metric">{{ "{:,}".format(post.metrics.likes) }} likes</span>
                <span class="metric">{{ "{:,}".format(post.metrics.comments) }} comments</span>
                {% if post.metrics.views %}
                <span class="metric">{{ "{:,}".format(post.metrics.views) }} views</span>
                {% endif %}
                <span class="metric outlier">{{ post.metrics.outlier_score }}x outlier</span>
            </div>

            <div class="hook">"{{ post.hook }}"</div>

            <span class="format-badge">{{ post.visual_format }}</span>

            {% if post.frame_images %}
            <div class="frames">
                {% for frame in post.frame_images %}
                <img src="{{ frame }}" alt="Frame from post">
                {% endfor %}
            </div>
            {% endif %}

            <div class="section">
                <p class="section-label">Format Breakdown</p>
                <p class="section-content">{{ post.format_breakdown }}</p>
            </div>

            <div class="section">
                <p class="section-label">Topic</p>
                <p class="section-content">{{ post.topic }}</p>
            </div>

            <div class="section">
                <p class="section-label">Why It Worked</p>
                <p class="section-content">{{ post.why_it_worked }}</p>
            </div>

            <div class="section">
                <p class="section-label">Replication Notes</p>
                <p class="section-content">{{ post.replication_notes }}</p>
            </div>

            {% if post.transcript %}
            <span class="transcript-toggle" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'block' ? 'none' : 'block'">
                Show Transcript
            </span>
            <div class="transcript-content">{{ post.transcript }}</div>
            {% endif %}

            <a class="post-link" href="{{ post.post_url }}" target="_blank">View Original Post &rarr;</a>
        </div>
        {% endfor %}
    </div>
</body>
</html>
```

- [ ] **Step 5: Implement generate_report.py**

`scripts/generate_report.py`:
```python
import argparse
import base64
import json
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def encode_frames_base64(short_code: str, frames_dir: str) -> list[str]:
    post_frames_dir = os.path.join(frames_dir, short_code)
    if not os.path.isdir(post_frames_dir):
        return []

    encoded = []
    for fname in sorted(os.listdir(post_frames_dir)):
        if fname.endswith(".jpg"):
            fpath = os.path.join(post_frames_dir, fname)
            with open(fpath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            encoded.append(f"data:image/jpeg;base64,{b64}")
    return encoded


def generate_report(
    analyses: list[dict],
    niche_summary: str,
    frames_dir: str,
    output_path: str,
) -> str:
    for analysis in analyses:
        analysis["frame_images"] = encode_frames_base64(
            analysis["shortCode"], frames_dir
        )

    handles = set()
    for a in analyses:
        handles.add(a["handle"])

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("report.html")

    html = template.render(
        date=datetime.now().strftime("%Y-%m-%d"),
        handle_count=len(handles),
        post_count=len(analyses),
        niche_summary=niche_summary,
        posts=analyses,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def main(input_path: str, niche_summary: str, frames_dir: str, output_dir: str) -> None:
    with open(input_path) as f:
        analyses = json.load(f)

    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = os.path.join(output_dir, f"IG-Competitor-Research_{date_str}.html")

    result = generate_report(analyses, niche_summary, frames_dir, output_path)
    print(f"Report generated -> {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate HTML report from analyses")
    parser.add_argument("--input", default="temp/analyses.json")
    parser.add_argument("--niche-summary", default="No summary provided.")
    parser.add_argument("--frames-dir", default="temp/frames")
    parser.add_argument("--output-dir", default="output/reports")
    args = parser.parse_args()
    main(args.input, args.niche_summary, args.frames_dir, args.output_dir)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate_report.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_report.py templates/report.html tests/test_generate_report.py tests/fixtures/sample_analyses.json
git commit -m "feat: add HTML report generator with Jinja2 template (Phase 4)"
```

---

### Task 7: Plugin Integration — Skill, Agent, and Command

**Files:**
- Create: `skills/competitor-research/skill.md`
- Create: `agents/post-analyzer.md`
- Create: `commands/competitor-research.yaml`

**Interfaces:**
- Consumes: All Python scripts from Tasks 1-6, `config/competitors.json`
- Produces: A fully functional Claude Code plugin invocable via `/competitor-research` or natural language

- [ ] **Step 1: Create the post-analyzer sub-agent**

`agents/post-analyzer.md`:
```markdown
---
name: post-analyzer
description: Analyzes a single Instagram post's visual content, transcript, and engagement metrics to explain why it performed well
tools:
  - Read
  - Write
  - Bash
  - Glob
---

You are a social media content analyst. You receive a single Instagram post with extracted video frames, transcript, and engagement metrics. Your job is to analyze WHY this post performed well and HOW someone could replicate its success.

## Input

You will be given:
1. A post ID and path to its frames directory (JPEGs to analyze visually)
2. A transcript file path (JSON with transcript text and hook)
3. Engagement metrics: likes, comments, views, outlier score
4. The post caption and handle

## Process

1. Read all frame images from the frames directory to understand the visual format
2. Read the transcript JSON for the spoken content and hook
3. Analyze the post considering:
   - What visual format is used (talking head, listicle, screen recording, B-roll, text overlay, etc.)
   - How the content is structured visually (transitions, text placement, pacing)
   - Why the hook works (or doesn't)
   - Why this post outperformed the account's median (the outlier score tells you by how much)
   - What specific elements could be replicated

## Output

Write a JSON file to the specified output path with this exact structure:

```json
{
    "shortCode": "<post ID>",
    "handle": "<@handle>",
    "hook": "<the opening hook — first 1-2 sentences or first 3 seconds>",
    "visual_format": "<format label: Talking Head, Listicle, Screen Recording, etc.>",
    "format_breakdown": "<describe visual structure: transitions, text placement, pacing>",
    "topic": "<specific topic/angle the post covers>",
    "why_it_worked": "<analysis of why this outperformed, referencing the outlier score>",
    "replication_notes": "<actionable steps to recreate this format with a different topic>",
    "metrics": {"likes": 0, "comments": 0, "views": 0, "outlier_score": 0.0},
    "transcript": "<full transcript text>",
    "post_url": "<original post URL>",
    "posted_date": "<YYYY-MM-DD>"
}
```

Be specific and actionable. "Good hook" is useless. "Negative framing hook ('Stop doing X wrong') creates curiosity gap — viewer watches to find out what they're doing wrong" is useful.
```

- [ ] **Step 2: Create the slash command**

`commands/competitor-research.yaml`:
```yaml
name: competitor-research
description: Run Instagram competitor research — scrapes recent posts, ranks by engagement, analyzes with AI, and generates an HTML report
skill: competitor-research
```

- [ ] **Step 3: Create the orchestration skill**

`skills/competitor-research/skill.md`:
```markdown
---
name: competitor-research
description: Automated Instagram competitor research. Scrapes competitor posts via Apify, ranks by engagement, downloads and analyzes media with AI vision, and generates a ranked HTML report. Use when the user asks to analyze competitors, run competitor research, check what's working on Instagram, or invokes /competitor-research.
---

# Instagram Competitor Research Pipeline

You are orchestrating an automated competitor research pipeline. Follow these phases in order.

## Prerequisites Check

Before starting, verify:
1. Run `python -c "import apify_client; print('apify-client OK')"` — if it fails, run `pip install -r requirements.txt`
2. Run `ffmpeg -version` — if it fails, tell the user to install FFmpeg
3. Check that `.env` exists with `APIFY_TOKEN` set — if not, ask the user to create it from `.env.example`

## Phase 1: Scrape Competitor Posts

Run the scraper:
```bash
python scripts/scrape_instagram.py --config config/competitors.json --output temp/raw_posts.json
```

Report to the user: how many posts were scraped, from how many handles.

## Phase 2: Rank & Select Top Posts

Run the ranker:
```bash
python scripts/rank_and_select.py --input temp/raw_posts.json --output temp/selected_posts.json --top-per-handle 3
```

Report: how many posts selected, top outlier scores.

## Phase 3a: Download Media

Run the downloader:
```bash
python scripts/download_media.py --input temp/selected_posts.json --output-dir temp/media
```

Report: how many media files downloaded successfully.

## Phase 3b: Extract Frames & Audio

Run frame extraction:
```bash
python scripts/extract_frames.py --input temp/selected_posts.json --frames-dir temp/frames --audio-dir temp/audio
```

## Phase 3c: Transcribe Audio

Run transcription:
```bash
python scripts/transcribe_audio.py --input temp/selected_posts.json --output-dir temp/transcripts
```

## Phase 3d: Analyze Posts with Sub-Agents

Read `temp/selected_posts.json` to get the list of posts to analyze.

For each post, spawn a `post-analyzer` sub-agent with this prompt:

```
Analyze Instagram post {id} from @{handle}.

Frames directory: temp/frames/{id}/
Transcript file: temp/transcripts/{id}.json
Output file: temp/analyses/{id}.json

Post data:
- URL: {url}
- Likes: {likes} | Comments: {comments} | Views: {views}
- Outlier Score: {outlier_score}x
- Caption: {caption}
- Posted: {posted_date}
```

Spawn up to 5 sub-agents at a time. Wait for each batch to complete before spawning the next.

After all sub-agents complete, merge all individual analysis files into `temp/analyses.json`:
```bash
python -c "
import json, glob, os
analyses = []
for f in sorted(glob.glob('temp/analyses/*.json')):
    with open(f) as fh:
        analyses.append(json.load(fh))
os.makedirs('temp', exist_ok=True)
with open('temp/analyses.json', 'w') as fh:
    json.dump(analyses, fh, indent=2)
print(f'Merged {len(analyses)} analyses')
"
```

## Phase 3.5: Generate Niche Summary

After all analyses are merged, read `temp/analyses.json` and generate a 2-3 paragraph summary of patterns across all posts:
- Which visual formats dominated?
- Which topics trended?
- What hook patterns were most common?
- Any surprising outliers?

Save this summary — you will pass it to the report generator.

## Phase 4: Generate Report

Run the report generator:
```bash
python scripts/generate_report.py --input temp/analyses.json --niche-summary "<your generated niche summary>" --frames-dir temp/frames --output-dir output/reports
```

## Phase 5: Cleanup & Present

1. Delete temp files:
```bash
python -c "import shutil; shutil.rmtree('temp', ignore_errors=True); print('Temp files cleaned up')"
```

2. Tell the user the report is ready and provide the path: `output/reports/IG-Competitor-Research_{date}.html`
3. Offer to open it in their browser

## Error Handling

- If any phase fails, report the error clearly and stop. Don't continue with partial data.
- If a sub-agent fails on a specific post, note it and continue with the remaining posts.
- If fewer than 3 posts are successfully analyzed, warn the user that the report may not be representative.
```

- [ ] **Step 4: Verify plugin structure**

Run: `ls -R skills/ agents/ commands/` (or equivalent) to confirm all files are in place.

Expected structure:
```
skills/competitor-research/skill.md
agents/post-analyzer.md
commands/competitor-research.yaml
```

- [ ] **Step 5: Commit**

```bash
git add skills/competitor-research/skill.md agents/post-analyzer.md commands/competitor-research.yaml
git commit -m "feat: add Claude Code skill, sub-agent, and slash command for pipeline orchestration"
```

---

### Task 8: End-to-End Test with Fixtures

**Files:**
- Create: `tests/test_end_to_end.py`
- Modify: `tests/fixtures/sample_raw_posts.json` (already exists from Task 2)

**Interfaces:**
- Consumes: All scripts from Tasks 1-6
- Produces: Validates the full pipeline works end-to-end with fixture data (no Apify call)

- [ ] **Step 1: Write the end-to-end test**

`tests/test_end_to_end.py`:
```python
import json
import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

from scripts.rank_and_select import rank_and_select
from scripts.generate_report import generate_report


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestPipelineIntegration:
    """Tests Phase 2 -> Phase 4 with fixture data, skipping Apify/media/FFmpeg/Whisper."""

    def test_rank_to_report(self, tmp_path):
        with open(os.path.join(FIXTURES_DIR, "sample_raw_posts.json")) as f:
            raw_posts = json.load(f)

        selected = rank_and_select(raw_posts, top_per_handle=3)
        assert len(selected) == 7  # 4 from creator1 (only 4 exist) + 3 from creator2

        analyses = []
        for post in selected:
            analyses.append({
                "shortCode": post["id"],
                "handle": f"@{post['handle']}",
                "hook": f"Hook for {post['id']}",
                "visual_format": "Talking Head",
                "format_breakdown": "Standard format",
                "topic": "AI tools",
                "why_it_worked": "Strong hook",
                "replication_notes": "Replicate by...",
                "metrics": {
                    "likes": post["likes"],
                    "comments": post["comments"],
                    "views": post["views"],
                    "outlier_score": post["outlier_score"],
                },
                "transcript": f"Transcript for {post['id']}",
                "post_url": post["url"],
                "posted_date": "2026-06-20",
            })

        output_path = str(tmp_path / "report.html")
        result = generate_report(
            analyses=analyses,
            niche_summary="AI tools dominate with talking head formats.",
            frames_dir=str(tmp_path / "frames"),
            output_path=output_path,
        )

        assert os.path.exists(result)
        with open(result) as f:
            html = f.read()
        assert "Competitor Research Report" in html
        assert "@creator1" in html
        assert "@creator2" in html
        assert len(html) > 1000
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/test_end_to_end.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "test: add end-to-end integration test with fixture data"
```
