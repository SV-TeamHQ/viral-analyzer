# Niche Discovery Run — Issues & Recommended Solutions

**Date:** 2026-07-01  
**Run:** google vids niche, Phase A → B → C  
**Status:** Completed with low-quality output — not production-ready

---

## Executive Summary

The first end-to-end run of the niche-discovery pipeline surfaced five distinct failure categories spanning all three phases. The core insight: **Instagram's hashtag pages return stripped GraphQL data (no usernames), and `#googlevids` is too small a hashtag to find established creators**. The scoring worked correctly once field-name mismatches were fixed, but the candidate pool was off-target. Fixes are straightforward but require both code changes and a rethink of the trend signal approach.

---

## Phase A — Trend Discovery Issues

### Issue 1: Empty seed defaults to "technology" — returns irrelevant results

**What happened:**  
Running `discovery_pull_trends.py` with no seed (`--seed ""`) defaulted internally to `"technology"` as the pytrends keyword. This returned rising queries like "texas roadhouse table service technology" and "ninja foodi air fryer" — completely unrelated to Instagram content niches.

**Root cause:**  
`pull_trends.py` line 19: `pytrends.build_payload([seed or "technology"], ...)` — the fallback is too broad.

**Fix:**  
- If no seed is provided, either refuse (require seed) or default to a curated list of broad social media categories: `["AI tools", "personal finance", "fitness", "entrepreneurship"]`
- Better: present the user with 4-5 category options before running the script at all

---

### Issue 2: Google Trends returns product names, not Instagram niches

**What happened:**  
Even with the correct seed (`"AI video"`), pytrends returned product/tool names like "hailuo ai", "seedance", "kling" rather than content niches like "AI video creation tutorials" or "screen recording workflows." These are useful signals but can't be directly mapped to Instagram hashtags.

**Root cause:**  
pytrends "rising related queries" returns what people are searching for, not what creators are posting about. The two are correlated but not identical.

**Recommended alternative approaches:**

| Source | Signal type | Quality | Setup cost |
|--------|------------|---------|-----------|
| pytrends rising queries | Search intent | Medium | Free, no key |
| Reddit hot posts (PRAW) | Community discussion | High | Free OAuth app |
| YouTube trending (yt-dlp metadata) | Creator content | High | Free |
| RapidAPI TikTok trending hashtags | Platform-native | Very high | Paid (~$10/mo) |
| SparkToro audience research | Audience behavior | Very high | Paid (~$150/mo) |
| Exploding Topics API | Rising trends | High | Paid (~$49/mo) |

**Near-term fix (free):**  
Add Reddit PRAW support (already in `requirements.txt`, not yet wired in). Reddit discussion titles from r/Entrepreneur, r/ChatGPT, r/SideProject give much better niche signals than Google Trends product queries.

**Medium-term fix:**  
Add a YouTube trending scraper — search YouTube for the seed term, extract video titles and channel names. The channels that appear are the actual creators; their topics are the actual niches. This completely avoids the Instagram-API cold-start problem because YouTube is open.

---

### Issue 3: No Reddit credentials — signal is halved

**What happened:**  
`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are not set in `.env`, so the Reddit fallback in `pull_trends.py` silently returns an empty list. The script ran on Google Trends only with no warning to the user.

**Fix:**  
- Log a visible warning when Reddit is skipped: `"WARN: Reddit signal unavailable (no REDDIT_CLIENT_ID). Add to .env for better niche signals."`
- Add `REDDIT_CLIENT_ID=` and `REDDIT_CLIENT_SECRET=` placeholder entries to `.env.example`

**Setup:** Create a free Reddit app at reddit.com/prefs/apps → "script" type. Takes 2 minutes.

---

## Phase B — Hashtag → Handle Discovery Issues

### Issue 4: `api-ninja/instagram-scraper` uses wrong input key for hashtags

**What happened:**  
`discovery_handles.py` passed `{"hashtags": ["#googlevids"], "resultsLimit": 50}` to the actor. The actor rejected this with "No input provided" — it requires `{"urls": ["https://www.instagram.com/explore/tags/googlevids/"], "resultsLimit": 50}`.

**Root cause:**  
The script was written assuming a `hashtags` parameter that doesn't exist on this actor. The correct approach is to construct the explore-tags URL.

**Fix applied (in this run):** Changed to `"urls"` with full Instagram explore URL. ✅

---

### Issue 5: Hashtag page returns GraphQL "lite" data — no username, only `owner.id`

**What happened:**  
Instagram's hashtag explore page returns a stripped GraphQL response where each post only has `owner: {"id": "72090083532"}`. There is no `username` field. The original `build_frequency()` looked for `user.username` and found nothing → 0 handles extracted.

**Root cause:**  
`api-ninja/instagram-scraper` uses two different API backends depending on what it's scraping:
- **Profile pages** → Instagram private API → full data including `user.username`
- **Hashtag explore pages** → Public GraphQL API → lite data, `owner.id` only

This is a fundamental Instagram platform difference, not an actor bug.

**Fix applied (in this run):** Store `owner.id` as handle; pass it to `apify/instagram-profile-scraper` in Phase C, which resolves IDs to usernames. ✅

**Alternative fix (more robust):**  
Switch Phase B to use `apify/instagram-hashtag-scraper` (a different Apify actor) — check if it returns full user data. Or use a two-step approach: scrape hashtag → get shortcodes → batch-scrape post details via a post scraper that returns full user objects.

---

### Issue 6: Auto-generated hashtags are too generic or too niche

**What happened:**  
`hashtags_for_niche("google vids")` generated: `#googlevids`, `#googlevidstips`, `#google`, `#vids`.

