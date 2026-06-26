import argparse
import json
import os
import subprocess


def get_duration(video_path: str) -> float:
    """Return video duration in seconds, or 0.0 if ffprobe fails (corrupt/
    unreadable file). A 0.0 duration makes extract_frames degrade to []."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=duration:format=duration",
                "-of", "json",
                video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0.0

    data = json.loads(result.stdout)
    for source in (data.get("streams", [{}])[0], data.get("format", {})):
        try:
            return float(source["duration"])
        except (KeyError, ValueError, TypeError):
            continue
    return 0.0


def extract_frames(video_path: str, output_dir: str, num_frames: int = 4) -> list[str] | None:
    os.makedirs(output_dir, exist_ok=True)
    duration = get_duration(video_path)
    if duration <= 0:
        return []

    paths = []
    for i in range(num_frames):
        timestamp = duration * (i / num_frames)
        out_path = os.path.join(output_dir, f"frame_{i + 1:02d}.jpg")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{timestamp:.3f}",
                    "-i", video_path,
                    "-frames:v", "1",
                    out_path,
                ],
                capture_output=True,
                check=True,
            )
        except Exception:
            print(f"  Failed to extract frame {i + 1} from {video_path}")
            continue
        if os.path.exists(out_path):
            paths.append(out_path)
    return paths


def extract_audio(video_path: str, output_path: str) -> str | None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-ac", "1", "-ar", "16000",
                output_path,
            ],
            capture_output=True,
            check=True,
        )
    except Exception:
        print(f"  Failed to extract audio from {video_path}")
        return None
    return output_path if os.path.exists(output_path) else None


def process_post(post: dict, frames_dir: str, audio_dir: str, num_frames: int = 4) -> dict:
    post = post.copy()
    local = post.get("local_media_path")
    if not local:
        post["frames"] = []
        post["audio_path"] = None
        return post

    if post.get("media_type") == "video":
        post_dir = os.path.join(frames_dir, post["id"])
        post["frames"] = extract_frames(local, post_dir, num_frames) or []
        post["audio_path"] = extract_audio(local, os.path.join(audio_dir, f"{post['id']}.wav"))
    else:
        # image / carousel: the downloaded media is the frame
        post["frames"] = [local]
        post["audio_path"] = None
    return post


def extract_all(posts: list[dict], frames_dir: str, audio_dir: str, num_frames: int = 4) -> list[dict]:
    results = []
    for post in posts:
        print(f"  Extracting frames/audio for {post['id']} ({post.get('media_type')})...")
        results.append(process_post(post, frames_dir, audio_dir, num_frames))
    return results


def main(input_path: str, frames_dir: str, audio_dir: str, num_frames: int) -> None:
    with open(input_path) as f:
        posts = json.load(f)

    results = extract_all(posts, frames_dir, audio_dir, num_frames)

    with open(input_path, "w") as f:
        json.dump(results, f, indent=2)

    framed = sum(1 for p in results if p["frames"])
    print(f"Extracted frames for {framed}/{len(results)} posts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract frames and audio from downloaded media")
    parser.add_argument("--input", default="temp/selected_posts.json")
    parser.add_argument("--frames-dir", default="temp/frames")
    parser.add_argument("--audio-dir", default="temp/audio")
    parser.add_argument("--num-frames", type=int, default=4)
    args = parser.parse_args()
    main(args.input, args.frames_dir, args.audio_dir, args.num_frames)
