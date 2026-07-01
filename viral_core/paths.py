"""Durable run-directory conventions: the backbone of stage-to-stage handoffs.

Each pipeline run gets one folder under <output_root>/runs/. Durable artifacts
(stage JSON, report files) live there; throwaway intermediates stay in temp/.
"""
from datetime import datetime
from pathlib import Path


def new_run_dir(output_root: str) -> Path:
    runs = Path(output_root) / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    run_dir = runs / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def latest_run(output_root: str) -> Path | None:
    runs = Path(output_root) / "runs"
    if not runs.exists():
        return None
    children = sorted(
        (d for d in runs.iterdir() if d.is_dir()),
        key=lambda d: d.name,
    )
    return children[-1] if children else None


def run_artifact(run_dir: str | Path, stage: str) -> Path:
    return Path(run_dir) / f"{stage}.json"
