# lafc_content

LAFC Content Analysis — what drives views and engagement on LAFC's YouTube channel. Examines format, content type, subject, and publishing time, separating what the content team can control from the channel-wide audience shifts they can only plan around.

**Scope:** 1,952 videos published 2024-01-02 to 2026-08-13, from a library of 3,648. I excluded the videos that were uploaded before the content team's strategy shift towards YouTube Shorts in 2024.

**Primary metrics:** Median view count, and engagement rate. Median views instead of mean, because a handful of extremely high performing videos skew the mean. Engagement rate is (likes + comments) per view.

**Definitions**

- **Format** — shorts, horizontal, or live. Derived from YouTube channel content tabs. Shorts are short vertical videos that appear in a scroll; horizontal and live are 16x9.
- **Content type** — community, feature, full_match, highlights, match_preview, podcast, press_interview, show, unclassified. Derived from a handmade classification of playlist titles. Videos in no playlist at all get `no_playlist` — 86% of Shorts fall here.
- **Subject** — which playlist a video is filed under, where that playlist is about a person or theme rather than a format. The Son Spotlight is the clearest case; its content type is `unclassified`.
- **Timing** — where a video sits in the match cycle: days before or after the nearest kickoff, split into bins.

## Headlines

**The signing of Son Heung-min grew the audience.** The median view count of videos uploaded in Quarter 3 of 2025, **increased x5.7** from the previous quarter. This coincided with the signing of Son Heung-min on August 6, 2025. In Quarter 3, median view count grew from 1,020 to 33,915, before Son's signing to after. Son's arrival increased view count across the channel -- translating into higher view counts for unrelated content. Excluding every video that is in his playlist or names him anywhere, median views still went from 820 in July to 14,479 in August, while uploads stayed flat at 100 to 103. Signing decisions fall outside of the scope of the content team.

**Two strategy shifts moved output, not reach.** Shorts went from 3.9% of uploads in 2023Q4 to 26.4% in 2024Q1 and stayed there, and annual volume went from 202 videos in 2023 to 737 in 2024. Median views fell through that ramp — 2,323 in 2024Q1 down to 501 in Q2 — and did not recover until Son's signing. The levers the content team controlled changed what was published; they did not change how many people watched.

**Views and engagement rate pulled against each other.** The formats and content types that brought in higher views, had a lower engagement rate, and vice versa — with one exception, below.

| format / content type | views vs highlights | engagement vs highlights |
|---|---|---|
| shorts | ×4.01 | −0.87 pts |
| podcast | ×0.30 | +2.18 pts |
| press interview | ×0.38 | +0.80 pts |
| show | ×0.45 | +0.71 pts |

All figures come from the two OLS models, against a baseline of a long-form highlights video published 0–1 days before a match in 2024Q1. Views are multipliers because that model predicts log views; engagement is in percentage points because that one predicts the rate directly.

**Short-form content brought in views but had lower engagement rate.** Shorts got **×4.0 the views** of horizontal and live videos after controlling for content type and timing — but **0.87 points less** engagement than horizontal / live formats. This is about the Shorts *format*, not about length. Within long-form, longer videos get *more* views, not fewer; a highlights package **7.5× longer got ×4.9 the views** — median 0.8 minutes and 1,175 views under a minute, against 6.0 minutes and 5,752 views in the 3–10 minute band.

**Podcasts had the highest engagement rate and among the fewest views.** A podcast got a quarter of a highlights package's views and nearly twice its engagement rate — median 677 views against 2,686, and 6.11% engagement against 3.48%, across 372 podcasts.

**The Son Spotlight bucks the trend.** Videos in The Son Spotlight playlist get **×6.6 the views** after controls, and gain engagement too — **+1.97 points**, p<0.001. It is the only lever in the analysis that comes out ahead on both; everything else trades one for the other.

**Timing has a modest effect on views and engagement.** Every window in the match cycle beats the 24 hours before kickoff, but in a narrow band — ×1.43 to ×1.88, peaking in the day after kickoff. Engagement runs the other way: all nine windows come out below the pre-kickoff reference, most clearly the 24 hours after kickoff at **0.91 points** lower. The views peak and the engagement trough are the same window.

Full write-up with sample sizes, caveats and open questions: **[docs/findings.md](docs/findings.md)**

## How it works

A python script uses the YouTube api to pull data from LAFC's YouTube channel into a SQLite3 database. Another python script pulls match data from ESPN into the database, and a third script derives point in time standings per team based on the match results. I left the standings analysis for later work.

I used SQL queries to combine video, playlist, and publishing time data into a pandas dataframe which I then analyzed in two exploration notebooks.

**Both models control for publish quarter.** View counts are a single snapshot, so an older video has had longer to collect them, and the channel was a different size when it was published. Without that control Son reads ×36 instead of ×6.6, because his videos are concentrated in the quarter the audience stepped up.

I derived content labels from **playlists, not a classifier**. I tried two title-based classifiers first — keyword matching, then a sentence-transformer — before deriving labels from playlists instead. The transformer failed in an instructive way: on serialized shows/podcasts the title is boilerplate plus a topic phrase, so it returned the *subject under discussion* as the *format of the video*, and it was **more confident on exactly those** — meaning no confidence threshold could filter them out.

That classification is found in `data/playlist_types.csv`: 56 hand-authored rows mapping playlist → content type, applied at query time. New videos inherit a label the moment they join a playlist, with nothing to re-run.

This is structurally a **long-form** labelling system — 86% of Shorts sit in no playlist at all, so any breakdown by content type is mostly a statement about long-form video.

## Data pipeline

```bash
python src/pull_youtube_data.py                    # YouTube channel + videos
python src/pull_match_data.py   --season 2018-2026 # MLS matches from ESPN
python src/derive_standings.py  --season 2018-2026 # point-in-time standings per LAFC match
```

Everything lands in `data/lafc_content.db` (SQLite, gitignored). The pull also loads `data/playlist_types.csv` and runs `sql/views.sql`, so a rebuilt database always has its views and labels.

## Layout

```
notebooks/exploration.ipynb   the analysis: distributions, breakdowns, two OLS models
notebooks/strategy_exploration.ipynb  the 2024 format shift behind the date filter
docs/img/                     charts exported from the notebooks
sql/                          queries; views.sql defines the shared views
src/                          pulls, plus palette.py (chart colour)
theme/palette.json            single source of truth for every colour used
docs/findings.md              findings by lever, with caveats and open questions
docs/method.md                labels, window, controls, and the traps found
data/playlist_types.csv       playlist → content type, hand-authored
```

## Docs

- [Findings](docs/findings.md) — every result with its sample sizes and caveats.
- [Method notes](docs/method.md) — where the labels come from, why the title classifier was retired, the analysis window, and the publish-quarter control.
- [Exploration notebook](notebooks/exploration.ipynb) — the analysis itself: distributions, breakdowns by format and content type, the match cycle, and two OLS models.
- [Strategy exploration notebook](notebooks/strategy_exploration.ipynb) — uploads and format share by quarter across the full library, which is where the 2024 date filter comes from.
- [Match data — caveats & conventions](docs/data_caveats.md) — read before trusting a standings number or joining videos to match context (2020 ESPN feed quirk, ranking convention, which match the on-field columns actually describe, timestamp formats).
