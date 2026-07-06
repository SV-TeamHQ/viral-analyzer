import sys, pathlib
from unittest.mock import patch
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
