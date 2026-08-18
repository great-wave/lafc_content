# Findings

Analysis of engagement rate and view count on LAFC's YouTube channel, organized by
**lever** — separating what the content team can *control* from *context* they
can only plan around.

- **Controllable levers:** when to publish (timing), what format (short/horizontal/live),
  what content type, what subject. These are actionable recommendations.
- **Uncontrollable context:** match result, opponent quality, league position.
  Useful only as a backdrop that predicts *attention*, never as a recommendation.

**Primary metric:** median **views** (reach). Median views because view
counts are dominated by a handful of viral videos — the mean describes "typical
+ a few megahits," the median describes the typical video. Engagement *rate*
(likes/comments per view) is tracked as a secondary signal where it tells a
different story.

**Data basis:** all cuts run on `sql/videos_vs_lafc_match_context.sql`, which
joins each video (n≈3,483 after the join) to its nearest *preceding* LAFC match
and computes `days_since_match`. Windows are analyzed as **disjoint** bins so
each is isolated (see Method Notes).

---

## Timing

### Finding 1 — The post-match attention window is ~24 hours (CONTROLLABLE)

**Question:** Does a video's timing relative to LAFC matches affect its views?

**Method:** Bucketed videos by days-since-match into disjoint windows; compared
median views. Confirmed with an OLS regression of `log(views)` on a binary
`is_matchday` (< 1 day) predictor, with and without controls.

**Result — median views by disjoint window:**

| Window | Videos | Median views |
|--------|--------|-------------|
| 0–1 day | 826 | **3,600** |
| 1–3 days | 659 | 1,260 |
| 3–7 days | 873 | 1,464 |
| 7–14 days | 284 | 1,987 |
| 14 days+ | 841 | 1,733 |

The lift lives almost entirely in the first 24 hours (~3× the surrounding
baseline) and is gone by day 1 — the 1–3 day bucket is actually the *lowest*.

**Regression confirmation:**
- `is_matchday` coefficient 0.882 → **×2.4 views** (+141%), p ≈ 1.5e-45.
- Survives controls for result and duration: still **×2.1**, p ≈ 3.7e-33.
- But R² = 0.056 (0.110 with controls): the effect is large and real, yet
  timing explains only ~6–11% of view variation. It moves the odds; it is not
  the master key.

**Caveat:** Correlational. Most of what drives views is unmodeled (subject,
content quality, virality).

**Actionable takeaway:** The fixture calendar is known months ahead; the 24-hour
post-match window is a predictable ~2–3× attention spike. **Plan production
around the fixture list and publish within 24h of full-time.** Content posted
2+ days later misses the wave.

> **⚠ Revised 2026-08-12 — see Finding 4.** This finding measures *days since*
> the previous match only, which mislabels build-up content: 44% of videos are
> closer to the *next* match than the last one, and the "3–7 days" bucket is
> 80% pre-match content. The 0–1 day spike survives, but the flat middle of the
> curve was rising build-up and falling follow-up cancelling out.

### Finding 2 — Result modulates the spike, but is CONTEXT, not a lever

Within the match-day window, result orders views cleanly — but the team can't
control results, so this only informs *what to expect*, not *what to do*.

| Result (match-day) | Videos | Median views | Comments per 1k views |
|--------------------|--------|-------------|----------------------|
| Win | 562 | 4,083 | 1.3 |
| Draw | 179 | 3,109 | 1.7 |
| Loss | 85 | 1,789 | **4.0** |

**Two opposite stories:** wins buy **reach** (most views), losses buy
**intensity** (3× the comment *rate* — fans show up to argue/vent). The one
lever hiding here: after a loss, discussion-driving formats (analysis/reaction)
may fit the audience's mood better than hype clips.

Note: result only matters *near* a match. Across all videos it is meaningless
(a video 20 days after a draw is not "about" that draw) — the plain `result`
coefficient in the controlled regression is confounded by this and should not
be read as a result effect. An interaction term (`is_matchday × result`) is the
correct tool if we want to settle it statistically. **[Open]**

