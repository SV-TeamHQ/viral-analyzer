# Phase B Profile-First Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a profile-first discovery path to `/niche-discovery` Phase B: a seed creator handle → `apify/instagram-profile-scraper` `relatedProfiles` → a candidate pool of established peers, routed by entry alongside the unchanged hashtag path.

**Architecture:** A new sibling script `scripts/discovery_profiles.py` produces the same `temp/candidate_handles.json` contract the hashtag path writes, so Phase C is untouched. The skill routes by entry (seed handle → profile-first; no seed → existing hashtag path). Thin/empty clusters exit non-zero so the skill can surface choices.

**Tech Stack:** Python 3, `apify-client` (already a dependency), `pytest`, `unittest.mock`. No new dependencies.

## Global Constraints

- **No `git add -A`.** Stage explicit paths in every commit (the standing lesson — `git add -A` swept a 1.7 MB PDF + stray docs on 2026-07-03).
- **Real-shape fixtures only.** The probe-confirmed `relatedProfiles` entry shape is `{username, id, full_name, is_verified, is_private, profile_pic_url}`. Do not invent fields. (Standing lesson from the 2026-07-01 bug arc.)
- **Hashtag path + Phase C untouched.** Do not modify `scripts/discovery_handles.py`, `scripts/discovery_explore_niches.py`, `scripts/discovery_score.py`, or `tests/test_discovery_handles.py`.
- **2-line `sys.path` bootstrap** at the top of any new script: `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))`.
- **`run_actor` signature:** `run_actor(token: str, actor_id: str, run_input: dict) -> list[dict]` (from `viral_core.apify_client`).
- **Profile actor:** `apify/instagram-profile-scraper`, input `{"usernames": [<handle>], "resultsLimit": 1}`.
- **THIN_THRESHOLD = 8.** Seed is always included as a candidate.

---

## File Structure

- **Create** `scripts/discovery_profiles.py` — the profile-first Phase B. One responsibility: seed → `relatedProfiles` → candidate pool in the shared contract. Owns `discover_from_seed`, `main`, and the CLI.
- **Create** `tests/test_discovery_profiles.py` — unit tests, real-shape fixtures, `run_actor` patched.
- **Modify** `tests/test_discovery_integration.py` — add one token-gated live smoke for `relatedProfiles`.
- **Modify** `skills/niche-discovery/SKILL.md` — two-step entry + profile-first routing + thin-cluster surfacing.

---

## Task 1: `discover_from_seed` happy path (ok + thin reasons)

**Files:**
- Create: `scripts/discovery_profiles.py`
- Test: `tests/test_discovery_profiles.py`

**Interfaces:**
- Consumes: `viral_core.apify_client.run_actor(token, actor_id, run_input) -> list[dict]`.
- Produces: `discover_from_seed(seed: str, niche: str, token: str) -> tuple[list[dict], str]` returning `(candidates, reason)` where `reason ∈ {"ok","thin","not_found","private","actor_error"}`. Candidate shape: `{"handle": str, "hashtags": [], "niche": str, "post_count": 0}`. Also module constants `PROFILE_ACTOR = "apify/instagram-profile-scraper"`, `THIN_THRESHOLD = 8`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_discovery_profiles.py`:

```python
import sys, pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.discovery_profiles import discover_from_seed, THIN_THRESHOLD


# Real shape captured by the 2026-07-06 capability probe (memory:
# apify-actor-capabilities-spec-b-probe). Each relatedProfiles entry is
# {username, id, full_name, is_verified, is_private, profile_pic_url}.
def _prof(related):
    return {
        "username": "cristiano",
        "id": "1",
        "followersCount": 671667959,
        "private": False,
        "relatedProfiles": related,
    }


def _rel(username, is_private=False):
    return {"username": username, "id": "x", "full_name": "N",
            "is_verified": False, "is_private": is_private,
            "profile_pic_url": "http://example/p.jpg"}


def test_happy_path_builds_candidates_and_seed(monkeypatch):
    related = [_rel(f"u{i}") for i in range(10)]            # 10 public -> ok
    related.append(_rel("private_one", is_private=True))    # skipped
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "ok"
    handles = [c["handle"] for c in candidates]
    assert "cristiano" in handles          # seed included
    for i in range(10):
        assert f"u{i}" in handles          # public related kept
    assert "private_one" not in handles    # private skipped
    # shared Phase B contract
    assert all(c["hashtags"] == [] for c in candidates)
    assert all(c["niche"] == "fitness" for c in candidates)
    assert all(c["post_count"] == 0 for c in candidates)


