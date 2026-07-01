"""Phase B prelude — hashtag-volume research.

Uses apify/instagram-hashtag-analytics-scraper to pull real Instagram volume
for a seed hashtag and its related hashtags, so the user can confirm a
high-volume set before Phase B scrapes them. This replaces the static guesswork
of pure string-generated hashtags (Issue 6).

Note: this actor returns aggregate analytics per hashtag (postsCount + related
hashtags with volume), NOT posts or usernames — so it cannot replace Phase B
handle discovery. It only informs hashtag selection.
"""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.config_io import load_env

ACTOR_ID = "apify/instagram-hashtag-analytics-scraper"


def parse_volume(info) -> int:
    """Parse a humanized volume string from the analytics actor's `info` field.

    Examples: "7.62 m" -> 7620000, "598.34 k" -> 598340, "12345" -> 12345.
    """
    if not info:
        return 0
    s = str(info).strip().lower().replace(",", "")
    mult = 1
    if s and s[-1] in "mbk":
        suf = s[-1]
        mult = {"m": 1_000_000, "b": 1_000_000_000, "k": 1_000}[suf]
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def research_hashtags(seed_tag: str, token: str, top_n: int = 10) -> list[dict]:
    """Return hashtags (seed + related) ranked by real Instagram volume.

    Each item: {hashtag, volume, source} where source is "seed" or "related".
    Returns [] if the actor returns nothing (caller falls back to the offline
    hashtags_for_niche() generator).
    """
    tag = seed_tag.lstrip("#")
    try:
        items = run_actor(token, ACTOR_ID, {"hashtags": [tag]})
    except Exception as e:
        print(f"WARN: hashtag research failed for #{tag}: {e}")
        return []
    if not items:
        return []
    rec = items[0]

    out: list[dict] = []
    posts_count = rec.get("postsCount") or 0
    if posts_count:
        out.append({"hashtag": f"#{tag}", "volume": int(posts_count), "source": "seed"})
    for r in rec.get("related") or []:
        h = r.get("hash") or ""
        if not h:
            continue
        if not h.startswith("#"):
            h = f"#{h}"
        out.append({"hashtag": h, "volume": parse_volume(r.get("info")), "source": "related"})

    out.sort(key=lambda d: d["volume"], reverse=True)
    return out[:top_n]


def main(seed_tag: str, output_path: str | None, top_n: int) -> None:
    project_dir = str(pathlib.Path(__file__).resolve().parents[1])
    if output_path:
        project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    ranked = research_hashtags(seed_tag, token, top_n=top_n)
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(ranked, f, indent=2)
        print(f"Wrote {len(ranked)} ranked hashtags -> {output_path}")
    else:
        for h in ranked:
            print(f"{h['hashtag']}\t{h['volume']:,}\t({h['source']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Research hashtag volumes (Phase B prelude)")
    parser.add_argument("--seed", required=True, help="seed hashtag (with or without #)")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", default=None, help="write JSON here; if omitted, print to stdout")
    args = parser.parse_args()
    main(args.seed, args.output, args.top_n)