### Null result — Home vs away doesn't matter

Match-day median views: home 3,564 vs away 3,703 — effectively flat. The timing
effect is about match *rhythm and result*, not venue. Reported because a tested
non-effect is itself informative.

---

## Format

### Finding 3 — Short-form is the reach engine (CONTROLLABLE)

**Question:** Does video length affect views?

**Method:** Converted ISO-8601 `duration` to seconds; bucketed into length
bands; compared median views. Checked and controlled for the match-day confound.

**Result — median views by length:**

| Length | Videos | Median views |
|--------|--------|-------------|
| <15s | 103 | **8,918** |
| 15–30s | 306 | 5,670 |
| 30–60s | 546 | 2,596 |
| 1–3m | 823 | 1,791 |
| 3–10m | 781 | 1,893 |
| 10–30m | 467 | 881 |
| 30m+ | 457 | **820** |

Steep, front-loaded decline — the shortest clips get **~11× the views** of
long-form shows.

**Confound checked and survived:** short videos *are* disproportionately
match-day (40% of <15s clips vs 3% of 30m+), so timing and length are entangled.
But within match-day videos only, the length effect **persists and strengthens**
(<15s = 13,535 median views), so short-form outperforms even holding timing
constant. On match day the pattern is mildly bimodal: very short clips win
biggest, with a secondary bump at 3–10m (highlight packages people seek out);
long-form (10m+) loses regardless.

**Caveats:**
- Duration is a **proxy for content *type*** (a <15s clip is a hype/reaction
  clip; a 30m+ is an `Inside LAFC` episode). "Short wins" really means "hype
  clips beat long-form shows." Separating length from type needs the
  classification work. **[Open]**
- Small samples at the long end of match-day (30m+ n=14).
- **Views is not the only goal.** Long-form drives watch time (what YouTube's
  algorithm and ad revenue reward) and loyalty, which raw views don't capture.

**Actionable takeaway:** Short-form clips (<30s) are the reach engine — ~11× the
views of long-form, and not merely a match-day effect. **For reach, prioritize
short cutdowns, especially in the match-day window.** Long-form serves a
different goal (depth, watch time, loyalty) and should not be judged on views
alone.

---

## Subject

*Not yet analyzed.* Does content about specific players (e.g. Son Heung-Min) or
rivalry opponents outperform? Requires subject tagging (classification pillar).

---

## Session 2026-08-12 — match-cycle position, channel era, playlist labels

### Finding 4 — Position videos in the match *cycle*, not days-since (CONTROLLABLE)

**Problem with the old measure:** the join only ever looks backward, so a
matchday hype clip published the night before kickoff was recorded as "5 days
since the previous match." MLS plays roughly weekly, so build-up content lands
squarely in the mid `days_since` buckets.

**Scale of the mislabeling:** 1,583 of 3,571 videos (**44.3%**) are closer to the
next match than the previous one. By old bin: `4–7 days` was **79.9%** pre-match
content, `30+` was 71.9%, `2–3` and `8–14` about 50% each. Only `0–1` meant what
its label said.

**Fix:** `sql/videos_vs_lafc_match_context.sql` now also returns
`days_until_match` (mirrored subquery, `MIN(kickoff_utc) > published_at`).
Downstream, a signed `days_from_match` takes the *nearer* of the two — negative
means published before a kickoff. Videos more than 21 days from a match in both
directions are masked to `NaN` (offseason / pre-2018; 504 videos).

**Result — median engagement rate by cycle position:**

| Position | Videos | Median engagement | Median views |
|----------|--------|-------------------|--------------|
| 3–7 days before | 238 | 4.27% | 1,884 |
| 1–3 days before | 675 | 4.50% | 1,326 |
| **matchday (<24h before)** | 202 | **5.05%** | 1,541 |
| **0–1 day after** | 1,096 | **3.61%** | **2,904** |
| 2–3 days after | 315 | 4.51% | 1,500 |
| 4–7 days after | 123 | 4.64% | 1,670 |

