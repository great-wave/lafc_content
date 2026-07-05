# Match data — caveats & conventions

Notes on the MLS match/standings data in `data/lafc_content.db`, pulled from the
undocumented public ESPN API. Read this before trusting a standings number or
joining videos to match context.

## Where the data comes from

Two scripts, separated by whether they touch the network:

| Script | Touches ESPN? | Writes |
|---|---|---|
| `src/pull_match_data.py` | Yes (only this one) | `matches` (league-wide, team-neutral), `teams`, `standings_official` |
| `src/derive_standings.py` | No (pure compute) | `lafc_match_context` (one row per LAFC match) |

Regenerate everything (idempotent — safe to re-run, never duplicates rows):

```bash
python src/pull_match_data.py   --season 2018-2026
python src/derive_standings.py  --season 2018-2026
```

`lafc_match_context` stores, for each LAFC match, the standing **going into** that
match (result not yet folded in) for both LAFC and the opponent, as raw
ingredients: points, games played, wins, goals for, goals against, conference.
Rank is deliberately **not** stored — compute it downstream (see caveat #2).

## Caveat 1 — 2020 is COVID-shortened, and ESPN's two feeds disagree

2020 was a shortened season; teams played an unequal number of games (18–23).

More importantly, ESPN's own two feeds contradict each other for LAFC in 2020:

- ESPN **schedule** feed (what `matches` aggregates): **22** LAFC regular-season
  games → 32 pts, 9-8-5. This matches LAFC's commonly published 2020 record.
- ESPN **standings** feed (`standings_official`): only **21** games / 31 pts — it
  silently drops one 1-1 draw.

**Our derived number (22 games) is the complete one; the `standings_official`
snapshot is the one with the gap.** So for 2020, sanity-check against
[mlssoccer.com](https://www.mlssoccer.com/standings/) or Wikipedia, **not** the
`standings_official` table. This is why `derive_standings.py` prints a rank
mismatch for 2020 — the verification is doing its job.

## Caveat 2 — ranking convention: points-per-game vs. total points

`derive_standings.py` orders teams by **points-per-game (PPG)**, then wins, then
goal differential, then goals for (MLS's actual tiebreakers — wins come *before*
goal difference, unlike Europe). Deeper tiebreakers (disciplinary points,
home/away splits) are skipped; ESPN's feed doesn't reliably expose them and they
rarely bind. See the comment on `mls_rank_key()`.

The PPG choice matters **only mid-season**, when teams have played unequal games:

- **Completed seasons (all 34 games):** PPG and total points give the identical
  order. All 7 completed seasons (2018–2019, 2021–2025) match ESPN exactly.
- **Partial season (e.g. 2026):** they diverge. Our PPG sort put LAFC 6th in the
  West; ESPN's live table (which sorts by **total points**) showed 5th, because a
  rival had played fewer games but had a higher PPG. Neither is "wrong" — they're
  different conventions. MLS's *live* in-season table uses total points; PPG is
  mainly the unequal-games case (like 2020).

Because we store raw ingredients rather than a rank, you can compute **either**
ordering downstream. Just decide explicitly which one your analysis wants.

## Convention — timestamps

All timestamps are UTC (nothing naive), in two textual styles:

- **Event times** (`videos.published_at`, `matches.kickoff_utc`,
  `lafc_match_context.kickoff_utc`): `Z`-suffixed, second precision, e.g.
  `2024-02-24T21:30:00Z`. Match kickoff is normalized to this exact form so
  video↔match joins are a plain string/time comparison — no timezone math.
- **Pull bookkeeping** (`fetched_at`, `derived_at`): `+00:00` offset with
  microseconds, e.g. `2026-07-02T23:33:30.255235+00:00`.

Note: LAFC's first match was **2018-03-04**. The YouTube channel predates the
team, so videos from ~2015 to early 2018 have **no** match context to join to —
that's expected, not a data gap.
