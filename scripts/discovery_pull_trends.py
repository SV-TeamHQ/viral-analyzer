"""Phase A — trend signals. Surfaces rising niches via Google Trends (+Reddit)."""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

SUBREDDITS = ["entrepreneur", "SideProject", "ChatGPT", "artificial"]


def _pytrends_niches(seed: str) -> list[tuple[str, int]]:
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return []
    try:
        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload([seed or "technology"], timeframe="today 3-m")
        df = pytrends.related_queries()[seed or "technology"].get("rising", [])
        if df is None or len(df) == 0:
            return []
        # df has 'query' and 'value' (percent growth); take top 10
        rows = df.head(10).to_dict("records")
        return [(r["query"], int(r.get("value") or 0)) for r in rows]
    except Exception:
        return []


def _reddit_niches(seed: str) -> list[tuple[str, int]]:
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return []
    try:
        import praw
    except ImportError:
        return []
    try:
        reddit = praw.Reddit(client_id=cid, client_secret=secret, user_agent="viral-analyzer")
        counts: dict[str, int] = {}
        for sub in SUBREDDITS:
            for post in reddit.subreddit(sub).hot(limit=25):
                title = post.title.lower()
                for word in title.split():
                    w = word.strip(".,!?")
                    if len(w) > 4:
                        counts[w] = counts.get(w, 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    except Exception:
        return []


def merge_niches(trends: list[tuple[str, int]], reddit: list[tuple[str, int]]) -> list[dict]:
    max_score = max([s for _, s in trends] + [s for _, s in reddit] + [1])
    seen: dict[str, dict] = {}
    for niche, score in trends:
        seen.setdefault(niche, {"niche": niche, "raw": 0, "sources": []})
        seen[niche]["raw"] += score
        seen[niche]["sources"].append("google_trends")
    for niche, score in reddit:
        seen.setdefault(niche, {"niche": niche, "raw": 0, "sources": []})
        seen[niche]["raw"] += score
        seen[niche]["sources"].append("reddit")
    out = []
    for v in seen.values():
        v["trend_score"] = round(100 * v["raw"] / max_score)
        del v["raw"]
        out.append(v)
    out.sort(key=lambda d: (len(d["sources"]), d["trend_score"]), reverse=True)
    return out


def pull_trends(seed: str, use_reddit: bool = True) -> list[dict]:
    trends = _pytrends_niches(seed)
    reddit = _reddit_niches(seed) if use_reddit else []
    return merge_niches(trends, reddit)


def main(seed: str, output_path: str) -> None:
    niches = pull_trends(seed, use_reddit=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(niches, f, indent=2)
    print(f"Wrote {len(niches)} niches -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull trending niches (Phase A)")
    parser.add_argument("--seed", default="")
    parser.add_argument("--output", default="temp/niches.json")
    args = parser.parse_args()
    main(args.seed, args.output)
