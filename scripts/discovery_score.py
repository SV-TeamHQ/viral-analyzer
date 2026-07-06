"""Phase C — creator scoring. Ranks candidate handles by engagement + niche authority."""
import argparse
import json
import os
import sys
import pathlib
from statistics import median
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.config_io import load_env
from viral_core.scoring import outlier_score

PROFILE_ACTOR = "apify/instagram-profile-scraper"

W_ENG = 0.4
W_CROSS = 0.4
W_OUTLIER = 0.2

# 4d — follower-tiered engagement caps (replaces the flat 0.10 normalization).
ENG_CAP_MICRO = 0.10   # < 10K followers
ENG_CAP_MID = 0.08     # 10K-100K
ENG_CAP_MACRO = 0.05   # 100K+

# 4c — effective weights when cross-hashtag is structurally impossible (max_tags < 2).
W_ENG_NOCROSS = 0.7
W_CROSS_NOCROSS = 0.0
W_OUTLIER_NOCROSS = 0.3


def qualifies(c: dict, min_tags: int, top20_eng_rate: float) -> bool:
    if len(c.get("hashtags", [])) >= min_tags:
        return True
    followers = c.get("followers") or 1
    eng = (c.get("avg_likes", 0) + c.get("avg_comments", 0)) / followers
    return eng >= top20_eng_rate


def _eng_cap(followers: int) -> float:
    """4d: engagement-rate cap by follower tier. Larger accounts saturate at a
    lower rate so a 100K/5% creator isn't equalized with a 1K/10% creator."""
    if followers >= 100_000:
        return ENG_CAP_MACRO
    if followers >= 10_000:
        return ENG_CAP_MID
    return ENG_CAP_MICRO


def compute_final_score(c: dict, max_tags: int, median_engagement: float,
                        sample_top_engagement: float) -> tuple[float, dict]:
    followers = c.get("followers") or 1
    eng_rate = (c.get("avg_likes", 0) + c.get("avg_comments", 0)) / followers
    cross = len(c.get("hashtags", []))
    cross_norm = min(cross / max_tags, 1.0) if max_tags else 0.0
    outlier_pot = outlier_score(sample_top_engagement, median_engagement) if median_engagement else 0.0
    eng_norm = min(eng_rate / _eng_cap(followers), 1.0)        # 4d
    out_norm = min(outlier_pot / 5.0, 1.0)
    if max_tags < 2:                                            # 4c
        w_eng, w_cross, w_out = W_ENG_NOCROSS, W_CROSS_NOCROSS, W_OUTLIER_NOCROSS
    else:
        w_eng, w_cross, w_out = W_ENG, W_CROSS, W_OUTLIER
    final = round(w_eng * eng_norm + w_cross * cross_norm + w_out * out_norm, 3)
    return final, {
        "engagement_rate": round(eng_rate, 4),
        "cross_hashtag_count": cross,
        "outlier_potential": round(outlier_pot, 2),
        "followers": followers,
    }


def _eng_rate(c: dict) -> float:
    """Engagement RATE for a candidate (avg interactions per follower)."""
    followers = c.get("followers") or 1
    return (c.get("avg_likes", 0) + c.get("avg_comments", 0)) / followers


def _eng_abs(c: dict) -> int | float:
    """Absolute engagement count (avg likes + comments) for a candidate."""
    return c.get("avg_likes", 0) + c.get("avg_comments", 0)


def _avg_engagement(prof: dict) -> tuple[float, float]:
    """Issue 7: apify/instagram-profile-scraper has no top-level avg fields.
    Compute avg likes/comments from its `latestPosts` array."""
    latest = prof.get("latestPosts") or []
    if not latest:
        return 0.0, 0.0
    n = len(latest)
    avg_likes = sum(p.get("likesCount", 0) for p in latest) / n
    avg_comments = sum(p.get("commentsCount", 0) for p in latest) / n
    return avg_likes, avg_comments


