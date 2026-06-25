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
