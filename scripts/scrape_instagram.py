import argparse
import json
import os
from datetime import datetime, timezone, timedelta

try:
    from apify_client import ApifyClient
except ImportError:
    ApifyClient = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TYPE_MAP = {
    "Video": "video",
    "Image": "image",
    "Sidecar": "carousel",
}


def normalize_post(raw: dict) -> dict:
    media_type = TYPE_MAP.get(raw.get("type", ""), "image")
    if media_type == "video":
        media_url = raw.get("videoUrl") or raw.get("displayUrl", "")
    else:
        media_url = raw.get("displayUrl", "")

    return {
        "id": raw["shortCode"],
        "platform": "instagram",
        "handle": raw["ownerUsername"],
        "url": raw["url"],
        "media_url": media_url,
        "media_type": media_type,
        "likes": raw.get("likesCount", 0),
        "comments": raw.get("commentsCount", 0),
        "views": raw.get("videoViewCount"),
        "caption": raw.get("caption", ""),
        "timestamp": raw["timestamp"],
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

    direct_urls = [f"https://www.instagram.com/{h['handle']}/" for h in handles]
    run_input = {
        "directUrls": direct_urls,
        "resultsType": "posts",
        "resultsLimit": posts_per_handle,
        "searchType": "user",
        "maxRequestRetries": 3,
        "addParentData": True,
    }

    run = client.actor("apify/instagram-scraper").call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    posts = [normalize_post(item) for item in items]
    return filter_recent_posts(posts, lookback_days)


def main(config_path: str, output_path: str) -> None:
    with open(config_path) as f:
        config = json.load(f)

    posts = scrape(
        handles=config["competitors"],
        posts_per_handle=config.get("posts_per_handle", 10),
        lookback_days=config.get("lookback_days", 7),
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