The old backward-only cut was nearly flat (medians 3.65–4.59%). The signed
version shows a real shape: build-up climbs to a matchday peak, collapses after
kickoff, recovers over the following week.

**Views and engagement move in opposition.** Views roughly double in the 24h
after a match (2,904 vs a ~1,500 baseline) exactly where engagement *rate*
bottoms out. Since rate = (likes+comments)/views, a burst of casual highlight
viewers inflates the denominator. The post-match "dip" is substantially a
**reach** story, not disengagement.

**Caveat — format composition.** The `0–1 after` bin is 52.8% `match` family,
which has a structurally low rate. Checked within families: the curve survives
in `match` (matchday 4.49% vs 2.89% after) and `social` (5.31% vs 4.00%) but
**not** in `show` (flat 4.8–5.7%). Real, but amplified by composition.

**Actionable takeaway:** matchday content reaches a smaller but far more
invested audience; the 24h post-match window is a reach spike with diluted
engagement. These are two different editorial goals and should be judged on
different metrics.

### Finding 5 — 2024 is a channel-era break, not a results story (CONTEXT)

Median views by year are volatile, not trending: 2,609 (2018) → 923 (2021) →
3,067 (2022) → **639 (2024)** → 2,600 (2025) → 3,242 (2026).

**On-field 2024 was strong** (19W-7D-8L, 63 GF — third-best in the dataset), so
the collapse is a content story:

| Year | Videos | Median duration | Share <1 min | Median views |
|------|--------|-----------------|--------------|--------------|
| 2023 | 202 | 6.83 min | 3.0% | 1,685 |
| 2024 | 737 | 4.33 min | 26.1% | **639** |
| 2025 | 827 | 1.33 min | 43.2% | 2,601 |

2024 is the Shorts pivot plus a 3.6× volume increase. It is not only a mix
shift — **both duration classes crashed and recovered**: long-form 1,617 → 499 →
1,242; short-form 5,865 → 2,447 → 5,001.

**Format families move in opposite directions**, which matters for regression:
`social` up 8× (1,367 → 11,542), `behind_scenes` up 2×, while `show` fell 4×
(5,540 → 1,410) and `signing` fell 1.8×; `match`/`media`/`feature` flat.

**Implication:** era is not a confound you can subtract with a single date term
— it *interacts* with format. Either model the interaction or restrict to a
stable window. **Recommended window: 2025 onward (1,138 videos)**; 2024 is
mid-pivot with depressed reach in every duration class.

### Finding 6 — Playlists are a better label source than keyword classification

The channel has **56 public playlists, 3,514 memberships covering 2,785 of
3,571 videos (78%)** — 88% of long-form but only 51% of Shorts. 84% of covered
videos sit in exactly one playlist. Full pull ≈ 110 quota units.

**Near-perfect labels:** LAFC Weekly, Acción LAFC, Black & Gold Insider (100%
`show`), In Touch With Steve Cherundolo (100% `media`), LAFC+ (99%), Inside LAFC
(98%), Behind The Crest (94%), Match Previews (90% `match`).

**Systematic disagreements** reveal a classifier defect:

| Playlist | n | How `format_family` splits it |
|----------|---|-------------------------------|
| Interviews | 393 | 44% `media`, 44% `social` |
| Features | 168 | 52% `social`, 27% `match`, **12% `feature`** |
| Community & Culture | 99 | 73% `social` |
| Major News | 33 | 58% `social`, 30% `match` |
| Highlights | 655 | 77% `match`, 15% `social` |

**Root cause:** `format_family` conflates two orthogonal axes — **subject**
(what the video is about) and **delivery format** (short/vertical vs long).
`social` has become a catch-all absorbing subject-based content. A 30-second
interview clip is both "an interview" and "a short"; forcing one label loses one
of those facts.

**Recommended rework:** derive *subject* from playlist membership (many-to-many;
needs a `playlist_items` join table) and *format* from a Shorts probe. Keep the
keyword classifier as fallback for the uncovered 22%, validated against the
2,785 labeled videos.

