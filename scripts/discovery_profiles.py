"""Phase B (profile-first) — seed creator -> relatedProfiles -> candidate pool.

A second Phase B path alongside discovery_handles.py. The user supplies a
seed creator handle; this scrapes it via apify/instagram-profile-scraper,
reads its relatedProfiles (Instagram's "similar accounts" graph), and emits
the same temp/candidate_handles.json contract Phase C already consumes.
Routed in by the niche-discovery skill when the user gives a seed handle.
"""
import argparse
import json
import os
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.config_io import load_env

PROFILE_ACTOR = "apify/instagram-profile-scraper"
THIN_THRESHOLD = 8
LAST_ACTOR_ERROR = None


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
    except Exception as e:
        global LAST_ACTOR_ERROR
        LAST_ACTOR_ERROR = str(e)
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


_CAUSE_MESSAGES = {
    "thin":      "THIN CLUSTER: {n} profiles from seed @{seed}",
    "not_found": "SEED NOT FOUND: @{seed}",
    "private":   "SEED PRIVATE: @{seed} has no related profiles",
    "actor_error": "SEED FAILED: @{seed} — {error}",
}


def main(seed: str, niche: str, output_path: str) -> None:
    project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    candidates, reason = discover_from_seed(seed, niche, token)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2)
    if reason == "ok":
        print(f"Wrote {len(candidates)} candidate handles -> {output_path}")
        return
    n = len(candidates)
    print(_CAUSE_MESSAGES[reason].format(n=n, seed=seed, error=LAST_ACTOR_ERROR or "actor raised"))
    sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Profile-first Phase B (seed -> relatedProfiles)")
    parser.add_argument("--seed", required=True, help="seed creator handle (username)")
    parser.add_argument("--niche", required=True, help="niche label tagging the run")
    parser.add_argument("--output", default="temp/candidate_handles.json")
    args = parser.parse_args()
    main(args.seed, args.niche, args.output)
