import json
import os
import pytest
from unittest.mock import patch

from scripts.extract_frames import (
    get_duration,
    extract_frames,
    extract_audio,
    process_post,
    extract_all,
)


class TestGetDuration:
    @patch("scripts.extract_frames.subprocess.run")
    def test_parses_ffprobe_json(self, mock_run, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x")
        mock_run.return_value.stdout = json.dumps(
            {"streams": [{"duration": "12.5"}], "format": {"duration": "12.5"}}
        )
        assert get_duration(str(video)) == pytest.approx(12.5)

    @patch("scripts.extract_frames.subprocess.run")
    def test_returns_zero_on_ffprobe_failure(self, mock_run, tmp_path):
        import subprocess as sp
        mock_run.side_effect = sp.CalledProcessError(1, "ffprobe")
        assert get_duration(str(tmp_path / "v.mp4")) == 0.0


class TestExtractFrames:
    @patch("scripts.extract_frames.get_duration")
    @patch("scripts.extract_frames.subprocess.run")
    def test_extracts_n_evenly_spaced_frames(self, mock_run, mock_dur, tmp_path):
        mock_dur.return_value = 8.0
        # Simulate ffmpeg writing each requested frame file.
        def fake_run(cmd, **kwargs):
            out = cmd[cmd.index("-frames:v") + 2] if "-frames:v" in cmd else cmd[-1]
            with open(out, "wb") as f:
                f.write(b"jpg")
        mock_run.side_effect = fake_run

        paths = extract_frames(str(tmp_path / "v.mp4"), str(tmp_path / "out"), num_frames=4)
        assert len(paths) == 4
        assert all(p.endswith(".jpg") for p in paths)
        assert all(os.path.exists(p) for p in paths)

    @patch("scripts.extract_frames.get_duration")
    @patch("scripts.extract_frames.subprocess.run")
    def test_returns_empty_on_ffmpeg_failure(self, mock_run, mock_dur, tmp_path):
        mock_dur.return_value = 8.0
        mock_run.return_value = None  # no files written
        paths = extract_frames(str(tmp_path / "v.mp4"), str(tmp_path / "out"), num_frames=4)
        assert paths == []


class TestExtractAudio:
    @patch("scripts.extract_frames.subprocess.run")
    def test_returns_wav_path_on_success(self, mock_run, tmp_path):
        out = tmp_path / "a.wav"

        def fake_run(cmd, **kwargs):
            with open(cmd[-1], "wb") as f:
                f.write(b"wav")
        mock_run.side_effect = fake_run
        result = extract_audio(str(tmp_path / "v.mp4"), str(out))
        assert result == str(out)
        assert os.path.exists(result)

    @patch("scripts.extract_frames.subprocess.run")
    def test_returns_none_on_failure(self, mock_run, tmp_path):
        mock_run.return_value = None
        assert extract_audio(str(tmp_path / "v.mp4"), str(tmp_path / "a.wav")) is None


class TestProcessPost:
    def test_video_post_gets_frames_and_audio(self, tmp_path):
        post = {"id": "V1", "media_type": "video", "local_media_path": str(tmp_path / "v.mp4")}
        with patch("scripts.extract_frames.extract_frames", return_value=["f1", "f2"]) as mf, \
             patch("scripts.extract_frames.extract_audio", return_value="a.wav") as ma:
            result = process_post(post, str(tmp_path / "fr"), str(tmp_path / "au"), num_frames=2)
        assert result["frames"] == ["f1", "f2"]
        assert result["audio_path"] == "a.wav"

    def test_image_post_reuses_local_media_as_frame(self, tmp_path):
        img = str(tmp_path / "i.jpg")
        post = {"id": "I1", "media_type": "image", "local_media_path": img}
        result = process_post(post, str(tmp_path / "fr"), str(tmp_path / "au"))
        assert result["frames"] == [img]
        assert result["audio_path"] is None

    def test_skips_post_with_no_local_media(self, tmp_path):
        post = {"id": "X1", "media_type": "video", "local_media_path": None}
        result = process_post(post, str(tmp_path / "fr"), str(tmp_path / "au"))
        assert result["frames"] == []
        assert result["audio_path"] is None


class TestExtractAll:
    def test_adds_frames_and_audio_fields(self, tmp_path):
        posts = [
            {"id": "V1", "media_type": "video", "local_media_path": str(tmp_path / "v.mp4")},
            {"id": "I1", "media_type": "image", "local_media_path": str(tmp_path / "i.jpg")},
        ]
        with patch("scripts.extract_frames.process_post") as mp:
            mp.side_effect = lambda p, *a, **k: {**p, "frames": ["f"], "audio_path": None}
            result = extract_all(posts, str(tmp_path / "fr"), str(tmp_path / "au"))
        assert len(result) == 2
        for p in result:
            assert "frames" in p and "audio_path" in p