**Detecting Shorts:** there is no `isShort` field in the Data API, and
`fileDetails.videoStreams[].aspectRatio` is owner-only. `GET
youtube.com/shorts/{id}` returns **200** for a real Short and **303** for
anything else. Verified against real IDs — note a 25-second video returned 303,
so `dur_min < 1` misclassifies.

---

### Finding 7 — The title classifier is retired; it reads topic, not format

**Decision (2026-08-14): stop using the classifier as a label source.**
`ml_label` / `ml_score` stay in `classified_videos` as a diagnostic, but
`content_type` should no longer promote them.

**What it actually classifies.** On serialized shows the title is boilerplate
plus a topic phrase, and the model classifies the phrase — returning the
*subject under discussion* as the *format of the video*. All four of these are
episodes of one weekly show:

| Title | `ml_label` |
|-------|------------|
| Inside LAFC \| Episode 212 – Off to a hot start | `match_preview` |
| Inside LAFC \| Episode 210 – MLS Is Back | `recap` |
| Inside LAFC \| Episode 214 – Leagues Cup | `highlights` |
| Inside LAFC Ep. 139 – Lewis O'Brien | `presser` |

Inside LAFC (n=226) splits across **9 labels**; the largest is `presser` at 39%.

**Confidence is anti-correlated with correctness — so no threshold can fix it.**
602 videos (16.5% of the library) carry serialized titles, and the model is
*more* confident on them than on everything else:

| Segment | n | Median `ml_score` | Below 0.36 |
|---------|---|-------------------|------------|
| Serialized titles | 602 | 0.519 | 15.9% |
| Everything else | 3,046 | 0.472 | 22.0% |

The 0.36 cut therefore *preferentially keeps* the bad labels: ~506 of the 602
clear it, about **18% of all non-null `content_type`**. Raising the threshold
makes this worse, shedding coverage where the classifier works while retaining
the errors where it does not. Affected series: Inside LAFC (203), LAFC+ (106),
LAFC Weekly (82), Acción LAFC (73), Black & Gold Insider (59), In Touch With
Steve Cherundolo (25).

**Why earlier validation missed it.** The sweep in `classification_v03.ipynb`
ran against five *content-type* playlists (Match Previews, Interviews,
Highlights, Full Matches, Anatomy of a Goal). Every *series* playlist was
excluded, so 78% precision describes only the segment where the classifier
works. Note also that its coverage figures are within the validation subset,
while the coverage numbers quoted in `sql/videos_vs_lafc_match_context.sql`
are library-wide (0.36 → 79%, 0.40 → 71%, 0.44 → 62%) — both correct, different
denominators.

**The structural problem.** Playlists already cover 78% of the library, so the
classifier's only real territory is the uncovered 815 — which is where it is
weakest:

| | Uncovered (815) | Covered (2,833) |
|---|---|---|
| Shorts | 462 (57%) | — |
| Median title length | 7.0 words | 8.8 words |
| Median `ml_score` | 0.429 | 0.497 |
| Below 0.36 | 33% | 17% |

It overrides playlists where they know the answer, and struggles where nothing
else can help. The information is not in the string: "Episode 210 – MLS Is Back"
does not contain the fact that it is a weekly roundup show, so retraining on
titles alone cannot recover it.

**Replacement:** subject from playlist membership, format from the Shorts probe
(Finding 6). Series playlists get one content-type decision per show (~15
decisions) rather than one guess per episode. Strip Shorts and series from the
uncovered set and roughly **329 horizontal videos** remain with no label source
— small enough to hand-label once, permanently, rather than model.

**Affects:** any cut sliced by `content_type`. Findings 1–5 use `format`,
`days_from_match`, and `format_family`, none of which depend on the classifier.

---

### Finding 8 — Playlist mapping replaces the classifier; it is a long-form label system

The classifier's replacement is `data/playlist_types.csv` — **56 hand-authored
rows**, one per playlist, mapping `playlist_title → content_type`. The mapping is
applied at query time, so new videos inherit a label the moment they join a
playlist; nothing needs re-running. 56 decisions replace 3,648 guesses.

