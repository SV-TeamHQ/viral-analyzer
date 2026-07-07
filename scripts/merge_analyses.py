import argparse
import json
import os

# Ground-truth metrics/metadata that always come from the scraped post, never
# from the sub-agent's analysis (so the report can't show a hallucinated number).
METADATA_KEYS = ("id", "handle", "url", "likes", "comments", "views",
                 "outlier_score", "caption", "frames")


def load_analysis(post_id: str, analyses_dir: str) -> dict | None:
    path = os.path.join(analyses_dir, f"{post_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_analyses(posts: list[dict], analyses_dir: str) -> list[dict]:
    merged = []
    analyzed_count = 0
    for post in posts:
        analysis = load_analysis(post["id"], analyses_dir)
        if analysis is None:
            record = {k: post.get(k) for k in METADATA_KEYS}
            record.update({"analyzed": False, "why_it_worked": "Analysis unavailable."})
        else:
            record = dict(analysis)
            # metadata wins over any stale/duplicate values the agent emitted
            record.update({k: post.get(k) for k in METADATA_KEYS})
            record["analyzed"] = True
            analyzed_count += 1
        merged.append(record)
    print(f"Merged {analyzed_count}/{len(posts)} analyzed posts")
    return merged


def main(selected_path: str, analyses_dir: str, output_path: str) -> None:
    with open(selected_path, encoding="utf-8") as f:
        posts = json.load(f)
    merged = merge_analyses(posts, analyses_dir)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    print(f"Wrote {len(merged)} analyses -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge per-post analyses into analyses.json")
    parser.add_argument("--input", default="temp/selected_posts.json")
    parser.add_argument("--analyses-dir", default="temp/analyses")
    parser.add_argument("--output", default="temp/analyses.json")
    args = parser.parse_args()
    main(args.input, args.analyses_dir, args.output)