def test_thin_reason_when_few_related(monkeypatch):
    related = [_rel("u0"), _rel("u1"), _rel("u2")]   # 3 < THIN_THRESHOLD
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "thin"
    assert len(candidates) == 4   # 3 related + seed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_discovery_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.discovery_profiles'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/discovery_profiles.py`:

```python
"""Phase B (profile-first) — seed creator -> relatedProfiles -> candidate pool.

A second Phase B path alongside discovery_handles.py. The user supplies a
seed creator handle; this scrapes it via apify/instagram-profile-scraper,
reads its relatedProfiles (Instagram's "similar accounts" graph), and emits
the same temp/candidate_handles.json contract Phase C already consumes.
Routed in by the niche-discovery skill when the user gives a seed handle.
"""
import argparse
import os
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor
from viral_core.config_io import load_env

PROFILE_ACTOR = "apify/instagram-profile-scraper"
THIN_THRESHOLD = 8


def discover_from_seed(seed: str, niche: str, token: str) -> tuple[list[dict], str]:
    """Scrape seed, read relatedProfiles, return (candidates, reason).

    Candidate shape matches discovery_handles output:
        {"handle": <username>, "hashtags": [], "niche": <niche>, "post_count": 0}
    The seed is included as a candidate; private related profiles are skipped.
    reason ∈ {"ok","thin","not_found","private","actor_error"}.
    """
    try:
        items = run_actor(token, PROFILE_ACTOR,
                          {"usernames": [seed], "resultsLimit": 1})
    except Exception:
        return [], "actor_error"
    if not items:
        return [], "not_found"
    prof = items[0]
    related = prof.get("relatedProfiles") or []
    candidates = []
    # Seed first (it is a creator in the niche too).
    seed_handle = prof.get("username") or seed
    candidates.append({"handle": seed_handle, "hashtags": [], "niche": niche, "post_count": 0})
    for r in related:
        username = r.get("username")
        if not username:
            continue
        if r.get("is_private"):
            continue
        candidates.append({"handle": username, "hashtags": [], "niche": niche, "post_count": 0})
    is_private_seed = bool(prof.get("private")) and not related
    if is_private_seed:
        return candidates, "private"
    if len(related) < THIN_THRESHOLD:
        return candidates, "thin"
    return candidates, "ok"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_discovery_profiles.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/discovery_profiles.py tests/test_discovery_profiles.py
git commit -m "feat: profile-first discover_from_seed (happy path + thin reason)"
```

---

## Task 2: `discover_from_seed` edge reasons (not_found, private, actor_error, missing username)

**Files:**
- Modify: `scripts/discovery_profiles.py` (no logic change expected — harden/verify only)
- Test: `tests/test_discovery_profiles.py`

**Interfaces:**
- Consumes: Task 1's `discover_from_seed`.
- Produces: unchanged signature; this task only adds test coverage for the remaining reason branches and the missing-username skip.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_discovery_profiles.py`:

```python
def test_not_found_when_actor_returns_empty(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[]):
        candidates, reason = discover_from_seed("ghost", "fitness", "tok")
    assert reason == "not_found"
    assert candidates == []


def test_private_seed_reason(monkeypatch):
    # Seed item exists, is private, and has no relatedProfiles field.
    prof = {"username": "locked", "private": True, "relatedProfiles": []}
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[prof]):
        candidates, reason = discover_from_seed("locked", "fitness", "tok")
    assert reason == "private"


