# Phase B Profile-First Discovery — Design Spec

**Date:** 2026-07-06
**Status:** Approved (pending user review of written spec)
**Scope:** Add a **profile-first** discovery path to `/niche-discovery` Phase B as a second entry-routed mode alongside the existing hashtag path. Profile-first asks Instagram "who is similar to this creator?" via the seed's `relatedProfiles`, surfacing established peers instead of whoever posted to a hashtag in the last few minutes. Phase A and Phase C are unchanged.

**Out of scope:** changing Phase C scoring (already hardened in Spec A, committed `ae20446`), changing the competitor-research pipeline, multi-seed clustering (single seed in v1; YAGNI), auto-deriving the niche label from IG's `businessCategoryName` (the user supplies the niche label at entry).

---

## Background — why a second path

The 2026-07-06 discovery-quality-report traced the micro-account bias to Phase B scraping the hashtag **recent feed** (whoever posted in the last few minutes → overwhelmingly small accounts). Spec A hardened Phase C scoring so the *current* output is honest and pickable regardless of pool quality. But the pool itself can still be micro-biased.

A live capability probe on 2026-07-06 (memory: `apify-actor-capabilities-spec-b-probe`) confirmed two things that make a better pool reachable:

1. **`apify/instagram-profile-scraper` populates `relatedProfiles`.** Scraping one creator (`cristiano`) returned **46 related accounts**, each carrying `{username, id, full_name, is_verified, is_private, profile_pic_url}` — **username present, no second lookup needed.** These are Instagram's own "similar accounts" — established peers of the seed.
2. **`apify/instagram-hashtag-scraper` has no top-posts toggle.** Its posts are recent-feed only (probe post[0] was 12 minutes old, `likesCount: 0`). So there is no "top-posts actor" fix; the bias-free primitive is **profile-first**.

Profile-first and hashtag discovery answer different questions and are both worth keeping:

| User has... | Path | Question answered |
|---|---|---|
| A creator they admire in the niche | **Profile-first** (new) | "Who else is like them?" → established peers |
| Only a niche/topic in mind | **Hashtag** (existing) | "Who's active in this niche?" → broad net |

So Spec B is **additive**: a second Phase B path, routed by entry. The proven hashtag path stays byte-for-byte intact (zero regression risk).

---

## Key decisions

- **Dual-mode, entry-routed.** The skill's entry captures a niche label, then asks for an optional seed creator handle. Seed present → profile-first; absent → existing hashtag path. The user never picks a "mode" explicitly — what they type routes implicitly.
- **New script `discovery_profiles.py`** (Option A from brainstorming), not a `--mode` flag on `discovery_handles.py`. One responsibility per script; the hashtag path is untouched.
- **Candidate pool = seed + all non-private `relatedProfiles`.** No quality filtering in Phase B — Phase C's existing gates (drop <10K followers, drop <100 abs engagement, slim-reveal, language/anomaly flags from Spec A) are the single source of truth for quality.
- **Shared output contract.** Both Phase B paths write the identical `temp/candidate_handles.json` shape Phase C already consumes. Profile-first fills `handle` = `relatedProfiles[].username` (already a username), `hashtags` = `[]`, `niche` = the entry niche label. The seed is included as a candidate.
- **Thin-cluster = surface, don't auto-switch.** If `relatedProfiles` returns `< THIN_THRESHOLD (8)`, or the seed is invalid/private, `discovery_profiles.py` exits non-zero with a named cause and the skill offers the user three choices (proceed / different seed / hashtag fallback). No silent strategy switch — mirrors Spec A's slim-reveal philosophy.
- **Single seed in v1.** No multi-seed merging. The user's choice of seed implicitly sets the follower tier (seed on a 500K creator → 100K–2M peers).

---

## Architecture

```
/niche-discovery entry
   Step 1: "What niche?"            ──► niche label (tags the whole run)
   Step 2: "Got a creator in this
            niche? Handle or skip."
        seed handle ────────────────────── no seed
              │                                │
       Phase B-profile                   Phase B-hashtag (unchanged)
     discovery_profiles.py             discovery_handles.py
     seed → relatedProfiles            Phase A (discovery_explore_niches.py)
              │                        → hashtag scrape (api-ninja)
              │                                │
              └────► temp/candidate_handles.json ◄─────┘
                     (identical contract either way)
                              │
                     Phase C (unchanged)
                  discovery_score.py
```

