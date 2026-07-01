"""Phase B — hashtag -> handle discovery. Turns niches into candidate creators."""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.config_io import load_env

ACTOR_ID = "api-ninja/instagram-scraper"

# Curated, vetted hashtag map shipped with the plugin (Issue 6).
SEEDS_PATH = pathlib.Path(__file__).resolve().parents[1] / "config" / "hashtag_seeds.json"


def _load_seed_map() -> dict[str, list[str]]:
    try:
        with open(SEEDS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return {}


def hashtags_for_niche(niche: str) -> list[str]:
    # Issue 6: prefer curated, known-volume hashtags over string generation.
    key = niche.strip().lower()
    for cat, tags in _load_seed_map().items():
        if cat.lower() == key:
            return list(tags)
    # Fallback: string manipulation for niches not in the seed map.
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
        # api-ninja hashtag pages return owner.id only (no username field).
        # The id is resolved to a username later, in Phase C (profile scraper).
        handle = (p.get("owner") or {}).get("id")
        tag = p.get("__hashtag")
        if not handle:
            continue
        handle = str(handle)
        entry = freq.setdefault(handle, {"handle": handle, "hashtags": [], "post_count": 0})
        if tag and tag not in entry["hashtags"]:
            entry["hashtags"].append(tag)
        entry["post_count"] += 1
    return freq


def discover_handles(niches: list[str], token: str, posts_per_hashtag: int = 50) -> list[dict]:
    all_posts: list[dict] = []
    for niche in niches:
        for tag in hashtags_for_niche(niche):
            tag_name = tag.lstrip("#")
            # Issue 4: api-ninja/instagram-scraper takes `urls` (explore-tags),
            # not a `hashtags` key.
            run_input = {
                "urls": [f"https://www.instagram.com/explore/tags/{tag_name}/"],
                "resultsLimit": posts_per_hashtag,
            }
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
    # Issue 8: load .env from the project root (output is <root>/temp/X.json).
    project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
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
    parser.add_argument("--niche", default=None,
                        help="single niche string (for use with --preview-hashtags)")
    parser.add_argument("--preview-hashtags", action="store_true",
                        help="print the hashtags that would be scraped for --niche, then exit "
                             "(lets the skill confirm hashtags with the user before scraping)")
    args = parser.parse_args()
    if args.preview_hashtags:
        print("\n".join(hashtags_for_niche(args.niche or "")))
    else:
        main(args.niches, args.output)
