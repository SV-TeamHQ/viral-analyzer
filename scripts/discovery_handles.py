"""Phase B — hashtag -> handle discovery. Turns niches into candidate creators."""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor

ACTOR_ID = "api-ninja/instagram-scraper"


def hashtags_for_niche(niche: str) -> list[str]:
    words = [w for w in niche.lower().replace("-", " ").split() if w]
    base = "".join(w for w in words[:2]) or "trending"
    candidates = [f"#{base}", f"#{base}tips", f"#{words[0] if words else 'trending'}"]
    for w in words[:3]:
        candidates.append(f"#{w}")
    # dedupe preserving order, keep 3-5
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:5]


def build_frequency(posts: list[dict]) -> dict:
    freq: dict[str, dict] = {}
    for p in posts:
        handle = (p.get("user") or {}).get("username")
        tag = p.get("__hashtag")
        if not handle:
            continue
        entry = freq.setdefault(handle, {"handle": handle, "hashtags": [], "post_count": 0})
        if tag and tag not in entry["hashtags"]:
            entry["hashtags"].append(tag)
        entry["post_count"] += 1
    return freq


def discover_handles(niches: list[str], token: str, posts_per_hashtag: int = 50) -> list[dict]:
    all_posts: list[dict] = []
    for niche in niches:
        for tag in hashtags_for_niche(niche):
            run_input = {"hashtags": [tag], "resultsLimit": posts_per_hashtag}
            try:
                items = run_actor(token, ACTOR_ID, run_input)
            except Exception as e:
                print(f"WARN: hashtag {tag} failed: {e}")
                continue
            for item in items:
                item["__hashtag"] = tag
                all_posts.append(item)
    freq = build_frequency(all_posts)
    out = list(freq.values())
    out.sort(key=lambda d: (len(d["hashtags"]), d["post_count"]), reverse=True)
    return out


def main(niches_path: str, output_path: str) -> None:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    with open(niches_path) as f:
        niches = [n["niche"] if isinstance(n, dict) else n for n in json.load(f)]
    handles = discover_handles(niches, token)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(handles, f, indent=2)
    print(f"Wrote {len(handles)} candidate handles -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover handles from niches (Phase B)")
    parser.add_argument("--niches", default="temp/niches.json")
    parser.add_argument("--output", default="temp/candidate_handles.json")
    args = parser.parse_args()
    main(args.niches, args.output)
