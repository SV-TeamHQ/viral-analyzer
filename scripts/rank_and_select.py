import argparse
import json
import os
from statistics import median


def calculate_outlier_score(post_engagement: int, account_median: float) -> float:
    if account_median == 0:
        return 0.0
    return round(post_engagement / account_median, 2)


def rank_and_select(posts: list[dict], top_per_handle: int) -> list[dict]:
    by_handle: dict[str, list[dict]] = {}
    for post in posts:
        by_handle.setdefault(post["handle"], []).append(post)

    account_medians: dict[str, float] = {}
    for handle, handle_posts in by_handle.items():
        engagements = [p["likes"] + p["comments"] for p in handle_posts]
        account_medians[handle] = median(engagements) if engagements else 0.0

    selected = []
    for handle, handle_posts in by_handle.items():
        sorted_posts = sorted(
            handle_posts,
            key=lambda p: p["likes"] + p["comments"],
            reverse=True,
        )
        selected.extend(sorted_posts[:top_per_handle])

    for post in selected:
        engagement = post["likes"] + post["comments"]
        post["outlier_score"] = calculate_outlier_score(
            engagement, account_medians[post["handle"]]
        )

    selected.sort(key=lambda p: p["outlier_score"], reverse=True)
    return selected


def main(input_path: str, output_path: str, top_per_handle: int) -> None:
    with open(input_path) as f:
        posts = json.load(f)

    selected = rank_and_select(posts, top_per_handle)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(selected, f, indent=2)

    print(f"Selected {len(selected)} posts -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rank and select top posts")
    parser.add_argument("--input", default="temp/raw_posts.json")
    parser.add_argument("--output", default="temp/selected_posts.json")
    parser.add_argument("--top-per-handle", type=int, default=3)
    args = parser.parse_args()
    main(args.input, args.output, args.top_per_handle)