- `#googlevids` → 20 posts, mostly small German productivity bloggers
- `#googlevidstips` → 0 posts (hashtag doesn't exist)
- `#google` → 20 posts, completely off-topic (Google brand page followers, random)
- `#vids` → 20 posts, random viral video accounts (Pakistani news, sports)

**Root cause:**  
The hashtag generator (`hashtags_for_niche()`) is a pure string manipulation function — it concatenates words without any knowledge of what hashtags actually exist or have volume.

**Recommended fix:**  
Replace the string-generation heuristic with a **hashtag suggestion step**:
1. Ask the user to confirm/edit the hashtag list before scraping (30-second UX step)
2. OR use the Instagram explore search to validate hashtag volume before scraping
3. OR seed with a curated hashtag map per niche category (e.g., `"AI tools"` → `["#aitools", "#artificialintelligence", "#chatgpt", "#aiproductivity", "#techhacks"]`)

---

## Phase C — Scoring Issues

### Issue 7: `apify/instagram-profile-scraper` returns `latestPosts`, not `avgLikes`/`avgComments`

**What happened:**  
`discovery_score.py` called `prof.get("avgLikes", 0)` and `prof.get("avgComments", 0)` — both returned 0 because the profile scraper doesn't have these top-level fields. All 53 candidates scored 0.4 (the cross-hashtag baseline with zero engagement).

**Root cause:**  
The profile scraper returns a `latestPosts` array with per-post `likesCount` and `commentsCount`. Averages must be computed manually.

**Fix applied (in this run):** Compute `avg_likes` and `avg_comments` from `latestPosts` array. ✅

---

### Issue 8: `load_env()` not called in Phase B or Phase C scripts

**What happened:**  
Both `discovery_handles.py` and `discovery_score.py` called `os.environ.get("APIFY_TOKEN")` without first calling `load_env(project_dir)`. Token was not set → `RuntimeError: APIFY_TOKEN not set`.

**Root cause:**  
Unlike `scrape_instagram.py` (which correctly calls `load_env()`), the new discovery scripts forgot to load `.env`.

**Fix applied (in this run):** Added `load_env()` calls to both scripts. ✅

**Systemic fix for the plugin repo:**  
Centralize token loading in `viral_core/apify_client.py` — have `run_actor()` auto-load `.env` from the CWD if `APIFY_TOKEN` is not already set. Then individual scripts never need to call `load_env()` manually.

---

### Issue 9: Scoring normalization doesn't filter noise effectively

**What happened:**  
Final shortlist was dominated by accounts with 2-14 followers that happened to have one viral post. An account with 14 followers scored 1.0 — same as the account with 10K followers.

**Root cause:**  
The scoring formula normalizes `engagement_rate` at a 10% cap and `outlier_potential` at 5x cap. Tiny accounts regularly exceed both caps, scoring identically to established creators regardless of size.

**Recommended fix:**  
Add a **minimum follower threshold** (e.g., 1,000 followers) as a hard gate before scoring. Alternatively, add a 4th component to the score:

```
audience_size_score = log10(followers) / log10(500_000)  × weight 0.15
```

This gives small but real weight to audience size without completely excluding micro-creators.

---

## Cold-Start Problem — Strategic Recommendations

The core cold-start issue: **we don't know which Instagram hashtags have large, engaged creator pools in our target niche**. Three recommended approaches:

### Option 1: YouTube-first discovery (recommended)

YouTube is fully open. Search for the target niche → extract creator channel names → find their Instagram handles → scrape their Instagram profiles directly. This completely bypasses the hashtag cold-start problem.

```
YouTube search: "google vids tutorial 2026"
→ Top 10 channels: TechWithTim, HowFinity, ...
→ Find Instagram: @techwithTim, @howfinity
→ Feed directly into Phase C (profile scraper) → score
→ Write to competitors.json
```

**New script needed:** `discovery_youtube.py` using `yt-dlp` to search YouTube (no API key required for basic search).

---

### Option 2: Curated hashtag seed map

Build and maintain a JSON file of known high-quality hashtags per niche category:

```json
{
  "AI tools": ["#aitools", "#chatgpt", "#artificialintelligence", "#aiproductivity", "#techhacks"],
  "AI video": ["#aivideo", "#aicontentcreator", "#videoai", "#generativeai", "#aianimation"],
  "personal finance": ["#personalfinance", "#investing", "#financialfreedom", "#moneytips"],
  "fitness": ["#fitness", "#workout", "#gym", "#fitnessmotivation", "#healthylifestyle"]
}
```

The skill prompts the user to confirm/edit hashtags before Phase B runs. Zero additional API calls; eliminates the auto-generation problem.

**New file needed:** `config/hashtag_seeds.json`

---

### Option 3: Cross-platform discovery (Exploding Topics / SparkToro)

Use a paid trend service that already maps topics → audience → social platforms. Expensive but accurate. Worth considering if niche discovery is run frequently.

---

## Cross-Pipeline Bugs (Main Viral Analyzer + Niche Discovery)

These two bugs were fixed in earlier sessions but are documented here because they affect all scripts that use `viral_core/apify_client.py` and are critical for anyone setting up the pipeline fresh.

### Issue 10: `load_dotenv()` path resolution requires explicit project root

**What happened:**  
Calling `load_dotenv()` with no arguments searches relative to the current working directory. When scripts are invoked from a different directory (e.g., from `F:\working-viral-analyzer` while the `.env` lives at the project root), the file is not found and `APIFY_TOKEN` stays unset — even though the file exists.

**Root cause:**  
`load_dotenv()` defaults to CWD, not the script's location. In a plugin architecture where `CLAUDE_PLUGIN_ROOT` (the bundled read-only code) is separate from `CLAUDE_PROJECT_DIR` (the user's working directory with `.env` and secrets), the caller must resolve the project root explicitly.

