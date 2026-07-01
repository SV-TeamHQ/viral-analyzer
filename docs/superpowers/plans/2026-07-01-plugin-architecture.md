# Viral-Analyzer Plugin Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn viral-analyzer from a single pipeline into a chain of stage-skills over a shared `viral_core` package, integrate `/niche-discovery` as stage 0, and add an additive report redesign (cross-post Niche Patterns synthesis + per-post spoken-hook block).

**Architecture:** Chained stages share a `viral_core` package (apify_client, scoring, config_io, paths) imported via a 2-line `sys.path` bootstrap. Each stage writes durable artifacts to `output/runs/{date}_{HHMM}/`; throwaway intermediates stay in `temp/`. The report gains two additive sections; nothing existing is removed.

**Tech Stack:** Python 3.10+ (modern type hints: `list[dict]`, `X | None`), Jinja2, apify_client, openai-whisper, pytrends, praw, pytest. FFmpeg/ffprobe via subprocess. Claude Code plugin runtime (`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`).

## Global Constraints

- **Python 3.10+** with modern union type hints (`dict | None`, not `Optional[Dict]`).
- **Path substitution:** scripts run as a plugin. Never assume CWD. Use the bootstrap (below) to import `viral_core`; accept all paths via CLI flags; use `${CLAUDE_PLUGIN_ROOT}` for read-only plugin assets and `${CLAUDE_PROJECT_DIR}` for user data in skill files.
- **`viral_core` bootstrap** — every script that imports `viral_core` begins with:
  ```python
  import sys, pathlib
  sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
  ```
- **Ground-truth metrics** (`likes`, `comments`, `views`, `outlier_score`, `handle`, `url`, `caption`) always come from scraped data, never from agent output. `merge_analyses.py` enforces this.
- **Backward compatibility:** existing tests (`python -m pytest`) must keep passing. Public names that existing tests import (`calculate_outlier_score`) are preserved as aliases.
- **TDD:** every code task writes the failing test first, runs it red, implements, runs it green, then commits.
- **Line endings:** repo normalizes LF↔CRLF on Windows; commit warnings are expected and ignored.
- **Spec of record:** `docs/superpowers/specs/2026-07-01-plugin-architecture-design.md`. Niche-discovery behavior: `2026-06-30-niche-discovery-design.md` (repo root).

---

## File Structure

**Create:**
- `viral_core/__init__.py`, `viral_core/scoring.py`, `viral_core/config_io.py`, `viral_core/paths.py`, `viral_core/apify_client.py` — shared package.
- `scripts/discovery_pull_trends.py`, `scripts/discovery_handles.py`, `scripts/discovery_score.py` — stage 0.
- `skills/niche-discovery/SKILL.md`, `commands/niche-discovery.md` — stage 0 orchestration.
- `agents/pattern-synthesizer.md` — cross-post synthesis agent.
- `tests/test_scoring.py`, `tests/test_config_io.py`, `tests/test_paths.py`, `tests/test_apify_client.py` — `viral_core` tests.
- `tests/test_discovery_pull_trends.py`, `tests/test_discovery_handles.py`, `tests/test_discovery_score.py` — stage 0 tests.
- `tests/fixtures/sample_analyses.json`, `tests/fixtures/sample_niches.json`, `tests/fixtures/sample_candidate_handles.json`, `tests/fixtures/sample_patterns.json` — test data.

**Modify:**
- `scripts/rank_and_select.py` — extract scoring to `viral_core`, keep alias.
- `scripts/scrape_instagram.py` — use `viral_core.apify_client` + `viral_core.config_io`.
- `scripts/generate_report.py` — `--patterns`, `--run-dir`, emit `research.json`, fallback summary.
- `templates/report.html.j2` — additive: patterns section + spoken-hook block.
- `agents/post-analyzer.md` — add `spoken_hook` to output schema.
- `skills/competitor-research/SKILL.md` — Phase 3e, run-dir, `research.json` emission.
- `tests/test_scrape_instagram.py` — patch `viral_core.apify_client.run_actor` instead of `ApifyClient`.
- `tests/test_merge_analyses.py` — add spoken_hook regression test.
- `tests/test_generate_report.py` — patterns + run-dir assertions.
- `requirements.txt` — `pytrends>=4.9.0`, `praw>=7.7.0`.
- `.env.example` — `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`.

---

## Task 1: `viral_core.scoring` — extract outlier score

**Files:**
- Create: `viral_core/__init__.py`, `viral_core/scoring.py`
- Modify: `scripts/rank_and_select.py:1-10` (import + alias)
- Test: `tests/test_scoring.py`

**Interfaces:**
- Produces: `viral_core.scoring.outlier_score(post_engagement: int | float, account_median: float) -> float` (returns `0.0` when median is `0`, else `round(engagement / median, 2)`). Also re-exported as `viral_core.outlier_score`.
- Backward compat: `scripts.rank_and_select.calculate_outlier_score` remains importable (alias).

- [ ] **Step 1: Write the failing test**

`tests/test_scoring.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.scoring import outlier_score


def test_outlier_score_basic():
    assert outlier_score(500, 100) == 5.0

def test_outlier_score_rounds_to_two_decimals():
    assert outlier_score(100, 3) == 33.33

def test_outlier_score_zero_median_is_zero():
    assert outlier_score(500, 0) == 0.0

def test_outlier_score_reexported_from_package():
    from viral_core import outlier_score as top_level
    assert top_level(500, 100) == 5.0

def test_calculate_outlier_score_alias_still_importable():
    from scripts.rank_and_select import calculate_outlier_score
    assert calculate_outlier_score(500, 100) == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'viral_core'`.

- [ ] **Step 3: Write minimal implementation**

`viral_core/__init__.py`:
```python
from viral_core.scoring import outlier_score

__all__ = ["outlier_score"]
```

`viral_core/scoring.py`:
```python
"""Outlier-score formula shared across stages.

A post's outlier score is its engagement divided by the account's median
engagement — how many times more viral than the account's typical post.
"""


def outlier_score(post_engagement: int | float, account_median: float) -> float:
    if account_median == 0:
        return 0.0
    return round(post_engagement / account_median, 2)
```

- [ ] **Step 4: Refactor `rank_and_select.py` to use it (keep alias)**

Replace the top of `scripts/rank_and_select.py` (lines 1–10) so the local function is removed and the alias is added. New top of file:

```python
import argparse
import json
import os
from statistics import median

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.scoring import outlier_score

# Backward-compat alias: existing tests import `calculate_outlier_score`.
calculate_outlier_score = outlier_score


def rank_and_select(posts: list[dict], top_per_handle: int = 10) -> list[dict]:
```
Leave the body of `rank_and_select` unchanged (its calls to `calculate_outlier_score(...)` now resolve to the alias).

- [ ] **Step 5: Run all affected tests**

Run: `python -m pytest tests/test_scoring.py tests/test_rank_and_select.py -v`
Expected: PASS (both new and existing tests green).

- [ ] **Step 6: Commit**

```bash
git add viral_core/__init__.py viral_core/scoring.py scripts/rank_and_select.py tests/test_scoring.py
git commit -m "feat: extract outlier_score into viral_core.scoring"
```

---

## Task 2: `viral_core.config_io` — competitors + env loading

**Files:**
- Create: `viral_core/config_io.py`
- Test: `tests/test_config_io.py`

**Interfaces:**
- Produces:
  - `load_competitors(path: str) -> dict` — read `competitors.json`.
  - `save_competitors(path: str, data: dict) -> None` — write it (mkdir parents).
  - `load_env(project_dir: str) -> None` — load `<project_dir>/.env` if `python-dotenv` is installed; no-op otherwise.

- [ ] **Step 1: Write the failing test**

`tests/test_config_io.py`:
```python
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.config_io import load_competitors, save_competitors, load_env


def test_save_then_load_roundtrip(tmp_path):
    cfg = {"competitors": [{"handle": "alice"}], "posts_per_handle": 5}
    path = tmp_path / "nested" / "competitors.json"
    save_competitors(str(path), cfg)
    assert json.loads(path.read_text()) == cfg
    assert load_competitors(str(path)) == cfg

def test_load_env_noop_without_dotenv(monkeypatch, tmp_path):
    # Force dotenv to be absent to exercise the no-op path.
    import viral_core.config_io as cio
    monkeypatch.setattr(cio, "load_dotenv", None)
    load_env(str(tmp_path))  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_io.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'viral_core.config_io'`.

