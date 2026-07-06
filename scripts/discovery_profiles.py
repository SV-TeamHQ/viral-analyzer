"""Phase B (profile-first) — seed creator -> relatedProfiles -> candidate pool.

A second Phase B path alongside discovery_handles.py. The user supplies a
seed creator handle; this scrapes it via apify/instagram-profile-scraper,
reads its relatedProfiles (Instagram's "similar accounts" graph), and emits
the same temp/candidate_handles.json contract Phase C already consumes.
Routed in by the niche-discovery skill when the user gives a seed handle.
"""
import argparse
import os
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.config_io import load_env

PROFILE_ACTOR = "apify/instagram-profile-scraper"
THIN_THRESHOLD = 8


def discover_from_seed(seed: str, niche: str, token: str) -> tuple[list[dict], str]:
    """Scrape seed, read relatedProfiles, return (candidates, reason).

    Candidate shape matches discovery_handles output:
        {"handle": <username>, "hashtags": [], "niche": <niche>, "post_count": 0}
    The seed is included as a candidate; private related profiles are skipped.
    reason ∈ {"ok","thin","not_found","private","actor_error"}.
    """
    try:
        items = run_actor(token, PROFILE_ACTOR,
                          {"usernames": [seed], "resultsLimit": 1})
    except Exception:
        return [], "actor_error"
    if not items:
        return [], "not_found"
    prof = items[0]
    related = prof.get("relatedProfiles") or []
    candidates = []
    # Seed first (it is a creator in the niche too).
    seed_handle = prof.get("username") or seed
    candidates.append({"handle": seed_handle, "hashtags": [], "niche": niche, "post_count": 0})
    for r in related:
        username = r.get("username")
        if not username:
            continue
        if r.get("is_private"):
            continue
        candidates.append({"handle": username, "hashtags": [], "niche": niche, "post_count": 0})
    is_private_seed = bool(prof.get("private")) and not related
    if is_private_seed:
        return candidates, "private"
    if len(related) < THIN_THRESHOLD:
        return candidates, "thin"
    return candidates, "ok"
