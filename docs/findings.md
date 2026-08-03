# Findings

Analysis of what drives engagement on LAFC's YouTube channel, organized by
**lever** — separating what the content team can *control* from *context* they
can only plan around.

- **Controllable levers:** when to publish (timing), what format (length/type),
  what subject. These are where actionable recommendations live.
- **Uncontrollable context:** match result, opponent quality, league position.
  Useful only as a backdrop that predicts *attention*, never as a recommendation.

**Primary metric:** median **views** (reach). Median, not mean, because view
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

## Open questions & anomalies

- **7–14 day loss anomaly:** videos 7–14 days after a loss have median 12,183
  views (n=61) — a real, unexplained spike breaking the otherwise-clean decay.
  Possibly a specific painful loss (playoff exit / big rivalry defeat) generating
  sustained content. Pull the actual titles to investigate.
- **Result × timing interaction:** settle the result effect properly with an
  interaction term rather than a confounded main effect.
- **Format classification:** separate video *length* from *type* so "short wins"
  can be tested as "which type wins." Feeds both Format and Subject pillars.

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
