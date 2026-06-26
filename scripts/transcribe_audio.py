import argparse
import json
import os

try:
    import whisper
except ImportError:
    whisper = None


def load_model(model_name: str = "base"):
    if whisper is None:
        raise ImportError(
            "openai-whisper is not installed. Run: pip install -r requirements.txt"
        )
    return whisper.load_model(model_name)


def transcribe(audio_path: str, model) -> dict | None:
    try:
        result = model.transcribe(audio_path)
    except Exception as e:
        print(f"  Transcription failed for {audio_path}: {e}")
        return None
    text = (result.get("text") or "").strip()
    segments = result.get("segments") or []
    if segments:
        hook = segments[0]["text"].strip()
    else:
        hook = text
    return {"text": text, "hook": hook}


def transcribe_post(post: dict, model, transcripts_dir: str) -> dict:
    post = post.copy()
    audio = post.get("audio_path")
    if not audio or not os.path.exists(audio):
        post["transcript"] = ""
        post["hook"] = ""
        return post

    result = transcribe(audio, model)
    if result is None:
        post["transcript"] = ""
        post["hook"] = ""
        return post

    post["transcript"] = result["text"]
    post["hook"] = result["hook"]

    os.makedirs(transcripts_dir, exist_ok=True)
    transcript_file = os.path.join(transcripts_dir, f"{post['id']}.txt")
    with open(transcript_file, "w", encoding="utf-8") as f:
        f.write(result["text"])

    return post


def transcribe_all(posts: list[dict], transcripts_dir: str, model_name: str = "base") -> list[dict]:
    model = load_model(model_name)
    results = []
    for post in posts:
        print(f"  Transcribing {post['id']} ({post.get('media_type')})...")
        results.append(transcribe_post(post, model, transcripts_dir))
    return results


def main(input_path: str, transcripts_dir: str, model_name: str) -> None:
    with open(input_path) as f:
        posts = json.load(f)

    results = transcribe_all(posts, transcripts_dir, model_name)

    with open(input_path, "w") as f:
        json.dump(results, f, indent=2)

    transcribed = sum(1 for p in results if p["transcript"])
    print(f"Transcribed {transcribed}/{len(results)} posts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio via local Whisper")
    parser.add_argument("--input", default="temp/selected_posts.json")
    parser.add_argument("--transcripts-dir", default="temp/transcripts")
    parser.add_argument("--model", default="base")
    args = parser.parse_args()
    main(args.input, args.transcripts_dir, args.model)