No change to Phase A, Phase C, the candidate JSON contract downstream of `temp/candidate_handles.json`, `config/competitors.json`, or the competitor-research pipeline.

---

## Components

### New: `scripts/discovery_profiles.py`

Single responsibility: turn one seed creator into a candidate pool via `relatedProfiles`.

**Signature:**

```python
PROFILE_ACTOR = "apify/instagram-profile-scraper"
THIN_THRESHOLD = 8

def discover_from_seed(seed: str, niche: str, token: str
                       ) -> tuple[list[dict], str]:
    """Scrape the seed, read relatedProfiles, return (candidates, reason).

    Candidates use the shared Phase B contract:
        {"handle": <username>, "hashtags": [], "niche": <niche>, "post_count": 0}
    The seed is included as a candidate. Private related profiles are skipped
    (no visible posts to analyze downstream).

    reason is one of: "ok" | "thin" | "not_found" | "private" | "actor_error".
    "thin" covers a public seed whose relatedProfiles count < THIN_THRESHOLD
    (including empty). The caller uses reason to name the cause when surfacing
    to the user.
    """
```

Behavior:
1. `run_actor(token, PROFILE_ACTOR, {"usernames": [seed], "resultsLimit": 1})`. On exception → return `([], "actor_error")`.
2. If no item returned → return `([], "not_found")`.
3. Read `prof.get("relatedProfiles") or []`. If the seed itself is private, this field is typically absent.
4. Build candidates: the seed itself (handle = `prof.get("username") or seed`) plus each related entry whose `username` is present and `is_private` is false. Each candidate: `{"handle": username, "hashtags": [], "niche": niche, "post_count": 0}`.
5. reason = `"private"` if the seed item exists but `relatedProfiles` is absent/empty AND the profile `private` flag is true; else `"thin"` if `len(relatedProfiles) < THIN_THRESHOLD`; else `"ok"`.
6. Return `(candidates, reason)`.

`main(seed, niche, output_path)`:
- `load_env(parent.parent of output_path)` then read `APIFY_TOKEN` (same pattern as `discovery_handles.py:100-106`).
- Call `discover_from_seed`, write candidates to `output_path`.
- **If `reason != "ok"`: print a clear cause-named message** (`THIN CLUSTER: N profiles from seed @<seed>` / `SEED NOT FOUND: @<seed>` / `SEED PRIVATE: @<seed> has no related profiles` / `SEED FAILED: @<seed> — <error>`) **and `sys.exit(1)`** so the skill can detect the signal and offer choices. The candidate JSON is still written first (so "proceed" is a no-op for the skill).

CLI:
```
python discovery_profiles.py --seed <handle> --niche "<label>" --output temp/candidate_handles.json
```
2-line `sys.path` bootstrap, identical to the sibling scripts.

### Modified: `skills/niche-discovery/SKILL.md`

- **Entry** becomes two-step. Replace the current single "Have a niche in mind, or want to browse trending categories?" with:
  1. "What niche are you researching?" (e.g. home gym, AI tools) — captures the niche label used by both paths and written to `competitors.json`.
  2. "Got a creator in this niche to start from? Paste an Instagram handle (e.g. `cristiano`), or skip to browse by hashtag."
- **Routing:**
  - Seed present → run `discovery_profiles.py --seed <handle> --niche <label> --output temp/candidate_handles.json`.
    - If it exits non-zero (thin cluster / seed not found / seed private): surface the cause and offer: *proceed with the thin pool* (the JSON was still written), *try a different seed*, or *fall back to the hashtag path for <niche>*.
    - On success → straight to Phase C.
  - No seed → the **existing** path verbatim (Phase A `discovery_explore_niches.py` → confirm hashtags → `discovery_handles.py`).
- **Phase C section:** unchanged. Note one line: profile-first candidates carry no hashtags, which Phase C handles via its single-hashtag weighting (Spec A 4c).

### Untouched

`scripts/discovery_handles.py`, `scripts/discovery_explore_niches.py`, `scripts/discovery_score.py`, `config/hashtag_seeds.json`, `config/competitors.json` schema, `requirements.txt` (no new dependency — `apify-client` already present), the competitor-research pipeline.

---

## Data contract

`temp/candidate_handles.json` — **unchanged shape**, produced by either Phase B path:

```json
[
  {"handle": "vitinha", "hashtags": [], "niche": "fitness", "post_count": 0},
  {"handle": "cristiano", "hashtags": [], "niche": "fitness", "post_count": 0}
]
```

