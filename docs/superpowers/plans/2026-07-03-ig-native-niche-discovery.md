# IG-Native Niche Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/niche-discovery` Phase A's external trend sources (pytrends + Reddit) with a single IG-native operation on the analytics actor's related-hashtag volumes, and drop the pytrends/praw dependencies.

**Architecture:** A new `discovery_explore_niches.py` wraps the existing `discovery_hashtag_research.research_hashtags()` and reshapes its output into the unchanged `{niche, trend_score, sources}` contract. Two entry modes (seeded keyword/hashtag, unseeded category) both resolve to a seed hashtag and call the same function. The skill is rewired to call the new script; the old `discovery_pull_trends.py` + pytrends/praw deps are removed.

**Tech Stack:** Python 3.10+ (modern type hints), apify-client, viral_core (`apify_client.run_actor`, `config_io.load_env`), pytest, Claude Code plugin runtime (`${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PROJECT_DIR}`).

## Global Constraints

- **Python 3.10+** with modern union type hints (`str | None`, not `Optional`).
- **`viral_core` bootstrap** — scripts importing viral_core begin with `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))`.
- **`.env` loading** — derive project dir as `parent.parent` of the `--output` path (output is `<root>/temp/X.json`), then `viral_core.config_io.load_env(project_dir)` before reading `APIFY_TOKEN`. Mirrors `scrape_instagram.py`.
- **Ground truth from scraped data only.** No agent-invented metrics.
- **TDD:** every code task writes the failing test first, runs it red, implements, runs it green, then commits.
- **Real-shape fixtures.** Test fixtures must mirror the actual analytics-actor output (`related[].hash` / `.info`), not invented shapes — the lesson from the 2026-07-01 bug arc.
- **Backward compatibility:** the `temp/niches.json` output contract (`{niche, trend_score, sources}`) is unchanged so `discovery_handles.py` (Phase B) needs no changes.
- **Spec of record:** `docs/superpowers/specs/2026-07-03-ig-native-niche-discovery-design.md`.
- **Line endings:** repo normalizes LF↔CRLF on Windows; commit warnings are expected and ignored.

---

## File Structure

**Create:**
- `scripts/discovery_explore_niches.py` — IG-native Phase A (wraps `research_hashtags`, reshapes to niche contract, 17-category map, CLI).
- `tests/test_discovery_explore_niches.py` — unit tests (mocked `research_hashtags`, real output shape).

**Modify:**
- `skills/niche-discovery/SKILL.md` — rewire Phase A to the new script; two-mode entry; drop pytrends/praw from first-run setup.

**Delete:**
- `scripts/discovery_pull_trends.py`
- `tests/test_discovery_pull_trends.py`

**Dependency removals:**
- `requirements.txt` — drop `pytrends>=4.9.0` and `praw>=7.7.0`.
- `.env.example` — remove the Reddit credential block (Phase A no longer uses Reddit).

**Reuse unchanged:** `scripts/discovery_hashtag_research.py` (`research_hashtags`, `parse_volume`), `scripts/discovery_handles.py` (Phase B, incl. `--hashtags` override and `hashtags_for_niche`), `tests/test_discovery_integration.py` (already covers the analytics actor).

---

## Task 1: `discovery_explore_niches.py` (the IG-native Phase A)

**Files:**
- Create: `scripts/discovery_explore_niches.py`
- Test: `tests/test_discovery_explore_niches.py`

**Interfaces:**
- Consumes: `discovery_hashtag_research.research_hashtags(seed_tag: str, token: str, top_n: int = 10) -> list[dict]` returning `[{"hashtag": str, "volume": int, "source": str}]`; `viral_core.config_io.load_env(project_dir: str) -> None`.
- Produces: `explore_niches(seed_hashtag: str, token: str, top_n: int = 10) -> list[dict]` returning `[{"niche": str, "trend_score": int, "sources": ["instagram"]}]`; `_resolve_seed(seed: str | None, category: str | None) -> str | None`; the `CATEGORIES` dict; CLI `--seed` / `--category` / `--top-n` / `--output`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discovery_explore_niches.py`:
```python
import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.discovery_explore_niches import explore_niches, _resolve_seed, CATEGORIES


def test_explore_niches_reshapes_to_contract(monkeypatch):
    # real research_hashtags output shape: [{hashtag, volume, source}]
    ranked = [
        {"hashtag": "#homegym", "volume": 7600000, "source": "related"},
        {"hashtag": "#homeworkout", "volume": 1400000, "source": "related"},
    ]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=ranked):
        out = explore_niches("#fitness", "tok", top_n=10)
    assert out == [
        {"niche": "homegym", "trend_score": 7600000, "sources": ["instagram"]},
        {"niche": "homeworkout", "trend_score": 1400000, "sources": ["instagram"]},
    ]

