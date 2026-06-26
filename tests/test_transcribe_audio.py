import os
import pytest
from unittest.mock import patch, MagicMock

from scripts.transcribe_audio import (
    load_model,
    transcribe,
    transcribe_post,
    transcribe_all,
)


class TestLoadModel:
    def test_loads_whisper_model(self):
        with patch("scripts.transcribe_audio.whisper") as mock_whisper:
            mock_whisper.load_model.return_value = "MODEL"
            assert load_model("base") == "MODEL"
            mock_whisper.load_model.assert_called_once_with("base")

    def test_raises_if_whisper_not_installed(self):
        with patch("scripts.transcribe_audio.whisper", None):
            with pytest.raises(ImportError):
                load_model("base")


class TestTranscribe:
    def test_returns_text_and_hook(self, tmp_path):
        model = MagicMock()
        model.transcribe.return_value = {
            "text": "Hello world. Goodbye.",
            "segments": [{"text": " Hello world."}],
        }
        result = transcribe(str(tmp_path / "a.wav"), model)
        assert result["text"] == "Hello world. Goodbye."
        assert result["hook"] == "Hello world."

    def test_hook_falls_back_to_full_text_when_no_segments(self, tmp_path):
        model = MagicMock()
        model.transcribe.return_value = {"text": "Only text.", "segments": []}
        result = transcribe(str(tmp_path / "a.wav"), model)
        assert result["hook"] == "Only text."

    def test_returns_none_on_transcribe_failure(self, tmp_path):
        model = MagicMock()
        model.transcribe.side_effect = Exception("boom")
        assert transcribe(str(tmp_path / "a.wav"), model) is None


class TestTranscribePost:
    def test_video_post_gets_transcript_and_hook(self, tmp_path):
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"x")
        post = {"id": "V1", "media_type": "video", "audio_path": str(audio)}
        model = MagicMock()
        model.transcribe.return_value = {
            "text": "Full transcript.",
            "segments": [{"text": " Full transcript."}],
        }
        result = transcribe_post(post, model, str(tmp_path / "t"))
        assert result["transcript"] == "Full transcript."
        assert result["hook"] == "Full transcript."
        assert os.path.exists(os.path.join(str(tmp_path / "t"), "V1.txt"))

    def test_post_without_audio_gets_empty_strings(self, tmp_path):
        post = {"id": "I1", "media_type": "image", "audio_path": None}
        result = transcribe_post(post, MagicMock(), str(tmp_path / "t"))
        assert result["transcript"] == ""
        assert result["hook"] == ""

    def test_post_with_missing_audio_file_gets_empty_strings(self, tmp_path):
        post = {"id": "X1", "media_type": "video", "audio_path": str(tmp_path / "nope.wav")}
        result = transcribe_post(post, MagicMock(), str(tmp_path / "t"))
        assert result["transcript"] == ""
        assert result["hook"] == ""


class TestTranscribeAll:
    def test_loads_model_once_and_adds_fields(self, tmp_path):
        posts = [
            {"id": "V1", "media_type": "video", "audio_path": None},
            {"id": "I1", "media_type": "image", "audio_path": None},
        ]
        with patch("scripts.transcribe_audio.load_model") as ml:
            ml.return_value = MagicMock()
            result = transcribe_all(posts, str(tmp_path / "t"), model_name="base")
        ml.assert_called_once_with("base")
        assert all("transcript" in p and "hook" in p for p in result)
