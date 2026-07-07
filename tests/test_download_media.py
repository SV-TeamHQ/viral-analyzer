import os
import json
import pytest
from unittest.mock import patch, MagicMock

from scripts.download_media import download_single, download_all_media, main


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


class TestMainUtf8:
    @patch("scripts.download_media.download_all_media")
    def test_main_round_trips_non_ascii_selected_posts(self, mock_download, tmp_path):
        # Bug 3 (download_media): main() reads selected_posts.json, then rewrites
        # it in place with local_media_path attached. Both opens must be UTF-8 so
        # emoji/non-ASCII captions don't UnicodeDecodeError on cp1252 Windows.
        # (Portability guard — passes on UTF-8-default locales, catches the
        # regression on cp1252 Windows where the crash was reported.)
        selected = tmp_path / "selected.json"
        payload = [{"id": "IMG1", "media_url": "https://cdn.example.com/i.jpg",
                    "media_type": "image", "handle": "alice",
                    "caption": "fire \U0001f525 emoji é"}]
        selected.write_text(json.dumps(payload), encoding="utf-8")

        def fake_download(posts, output_dir):
            return [{**p, "local_media_path": f"{output_dir}/{p['id']}.jpg"}
                    for p in posts]
        mock_download.side_effect = fake_download

        main(str(selected), str(tmp_path / "media"))

        rewritten = json.loads(selected.read_text(encoding="utf-8"))
        assert rewritten[0]["caption"] == "fire \U0001f525 emoji é"
        assert rewritten[0]["local_media_path"].endswith("IMG1.jpg")