def test_explore_niches_preserves_volume_order(monkeypatch):
    # research_hashtags already ranks by volume desc; explore_niches must preserve order
    ranked = [{"hashtag": "#a", "volume": 100, "source": "related"},
              {"hashtag": "#b", "volume": 50, "source": "related"}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=ranked):
        out = explore_niches("#x", "tok")
    assert [n["trend_score"] for n in out] == [100, 50]

def test_explore_niches_top_n_truncation(monkeypatch):
    ranked = [{"hashtag": f"#t{i}", "volume": i, "source": "related"} for i in range(20)]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=ranked):
        out = explore_niches("#x", "tok", top_n=5)
    assert len(out) == 5

def test_explore_niches_empty_on_failure(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_explore_niches.research_hashtags", return_value=[]):
        assert explore_niches("#dead", "tok") == []

def test_resolve_seed_from_seed():
    assert _resolve_seed("homegym", None) == "#homegym"
    assert _resolve_seed("#homegym", None) == "#homegym"

def test_resolve_seed_from_category():
    assert _resolve_seed(None, "Fitness") == "#fitness"
    assert _resolve_seed(None, "AI") == "#ai"
    assert _resolve_seed(None, "health & wellness") == "#wellness"
    assert _resolve_seed(None, "apps") == "#apps"

def test_resolve_seed_unknown_category_raises():
    try:
        _resolve_seed(None, "nonexistent")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)

def test_resolve_seed_neither_returns_none():
    assert _resolve_seed(None, None) is None

def test_categories_has_17_entries():
    assert len(CATEGORIES) == 17
    for key in ("ai", "beauty", "apps", "fitness", "tech"):
        assert key in CATEGORIES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_discovery_explore_niches.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.discovery_explore_niches'`.

- [ ] **Step 3: Implement `scripts/discovery_explore_niches.py`**

```python
"""Phase A — IG-native niche discovery.

Surfaces niche candidates from INSIDE Instagram by reading the analytics
actor's related hashtags (with real IG volume) for a seed hashtag. Replaces
the old pytrends/Reddit external trend sources. The niche the user picks IS
an IG hashtag, so there is no topic->hashtag translation step.

Two entry modes, both resolving to a seed hashtag:
  - seeded:   --seed <niche/keyword/hashtag>  (mapped via hashtags_for_niche)
  - unseeded: --category <name>               (mapped via the CATEGORIES list)

Output (temp/niches.json) matches the existing {niche, trend_score, sources}
contract so Phase B (discovery_handles.py) is unchanged.
"""
import argparse
import json
import os
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from scripts.discovery_hashtag_research import research_hashtags
except ModuleNotFoundError:
    from discovery_hashtag_research import research_hashtags
from viral_core.config_io import load_env

# 17 broad category -> mega-hashtag seeds for unseeded discovery.
CATEGORIES = {
    "fitness": "#fitness", "tech": "#tech", "food": "#food",
    "finance": "#personalfinance", "beauty": "#beauty", "gaming": "#gaming",
    "travel": "#travel", "business": "#entrepreneur",
    "ai": "#ai", "fashion": "#fashion", "health & wellness": "#wellness",
    "photography": "#photography", "real estate": "#realestate",
    "pets": "#pets", "music": "#music", "cars": "#cars", "apps": "#apps",
}


def _resolve_seed(seed: str | None, category: str | None) -> str | None:
    """Resolve a seed hashtag from --seed (keyword/hashtag) or --category."""
    if seed:
        return seed if seed.startswith("#") else f"#{seed}"
    if category:
        key = category.strip().lower()
        if key not in CATEGORIES:
            raise ValueError(
                f"unknown category {category!r}; choose from: "
                f"{', '.join(sorted(CATEGORIES))}"
            )
        return CATEGORIES[key]
    return None


def explore_niches(seed_hashtag: str, token: str, top_n: int = 10) -> list[dict]:
    """IG-native Phase A. Calls the analytics actor (via research_hashtags) on
    a seed hashtag and returns its related hashtags as niche candidates.

    `niche` is the related hashtag token, #-stripped (e.g. 'homegym'). Real IG
    related hashtags are concatenated tokens with no separators, so no
    word-splitting is attempted; the token is re-prefixed with '#' at Phase B
    handoff (lossless round-trip).
    """
    ranked = research_hashtags(seed_hashtag, token, top_n=top_n)
    return [
        {
            "niche": h["hashtag"].lstrip("#"),
            "trend_score": h["volume"],
            "sources": ["instagram"],
        }
        for h in ranked
    ]


def main(seed: str | None = None, category: str | None = None,
         output_path: str = "temp/niches.json", top_n: int = 10) -> None:
    project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")

    seed_hashtag = _resolve_seed(seed, category)
    if not seed_hashtag:
        print("ERR: provide --seed <hashtag or niche> or --category <name>.")
        return

    niches = explore_niches(seed_hashtag, token, top_n=top_n)
    if not niches:
        print(f"IG niche discovery unavailable for {seed_hashtag}. "
              f"Try a different seed/category or check APIFY_TOKEN.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(niches, f, indent=2)
    print(f"Wrote {len(niches)} niches -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IG-native niche discovery (Phase A)")
    parser.add_argument("--seed", default=None,
                        help="seed hashtag, niche, or keyword (seeded mode)")
    parser.add_argument("--category", default=None,
                        help="broad category name for unseeded mode "
                             "(e.g. fitness, ai, apps)")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", default="temp/niches.json")
    args = parser.parse_args()
    main(seed=args.seed, category=args.category,
         output_path=args.output, top_n=args.top_n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_discovery_explore_niches.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: all green (existing tests + the 9 new ones).

- [ ] **Step 6: Commit**

```bash
git add scripts/discovery_explore_niches.py tests/test_discovery_explore_niches.py
git commit -m "feat: IG-native Phase A (discovery_explore_niches) wrapping analytics actor"
```

---

## Task 2: Rewire the niche-discovery skill to the IG-native Phase A

**Files:**
- Modify: `skills/niche-discovery/SKILL.md`

**Interfaces:**
- Consumes: Task 1's `discovery_explore_niches.py` CLI (`--seed` / `--category` / `--top-n` / `--output`).
- Produces: a skill whose Phase A calls `discovery_explore_niches.py` (seeded or unseeded), presents volume-ranked IG hashtags as niches, supports optional drill-down, and hands the picked hashtags to Phase B via `--hashtags`.

- [ ] **Step 1: Read the current skill file**

Run: read `skills/niche-discovery/SKILL.md` to locate the exact text of the `## Entry`, `## Phase A — Trend signals`, `## First-run setup`, and `## Phase B` sections. (The file was edited in a prior task; do not assume old wording — read it.)