- [ ] **Step 3: Write minimal implementation**

`viral_core/config_io.py`:
```python
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
```

Add `config_io` to the package re-exports in `viral_core/__init__.py` (append):
```python
from viral_core.config_io import load_competitors, save_competitors, load_env
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_config_io.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viral_core/config_io.py viral_core/__init__.py tests/test_config_io.py
git commit -m "feat: add viral_core.config_io (competitors + env loading)"
```

---

## Task 3: `viral_core.paths` — durable run directories

**Files:**
- Create: `viral_core/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces:
  - `new_run_dir(output_root: str) -> Path` — create and return `<output_root>/runs/{YYYY-MM-DD}_{HHMM}` (local time). Raises if it already exists (collision → second-precision fallback handled by caller waiting is not needed; minute granularity is sufficient per existing report naming).
  - `latest_run(output_root: str) -> Path | None` — most recently created dir under `<output_root>/runs/`, or `None` if none exist.
  - `run_artifact(run_dir: str | Path, stage: str) -> Path` — `<run_dir>/<stage>.json`.

- [ ] **Step 1: Write the failing test**

`tests/test_paths.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.paths import new_run_dir, latest_run, run_artifact


def test_new_run_dir_created_under_runs(tmp_path):
    run = new_run_dir(str(tmp_path))
    assert run.parent == (tmp_path / "runs").resolve()
    assert run.exists() and run.is_dir()

def test_latest_run_returns_most_recent(tmp_path):
    first = new_run_dir(str(tmp_path))
    # minute-granularity stamp: force a distinct name by renaming the first
    first = first.rename(first.parent / (first.name + "_a"))
    second = new_run_dir(str(tmp_path))
    second = second.rename(second.parent / (second.name + "_b"))
    assert latest_run(str(tmp_path)).name.endswith("_b")

def test_latest_run_none_when_empty(tmp_path):
    assert latest_run(str(tmp_path)) is None

def test_run_artifact_path(tmp_path):
    run = new_run_dir(str(tmp_path))
    assert run_artifact(run, "research") == run / "research.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`viral_core/paths.py`:
```python
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
```

Append to `viral_core/__init__.py`:
```python
from viral_core.paths import new_run_dir, latest_run, run_artifact
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viral_core/paths.py viral_core/__init__.py tests/test_paths.py
git commit -m "feat: add viral_core.paths (durable run directories)"
```

---

## Task 4: `viral_core.apify_client` — shared actor runner

**Files:**
- Create: `viral_core/apify_client.py`
- Test: `tests/test_apify_client.py`

**Interfaces:**
- Produces: `run_actor(token: str, actor_id: str, run_input: dict) -> list[dict]` — creates an `ApifyClient`, calls the actor, iterates the default dataset, returns the items list. Raises `RuntimeError("APIFY_TOKEN not set")` if `token` is empty.
- Consumes: `apify_client.ApifyClient` (third-party; mocked in tests).

- [ ] **Step 1: Write the failing test**

`tests/test_apify_client.py`:
```python
import sys, pathlib
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor


def test_run_actor_returns_dataset_items():
    fake_run = MagicMock(default_dataset_id="ds1")
    fake_client = MagicMock()
    fake_client.actor.return_value.call.return_value = fake_run
    fake_client.dataset.return_value.iterate_items.return_value = iter([{"a": 1}, {"a": 2}])

    with patch("viral_core.apify_client.ApifyClient", return_value=fake_client) as AC:
        items = run_actor("tok", "the/actor", {"urls": ["x"]})

    AC.assert_called_once_with("tok")
    fake_client.actor.assert_called_with("the/actor")
    assert items == [{"a": 1}, {"a": 2}]

def test_run_actor_requires_token():
    try:
        run_actor("", "the/actor", {})
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "APIFY_TOKEN" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apify_client.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`viral_core/apify_client.py`:
```python
"""One Apify actor-runner shared by every stage that scrapes.

Encapsulates the client → actor → call → dataset → items chain so callers
get a plain list back and don't reimplement Apify boilerplate.
"""
try:
    from apify_client import ApifyClient
except ImportError:
    ApifyClient = None


def run_actor(token: str, actor_id: str, run_input: dict) -> list[dict]:
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    if ApifyClient is None:
        raise RuntimeError("apify_client package not installed")
    client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=run_input)
    return list(client.dataset(run.default_dataset_id).iterate_items())
```

Append to `viral_core/__init__.py`:
```python
from viral_core.apify_client import run_actor
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_apify_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viral_core/apify_client.py viral_core/__init__.py tests/test_apify_client.py
git commit -m "feat: add viral_core.apify_client.run_actor"
```

---

## Task 5: Refactor `scrape_instagram.py` onto `viral_core`

**Files:**
- Modify: `scripts/scrape_instagram.py`
- Modify: `tests/test_scrape_instagram.py`
- Test: `tests/test_scrape_instagram.py` (rewrite mocks to patch `viral_core.apify_client.run_actor`)

**Interfaces:**
- Consumes: `viral_core.apify_client.run_actor`, `viral_core.config_io.load_env`.
- Produces: unchanged `scrape(...)`, `normalize_post(...)`, `main(...)` — existing public surface preserved. `scrape()` now calls `run_actor(token, ACTOR_ID, run_input)`.

- [ ] **Step 1: Update the tests to mock `run_actor`**

The existing tests patch `scripts.scrape_instagram.ApifyClient` and construct actor/dataset mocks. Replace that with patching `viral_core.apify_client.run_actor` to return a list of raw items directly. In `tests/test_scrape_instagram.py`, change every:
```python
@patch("scripts.scrape_instagram.ApifyClient")
def test_x(self, MockClient):
    # ... build actor().call().default_dataset_id / dataset().iterate_items() ...
```
to:
```python
@patch("scripts.scrape_instagram.run_actor")
def test_x(self, mock_run_actor):
    mock_run_actor.return_value = [<raw item dicts the test already uses>]
    os.environ["APIFY_TOKEN"] = "test-token"
    posts = scrape([{"handle": "alice"}], posts_per_handle=10, lookback_days=365)
    # ... existing assertions on normalized posts ...
```
Add `import os` and set `os.environ["APIFY_TOKEN"] = "test-token"` in each test (or in `setUp`). Keep all existing normalization/filter assertions intact — only the mock setup changes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scrape_instagram.py -v`
Expected: FAIL — `run_actor` not importable from `scripts.scrape_instagram` (AttributeError on patch target).

- [ ] **Step 3: Refactor the script**

Edit `scripts/scrape_instagram.py`. Replace lines 1–15 (imports) with:
```python
import argparse
import json
import os
from datetime import datetime, timezone, timedelta

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.config_io import load_env
```
Remove the now-unused `try: from apify_client import ApifyClient`, `try: from dotenv import load_dotenv`, and the `_env_path_for` helper. Replace the body of `scrape(...)` so the actor/dataset block becomes a single `run_actor` call:

```python
def scrape(handles: list[dict], posts_per_handle: int, lookback_days: int) -> list[dict]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise ValueError("APIFY_TOKEN environment variable is not set")

    urls = [f"https://www.instagram.com/{h['handle']}/" for h in handles]
    run_input = {
        "urls": urls,
        # Over-fetch: the actor often returns collab/related posts from other
        # handles, which we filter out below. Headroom keeps the requested
        # handle's count from being starved.
        "resultsLimit": posts_per_handle * 2,
    }

    items = run_actor(token, ACTOR_ID, run_input)
    posts = [normalize_post(item) for item in items]

    requested = {h["handle"].strip().lower() for h in handles}
    posts = [p for p in posts if p["handle"].lower() in requested]

    return filter_recent_posts(posts, lookback_days)
```

Replace the `.env`-loading block at the top of `main(...)` (lines ~123–126) with:
```python
def main(config_path: str, output_path: str) -> None:
    project_dir = str(pathlib.Path(config_path).resolve().parent.parent)
    load_env(project_dir)

    with open(config_path) as f:
        config = json.load(f)
    # ... rest unchanged ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_scrape_instagram.py -v`
