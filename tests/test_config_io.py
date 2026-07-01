import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.config_io import load_competitors, save_competitors, load_env


def test_save_then_load_roundtrip(tmp_path):
    cfg = {"competitors": [{"handle": "alice"}], "posts_per_handle": 5}
    path = tmp_path / "nested" / "competitors.json"
    save_competitors(str(path), cfg)
    assert json.loads(path.read_text()) == cfg
    assert load_competitors(str(path)) == cfg

def test_load_env_noop_without_dotenv(monkeypatch, tmp_path):
    # Force dotenv to be absent to exercise the no-op path.
    import viral_core.config_io as cio
    monkeypatch.setattr(cio, "load_dotenv", None)
    load_env(str(tmp_path))  # must not raise