**Coverage: 2,503 videos (69%) receive a real content type.** The remainder is
330 in playlists deliberately marked `unclassified` (themes whose videos span
formats — BMO Stadium, Major News, Adventures in the U.S. Open Cup) and 815 with
no playlist at all.

| content_type | videos | median views |
|--------------|--------|--------------|
| `highlights` | 708 | **3,705** |
| `podcast` | 507 | 720 |
| `press_interview` | 404 | 613 |
| `show` | 369 | 1,242 |
| `feature` | 277 | 1,657 |
| `community` | 150 | 1,325 |
| `match_preview` | 79 | 1,412 |
| `full_match` | 9 | 352 |

**Only `highlights` beats the channel median** of 1,918 — everything else sits at
or below it. Treat that ordering as descriptive, not causal: format is a
confound, since `highlights` is Shorts-heavy and Finding 3 already establishes
short-form as the reach engine. The cut worth running is content type *within*
duration class.

**This is a long-form labelling system, and that is a structural limit.**
Playlist filing is a deliberate curation step that Shorts largely skip:

| format | total | unfiled | % unfiled |
|--------|-------|---------|-----------|
| short | 539 | 462 | **85.7%** |
| live | 103 | 24 | 23.3% |
| horizontal | 3,006 | 329 | 10.9% |

Any cut by `content_type` is therefore mostly a statement about long-form. Note
this has degraded sharply since Finding 6 measured 51% Shorts coverage — now
14% — so Shorts volume is outgrowing anyone's filing of it. The Shorts probe is
the higher-value work; further classification effort is not.

**Most playlists are dormant.** `status = active` means **at least one video
published in 2025 or later**; `dormant` means the most recent video predates
2025. The cutoff is set to match Finding 5's recommended 2025+ analysis window,
not chosen independently. On that rule 38 of 56 playlists are dormant (701
videos) and 18 are active (2,132), so decisions on dormant playlists are
low-stakes. The bar is deliberately loose — as of Aug 2026 it means "active
within ~20 months," and Community & Culture qualifies on a single video. Stricter
alternatives: 2026+ gives 13 active / 43 dormant; 2024+ gives 28 / 28.

**Vocabulary notes.** `show` and `podcast` are separate values and the
distinction is real: `show` is a produced episodic program, `podcast` a
conversation format. All 226 Inside LAFC videos are podcast — the apparent split
between `| Episode N` and `Ep. N` titles is a naming-convention change over
time, not two series. `goal_clip` and `match_recap` were folded into
`highlights` (same job; match recaps are a 3.0-min cut against 1.1-min
highlights, with near-identical views).

**Anomaly worth its own look: The Son Spotlight.** 69 videos, all published
2025+, median **84,187 views** — 44× the channel median and the highest-performing
playlist in the library by a wide margin. Not a show but a player compilation.
It alone was distorting the `show` group median before being separated out.

---

### Finding 9 — `format` is a delivery surface, not a content category

The three channel tabs (`UULF` → horizontal, `UUSH` → short, `UULV` → live) are
**where YouTube puts a video**, not what kind of video it is. Two unrelated
distinctions are collapsed into one column:

| | n | median duration | median views | under 1 min |
|---|---|---|---|---|
| `short` | 539 | 0.4 min | **6,503** | 94% |
| `horizontal` | 3,006 | 3.9 min | 1,518 | 17% |
| `live` | 103 | **49.8 min** | 1,968 | 0% |

- **`short` vs the rest is a distribution difference.** The vertical swipe feed
  is a separate surface with its own discovery mechanics. This is the real axis,
  and it is what Finding 3 is actually measuring.
- **`live` vs `horizontal` is a delivery difference.** Both are long-form
  horizontal video landing in the same feed; only the broadcast mode differs.

**The proof is Inside LAFC.** 135 numbered episodes, and **no episode number
appears under both formats** — this is a switchover, not duplication:

| format | episodes | years |
|--------|----------|-------|
| horizontal | 78–148 (n=65) | 2023: 22, 2024: 42, 2025: 1 |
| live | 144–214 (n=70) | 2025: 43, 2026: 27 |

