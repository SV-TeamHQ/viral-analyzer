import argparse
import json
import os
import time

import requests


EXTENSION_MAP = {
    "video": ".mp4",
    "image": ".jpg",
    "carousel": ".jpg",
}


def download_single(post: dict, output_dir: str) -> str | None:
    ext = EXTENSION_MAP.get(post["media_type"], ".jpg")
    output_path = os.path.join(output_dir, f"{post['id']}{ext}")

    try:
        response = requests.get(
            post["media_url"],
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
            timeout=30,
        )
        response.raise_for_status()
    except Exception:
        print(f"  Failed to download {post['id']}: media unavailable")
        return None

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return output_path


def download_all_media(posts: list[dict], output_dir: str) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for i, post in enumerate(posts):
        print(f"  Downloading {post['id']} ({post['media_type']})...")
        post = post.copy()
        post["local_media_path"] = download_single(post, output_dir)
        results.append(post)

        if i < len(posts) - 1:
            time.sleep(1)

    return results


def main(input_path: str, output_dir: str) -> None:
    with open(input_path, encoding="utf-8") as f:
        posts = json.load(f)

    results = download_all_media(posts, output_dir)

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    downloaded = sum(1 for p in results if p["local_media_path"])
    print(f"Downloaded {downloaded}/{len(results)} media files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download media for selected posts")
    parser.add_argument("--input", default="temp/selected_posts.json")
    parser.add_argument("--output-dir", default="temp/media")
    args = parser.parse_args()
    main(args.input, args.output_dir)