- [ ] **Step 2: Replace the `## Entry` section**

Replace the existing `## Entry` section (the fast/discovery-path text) with:

```markdown
## Entry

Ask: "Have a niche in mind, or want to browse trending categories?"

- **Seeded** — user types a niche, keyword, or hashtag (e.g. "home gym", "#fitness",
  "AI tools"). Resolve it to a seed hashtag via `hashtags_for_niche()` and pass it
  to Phase A as `--seed`.
- **Unseeded** — user wants options. Present the 17 broad categories (Fitness, Tech,
  Food, Finance, Beauty, Gaming, Travel, Business, AI, Fashion, Health & Wellness,
  Photography, Real Estate, Pets, Music, Cars, Apps); the picked category becomes
  Phase A's `--category`.
```

- [ ] **Step 3: Replace the `## Phase A` section**

Replace the entire `## Phase A — Trend signals` section (the `discovery_pull_trends.py` call and surrounding text) with:

```markdown
## Phase A — IG-native niche discovery

One analytics-actor call on a seed hashtag returns its related hashtags with
real IG volume — those related hashtags *are* the niche candidates. The niche
you pick is already an IG hashtag, so there is no topic→hashtag translation.

Seeded:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_explore_niches.py" \
  --seed "#homegym" \
  --output "${CLAUDE_PROJECT_DIR}/temp/niches.json"
```

Unseeded (pick a category):
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_explore_niches.py" \
  --category fitness \
  --output "${CLAUDE_PROJECT_DIR}/temp/niches.json"
```

Present the volume-ranked niches from `temp/niches.json` (e.g. `homegym 7.6m ·
homeworkout 1.4m · garagegym 580k`). User picks 1–3.

**Optional drill-down:** if the top-level niches feel too broad, re-run Phase A
with one of the picks as the seed (`--seed "#homegym"`) to surface finer
sub-niches before Phase B.

If Phase A returns nothing (analytics actor failed / rate-limited / no token),
fall back to the fast path: the user types a niche → `hashtags_for_niche()`
offline → straight to Phase B. Discovery never hard-fails.
```

- [ ] **Step 4: Update the Phase B command to use the picked niches via `--hashtags`**

In the `## Phase B — Hashtag -> handle discovery` section, ensure the scrape step passes the user-confirmed hashtags (the picked niches, `#`-prefixed) through `--hashtags`. If the section already documents `--hashtags` (it does, from a prior task), just confirm the prose says the picked Phase A niches feed in here. If not, set the scrape command to:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_handles.py" \
  --hashtags "#homegym,#homeworkout" \
  --output "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json"