def test_actor_error_reason(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", side_effect=RuntimeError("boom")):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "actor_error"
    assert candidates == []


def test_related_entry_missing_username_is_skipped(monkeypatch):
    related = [_rel(f"u{i}") for i in range(10)]
    related.append({"id": "999", "full_name": "NoHandle", "is_private": False})  # no username
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        candidates, reason = discover_from_seed("cristiano", "fitness", "tok")
    assert reason == "ok"
    assert all(c["handle"] != "999" and c["handle"] for c in candidates)
```

- [ ] **Step 2: Run tests to verify they fail (or pass if Task 1 logic already covers them)**

Run: `python -m pytest tests/test_discovery_profiles.py -v`
Expected: All 6 tests PASS (Task 1's implementation already returns these reasons). If any FAIL, fix the branch in `scripts/discovery_profiles.py:discover_from_seed` until green — do not change the signature.

- [ ] **Step 3: Commit**

```bash
git add tests/test_discovery_profiles.py
git commit -m "test: cover discover_from_seed edge reasons (not_found/private/actor_error/missing-username)"
```

---

## Task 3: `main()` + CLI + non-zero exit on non-`ok` reason

**Files:**
- Modify: `scripts/discovery_profiles.py` (add `main` + `__main__` block)
- Test: `tests/test_discovery_profiles.py`

**Interfaces:**
- Consumes: `viral_core.config_io.load_env(project_dir)`, Task 1's `discover_from_seed`.
- Produces: `main(seed, niche, output_path) -> None`. Writes `temp/candidate_handles.json`, exits `sys.exit(1)` when reason ≠ `"ok"` (after writing the JSON).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_discovery_profiles.py`:

```python
import json


def test_main_writes_candidates_and_exits_zero_on_ok(tmp_path, monkeypatch):
    related = [_rel(f"u{i}") for i in range(10)]
    out = tmp_path / "candidate_handles.json"
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        from scripts.discovery_profiles import main
        main("cristiano", "fitness", str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert any(c["handle"] == "cristiano" for c in data)
    assert all(c["hashtags"] == [] and c["niche"] == "fitness" for c in data)


def test_main_writes_json_then_exits_nonzero_on_thin(tmp_path, monkeypatch):
    related = [_rel("u0"), _rel("u1")]   # thin
    out = tmp_path / "candidate_handles.json"
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    with patch("scripts.discovery_profiles.run_actor", return_value=[_prof(related)]):
        import pytest
        from scripts.discovery_profiles import main
        with pytest.raises(SystemExit) as exc:
            main("cristiano", "fitness", str(out))
        assert exc.value.code == 1
    # JSON still written so the skill can offer "proceed"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 3   # 2 related + seed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_discovery_profiles.py -v`
Expected: FAIL — `ImportError: cannot import name 'main' from 'scripts.discovery_profiles'`.

- [ ] **Step 3: Write the implementation**

Append to `scripts/discovery_profiles.py` (after `discover_from_seed`):

```python
_CAUSE_MESSAGES = {
    "thin":      "THIN CLUSTER: {n} profiles from seed @{seed}",
    "not_found": "SEED NOT FOUND: @{seed}",
    "private":   "SEED PRIVATE: @{seed} has no related profiles",
    "actor_error": "SEED FAILED: @{seed} — actor raised",
}


def main(seed: str, niche: str, output_path: str) -> None:
    project_dir = str(pathlib.Path(output_path).resolve().parent.parent)
    load_env(project_dir)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    candidates, reason = discover_from_seed(seed, niche, token)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2)
    if reason == "ok":
        print(f"Wrote {len(candidates)} candidate handles -> {output_path}")
        return
    n = len(candidates)
    print(_CAUSE_MESSAGES[reason].format(n=n, seed=seed))
    sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Profile-first Phase B (seed -> relatedProfiles)")
    parser.add_argument("--seed", required=True, help="seed creator handle (username)")
    parser.add_argument("--niche", required=True, help="niche label tagging the run")
    parser.add_argument("--output", default="temp/candidate_handles.json")
    args = parser.parse_args()
    main(args.seed, args.niche, args.output)
```

Add `import json` to the imports at the top of the file (after `import argparse`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_discovery_profiles.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/discovery_profiles.py tests/test_discovery_profiles.py
git commit -m "feat: discovery_profiles main() + CLI, non-zero exit on thin/error"
```

---

## Task 4: Token-gated live integration smoke

**Files:**
- Modify: `tests/test_discovery_integration.py`

**Interfaces:**
- Consumes: `apify/instagram-profile-scraper` via `run_actor` (already imported in this test file as `PROFILE_ACTOR`).

- [ ] **Step 1: Write the test**

Append to `tests/test_discovery_integration.py`:

```python
def test_profile_scrape_returns_related_profiles_with_username():
    # Profile-first Phase B depends on relatedProfiles[].username existing.
    profs = run_actor(TOKEN, PROFILE_ACTOR,
                      {"usernames": ["cristiano"], "resultsLimit": 1})
    assert profs, "profile actor returned no items"
    related = profs[0].get("relatedProfiles") or []
    assert related, f"no relatedProfiles — shape drift? keys: {list(profs[0].keys())}"
    assert related[0].get("username"), (
        f"related entry missing username — shape drift? entry: {related[0]}")
```

- [ ] **Step 2: Run the test (skipped without a token; run live to confirm)**

Run (no token): `python -m pytest tests/test_discovery_integration.py -v`
Expected: all tests SKIPPED (`needs APIFY_TOKEN`).

Run (live, to confirm shape): `APIFY_TOKEN=... python -m pytest tests/test_discovery_integration.py::test_profile_scrape_returns_related_profiles_with_username -v`
Expected: PASS (probe already confirmed `relatedProfiles[].username`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_discovery_integration.py
git commit -m "test: live smoke for profile-scraper relatedProfiles[].username"
```

---

## Task 5: Skill wiring — two-step entry + profile-first routing

**Files:**
- Modify: `skills/niche-discovery/SKILL.md`

**Interfaces:**
- Consumes: Task 3's CLI (`scripts/discovery_profiles.py --seed --niche --output`), the existing `scripts/discovery_handles.py` path, the existing Phase C command.

- [ ] **Step 1: Replace the Entry section**

In `skills/niche-discovery/SKILL.md`, replace the `## Entry` section (the block starting `Ask: "Have a niche in mind, or want to browse trending categories?"` through the end of that section) with:

```markdown
## Entry

Ask in two steps.

**Step 1 — niche label** (always; tags the whole run and is written to
`config/competitors.json`):
"What niche are you researching?" (e.g. "home gym", "AI tools", "fitness").

**Step 2 — optional seed creator** (routes Phase B):
"Got a creator in this niche to start from? Paste an Instagram handle
(e.g. `cristiano`), or skip to browse by hashtag."

- **Seed handle given → profile-first Phase B** (bias-free established-peer
  discovery via Instagram's related-accounts graph).
- **Skip → hashtag Phase B** (the existing Phase A → hashtag path).

Capture both: `niche_label` (Step 1) and `seed_handle` (Step 2, may be empty).
```

- [ ] **Step 2: Insert the profile-first Phase B section**

Immediately before the existing `## Phase B — Hashtag -> handle discovery` heading, insert:

```markdown
## Phase B (profile-first) — Seed -> related creators

When the user gave a seed handle in Step 2, run the profile-first path instead
of the hashtag path. One scrape of the seed returns its `relatedProfiles`
(Instagram's "similar accounts" — established peers, not whoever posted in
the last 10 minutes).

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/discovery_profiles.py" \
  --seed "<handle>" \
  --niche "<niche_label>" \
  --output "${CLAUDE_PROJECT_DIR}/temp/candidate_handles.json"
```

The candidate JSON is the same contract the hashtag path writes, so Phase C
consumes it unchanged. Candidates carry no hashtags (Phase C's single-hashtag
weighting from the Phase C hardening handles that).

**If the script exits non-zero** (it prints a cause-named message), the cluster
is thin or the seed was invalid/private. Surface the cause and offer the user
three choices — do not silently switch strategies:
1. **Proceed** with the thin pool (the candidate JSON was still written).
2. **Try a different seed** handle.
3. **Fall back to the hashtag path** for `<niche_label>` (continue to the
   "Phase B — Hashtag" section below).

On a non-thin success, skip straight to Phase C.
```

- [ ] **Step 3: Verify the skill renders coherently**

Run: `python -m pytest -q`
Expected: full suite green (no code change here; confirms nothing else broke).

Read back `skills/niche-discovery/SKILL.md` and confirm: Entry is two-step, the profile-first section sits before the hashtag Phase B section, Phase C is unchanged, and the path-convention variables (`${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PROJECT_DIR}`) are used correctly.

- [ ] **Step 4: Commit**

```bash
git add skills/niche-discovery/SKILL.md
git commit -m "feat(skill): two-step entry + profile-first Phase B routing"
```

---

## Verification (whole plan)

1. **Unit suite:** `python -m pytest tests/test_discovery_profiles.py -v` — all 8 cases green.
2. **Full suite:** `python -m pytest -q` — green; `tests/test_discovery_handles.py` and Phase C tests untouched.
3. **Live smoke (token required):** `APIFY_TOKEN=… python -m pytest tests/test_discovery_integration.py -v` — confirms the real `relatedProfiles[].username` shape.
4. **End-to-end, profile-first:** `/niche-discovery` → niche "fitness" → seed `cristiano` → ~46 candidates → Phase C returns an established-creator shortlist (not the 1K–8K micro-bias) → `config/competitors.json` holds real usernames.
5. **End-to-end, hashtag fallback:** `/niche-discovery` → niche "home gym" → skip seed → the existing path runs unchanged.
6. **Thin-cluster negative:** supply a private/obscure seed → skill surfaces the cause and offers the three choices (no silent switch, no empty result).
