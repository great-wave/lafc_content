# lafc_content

LAFC Content Analysis — what drives views and engagement on LAFC's YouTube
channel. Examines format, content type, and (publishing time against the match
calendar), separating what the content team can **control** from **context** they
can only plan around.

**Scope:** 1,215 videos published 2025-01-13 to 2026-08-13, from a library of
3,648. I excluded the videos that were uploaded before, and during, the content team's strategy
shift towards YouTube Shorts in 2024.

**Primary metrics:** Median views, and engagement rate. Median views instead of mean because a handful of
viral videos skew the mean. Engagement rate is (likes + comments) per view.

**Definitions**

- **Format** — shorts, horizontal, or live. Derived from YouTube channel content
  tabs. Shorts are short vertical videos that appear in a scroll; horizontal and
  live are 16x9.
- **Content type** — community, feature, full_match, highlights, match_preview,
  podcast, press_interview, show, unclassified. Derived from a handmade
  classification of playlist titles. Videos in no playlist at all get
  `no_playlist` — 86% of Shorts fall here.
- **Publishing time against the match calendar** — days before or after the
  nearest kickoff, split into categories.

## Headline findings

**Short-form is the reach engine, and it costs engagement.** Shorts got **×3.2
the views** of horizontal and live videos after controlling for content type and timing — but
**1.3 points less** engagement. This is about the Shorts *surface*, not about
length: within long-form, longer videos get *more* views, not fewer — a
highlights package 10× longer gets roughly ×6.

**Reach and engagement pull against each other.** The ranking that maximises
views is close to the reverse of the one that maximises engagement:

| content type | views vs highlights | engagement vs highlights |
|---|---|---|
| podcast | ×0.33 | +2.6 pts |
| press interview | ×0.42 | +1.0 pts |
| show | ×0.49 | +0.8 pts |

**The post-match window is 48 hours, not 24.** Views run ×2.4 in the first day
after kickoff and ×2.0 in the second, then the effect disappears entirely by day
three. The 24 hours *before* kickoff are the weakest slot in the whole cycle for
views — and the strongest for engagement.

**One player is the largest single effect in the data.** Videos in The Son
Spotlight playlist get **×19 the views** after controls and have no engagement
penalty. It holds in shorts and horizontal formats, so it is not a Shorts
artifact — but with only one comparable player playlist (the Vela Vault), this cannot yet be
separated from player content generally.

**On-field context does not move content performance.** Match result does not
survive controls (win ×1.34, loss ×0.71, neither significant on 420 post-match
videos). League standing predicts nothing (LAFC form p=0.155; opponent strength
is significant pooled but disappears in the post-match window where the
mechanism would have to operate). Home vs away *looks* like a ×1.9 away
advantage — until you notice that 25% of away post-match videos are about Son
against 7% of home ones. Split that out and the medians are near-identical
(3,108 vs 2,939). What the team controls — format, subject, timing — moves views
far more than how the season is going.

Full write-up with sample sizes, caveats and open questions:
**[docs/findings.md](docs/findings.md)**

## How it works

A python script uses the YouTube api to pull data from LAFC's YouTube channel 
into a SQLite3 database. Another python script pulls match data from ESPN into
the database, and a third script derives point in time standings per team based
on the match results.

I used SQL queries to combine video, playlist, and publishing time data into a
pandas dataframe which I then analyzed in an exploration notebook.

I derived content labels from **playlists, not a classifier**. I tried two
title-based classifiers first — keyword matching, then a sentence-transformer —
before deriving labels from playlists instead. The transformer failed in an
instructive way: on serialized shows/podcasts the title is boilerplate plus a topic
phrase, so it returned the *subject under discussion* as the *format of the
video*, and it was **more confident on exactly those** — meaning no confidence
threshold could filter them out.

That classification is found in `data/playlist_types.csv`: 56 hand-authored rows mapping
playlist → content type, applied at query time. New videos inherit a label the moment
they join a playlist, with nothing to re-run.

This is structurally a **long-form** labelling system — 86% of Shorts sit in no
playlist at all, so any cut by content type is mostly a statement about
long-form video.

## Data pipeline

```bash
python src/pull_youtube_data.py                    # YouTube channel + videos
python src/pull_match_data.py   --season 2018-2026 # MLS matches from ESPN
python src/derive_standings.py  --season 2018-2026 # point-in-time standings per LAFC match
```

Everything lands in `data/lafc_content.db` (SQLite, gitignored). The pull also
loads `data/playlist_types.csv` and runs `sql/views.sql`, so a rebuilt database
always has its views and labels.

## Layout

```
notebooks/exploration.ipynb   the analysis: distributions, cuts, two OLS models
sql/                          queries; views.sql defines the shared views
src/                          pulls, plus palette.py (chart colour)
theme/palette.json            single source of truth for every colour used
docs/findings.md              numbered findings, caveats, open questions
data/playlist_types.csv       playlist → content type, hand-authored
```

## Docs

- [Findings](docs/findings.md) — every result with its sample sizes and caveats.
- [Exploration notebook](notebooks/exploration.ipynb) — the analysis itself:
  distributions, cuts by format and content type, the match cycle, and two OLS
  models.
- [Match data — caveats & conventions](docs/data_caveats.md) — read before
  trusting a standings number or joining videos to match context (2020 ESPN feed
  quirk, ranking convention, timestamp formats).