Profile-first always emits `hashtags: []`. Phase C already tolerates this: Spec A's 4c sets the cross-hashtag weight to 0 when `max_tags < 2`, so an empty-hashtag pool scores on engagement + outlier alone. No Phase C change.

`config/competitors.json` and the provenance record (`output/runs/{ts}/discovery.json`) are unchanged — Phase C writes them as before; the niche label flows through from entry.

---

## Error handling

- **Thin cluster (`relatedProfiles` count < 8, including empty):** `discovery_profiles.py` writes the candidate JSON (so "proceed" is viable) but exits non-zero with `THIN CLUSTER: N profiles from seed @<seed>`. The skill surfaces the count and offers: proceed / different seed / hashtag fallback.
- **Seed not found** (scraper returns no item): same non-zero surface-and-offer, cause = "seed @x not found".
- **Seed is private** (item returned but no `relatedProfiles` field): same, cause = "seed @x is private — no related profiles available".
- **`relatedProfiles` entry missing `username`:** that entry is skipped; the rest are kept. Defensive against actor field drift (probe confirmed `username` present, but actors drift — the standing lesson).
- **No `APIFY_TOKEN` / actor exception:** `RuntimeError("APIFY_TOKEN not set")` or a visible `WARN: seed @x failed: <e>` — same pattern as `discovery_handles.py:88-90`. Discovery never hard-fails silently; the skill can always offer the hashtag fallback.

---

## Testing

TDD throughout, **real-shape fixtures from the probe** (the standing lesson from the 2026-07-01 bug arc: never invented shapes). New file `tests/test_discovery_profiles.py`:

- **Happy path** — fixture mirroring the probe's real `relatedProfiles` (`[{username, id, full_name, is_verified, is_private, profile_pic_url}, …]`, mix of public/private). Patch `run_actor`. Assert `discover_from_seed` returns candidates with `handle == username`, `hashtags == []`, `niche == <label>`, the seed included, private entries skipped, and `reason == "ok"` when ≥8 related.
- **Thin cluster** — fixture with 3 related profiles → `reason == "thin"`; CLI `main()` writes the JSON and exits non-zero (assert `SystemExit`/`sys.exit(1)`).
- **Empty `relatedProfiles`** — seed profile with no `relatedProfiles` key (public seed) → returns `[seed]`, `reason == "thin"`.
- **Seed not found** — `run_actor` returns `[]` → returns `[]`, `reason == "not_found"`.
- **Seed private** — item returned with `private: true` and no `relatedProfiles` → `reason == "private"`.
- **Actor error** — `run_actor` raises → `([], "actor_error")`.
- **Missing `username` on a related entry** — that entry skipped, others kept.
- **CLI smoke** — `--seed cristiano --niche fitness` (patched `run_actor`) writes candidate JSON matching the shared contract; assert the fixture output is consumable by Phase C (feed it to the candidate-parser path in `discovery_score.py` and confirm empty `hashtags` does not raise).
- **Live token-gated integration test** — extend `tests/test_discovery_integration.py` (already skip-gated on `APIFY_TOKEN`) with ONE real profile scrape on a reliably-public account (`cristiano`), asserting `relatedProfiles[].username` exists. Catches future shape drift.

`tests/test_discovery_handles.py` is **untouched** — it remains the regression guard for the unchanged hashtag path.

---

## Verification

1. **Unit suite green:** `python -m pytest tests/test_discovery_profiles.py -v` — real-shape fixtures, all cases above pass.
2. **Full suite:** `python -m pytest -q` — no regressions (hashtag-path tests unchanged, Phase C tests unchanged).
3. **Live integration smoke (token required):** `APIFY_TOKEN=… python -m pytest tests/test_discovery_integration.py -v` — confirms the real `relatedProfiles` shape today.
4. **End-to-end manual run**, profile-first: `/niche-discovery` → niche "fitness" → seed `cristiano` → confirm Phase B-profile writes ~45+ candidates with real usernames → Phase C returns an established-creator shortlist (not the 1K–8K micro-bias seen in the 2026-07-06 report) → `config/competitors.json` contains real usernames.
5. **End-to-end manual run**, hashtag fallback: `/niche-discovery` → niche "home gym" → skip seed → confirm the existing hashtag path runs unchanged and produces the same shape it did before Spec B.
6. **Thin-cluster negative check:** supply a private/obscure seed → confirm the skill surfaces the cause and offers the three choices (not a silent switch or empty result).
