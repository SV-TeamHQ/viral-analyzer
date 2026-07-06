import sys, pathlib
from unittest.mock import patch
import json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_profiles import discover_from_seed, THIN_THRESHOLD


# Real shape captured by the 2026-07-06 capability probe (memory:
# apify-actor-capabilities-spec-b-probe). Each relatedProfiles entry is
# {username, id, full_name, is_verified, is_private, profile_pic_url}.
def _prof(related):
    return {
        "username": "cristiano",
        "id": "1",
        "followersCount": 671667959,
        "private": False,
        "relatedProfiles": related,
    }


def _rel(username, is_private=False):
    return {"username": username, "id": "x", "full_name": "N",
            "is_verified": False, "is_private": is_private,
            "profile_pic_url": "http://example/p.jpg"}


def test_happy_path_builds_candidates_and_seed(monkeypatch):
    related = [_rel(f"u{i}") for i in range(10)]            # 10 public -> ok
    related.append(_rel("private_one", is_private=True))    # skipped
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "ok"
    handles = [c["handle"] for c in candidates]
    assert "cristiano" in handles          # seed included
    for i in range(10):
        assert f"u{i}" in handles          # public related kept
    assert "private_one" not in handles    # private skipped
    # shared Phase B contract
    assert all(c["hashtags"] == [] for c in candidates)
    assert all(c["niche"] == "fitness" for c in candidates)
    assert all(c["post_count"] == 0 for c in candidates)


def test_thin_reason_when_few_related(monkeypatch):
    related = [_rel("u0"), _rel("u1"), _rel("u2")]   # 3 < THIN_THRESHOLD
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "thin"
    assert len(candidates) == 4   # 3 related + seed


def test_not_found_when_actor_returns_empty(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[]):
        candidates, reason = discover_from_seed("ghost", "fitness", "tok")
    assert reason == "not_found"
    assert candidates == []


def test_private_seed_reason(monkeypatch):
    # Seed item exists, is private, and has no relatedProfiles field.
    prof = {"username": "locked", "private": True, "relatedProfiles": []}
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[prof]):
        candidates, reason = discover_from_seed("locked", "fitness", "tok")
    assert reason == "private"


def test_actor_error_reason(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", side_effect=RuntimeError("boom")):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "actor_error"
    assert candidates == []
    from scripts.discovery_profiles import LAST_ACTOR_ERROR
    assert LAST_ACTOR_ERROR == "boom"


def test_related_entry_missing_username_is_skipped(monkeypatch):
    related = [_rel(f"u{i}") for i in range(10)]
    related.append({"id": "999", "full_name": "NoHandle", "is_private": False})  # no username
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "ok"
    assert all(c["handle"] != "999" and c["handle"] for c in candidates)


def test_main_writes_candidates_and_exits_zero_on_ok(tmp_path, monkeypatch):
    related = [_rel(f"u{i}") for i in range(10)]
    out = tmp_path / "candidate_handles.json"
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        from scripts.discovery_profiles import main
        main("cristiano", "fitness", str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert any(c["handle"] == "cristiano" for c in data)
    assert all(c["hashtags"] == [] and c["niche"] == "fitness" for c in data)


def test_main_writes_json_then_exits_nonzero_on_thin(tmp_path, monkeypatch):
    related = [_rel("u0"), _rel("u1")]   # thin
    out = tmp_path / "candidate_handles.json"
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        import pytest
        from scripts.discovery_profiles import main
        with pytest.raises(SystemExit) as exc:
            main("cristiano", "fitness", str(out))
        assert exc.value.code == 1
    # JSON still written so the skill can offer "proceed"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 3   # 2 related + seed