Expected: PASS (all existing assertions still hold via the new mock).

- [ ] **Step 5: Commit**

```bash
git add scripts/scrape_instagram.py tests/test_scrape_instagram.py
git commit -m "refactor: scrape_instagram uses viral_core.apify_client + config_io"
```

---

## Task 6: `post-analyzer` spoken-hook schema + merge regression test

**Files:**
- Modify: `agents/post-analyzer.md` (add `spoken_hook` to output schema)
- Test: `tests/test_merge_analyses.py` (add regression test; no code change to `merge_analyses.py` — it already passes agent fields through)

**Interfaces:**
- Produces: each post-analysis object may now include `spoken_hook: {text, type, window}`. `merge_analyses.py` passes it through unchanged (it is not a ground-truth key).

- [ ] **Step 1: Write the failing regression test**

In `tests/test_merge_analyses.py`, add:
```python
def test_spoken_hook_passes_through_merge(self):
    # post in selected_posts.json
    posts = [{"id": "C1", "handle": "alice", "url": "u", "likes": 5,
              "comments": 1, "views": 10, "outlier_score": 1.0, "caption": "c"}]
    # agent analysis includes a spoken_hook
    analysis = {"shortCode": "C1", "handle": "agent-said", "why_it_worked": "x",
                "spoken_hook": {"text": "Stop scrolling.", "type": "pattern interrupt",
                                "window": "0:00-0:02"}}
    with open(os.path.join(self.analyses_dir, "C1.json"), "w") as f:
        json.dump(analysis, f)
    merged = merge_analyses(posts, self.analyses_dir)
    assert merged[0]["spoken_hook"] == analysis["spoken_hook"]
    # ground-truth handle still wins over the agent's
    assert merged[0]["handle"] == "alice"
```
(Use the existing test class's `self.analyses_dir` fixture setup; if the class uses a different attribute name, match it. Ensure `import os, json` are present — they already are in that file.)

- [ ] **Step 2: Run test to verify it passes immediately**

Run: `python -m pytest tests/test_merge_analyses.py::TestMergeAnalyses::test_spoken_hook_passes_through_merge -v`
Expected: PASS — `merge_analyses` already preserves agent-emitted fields via `dict(analysis)`. This test locks that behavior so a future refactor can't silently drop `spoken_hook`.

- [ ] **Step 3: Update the analyzer agent's output schema**

In `agents/post-analyzer.md`, add `spoken_hook` to the "Analysis fields" list and the output JSON shape. Insert after the existing `hook` field description:

```markdown
- **spoken_hook** — a structured object capturing the verbatim spoken opener:
  - `text` — the exact words spoken in the first ~3 seconds (verbatim, from the transcript)
  - `type` — one of: `contrarian claim`, `curiosity gap`, `pattern interrupt`,
    `direct address`, `story / open loop`, `numbered promise`, `question`,
    `shocking stat` (use `other` only if none fit)
  - `window` — the time range it occupies, e.g. `0:00-0:03`
```

And update the output JSON example block to include:
```json
  "hook": "...",
  "spoken_hook": {
    "text": "...",
    "type": "contrarian claim",
    "window": "0:00-0:03"
  },
```

Add a rule under "## Rules":
```markdown
- If there is no spoken audio (silent reel, image post), omit `spoken_hook`
  entirely — the report renders without that block. Do not emit empty strings.
```

- [ ] **Step 4: Run the full merge test suite**

Run: `python -m pytest tests/test_merge_analyses.py -v`
Expected: PASS (all existing + new regression test green).

- [ ] **Step 5: Commit**

```bash
git add agents/post-analyzer.md tests/test_merge_analyses.py
git commit -m "feat: post-analyzer emits structured spoken_hook; merge regression test"
```

---

## Task 7: `pattern-synthesizer` agent + sample fixture

**Files:**
- Create: `agents/pattern-synthesizer.md`
- Create: `tests/fixtures/sample_analyses.json`
- Create: `tests/fixtures/sample_patterns.json`
- Test: no unit test (agent output is consumed by `generate_report`, tested in Task 8). This task delivers the schema contract + fixture.

**Interfaces:**
- Produces: a `patterns` object (JSON) written by the agent to `temp/patterns.json`, conforming to:
  ```json
  {
    "summary": "<prose paragraph>",
    "hook_types": [
      {"name": "...", "definition": "...", "count": int, "share": float,
       "examples": [{"post_id": "...", "handle": "...", "execution": "...", "outlier_score": float}]}
    ],
    "formats": [{"name": "...", "count": int, "share": float}],
    "topics": ["...", "..."]
  }
  ```

- [ ] **Step 1: Write the agent prompt**

`agents/pattern-synthesizer.md`:
```markdown
---
name: pattern-synthesizer
description: Reads the full cohort of analyzed posts (temp/analyses.json) and synthesizes cross-post niche patterns — a prose summary, hook-type playbook (definition + examples), format mix, and recurring topics. Spawned once by the competitor-research skill during Phase 3e, after the per-post analyses are merged. The complement of post-analyzer (which works one post in isolation).
tools: Read, Write
---

# Pattern Synthesizer

You read **all** analyzed posts and surface what the niche is doing collectively.
This is the opposite of `post-analyzer`: it requires the whole cohort.

## Input

`${CLAUDE_PROJECT_DIR}/temp/analyses.json` — a list of merged post-analysis
objects. Each has: `id`, `handle`, `likes`, `comments`, `views`, `outlier_score`,
`hook`, `spoken_hook` (may be absent), `visual_format`, `topic`, `why_it_worked`,
`replication_notes`, `transcript`.

## What to produce

Write `${CLAUDE_PROJECT_DIR}/temp/patterns.json` with exactly this shape:

\`\`\`json
{
  "summary": "<3-5 sentence prose paragraph: what's working in this niche, grounded in the dominant hooks/formats/topics you observed>",
  "hook_types": [
    {
      "name": "Contrarian claim",
      "definition": "<one sentence: what this hook type is>",
      "count": 18,
      "share": 0.36,
      "examples": [
        {"post_id": "<id>", "handle": "<@handle>",
         "execution": "<one sentence: how THIS creator carried it out, referencing the opener>",
         "outlier_score": 8.4}
      ]
    }
  ],
  "formats": [{"name": "Talking head", "count": 27, "share": 0.54}],
  "topics": ["cost-reduction", "workflow speed"]
}
\`\`\`

## Rules

- Use this fixed hook-type taxonomy for `spoken_hook.type` classification:
  `contrarian claim`, `curiosity gap`, `pattern interrupt`, `direct address`,
  `story / open loop`, `numbered promise`, `question`, `shocking stat`. Map any
  agent-supplied `spoken_hook.type` to the closest taxonomy label.
- `hook_types`: include only types with count >= 2. Sort by count descending.
  Each type needs a one-line `definition` and 1-3 `examples` drawn from real
  posts (cite `post_id` + `handle`; `execution` explains how it was carried out).
- `formats`: aggregate `visual_format` values; normalize near-duplicates (e.g.
  "talking head" and "talking-head" merge). `share` = count / total analyzed.
- `topics`: 4-8 recurring topic strings, most common first.
- `share` values are floats in [0,1], rounded to 2 decimals.
- Always write the file, even if the cohort is small — note sparseness in `summary`.
- Ground every claim in the data; do not invent handles, ids, or scores.
```

- [ ] **Step 2: Create the cohort fixture**

`tests/fixtures/sample_analyses.json` — a list of 6 post-analysis objects spanning 3 handles, each with `spoken_hook`, varying hook types and formats. Example structure (abridged; include all fields a real merged object has):
```json
[
  {"id": "C1", "handle": "mrwhosetheboss", "url": "https://instagram.com/p/C1/",
   "likes": 124000, "comments": 3100, "views": 1200000, "outlier_score": 8.4,
   "analyzed": true, "caption": "...",
   "hook": "This AI editor replaced my entire video team in a week.",
   "spoken_hook": {"text": "This AI editor replaced my entire video team in a week.",
                   "type": "contrarian claim", "window": "0:00-0:03"},
   "visual_format": "talking head", "topic": "cost-reduction",
   "why_it_worked": "...", "replication_notes": "...", "transcript": "..."},
  {"id": "C2", "handle": "aiexplained", "outlier_score": 6.1, "analyzed": true,
   "spoken_hook": {"text": "Stop paying for Premiere.", "type": "contrarian claim", "window": "0:00-0:02"},
   "visual_format": "talking head", "topic": "cost-reduction", "...": "..."},
  {"id": "C3", "handle": "aiexplained", "outlier_score": 4.7, "analyzed": true,
   "spoken_hook": {"text": "The prompt nobody is sharing.", "type": "curiosity gap", "window": "0:00-0:02"},
   "visual_format": "screen recording", "topic": "workflow speed", "...": "..."},
  {"id": "C4", "handle": "techled", "outlier_score": 5.3, "analyzed": true,
   "spoken_hook": {"text": "Editors are about to lose their jobs.", "type": "contrarian claim", "window": "0:00-0:03"},
   "visual_format": "talking head", "topic": "cost-reduction", "...": "..."},
  {"id": "C5", "handle": "mrwhosetheboss", "outlier_score": 4.2, "analyzed": true,
   "spoken_hook": {"text": "The one setting that fixes everything.", "type": "curiosity gap", "window": "0:00-0:02"},
   "visual_format": "screen recording", "topic": "workflow speed", "...": "..."},
  {"id": "C6", "handle": "techled", "outlier_score": 3.1, "analyzed": true,
   "spoken_hook": {"text": "Three tools that replaced my whole stack.", "type": "numbered promise", "window": "0:00-0:03"},
   "visual_format": "carousel", "topic": "tool comparison", "...": "..."}
]
```
(Fill `likes`/`comments`/`views`/`caption`/`why_it_worked`/`replication_notes`/`transcript`/`url` for every entry with plausible non-empty values.)

- [ ] **Step 3: Create the expected-patterns fixture**

`tests/fixtures/sample_patterns.json` — what the synthesizer *should* produce from the cohort above (used by the report test in Task 8). Must satisfy: `hook_types[0].name == "Contrarian claim"` with `count == 3`, `examples` citing `C1`/`C2`/`C4`; `formats` totals match the cohort (talking head 3, screen recording 2, carousel 1); `summary` is a 3-5 sentence prose paragraph; `topics` lists at least `cost-reduction`, `workflow speed`.

- [ ] **Step 4: Commit**

```bash
git add agents/pattern-synthesizer.md tests/fixtures/sample_analyses.json tests/fixtures/sample_patterns.json
git commit -m "feat: pattern-synthesizer agent + cohort/patterns fixtures"
```

---

## Task 8: `generate_report.py` — patterns, run-dir, `research.json`, fallback

**Files:**
- Modify: `scripts/generate_report.py`
- Test: `tests/test_generate_report.py`

**Interfaces:**
- Consumes: `viral_core.paths` (`new_run_dir`, `run_artifact`). Patterns JSON (optional `--patterns`).
- Produces: `generate_report(...)` now also writes `<run_dir>/research.json` and writes the HTML/PDF into `<run_dir>` instead of `output/reports/`. New CLI flags: `--patterns`, `--run-dir`. When `--run-dir` is absent, one is created via `new_run_dir(output_root)`.
- `build_summary()` behavior: if a `patterns` block with `summary` is provided, use it; else fall back to a data-driven one-liner (existing logic).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_generate_report.py`:
```python
import json
from pathlib import Path

def test_writes_research_json_into_run_dir(tmp_path):
    from scripts.generate_report import generate_report
    analyses = json.loads(Path("tests/fixtures/sample_analyses.json").read_text())
    analyses_path = tmp_path / "analyses.json"
    analyses_path.write_text(json.dumps(analyses))
    patterns_path = tmp_path / "patterns.json"
    patterns_path.write_text(Path("tests/fixtures/sample_patterns.json").read_text())

    out = generate_report(
        input_path=str(analyses_path),
        output_dir=str(tmp_path / "out"),
        summary_path=None,
        patterns_path=str(patterns_path),
        pdf=False,
    )
    run_dir = Path(out).parent
    research = json.loads((run_dir / "research.json").read_text())
    assert research["stage"] == "research"
    assert research["run_dir"] == str(run_dir)
    assert research["patterns"]["summary"]
    assert research["patterns"]["hook_types"][0]["name"] == "Contrarian claim"
    assert Path(research["report"]["html"]).exists()

def test_falls_back_when_no_patterns(tmp_path):
    from scripts.generate_report import generate_report
    analyses = [{"id": "C1", "handle": "alice", "likes": 10, "comments": 1,
                 "views": 100, "outlier_score": 2.0, "caption": "c",
                 "analyzed": True, "visual_format": "talking head",
                 "why_it_worked": "x"}]
    analyses_path = tmp_path / "analyses.json"
    analyses_path.write_text(json.dumps(analyses))
    out = generate_report(
        input_path=str(analyses_path),
        output_dir=str(tmp_path / "out"),
        summary_path=None,
        patterns_path=None,
        pdf=False,
    )
    run_dir = Path(out).parent
    research = json.loads((run_dir / "research.json").read_text())
    # patterns block may be absent, but research.json still written
    assert research["stage"] == "research"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate_report.py -v`
Expected: FAIL — `generate_report() got an unexpected keyword argument 'patterns_path'`.

- [ ] **Step 3: Implement**

Edit `scripts/generate_report.py`. Add the bootstrap + imports near the top:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from viral_core.paths import new_run_dir, run_artifact
```

Replace `build_summary` so it accepts an optional patterns block:
```python
def build_summary(analyses: list[dict], patterns: dict | None = None) -> str:
    if patterns and patterns.get("summary"):
        return patterns["summary"]
    handles = sorted({a.get("handle") for a in analyses if a.get("handle")})
    formats = [a.get("visual_format") for a in analyses
               if a.get("visual_format") and a.get("analyzed")]
    top_format = Counter(formats).most_common(1)[0][0] if formats else "n/a"
    analyzed = sum(1 for a in analyses if a.get("analyzed"))
    return (
        f"Analyzed {analyzed}/{len(analyses)} top posts across "
        f"{len(handles)} handles ({', '.join(handles)}). "
        f"Most common format: {top_format}."
    )
```

Replace the `generate_report(...)` signature and body to accept `patterns_path`, resolve/create a run dir, write into it, and emit `research.json`:
```python
def generate_report(input_path: str, output_dir: str, summary_path: str | None = None,
                    date_str: str | None = None, pdf: bool = False,
                    patterns_path: str | None = None,
                    run_dir: str | None = None) -> str:
    with open(input_path, encoding="utf-8") as f:
        analyses = json.load(f)

    patterns = None
    if patterns_path and os.path.exists(patterns_path):
        with open(patterns_path, encoding="utf-8") as f:
            patterns = json.load(f)

    summary = build_summary(analyses, patterns)
    if summary_path and os.path.exists(summary_path):
        with open(summary_path, encoding="utf-8") as f:
            summary = f.read().strip() or summary

    # Resolve/create the run directory: the single durable home for this run.
    if run_dir is None:
        run_dir = str(new_run_dir(output_dir))
    else:
        os.makedirs(run_dir, exist_ok=True)
    output_dir = run_dir

    date_str_is_override = date_str is not None
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    html = render_report(analyses, summary, date_str,
                         str(TEMPLATE_DIR / "report.html.j2"),
                         patterns=patterns)

    if date_str_is_override:
        stamp = date_str
    else:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_path = os.path.join(output_dir, f"IG-Competitor-Research_{stamp}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote report -> {out_path}")

    if pdf:
        try:
            from scripts.generate_pdf import render_pdf
        except ModuleNotFoundError:
            from generate_pdf import render_pdf
        pdf_path = os.path.join(output_dir, f"IG-Competitor-Research_{stamp}.pdf")
        pdf_name = render_pdf(out_path, pdf_path) if render_pdf(out_path, pdf_path) else None
        pdf_name = f"IG-Competitor-Research_{stamp}.pdf" if pdf_name else None
    else:
        pdf_name = None

    # Durable handoff artifact for downstream stages.
    research = {
        "stage": "research",
        "created_at": datetime.now().astimezone().isoformat(),
        "run_dir": run_dir,
        "config": None,
        "posts": analyses,
        "patterns": patterns or {},
        "report": {"html": os.path.basename(out_path),
                   "pdf": pdf_name},
    }
    with open(run_artifact(run_dir, "research"), "w", encoding="utf-8") as f:
        json.dump(research, f, indent=2)

    return out_path
```

Update `render_report` to accept and forward `patterns`:
```python
def render_report(analyses, summary, date_str, template_path, patterns=None):
    ...
    return template.render(
        posts=posts, summary=summary, date_str=date_str,
        handles=handles, total=len(analyses), patterns=patterns,
    )
```

Update the `__main__` argparse to add the flags and pass `run_dir` through when provided:
```python
    parser.add_argument("--patterns", default="temp/patterns.json")
    parser.add_argument("--run-dir", default=None)
    ...
    generate_report(
        args.input, args.output_dir,
        summary_path=args.summary if args.summary else None,
        pdf=args.pdf,
        patterns_path=args.patterns if args.patterns else None,
        run_dir=args.run_dir,
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_generate_report.py -v`
Expected: PASS. (Note: the existing tests that call `generate_report(...)` positionally with 4 args still work because `output_dir` is still the 2nd positional; if any existing test asserts the report was written to `output/reports/`, update it to expect the new run-dir location.)

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_report.py tests/test_generate_report.py
git commit -m "feat: generate_report emits research.json + consumes patterns in run dir"
```

---

## Task 9: Report template — patterns section + spoken-hook block

**Files:**
- Modify: `templates/report.html.j2`
- Test: `tests/test_generate_report.py` (render assertions)

**Interfaces:**
- Consumes: `patterns` (template var, may be `None`) and `post.spoken_hook` (object, may be absent).
- Renders: a unified top section (prose summary already shown + pattern stats: hook playbook, format bars, topics) and a per-post spoken-hook block. Existing fields unchanged.

- [ ] **Step 1: Write the failing render tests**

Add to `tests/test_generate_report.py`:
```python
def test_patterns_section_renders(tmp_path):
    from scripts.generate_report import render_report
    analyses = json.loads(Path("tests/fixtures/sample_analyses.json").read_text())
    patterns = json.loads(Path("tests/fixtures/sample_patterns.json").read_text())
    html = render_report(analyses, "SUM", "2026-07-01",
                         "templates/report.html.j2", patterns=patterns)
    assert "Niche Patterns" in html
    assert "Contrarian claim" in html          # hook type name
    assert "Talking head" in html              # format name
    assert "cost-reduction" in html            # topic

def test_spoken_hook_block_renders(tmp_path):
    from scripts.generate_report import render_report
    analyses = json.loads(Path("tests/fixtures/sample_analyses.json").read_text())
    html = render_report(analyses, "SUM", "2026-07-01",
                         "templates/report.html.j2", patterns=None)
    assert "SPOKEN HOOK" in html
    assert "contrarian claim" in html
    assert "0:00-0:03" in html

def test_card_renders_without_spoken_hook():
    from scripts.generate_report import render_report
    analyses = [{"id": "C1", "handle": "alice", "likes": 1, "comments": 0,
                 "views": 10, "outlier_score": 1.0, "caption": "", "analyzed": True,
                 "hook": "hi", "visual_format": "image"}]
    html = render_report(analyses, "SUM", "2026-07-01",
                         "templates/report.html.j2", patterns=None)
    assert "SPOKEN HOOK" not in html   # graceful absence
    assert "Why It Worked" in html or "Why It" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate_report.py -v`
Expected: FAIL — `Niche Patterns` / `SPOKEN HOOK` not in rendered HTML.

- [ ] **Step 3: Edit the template**

In `templates/report.html.j2`, first add CSS for the new elements inside the existing `<style>` block (before the `@media print` rule):
```css
.patterns { border-color: var(--accent2); }
.patterns h2 { margin-bottom: 10px; }
.pattern-block { margin-top: 14px; }
.pattern-block .label { margin-bottom: 6px; }
.hook-type { background: #15171c; border: 1px solid var(--line); border-radius: 6px;
  margin-bottom: 6px; }
.hook-type > .ht-head { padding: 8px 10px; font-size: 13px; }
.hook-type > .ht-body { border-top: 1px solid var(--line); padding: 8px 10px;
  font-size: 12px; color: var(--dim); }
.hook-type .ht-body ul { margin: 4px 0 0 16px; padding: 0; color: #cdd2da; line-height: 1.5; }
.fmt-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; font-size: 12px; }
.fmt-name { width: 120px; display: inline-block; }
.fmt-bar { height: 6px; border-radius: 3px; display: inline-block; }
.spoken-hook { background: #15171c; border-left: 3px solid var(--accent);
  border-radius: 4px; padding: 8px 10px; margin: 0 0 12px; }
.spoken-hook .sh-tag { color: var(--accent); font-size: 11px; }
.spoken-hook .sh-chip { background: var(--line); color: #cdd2da; font-size: 10px;
  padding: 1px 6px; border-radius: 8px; }
.spoken-hook .sh-win { color: var(--dim); font-size: 10px; }
.spoken-hook .sh-text { font-style: italic; color: var(--ink); font-size: 13px; }
```

Replace the existing `<section class="summary">...</section>` block (lines ~82–85) with a unified section that shows the prose summary and, when `patterns` is present, the pattern statistics:
```html
    <section class="summary patterns">
      <h2>🔥 What's Working in the Niche</h2>
      <p>{{ summary }}</p>

      {% if patterns %}
      <div class="pattern-block">
        <div class="label">Top hook structures</div>
        {% for ht in patterns.hook_types or [] %}
        <div class="hook-type">
          <div class="ht-head"><strong style="color:var(--accent);">{{ loop.index }}. {{ ht.name }}</strong> · {{ ht.count }} posts ({{ "{:.0%}".format(ht.share) }})</div>
          <div class="ht-body">
            <em>Definition:</em> {{ ht.definition }}
            <div style="margin-top:4px;"><em>How it was executed:</em></div>
            <ul>
              {% for ex in ht.examples or [] %}
              <li><strong>@{{ ex.handle }}</strong> — {{ ex.execution }} <span style="color:var(--accent);">{{ ex.outlier_score }}x</span></li>
              {% endfor %}
            </ul>
          </div>
        </div>
        {% endfor %}

        {% if patterns.formats %}
        <div class="label" style="margin-top:10px;">Dominant formats</div>
        {% for f in patterns.formats %}
        <div class="fmt-row">
          <span class="fmt-name">{{ f.name }}</span>
          <span class="fmt-bar" style="width: {{ "{:.0%}".format(f.share) }}; background: {{ loop.index0 == 0 if 'var(--accent)' or 'var(--accent2)' }};"></span>
          <span style="color:var(--dim);">{{ "{:.0%}".format(f.share) }}</span>
        </div>
        {% endfor %}
        {% endif %}

        {% if patterns.topics %}
        <div class="label" style="margin-top:10px;">Recurring topics</div>
        <p style="font-size:13px;color:#cdd2da;">{{ patterns.topics | join(" · ") }}</p>
        {% endif %}
      </div>
      {% endif %}
    </section>
```

Add the spoken-hook block inside the per-post card, between the thumbnail `{% endif %}` (line ~101) and the `{% if post.analyzed %}` block:
```html
        {% if post.spoken_hook %}
        <div class="spoken-hook">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap;">
            <span class="sh-tag">▶ SPOKEN HOOK</span>
            <span class="sh-chip">{{ post.spoken_hook.type }}</span>
            <span class="sh-win">{{ post.spoken_hook.window }}</span>
          </div>
          <div class="sh-text">"{{ post.spoken_hook.text }}"</div>
        </div>
        {% endif %}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_generate_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/report.html.j2 tests/test_generate_report.py
git commit -m "feat: report shows Niche Patterns section + per-post spoken hook"
```

---

## Task 10: `discovery_pull_trends.py` (Phase A) + deps

**Files:**
- Create: `scripts/discovery_pull_trends.py`
- Modify: `requirements.txt`, `.env.example`
- Test: `tests/test_discovery_pull_trends.py`
- Fixtures: `tests/fixtures/sample_niches.json`

**Interfaces:**
- Produces: `pull_trends(seed: str, use_reddit: bool = True) -> list[dict]` returning `[{niche, trend_score, sources}]`. CLI: `--seed`, `--output`. Reads `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` from env for Reddit; no-op when absent.
- Consumes: `pytrends`, `praw` (both optional at runtime — graceful degradation).

- [ ] **Step 1: Add dependencies**

`requirements.txt` — append:
```
pytrends>=4.9.0
praw>=7.7.0
```
`.env.example` — append:
```
# Optional — enables Reddit trend signals in /niche-discovery Phase A
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

- [ ] **Step 2: Write the failing test**

`tests/test_discovery_pull_trends.py`:
```python
import json, sys, pathlib
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_pull_trends import pull_trends, merge_niches


def test_merge_boosts_niches_in_both_sources():
    trends = [("AI video editors", 87), ("AI coding assistants", 74)]
    reddit = [("AI video editors", 5), ("Notion templates", 3)]
    merged = merge_niches(trends, reddit)
    by_niche = {m["niche"]: m for m in merged}
    assert "google_trends" in by_niche["AI video editors"]["sources"]
    assert "reddit" in by_niche["AI video editors"]["sources"]
    # a niche in both should outrank a trends-only niche with a lower raw score
    assert by_niche["AI video editors"]["trend_score"] >= by_niche["AI coding assistants"]["trend_score"]

def test_pull_trends_pytrends_only(monkeypatch):
    import scripts.discovery_pull_trends as m
    monkeypatch.setattr(m, "_pytrends_niches", lambda seed: [("AI video editors", 87)])
    monkeypatch.setattr(m, "_reddit_niches", lambda seed: [])  # reddit unavailable
    out = pull_trends("AI", use_reddit=True)
    assert out[0]["niche"] == "AI video editors"
    assert out[0]["sources"] == ["google_trends"]

def test_pull_trends_empty_when_no_sources(monkeypatch):
    import scripts.discovery_pull_trends as m
    monkeypatch.setattr(m, "_pytrends_niches", lambda seed: [])
    monkeypatch.setattr(m, "_reddit_niches", lambda seed: [])
    assert pull_trends("AI", use_reddit=True) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_discovery_pull_trends.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

`scripts/discovery_pull_trends.py`:
```python
"""Phase A — trend signals. Surfaces rising niches via Google Trends (+Reddit)."""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

SUBREDDITS = ["entrepreneur", "SideProject", "ChatGPT", "artificial"]


def _pytrends_niches(seed: str) -> list[tuple[str, int]]:
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return []
    try:
        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload([seed or "technology"], timeframe="today 3-m")
        df = pytrends.related_queries()[seed or "technology"].get("rising", [])
        if df is None or len(df) == 0:
            return []
        # df has 'query' and 'value' (percent growth); take top 10
        rows = df.head(10).to_dict("records")
        return [(r["query"], int(r.get("value") or 0)) for r in rows]
    except Exception:
        return []


def _reddit_niches(seed: str) -> list[tuple[str, int]]:
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return []
    try:
        import praw
    except ImportError:
        return []
    try:
        reddit = praw.Reddit(client_id=cid, client_secret=secret, user_agent="viral-analyzer")
        counts: dict[str, int] = {}
        for sub in SUBREDDITS:
            for post in reddit.subreddit(sub).hot(limit=25):
                title = post.title.lower()
                for word in title.split():
                    w = word.strip(".,!?")
                    if len(w) > 4:
                        counts[w] = counts.get(w, 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    except Exception:
        return []


def merge_niches(trends: list[tuple[str, int]], reddit: list[tuple[str, int]]) -> list[dict]:
    max_score = max([s for _, s in trends] + [s for _, s in reddit] + [1])
    seen: dict[str, dict] = {}
    for niche, score in trends:
        seen.setdefault(niche, {"niche": niche, "raw": 0, "sources": []})
        seen[niche]["raw"] += score
        seen[niche]["sources"].append("google_trends")
    for niche, score in reddit:
        seen.setdefault(niche, {"niche": niche, "raw": 0, "sources": []})
        seen[niche]["raw"] += score
        seen[niche]["sources"].append("reddit")
    out = []
    for v in seen.values():
        v["trend_score"] = round(100 * v["raw"] / max_score)
        out.append(v)
    out.sort(key=lambda d: (len(d["sources"]), d["trend_score"]), reverse=True)
    return out


def pull_trends(seed: str, use_reddit: bool = True) -> list[dict]:
    trends = _pytrends_niches(seed)
    reddit = _reddit_niches(seed) if use_reddit else []
    return merge_niches(trends, reddit)


def main(seed: str, output_path: str) -> None:
    niches = pull_trends(seed, use_reddit=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(niches, f, indent=2)
    print(f"Wrote {len(niches)} niches -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull trending niches (Phase A)")
    parser.add_argument("--seed", default="")
    parser.add_argument("--output", default="temp/niches.json")
    args = parser.parse_args()
    main(args.seed, args.output)
```

Create `tests/fixtures/sample_niches.json` with the example from the niche-discovery spec (3 entries).

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_discovery_pull_trends.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/discovery_pull_trends.py requirements.txt .env.example tests/test_discovery_pull_trends.py tests/fixtures/sample_niches.json
git commit -m "feat: discovery_pull_trends (Phase A) + pytrends/praw deps"
```

---

## Task 11: `discovery_handles.py` (Phase B)

**Files:**
- Create: `scripts/discovery_handles.py`
- Test: `tests/test_discovery_handles.py`
- Fixture: `tests/fixtures/sample_candidate_handles.json`

**Interfaces:**
- Produces: `discover_handles(niches: list[str], token: str) -> list[dict]` → `[{handle, hashtags, post_count}]`. Cross-hashtag frequency: a handle appearing in more hashtags ranks higher. CLI: `--niches` (path), `--output`.
- Consumes: `viral_core.apify_client.run_actor` (`api-ninja/instagram-scraper`, hashtag mode).

- [ ] **Step 1: Write the failing test**

`tests/test_discovery_handles.py`:
```python
import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_handles import hashtags_for_niche, build_frequency, discover_handles


def test_hashtags_for_niche():
    tags = hashtags_for_niche("AI video editors")
    assert all(t.startswith("#") for t in tags)
    assert 3 <= len(tags) <= 5

def test_build_frequency_cross_hashtag():
    posts = [
        {"user": {"username": "a"}, "__hashtag": "#ai"},
        {"user": {"username": "a"}, "__hashtag": "#video"},
        {"user": {"username": "b"}, "__hashtag": "#ai"},
    ]
    freq = build_frequency(posts)
    assert freq["a"]["post_count"] == 2
    assert set(freq["a"]["hashtags"]) == {"#ai", "#video"}
    assert freq["b"]["post_count"] == 1

def test_discover_handles_uses_run_actor(monkeypatch):
    def fake_run(token, actor, run_input):
        tag = run_input["hashtags"][0]
        return [{"user": {"username": "a"}}, {"user": {"username": "b"}}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_handles.run_actor", side_effect=fake_run) as ra:
        out = discover_handles(["AI video editors"], "tok")
    assert ra.call_count >= 1
    handles = {h["handle"] for h in out}
    assert {"a", "b"} <= handles
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_discovery_handles.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`scripts/discovery_handles.py`:
```python
"""Phase B — hashtag -> handle discovery. Turns niches into candidate creators."""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor

ACTOR_ID = "api-ninja/instagram-scraper"


def hashtags_for_niche(niche: str) -> list[str]:
    words = [w for w in niche.lower().replace("-", " ").split() if w]
    base = "".join(w for w in words[:2]) or "trending"
    candidates = [f"#{base}", f"#{base}tips", f"#{words[0] if words else 'trending'}"]
    for w in words[:3]:
        candidates.append(f"#{w}")
    # dedupe preserving order, keep 3-5
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:5]


def build_frequency(posts: list[dict]) -> dict:
    freq: dict[str, dict] = {}
    for p in posts:
        handle = (p.get("user") or {}).get("username")
        tag = p.get("__hashtag")
        if not handle:
            continue
        entry = freq.setdefault(handle, {"handle": handle, "hashtags": [], "post_count": 0})
        if tag and tag not in entry["hashtags"]:
            entry["hashtags"].append(tag)
        entry["post_count"] += 1
    return freq


def discover_handles(niches: list[str], token: str, posts_per_hashtag: int = 50) -> list[dict]:
    all_posts: list[dict] = []
    for niche in niches:
        for tag in hashtags_for_niche(niche):
            run_input = {"hashtags": [tag], "resultsLimit": posts_per_hashtag}
            try:
                items = run_actor(token, ACTOR_ID, run_input)
            except Exception as e:
                print(f"WARN: hashtag {tag} failed: {e}")
                continue
            for item in items:
                item["__hashtag"] = tag
                all_posts.append(item)
    freq = build_frequency(all_posts)
    out = list(freq.values())
    out.sort(key=lambda d: (len(d["hashtags"]), d["post_count"]), reverse=True)
    return out


def main(niches_path: str, output_path: str) -> None:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    with open(niches_path) as f:
        niches = [n["niche"] if isinstance(n, dict) else n for n in json.load(f)]
    handles = discover_handles(niches, token)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(handles, f, indent=2)
    print(f"Wrote {len(handles)} candidate handles -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover handles from niches (Phase B)")
    parser.add_argument("--niches", default="temp/niches.json")
    parser.add_argument("--output", default="temp/candidate_handles.json")
    args = parser.parse_args()
    main(args.niches, args.output)
```

Create `tests/fixtures/sample_candidate_handles.json` (2 entries matching the spec's example).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_discovery_handles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/discovery_handles.py tests/test_discovery_handles.py tests/fixtures/sample_candidate_handles.json
git commit -m "feat: discovery_handles (Phase B) via viral_core.apify_client"
```

---

## Task 12: `discovery_score.py` (Phase C)

**Files:**
- Create: `scripts/discovery_score.py`
- Test: `tests/test_discovery_score.py`

**Interfaces:**
- Produces: `score_handles(candidates: list[dict], token: str) -> list[dict]` → top 10 by `final_score`, each `{handle, final_score, engagement_rate, cross_hashtag_count, outlier_potential, followers, niche}`. Qualification: handle in ≥2 hashtags OR top-20% engagement.
- Consumes: `viral_core.apify_client.run_actor` (`apify/instagram-profile-scraper`), `viral_core.scoring.outlier_score`.

- [ ] **Step 1: Write the failing test**

`tests/test_discovery_score.py`:
```python
import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_score import compute_final_score, qualifies, score_handles


def test_qualifies_by_cross_hashtag():
    c = {"handle": "a", "hashtags": ["#x", "#y"], "post_count": 1,
         "followers": 1000, "avg_likes": 50, "avg_comments": 5}
    assert qualifies(c, min_tags=2, top20_eng_rate=1.0) is True

def test_compute_final_score_weights():
    c = {"handle": "a", "hashtags": ["#x", "#y", "#z"], "post_count": 1,
         "followers": 1000, "avg_likes": 50, "avg_comments": 10}
    # engagement_rate = (50+10)/1000 = 0.06 ; cross = 3/3 = 1.0
    score, parts = compute_final_score(c, max_tags=3, median_engagement=30, sample_top_engagement=93)
    assert 0.0 <= score <= 1.0
    assert parts["engagement_rate"] == 0.06
    assert parts["cross_hashtag_count"] == 3

def test_score_handles_returns_top_sorted(monkeypatch):
    candidates = [
        {"handle": "a", "hashtags": ["#x", "#y"], "post_count": 2, "niche": "AI"},
        {"handle": "b", "hashtags": ["#x"], "post_count": 1, "niche": "AI"},
    ]
    def fake_run(token, actor, run_input):
        return [{"followersCount": 1000, "avgLikes": 80, "avgComments": 10}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_score.run_actor", side_effect=fake_run):
        out = score_handles(candidates, "tok", top_n=10)
    assert out[0]["final_score"] >= out[-1]["final_score"]
    assert "handle" in out[0] and "niche" in out[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`scripts/discovery_score.py`:
```python
"""Phase C — creator scoring. Ranks candidate handles by engagement + niche authority."""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.scoring import outlier_score

PROFILE_ACTOR = "apify/instagram-profile-scraper"

W_ENG = 0.4
W_CROSS = 0.4
W_OUTLIER = 0.2


def qualifies(c: dict, min_tags: int, top20_eng_rate: float) -> bool:
    if len(c.get("hashtags", [])) >= min_tags:
        return True
    followers = c.get("followers") or 1
    eng = (c.get("avg_likes", 0) + c.get("avg_comments", 0)) / followers
    return eng >= top20_eng_rate


def compute_final_score(c: dict, max_tags: int, median_engagement: float,
                        sample_top_engagement: float) -> tuple[float, dict]:
    followers = c.get("followers") or 1
    eng_rate = (c.get("avg_likes", 0) + c.get("avg_comments", 0)) / followers
    cross = len(c.get("hashtags", []))
    cross_norm = min(cross / max_tags, 1.0) if max_tags else 0.0
    # outlier potential: how viral the creator's best content is vs their median
    outlier_pot = outlier_score(sample_top_engagement, median_engagement) if median_engagement else 0.0
    # normalize components to [0,1] with soft caps
    eng_norm = min(eng_rate / 0.10, 1.0)        # 10% engagement = max
    out_norm = min(outlier_pot / 5.0, 1.0)      # 5x = max
    final = round(W_ENG * eng_norm + W_CROSS * cross_norm + W_OUTLIER * out_norm, 3)
    return final, {
        "engagement_rate": round(eng_rate, 4),
        "cross_hashtag_count": cross,
        "outlier_potential": round(outlier_pot, 2),
        "followers": followers,
    }


def score_handles(candidates: list[dict], token: str, top_n: int = 10) -> list[dict]:
    max_tags = max((len(c.get("hashtags", [])) for c in candidates), default=1) or 1
    # rough cohort engagement for the 80th-percentile threshold + a median baseline
    eng_rates = []
    for c in candidates:
        f = c.get("followers") or 1
        eng_rates.append((c.get("avg_likes", 0) + c.get("avg_comments", 0)) / f)
    eng_rates.sort()
    top20 = eng_rates[-max(1, len(eng_rates) // 5)] if eng_rates else 1.0
    median_eng = eng_rates[len(eng_rates) // 2] if eng_rates else 0.0

    scored = []
    for c in candidates:
        if not qualifies(c, min_tags=2, top20_eng_rate=top20):
            continue
        run_input = {"usernames": [c["handle"]]}
        try:
            items = run_actor(token, PROFILE_ACTOR, run_input)
        except Exception as e:
            print(f"WARN: profile scrape failed for {c['handle']}: {e}")
            continue
        if not items:
            continue
        prof = items[0]
        c["followers"] = prof.get("followersCount", 0)
        c["avg_likes"] = prof.get("avgLikes", 0)
        c["avg_comments"] = prof.get("avgComments", 0)
        final, parts = compute_final_score(c, max_tags, median_eng * c["followers"],
                                           sample_top_engagement=c["avg_likes"] + c["avg_comments"])
        scored.append({"handle": c["handle"], "niche": c.get("niche", ""),
                       "final_score": final, **parts})
    scored.sort(key=lambda d: d["final_score"], reverse=True)
    return scored[:top_n]


def main(input_path: str, output_path: str, top_n: int) -> None:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    with open(input_path) as f:
        candidates = json.load(f)
    scored = score_handles(candidates, token, top_n)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2)
    print(f"Wrote {len(scored)} scored handles -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score candidate handles (Phase C)")
    parser.add_argument("--input", default="temp/candidate_handles.json")
    parser.add_argument("--output", default="temp/scored_handles.json")
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()
    main(args.input, args.output, args.top_n)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_discovery_score.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/discovery_score.py tests/test_discovery_score.py
git commit -m "feat: discovery_score (Phase C) using viral_core scoring + apify"
```

---

## Task 13: Niche-discovery skill + command

**Files:**
- Create: `skills/niche-discovery/SKILL.md`
- Create: `commands/niche-discovery.md`

**Interfaces:**
- Produces: `/niche-discovery` orchestration. Writes `config/competitors.json` (functional handoff) + `output/runs/{ts}/discovery.json` (provenance).

- [ ] **Step 1: Write the skill**

`skills/niche-discovery/SKILL.md`:
```markdown
---
name: niche-discovery
description: Discovers trending niches, maps them to Instagram hashtags, extracts and scores creator handles, and writes a ranked shortlist to config/competitors.json. Solves the cold-start problem before /competitor-research. Triggered by "/niche-discovery" or natural language like "find me creators in the X niche", "discover trending niches", or "who should I research on Instagram".
---

# Niche & Creator Discovery

Stage 0 of the viral-analyzer chain. Ends by writing `config/competitors.json`,
which `/competitor-research` reads — no changes to that pipeline.

## Path conventions

- `${CLAUDE_PLUGIN_ROOT}` — read-only plugin code (scripts).
- `${CLAUDE_PROJECT_DIR}` — user project (working data, config, .env, output).

Scripts -> `${CLAUDE_PLUGIN_ROOT}/scripts/discovery_*.py`
Working data -> `${CLAUDE_PROJECT_DIR}/temp/...`
Config -> `${CLAUDE_PROJECT_DIR}/config/competitors.json`
Provenance -> `${CLAUDE_PROJECT_DIR}/output/runs/{ts}/discovery.json`

## First-run setup

1. Python deps: `python -c "import requests, apify_client, pytrends"`. If missing,
   `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.
2. `APIFY_TOKEN` in `${CLAUDE_PROJECT_DIR}/.env` (required for Phases B + C).
3. Reddit is optional: `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` enable Phase A's
   Reddit signal. Absent -> Phase A runs on Google Trends only.

## Entry

Ask: "Do you have a niche in mind, or should I discover trending niches for you?"

- **Fast path** — user types a niche: skip Phase A; seed Phase B with it.
- **Discovery path** — run Phase A, present top 10 niches, user picks 1-3.

## Phase A — Trend signals

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_pull_trends.py" \
  --seed "<optional broad category>" \
  --output "${CLAUDE_PROJECT_DIR}/temp/niches.json"
```
Present top 10; user picks 1-3.

## Phase B — Hashtag -> handle discovery

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_handles.py" \
  --niches "${CLAUDE_PROJECT_DIR}/temp/niches.json" \
  --output "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json"
```

## Phase C — Creator scoring

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_score.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json" \
  --output "${CLAUDE_PROJECT_DIR}/temp/scored_handles.json" \
  --top-n 10
```
Present the ranked table (rank, handle, score, eng rate, hashtags, followers).
User picks 3-5.

## Shortlist + write config

Ask: "Replace existing competitors or add?" (default: replace).

Write `config/competitors.json` (preserve `posts_per_handle`, `lookback_days` if
replacing; keep their existing values otherwise):
```json
{
  "competitors": [{"handle": "...", "niche": "..."}],
  "posts_per_handle": 10,
  "lookback_days": 365
}
```

Then write the provenance record to `${CLAUDE_PROJECT_DIR}/output/runs/{ts}/discovery.json`:
```json
{
  "stage": "discovery",
  "created_at": "<iso>",
  "niche_seed": "<seed or typed niche>",
  "niches_explored": ["..."],
  "selected_creators": [{"handle": "...", "final_score": 0.0, "niche": "..."}],
  "config_written_to": "config/competitors.json"
}
```

Offer to run `/competitor-research` next.
```

- [ ] **Step 2: Write the command**

`commands/niche-discovery.md`:
```markdown
---
description: Discover trending niches and creators, write them to config/competitors.json (feeds /competitor-research)
---

Invoke the `niche-discovery` skill to discover trending niches, map them to
hashtags, extract and score creator handles, and write a ranked shortlist to
`config/competitors.json`. This is stage 0 of the viral-analyzer chain; run
`/competitor-research` afterwards to analyze the selected creators' top posts.

Passes `$ARGUMENTS` (an optional seed niche) through to the skill.
```

- [ ] **Step 3: Sanity-check the plugin loads**

Run: `python -c "import sys; sys.path.insert(0,'.'); import viral_core; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add skills/niche-discovery/SKILL.md commands/niche-discovery.md
git commit -m "feat: /niche-discovery skill + command (stage 0)"
```

---

## Task 14: Wire competitor-research skill to Phase 3e + run dir + research.json

**Files:**
- Modify: `skills/competitor-research/SKILL.md`
- Modify: `agents/post-analyzer.md` is already done (Task 6); no further change.

**Interfaces:**
- Produces: the research stage now runs Phase 3e (pattern-synthesizer → `temp/patterns.json`), passes `--patterns` and `--run-dir` to `generate_report`, and the report + `research.json` land in the run dir.

- [ ] **Step 1: Update the skill orchestration**

In `skills/competitor-research/SKILL.md`:

a) In "Pipeline Phases", after the Phase 3d merge block and before "Phase 4", insert a new Phase 3e:
```markdown
### Phase 3e — Niche Patterns (cross-post synthesis) ✅

Spawn the `pattern-synthesizer` sub-agent ONCE (not in parallel — it needs the
whole cohort). It reads `${CLAUDE_PROJECT_DIR}/temp/analyses.json` and writes
`${CLAUDE_PROJECT_DIR}/temp/patterns.json` (prose summary + hook playbook +
format mix + topics).

If it fails or the file is absent, Phase 4 still runs — `generate_report` falls
back to a data-driven summary.
```

b) Replace the Phase 4 command block with one that passes `--patterns` and writes to a run dir:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_report.py" \
  --input "${CLAUDE_PROJECT_DIR}/temp/analyses.json" \
  --output-dir "${CLAUDE_PROJECT_DIR}/output" \
  --summary "${CLAUDE_PROJECT_DIR}/temp/niche_summary.txt" \
  --patterns "${CLAUDE_PROJECT_DIR}/temp/patterns.json"
```
Note in the surrounding prose: the report, PDF, and `research.json` (the durable
handoff for future stages) are all written into the new run dir
`output/runs/{date}_{HHMM}/`. `--output-dir` is now the runs-root parent
(`output`); `generate_report` creates the timestamped run dir itself.

c) Update "Orchestration" to mention the durable artifact:
```markdown
After Phase 4, the run's durable outputs live in `${CLAUDE_PROJECT_DIR}/output/runs/{date}_{HHMM}/`:
the HTML/PDF report and `research.json` (analyzed posts + patterns). Future stages
read `research.json` without re-scraping.
```

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests PASS (existing + every new test added in Tasks 1–12).

- [ ] **Step 3: Commit**

```bash
git add skills/competitor-research/SKILL.md
git commit -m "feat: competitor-research runs Phase 3e + emits research.json in run dir"
```

---

## Self-Review (completed during authoring)

**Spec coverage:** every section of `2026-07-01-plugin-architecture-design.md` maps to a task — `viral_core` (Tasks 1–4), durable run artifacts (Task 3 + 8), niche-discovery integration (Tasks 10–13), light refactor of existing scripts (Tasks 1, 5, 6), report redesign (Tasks 6–9), data contracts (Task 8 `research.json`, Task 13 `discovery.json`, Task 6 `spoken_hook`), error-handling fallbacks (Task 8 fallback summary, Task 7 always-write rule, Task 11 skip-empty-hashtag), testing strategy (fixtures in Tasks 7, 10, 11; unit tests throughout).

**Placeholder scan:** none — every code step contains real code; fixtures are specified with concrete contents.

**Type/name consistency:** `outlier_score` (Task 1) is consumed by Task 12 (`from viral_core.scoring import outlier_score`). `run_actor(token, actor_id, run_input)` (Task 4) is consumed by Tasks 5, 11, 12 with matching call order. `new_run_dir`/`run_artifact` (Task 3) consumed by Task 8. `patterns_path`/`run_dir` params (Task 8) match the template's `patterns` var (Task 9) and the skill's `--patterns` flag (Task 14). `spoken_hook` object shape (Task 6) matches template usage (Task 9).
