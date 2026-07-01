import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest

from scripts.scrape_instagram import scrape, normalize_post, filter_recent_posts


# Fixtures use the api-ninja/instagram-scraper schema (Instagram private API).

SAMPLE_VIDEO_POST = {
    "code": "ABC123",
    "user": {"username": "competitor1"},
    "media_type": 2,
    "video_versions": [{"url": "https://cdn.instagram.com/video.mp4"}],
    "image_versions2": {"candidates": [{"url": "https://cdn.instagram.com/cover.jpg"}]},
    "like_count": 5432,
    "comment_count": 231,
    "play_count": 89000,
    "caption": {"text": "Check out this AI tool"},
    "taken_at": int(datetime.now(timezone.utc).timestamp()),
}

SAMPLE_IMAGE_POST = {
    "code": "DEF456",
    "user": {"username": "competitor2"},
    "media_type": 1,
    "image_versions2": {"candidates": [{"url": "https://cdn.instagram.com/image2.jpg"}]},
    "like_count": 1200,
    "comment_count": 45,
    "play_count": None,
    "caption": {"text": "New feature drop"},
    "taken_at": int(datetime.now(timezone.utc).timestamp()),
}

SAMPLE_CAROUSEL_POST = {
    **SAMPLE_VIDEO_POST,
    "code": "CAR789",
    "media_type": 8,
}

OLD_POST = {
    **SAMPLE_VIDEO_POST,
    "code": "OLD999",
    "taken_at": int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp()),
}


class TestNormalizePost:
    def test_normalizes_video_post(self):
        result = normalize_post(SAMPLE_VIDEO_POST)
        assert result["id"] == "ABC123"
        assert result["platform"] == "instagram"
        assert result["handle"] == "competitor1"
        assert result["url"] == "https://www.instagram.com/p/ABC123/"
        assert result["media_url"] == "https://cdn.instagram.com/video.mp4"
        assert result["media_type"] == "video"
        assert result["likes"] == 5432
        assert result["comments"] == 231
        assert result["views"] == 89000
        assert result["caption"] == "Check out this AI tool"
        # timestamp normalized to an ISO string downstream code can parse
        assert isinstance(result["timestamp"], str)
        datetime.fromisoformat(result["timestamp"])

    def test_normalizes_image_post(self):
        result = normalize_post(SAMPLE_IMAGE_POST)
        assert result["media_url"] == "https://cdn.instagram.com/image2.jpg"
        assert result["media_type"] == "image"
        assert result["views"] is None

    def test_carousel_type(self):
        result = normalize_post(SAMPLE_CAROUSEL_POST)
        assert result["media_type"] == "carousel"
        # carousel uses the cover image as its media url
        assert result["media_url"] == "https://cdn.instagram.com/cover.jpg"

    def test_caption_none_becomes_empty_string(self):
        raw = {**SAMPLE_VIDEO_POST, "caption": None}
        assert normalize_post(raw)["caption"] == ""


class TestFilterRecentPosts:
    def test_filters_old_posts(self):
        posts = [normalize_post(SAMPLE_VIDEO_POST), normalize_post(OLD_POST)]
        recent = filter_recent_posts(posts, lookback_days=7)
        assert len(recent) == 1
        assert recent[0]["id"] == "ABC123"

    def test_keeps_all_recent(self):
        posts = [normalize_post(SAMPLE_VIDEO_POST), normalize_post(SAMPLE_IMAGE_POST)]
        recent = filter_recent_posts(posts, lookback_days=7)
        assert len(recent) == 2


class TestScrape:
    @patch("scripts.scrape_instagram.run_actor")
    def test_scrape_uses_api_ninja_actor_and_normalizes(self, mock_run_actor):
        mock_run_actor.return_value = [SAMPLE_VIDEO_POST, SAMPLE_IMAGE_POST]

        handles = [{"handle": "competitor1", "niche": "AI tools"},
                   {"handle": "competitor2", "niche": "AI tools"}]
        with patch.dict(os.environ, {"APIFY_TOKEN": "test_token"}):
            result = scrape(handles, posts_per_handle=10, lookback_days=7)

        assert len(result) == 2
        assert result[0]["platform"] == "instagram"
        assert result[0]["id"] == "ABC123"
        # run_actor is called with (token, actor_id, run_input) positionally
        args, _ = mock_run_actor.call_args
        assert args[1] == "api-ninja/instagram-scraper"
        # input format: urls + resultsLimit (no directUrls/resultsType/searchType)
        run_input = args[2]
        assert "urls" in run_input and "resultsLimit" in run_input
        assert "directUrls" not in run_input

    @patch("scripts.scrape_instagram.run_actor")
    def test_scrape_filters_old_posts(self, mock_run_actor):
        mock_run_actor.return_value = [SAMPLE_VIDEO_POST, OLD_POST]

        handles = [{"handle": "competitor1", "niche": "AI tools"}]
        with patch.dict(os.environ, {"APIFY_TOKEN": "test_token"}):
            result = scrape(handles, posts_per_handle=10, lookback_days=7)

        assert len(result) == 1
        assert result[0]["id"] == "ABC123"

    def test_scrape_requires_apify_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                scrape([{"handle": "x"}], posts_per_handle=10, lookback_days=7)

    @patch("scripts.scrape_instagram.run_actor")
    def test_scrape_drops_posts_from_other_handles(self, mock_run_actor):
        # the actor returns a collab/related post from a different user
        leaked = {
            **SAMPLE_VIDEO_POST,
            "code": "LEAK1",
            "user": {"username": "atlasberry008"},
        }
        mock_run_actor.return_value = [SAMPLE_VIDEO_POST, leaked]

        handles = [{"handle": "competitor1"}]  # only competitor1 requested
        with patch.dict(os.environ, {"APIFY_TOKEN": "test_token"}):
            result = scrape(handles, posts_per_handle=10, lookback_days=365)

        result_handles = {p["handle"] for p in result}
        assert "atlasberry008" not in result_handles
        assert result_handles == {"competitor1"}

    @patch("scripts.scrape_instagram.run_actor")
    def test_scrape_handle_filter_is_case_insensitive(self, mock_run_actor):
        mock_run_actor.return_value = [SAMPLE_VIDEO_POST]  # user: competitor1

        with patch.dict(os.environ, {"APIFY_TOKEN": "test_token"}):
            result = scrape([{"handle": "Competitor1"}], posts_per_handle=10, lookback_days=365)
        assert len(result) == 1 and result[0]["handle"] == "competitor1"

    @patch("scripts.scrape_instagram.run_actor")
    def test_scrape_overfetches_results_limit(self, mock_run_actor):
        mock_run_actor.return_value = []

        with patch.dict(os.environ, {"APIFY_TOKEN": "test_token"}):
            scrape([{"handle": "competitor1"}], posts_per_handle=10, lookback_days=365)

        args, _ = mock_run_actor.call_args
        run_input = args[2]
        # over-fetch so handle filtering doesn't starve the count
        assert run_input["resultsLimit"] >= 20
