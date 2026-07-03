"""Phase A — IG-native niche discovery.

Surfaces niche candidates from INSIDE Instagram by reading the analytics
actor's related hashtags (with real IG volume) for a seed hashtag. Replaces
the old pytrends/Reddit external trend sources. The niche the user picks IS
an IG hashtag, so there is no topic->hashtag translation step.

Two entry modes, both resolving to a seed hashtag:
  - seeded:   --seed <niche/keyword/hashtag>  (mapped via hashtags_for_niche)
  - unseeded: --category <name>               (mapped via the CATEGORIES list)

Output (temp/niches.json) matches the existing {niche, trend_score, sources}
contract so Phase B (discovery_handles.py) is unchanged.
"""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from scripts.discovery_hashtag_research import research_hashtags
except ModuleNotFoundError:
    from discovery_hashtag_research import research_hashtags
from viral_core.config_io import load_env

# 17 broad category -> mega-hashtag seeds for unseeded discovery.
CATEGORIES = {
    "fitness": "#fitness", "tech": "#tech", "food": "#food",
    "finance": "#personalfinance", "beauty": "#beauty", "gaming": "#gaming",
    "travel": "#travel", "business": "#entrepreneur",
    "ai": "#ai", "fashion": "#fashion", "health & wellness": "#wellness",
    "photography": "#photography", "real estate": "#realestate",
    "pets": "#pets", "music": "#music", "cars": "#cars", "apps": "#apps",
}


def _resolve_seed(seed: str | None, category: str | None) -> str | None:
    """Resolve a seed hashtag from --seed (keyword/hashtag) or --category."""
    if seed:
        return seed if seed.startswith("#") else f"#{seed}"
    if category:
        key = category.strip().lower()
        if key not in CATEGORIES:
            raise ValueError(
                f"unknown category {category!r}; choose from: "
                f"{', '.join(sorted(CATEGORIES))}"
            )
        return CATEGORIES[key]
    return None


def explore_niches(seed_hashtag: str, token: str, top_n: int = 10) -> list[dict]:
    """IG-native Phase A. Calls the analytics actor (via research_hashtags) on
    a seed hashtag and returns its related hashtags as niche candidates.

    `niche` is the related hashtag token, #-stripped (e.g. 'homegym'). Real IG
    related hashtags are concatenated tokens with no separators, so no
    word-splitting is attempted; the token is re-prefixed with '#' at Phase B
    handoff (lossless round-trip).
    """
    ranked = research_hashtags(seed_hashtag, token, top_n=top_n)
    return [
        {
            "niche": h["hashtag"].lstrip("#"),
            "trend_score": h["volume"],
            "sources": ["instagram"],
        }
        for h in ranked[:top_n]
    ]


def main(seed: str | None = None, category: str | None = None,
         output_path: str = "temp/niches.json", top_n: int = 10) -> None:
    project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")

    seed_hashtag = _resolve_seed(seed, category)
    if not seed_hashtag:
        print("ERR: provide --seed <hashtag or niche> or --category <name>.")
        return

    niches = explore_niches(seed_hashtag, token, top_n=top_n)
    if not niches:
        print(f"IG niche discovery unavailable for {seed_hashtag}. "
              f"Try a different seed/category or check APIFY_TOKEN.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(niches, f, indent=2)
    print(f"Wrote {len(niches)} niches -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IG-native niche discovery (Phase A)")
    parser.add_argument("--seed", default=None,
                        help="seed hashtag, niche, or keyword (seeded mode)")
    parser.add_argument("--category", default=None,
                        help="broad category name for unseeded mode "
                             "(e.g. fitness, ai, apps)")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", default="temp/niches.json")
    args = parser.parse_args()
    main(seed=args.seed, category=args.category,
         output_path=args.output, top_n=args.top_n)
