---
description: Discover trending niches and creators, write them to config/competitors.json (feeds /competitor-research)
---

Invoke the `niche-discovery` skill to discover trending niches, map them to
hashtags, extract and score creator handles, and write a ranked shortlist to
`config/competitors.json`. This is stage 0 of the viral-analyzer chain; run
`/competitor-research` afterwards to analyze the selected creators' top posts.

Passes `$ARGUMENTS` (an optional seed niche) through to the skill.