The podcast moved to live streaming around **episode 144 in early 2025**. Same
show, same format, same length — a different tab. That is only possible because
the tab describes delivery. It also explains the `live` bucket overall: 103
videos, 76 of them since 2025, 69 of them podcast. `live` is largely one show.

**How to use the axis:** treat format as **short vs long-form**, folding `live`
into `horizontal`, unless the question is specifically about live-vs-VOD.
Reporting three formats implies three content categories and invites the reading
that "live does better than horizontal" — when the live bucket is mostly one
podcast and the horizontal bucket is everything else on the channel.

**Suggestive, not causal:** Inside LAFC's median went 744 views as horizontal →
1,951 as live, a 2.6× lift on the same show. But the switch coincides with the
channel's recovery from the 2024 era slump (Finding 5), so era and delivery move
together. It is a clean natural experiment on a single show and deserves a
proper look before anyone claims live streaming caused it.

**Re-uploads are not a confound.** Only 4 titles appear under more than one
format across the whole library, all `short`/`horizontal` pairs posted minutes
apart — the same asset cut for both aspect ratios. The Short wins decisively in
three of the four (8.1×, 3.5×, 4.6×), losing only on "A new era begins in Black
& Gold." (131,677 vs 153,937). A tiny sample, but it points the same way as
Finding 3.

---

## Open questions & anomalies

- **7–14 day loss anomaly:** videos 7–14 days after a loss have median 12,183
  views (n=61) — a real, unexplained spike breaking the otherwise-clean decay.
  Possibly a specific painful loss (playoff exit / big rivalry defeat) generating
  sustained content. Pull the actual titles to investigate.
- **Result × timing interaction:** settle the result effect properly with an
  interaction term rather than a confounded main effect.
- **Format classification:** separate video *length* from *type* so "short wins"
  can be tested as "which type wins." Feeds both Format and Subject pillars.
  **[Addressed by Finding 6 — split subject (playlists) from format (Shorts
  probe). Implementation still open.]**

### Next steps (as of 2026-08-14)

1. ~~Add `playlists` / `playlist_items` tables to `src/pull_youtube_data.py`.~~
   **Done** — both tables are populated, and `sql/views.sql` derives
   `smallest_playlist_per_video` / `every_playlist_per_video` from them.
2. Rework classification: subject from playlists, format from the Shorts probe.
   The classifier is retired as a label source (Finding 7) — no further
   validation of it is planned. Remaining work is the ~15 per-show content-type
   decisions for series playlists, and a one-time hand-label of the ~329
   horizontal videos with no playlist.
3. **Blocker:** `format_family` does not exist in the query output — the columns
   are `format`, `content_type`, `ml_label`, `playlist`. Cells in
   `exploration.ipynb` keyed to it raise `KeyError`. Decide its replacement
   (`subject`, or a rebuilt family mapping) before the cuts below.
4. Re-run the match-cycle chart faceted by format family to separate the
   timing effect from the composition effect (Finding 4 caveat).
5. Revisit Finding 1's regression using signed `days_from_match` and an
   `is_matchday × result` interaction.
6. Decide the analysis window — 2025+ recommended (Finding 5).

---

## Method notes

- **Median over mean** for all view comparisons (skew from viral outliers).
- **Disjoint (non-overlapping) bins**, not cumulative windows: a cumulative
  "0–3 day" cut was initially misleading because it double-counted the strong
  0–1 day videos. Each window must be isolated to be read on its own.
- **Log-transform views for regression** (`np.log`); exponentiate coefficients
  (`np.exp`) back to a multiplier for interpretation.
- **Bin boundaries are judgment calls** (timing: 1/3/7/14 days; length:
  15s/30s/1m/3m/10m/30m) — chosen as human-meaningful spans, not derived from
  the data.
- **The video↔match join is temporal**, not by id: each video pairs to the
  latest match with `kickoff_utc <= published_at`. Both timestamps are stored
  UTC-'Z' second-precision so the comparison is a plain string comparison.
