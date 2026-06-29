import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from apify_client import ApifyClient
except ImportError:
    ApifyClient = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# The actor used for scraping. NOTE: `apify/instagram-scraper` (web GraphQL) is
# aggressively blocked by Instagram on post-detail requests and returns error stubs.
# `api-ninja/instagram-scraper` uses Instagram's private API and works reliably.
ACTOR_ID = "api-ninja/instagram-scraper"

# api-ninja returns Instagram private-API media_type codes.
MEDIA_TYPE_MAP = {
    1: "image",
    2: "video",
    8: "carousel",
}


def _epoch_to_iso(epoch):
    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def normalize_post(raw: dict) -> dict:
    media_type = MEDIA_TYPE_MAP.get(raw.get("media_type"), "image")

    if media_type == "video":
        video_versions = raw.get("video_versions") or []
        media_url = video_versions[0]["url"] if video_versions else ""
    else:
        # image or carousel: use the cover image candidates
        candidates = (raw.get("image_versions2") or {}).get("candidates") or []
        media_url = candidates[0]["url"] if candidates else ""

    caption = raw.get("caption")
    if isinstance(caption, dict):
        caption_text = caption.get("text", "")
    else:
        caption_text = caption or ""

    code = raw.get("code", "")
    return {
        "id": code,
        "platform": "instagram",
        "handle": (raw.get("user") or {}).get("username", ""),
        "url": f"https://www.instagram.com/p/{code}/" if code else "",
        "media_url": media_url,
        "media_type": media_type,
        "likes": raw.get("like_count", 0),
        "comments": raw.get("comment_count", 0),
        "views": raw.get("play_count"),
        "caption": caption_text,
        "timestamp": _epoch_to_iso(raw.get("taken_at")),
    }


def filter_recent_posts(posts: list[dict], lookback_days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    recent = []
    for post in posts:
        post_time = datetime.fromisoformat(post["timestamp"])
        if post_time.tzinfo is None:
            post_time = post_time.replace(tzinfo=timezone.utc)
        if post_time >= cutoff:
            recent.append(post)
    return recent


def scrape(handles: list[dict], posts_per_handle: int, lookback_days: int) -> list[dict]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise ValueError("APIFY_TOKEN environment variable is not set")

    client = ApifyClient(token)

    urls = [f"https://www.instagram.com/{h['handle']}/" for h in handles]
    run_input = {
        "urls": urls,
        # Over-fetch: the actor often returns collab/related posts from other
        # handles, which we filter out below. Headroom keeps the requested
        # handle's count from being starved.
        "resultsLimit": posts_per_handle * 2,
    }

    run = client.actor(ACTOR_ID).call(run_input=run_input)
    dataset_id = run.default_dataset_id
    items = list(client.dataset(dataset_id).iterate_items())

    posts = [normalize_post(item) for item in items]

    # The actor can return posts from other users (collabs, related, reposts).
    # Keep only posts from the handles we actually requested.
    requested = {h["handle"].strip().lower() for h in handles}
    posts = [p for p in posts if p["handle"].lower() in requested]

    return filter_recent_posts(posts, lookback_days)


def _env_path_for(config_path: str) -> Path:
    """Derive the project-root .env from the config path.

    The standard layout is <project>/config/competitors.json, so the project root is
    the config file's grandparent. This lets the script find .env regardless of CWD
    when run as a plugin.
    """
    return Path(config_path).resolve().parent.parent / ".env"


def main(config_path: str, output_path: str) -> None:
    # Load .env from the project root (derived from --config), then fall back to CWD.
    if load_dotenv is not None:
        load_dotenv(_env_path_for(config_path))
        load_dotenv()

    with open(config_path) as f:
        config = json.load(f)

    posts = scrape(
        handles=config["competitors"],
        posts_per_handle=config.get("posts_per_handle", 10),
        lookback_days=config.get("lookback_days", 365),
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(posts, f, indent=2)

    print(f"Scraped {len(posts)} posts -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Instagram competitor posts via Apify")
    parser.add_argument("--config", default="config/competitors.json")
    parser.add_argument("--output", default="temp/raw_posts.json")
    args = parser.parse_args()
    main(args.config, args.output)