**Fix applied:**  
Pass the explicit project root path: `load_env(str(pathlib.Path(input_path).resolve().parent.parent))`. The `load_env()` wrapper in `viral_core/config_io.py` then calls `load_dotenv(project_dir / ".env")` with a fully resolved path.

**Systemic note:**  
This is the right pattern for all scripts in the plugin. The project root must be passed down from `main()` — scripts that are called without a known input path should accept an explicit `--project-dir` argument.

---

### Issue 11: apify-client v3 returns Pydantic `Run` objects — subscript access fails

**What happened:**  
Code like `run["defaultDatasetId"]` raised `TypeError: 'Run' object is not subscriptable`. apify-client v3 changed `Run` from a plain `dict` to a Pydantic model.

**Root cause:**  
apify-client v2 returned raw dicts from `client.actor().call()`. v3 returns typed Pydantic objects. Any code written against v2 that uses `run["key"]` breaks silently at runtime — the error only surfaces when the key is actually accessed.

**Fix applied:**  
Changed all subscript access to attribute access: `run.default_dataset_id` (snake_case) instead of `run["defaultDatasetId"]` (camelCase). The attribute names follow Python snake_case convention in the Pydantic model regardless of the JSON field names.

**What to watch for:**  
If you see `TypeError: 'Run' object is not subscriptable` or `TypeError: 'DatasetClient' object is not subscriptable`, this is the same issue. Check `viral_core/apify_client.py` for any remaining `run[...]` subscript patterns.

---

## Summary of Bugs Fixed in This Run

| # | Bug | Fix status |
|---|-----|-----------|
| 1 | Empty seed → "technology" default | Workaround (user provided seed) |
| 2 | Wrong actor input key (`hashtags` → `urls`) | Fixed ✅ |
| 3 | Hashtag page returns `owner.id` not username | Fixed ✅ |
| 4 | `avgLikes`/`avgComments` don't exist → use `latestPosts` | Fixed ✅ |
| 5 | `load_env()` missing from Phase B + C scripts | Fixed ✅ |
| 6 | `load_dotenv()` path resolution (all scripts) | Fixed ✅ (earlier session) |
| 7 | apify-client v3 Pydantic `Run` object — no subscript access | Fixed ✅ (earlier session) |

## Summary of Outstanding Issues

| # | Issue | Priority | Effort |
|---|-------|----------|--------|
| 1 | Auto-generated hashtags are wrong quality | High | Medium |
| 2 | No Reddit credentials → halved signal | High | Low (15 min setup) |
| 3 | Tiny accounts dominate scoring | High | Low (add follower gate) |
| 4 | pytrends returns product names not niches | Medium | Medium |
| 5 | No YouTube-first discovery path | Medium | High |
| 6 | `load_env` should be centralized in `run_actor()` | Low | Low |
| 7 | `#googlevidstips` type hashtags need volume check | Low | Medium |

---

## Next Steps

1. **Immediate:** Add min-follower gate (1,000) to `discovery_score.py`
2. **This week:** Set up Reddit PRAW credentials + add to `.env.example`
3. **This week:** Replace hashtag auto-generation with curated seed map (`config/hashtag_seeds.json`) + user confirmation step in skill
4. **Next sprint:** Add YouTube-first discovery path (`discovery_youtube.py`)
5. **Plugin repo:** Centralize `load_env()` into `run_actor()` so scripts never forget it