def caption_language(prof: dict, max_captions: int = 5) -> str:
    """Fix 5: modal ISO language code across recent captions; 'unknown' if none
    are present, langdetect isn't installed, or every detection raises.
    langdetect is imported lazily so this module loads without it."""
    captions = [p.get("caption", "") for p in (prof.get("latestPosts") or [])
                if p.get("caption")]
    if not captions:
        return "unknown"
    try:
        from langdetect import detect
    except ImportError:
        return "unknown"
    from collections import Counter
    langs = []
    for cap in captions[:max_captions]:
        try:
            langs.append(detect(cap))
        except Exception:
            pass
    return Counter(langs).most_common(1)[0][0] if langs else "unknown"


def score_handles(candidates: list[dict], token: str, top_n: int = 10,
                  min_followers: int = 1000) -> list[dict]:
    max_tags = max((len(c.get("hashtags", [])) for c in candidates), default=1) or 1

    # ----- Pass 1: enrich every candidate via profile scrape -----
    # Real Phase B candidates have NO followers/engagement yet, so cohort
    # statistics MUST be computed from scraped data, not pre-scrape zeros.
    # `handle` arrives as an Instagram owner.id; the profile scraper resolves
    # it to a username, which we emit so competitors.json stays username-based.
    enriched: list[dict] = []
    for c in candidates:
        run_input = {"usernames": [c["handle"]]}
        try:
            items = run_actor(token, PROFILE_ACTOR, run_input)
        except Exception as e:
            print(f"WARN: profile scrape failed for {c['handle']}: {e}")
            continue
        if not items:
            continue
        prof = items[0]
        c["followers"] = prof.get("followersCount", 0) or 0
        c["avg_likes"], c["avg_comments"] = _avg_engagement(prof)
        # Issue 9: drop tiny accounts before they pollute cohort stats / scoring.
        if c["followers"] < min_followers:
            continue
        username = prof.get("username")
        if username:
            c["handle"] = username  # resolve owner.id -> username
        enriched.append(c)

    if not enriched:
        return []

    # ----- Cohort statistics from REAL scraped data -----
    # median_abs: median absolute engagement count across the cohort.
    median_abs = median(_eng_abs(c) for c in enriched)
    # top20_rate: engagement RATE at the 80th percentile (upper quintile) —
    # the gate above which a creator qualifies on engagement alone.
    rates_sorted = sorted(_eng_rate(c) for c in enriched)
    top20_idx = max(1, len(rates_sorted) - max(1, len(rates_sorted) // 5))
    top20_rate = rates_sorted[top20_idx - 1] if rates_sorted else 1.0

    # ----- Pass 2: qualify + score against the real cohort baseline -----
    scored = []
    for c in enriched:
        if not qualifies(c, min_tags=2, top20_eng_rate=top20_rate):
            continue
        sample_top = _eng_abs(c)
        final, parts = compute_final_score(c, max_tags, median_abs,
                                           sample_top_engagement=sample_top)
        scored.append({"handle": c["handle"], "niche": c.get("niche", ""),
                       "final_score": final, **parts})
    scored.sort(key=lambda d: d["final_score"], reverse=True)
    return scored[:top_n]


def main(input_path: str, output_path: str, top_n: int, min_followers: int = 1000) -> None:
    # Issue 8: load .env from the project root (output is <root>/temp/X.json).
    project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    with open(input_path) as f:
        candidates = json.load(f)
    scored = score_handles(candidates, token, top_n, min_followers=min_followers)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2)
    print(f"Wrote {len(scored)} scored handles -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score candidate handles (Phase C)")
    parser.add_argument("--input", default="temp/candidate_handles.json")
    parser.add_argument("--output", default="temp/scored_handles.json")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-followers", type=int, default=1000,
                        help="drop candidates below this follower count (Issue 9)")
    args = parser.parse_args()
    main(args.input, args.output, args.top_n, min_followers=args.min_followers)
