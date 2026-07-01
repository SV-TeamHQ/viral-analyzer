"""Live integration smoke test for /niche-discovery against real Apify.

Skipped unless APIFY_TOKEN is set, so it stays out of normal CI but runs on
demand to catch Apify response-shape drift that the mocked unit tests cannot
(the bug class that let Issues 4/5/7 ship green in the first place):

    APIFY_TOKEN=... python -m pytest tests/test_discovery_integration.py -v
"""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from viral_core.apify_client import run_actor

TOKEN = os.environ.get("APIFY_TOKEN")
pytestmark = pytest.mark.skipif(not TOKEN, reason="needs APIFY_TOKEN (live Apify)")

HASHTAG_ACTOR = "api-ninja/instagram-scraper"
PROFILE_ACTOR = "apify/instagram-profile-scraper"
HASHTAG_URL = "https://www.instagram.com/explore/tags/aitools/"


def test_hashtag_scrape_returns_owner_id():
    items = run_actor(TOKEN, HASHTAG_ACTOR,
                      {"urls": [HASHTAG_URL], "resultsLimit": 3})
    assert items, "actor returned no items"
    owner_ids = [(it.get("owner") or {}).get("id") for it in items]
    assert any(owner_ids), f"no owner.id found — shape drift? sample item: {items[0]}"


def test_profile_scrape_returns_followers_latestposts_username():
    # Resolve a real owner.id from a hashtag, then scrape that profile.
    items = run_actor(TOKEN, HASHTAG_ACTOR,
                      {"urls": [HASHTAG_URL], "resultsLimit": 3})
    owner_id = next((it.get("owner") or {}).get("id") for it in items
                    if (it.get("owner") or {}).get("id"))
    assert owner_id, "no owner.id available to resolve"
    profs = run_actor(TOKEN, PROFILE_ACTOR, {"usernames": [str(owner_id)]})
    assert profs, "profile actor returned no items"
    p = profs[0]
    assert "followersCount" in p, f"no followersCount — shape drift? keys: {list(p.keys())}"
    assert "latestPosts" in p, f"no latestPosts — shape drift? keys: {list(p.keys())}"
    assert p.get("username"), "profile did not resolve owner.id to a username"