```

(The picked niches are hashtag tokens; prepend `#` when building `--hashtags`.)

- [ ] **Step 5: Drop pytrends/praw from First-run setup**

In `## First-run setup`, change the Python-deps check from
`python -c "import requests, apify_client, pytrends"` to
`python -c "import requests, apify_client"` (Phase A no longer uses pytrends or
praw). `APIFY_TOKEN` is now the only external credential Phase A needs. Remove
any Reddit-specific bullet (the `REDDIT_CLIENT_ID`/`SECRET` note) from First-run
setup.

- [ ] **Step 6: Sanity-check the plugin imports and tests**

Run: `python -c "import sys; sys.path.insert(0,'.'); import viral_core; print('ok')"`
Expected: prints `ok`.
Run: `python -m pytest -q`
Expected: all green (docs-only skill change; no test impact).

- [ ] **Step 7: Commit**

```bash
git add skills/niche-discovery/SKILL.md
git commit -m "feat: rewire niche-discovery Phase A to IG-native explore_niches"
```

---

## Task 3: Remove `discovery_pull_trends.py` + pytrends/praw dependencies

**Files:**
- Delete: `scripts/discovery_pull_trends.py`
- Delete: `tests/test_discovery_pull_trends.py`
- Modify: `requirements.txt` (remove `pytrends>=4.9.0` and `praw>=7.7.0`)
- Modify: `.env.example` (remove the Reddit credential block)

**Interfaces:**
- Consumes: Task 2 (the skill no longer references `discovery_pull_trends.py`, so it is now dead code and safe to delete).

- [ ] **Step 1: Delete the old Phase A script and its tests**

```bash
git rm scripts/discovery_pull_trends.py tests/test_discovery_pull_trends.py
```

- [ ] **Step 2: Remove pytrends + praw from requirements.txt**

Edit `requirements.txt` to delete these two lines:
```
pytrends>=4.9.0
praw>=7.7.0
```
The file should now be exactly:
```
requests>=2.31.0
openai-whisper>=20231117
apify-client>=1.7.0
python-dotenv>=1.0.0
jinja2>=3.1.0
Pillow>=10.0.0
pytest>=7.0.0
playwright>=1.40.0
```

- [ ] **Step 3: Remove the Reddit credential block from .env.example**

Read `.env.example` and delete the Reddit block (the comment line plus
`REDDIT_CLIENT_ID=` and `REDDIT_CLIENT_SECRET=`). Leave `APIFY_TOKEN=` intact.

- [ ] **Step 4: Confirm nothing imports pytrends or praw**

Run: `grep -rn "pytrends\|praw\|discovery_pull_trends" scripts/ skills/ tests/ commands/ agents/ 2>/dev/null`
Expected: no output (no remaining references). If anything appears, remove/fix it before continuing.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all green (the removed test file is gone; no other test referenced it).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove pytrends/praw and discovery_pull_trends (Phase A is IG-native now)"
```

---

## Self-Review (completed during authoring)

**Spec coverage:**
- New `discovery_explore_niches.py` with `explore_niches`, `_resolve_seed`, 17-category `CATEGORIES`, CLI → Task 1.
- Two entry modes (seeded/unseeded), drill-down, Phase B `--hashtags` handoff, fast-path fallback, first-run setup → Task 2.
- Remove `discovery_pull_trends.py` + pytrends/praw + Reddit creds → Task 3.
- Unchanged `temp/niches.json` contract → enforced by Task 1's `test_explore_niches_reshapes_to_contract` (asserts exact `{niche, trend_score, sources}` shape).
- Real-shape fixtures → Task 1 mocks `research_hashtags` with the real `[{hashtag, volume, source}]` shape it produces.
- Error handling (empty-on-failure, unknown-category, missing-token) → Task 1 tests + `main()` messages.
- Out-of-scope (trending scraper) correctly excluded; no task adds it.

**Placeholder scan:** none. Every code step contains complete code; the skill steps contain the full replacement markdown; removal steps name exact files/lines.

**Type/name consistency:** `explore_niches(seed_hashtag, token, top_n)` matches across Task 1's tests and implementation; `_resolve_seed(seed, category)` matches; `CATEGORIES` keys (`"ai"`, `"apps"`, `"health & wellness"`) match the test assertions and the skill's category list; the contract field names (`niche`, `trend_score`, `sources`) match `discovery_handles.py`'s `n["niche"]` consumer (verified — unchanged). `research_hashtags` signature matches the existing `discovery_hashtag_research.py`.
