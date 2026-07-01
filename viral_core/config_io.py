"""Centralized competitors.json and .env handling."""
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def load_competitors(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_competitors(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_env(project_dir: str) -> None:
    """Load <project_dir>/.env if python-dotenv is available; no-op otherwise."""
    if load_dotenv is None:
        return
    env_path = Path(project_dir) / ".env"
    if env_path.exists():
        load_dotenv(env_path)
