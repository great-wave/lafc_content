# Method notes

How I designed the labels, the analysis window, and the controls in [findings.md](findings.md).

## Labels come from playlists, not a classifier

`data/playlist_types.csv` is **56 hand-authored rows**, one per playlist, mapping `playlist_title → content_type`. The mapping is applied at query time, so a video gets its label the moment it joins a playlist.

Three values are deliberate choices rather than gaps:

- `unclassified` — the playlist is a theme, and the videos in it are all different kinds of video (BMO Stadium, Major News, Adventures in the U.S. Open Cup).
- `no_playlist` — the video isn't in a playlist at all.
- the `status` column — `active` means the playlist has published something in 2025 or later. By that rule 38 of the 56 are dormant, so getting those wrong costs little.

**Vocabulary notes.** `show` and `podcast` are separate categories: `show` is a produced docu-style program, `podcast` a conversation format. `goal_clip` and `match_recap` were folded into `highlights`.

## I tried and retired two title classifiers

I tried keyword matching first, then a sentence-transformer. Both read the title, and on serialized shows the title is boilerplate plus a topic phrase — so the model classified the topic and returned it as the *format* of the video. All four of these are episodes of the same weekly show:

| Title | `ml_label` |
|-------|------------|
| Inside LAFC \| Episode 212 – Off to a hot start | `match_preview` |
| Inside LAFC \| Episode 210 – MLS Is Back | `recap` |
| Inside LAFC \| Episode 214 – Leagues Cup | `highlights` |
| Inside LAFC Ep. 139 – Lewis O'Brien | `presser` |

Inside LAFC (n=226) split across **9 labels**; the largest was `presser`, at 39%.

**The model was most confident exactly where it was most wrong.** 602 videos have serialized titles, and their median confidence score was 0.519 against 0.472 everywhere else. So filtering at 0.36 keeps the bad labels and drops good ones, and raising the threshold makes it worse — it loses coverage where the classifier works while keeping the mistakes where it doesn't. There is no cutoff that fixes this.

**Why I didn't catch it earlier.** The test in `classification_v03.ipynb` (retired) used five playlists that each hold one kind of video, and left out every series playlist. So the 78% accuracy I measured only described the part of the library where the classifier already worked.

**The deeper problem.** Playlists already label most of the channel, so the only videos the classifier could add anything for were the ones playlists missed — and that is exactly where it performed worst. The answer isn't in the title. "Episode 210 – MLS Is Back" doesn't say anywhere that it is a weekly roundup show, so no amount of retraining on titles gets it back.

## This is a long-form labelling system

Someone has to file a video into a playlist by hand, and for Shorts that mostly doesn't happen:

| format | videos | unfiled | % unfiled |
|---|---|---|---|
| short | 528 | 452 | **85.6%** |
| live | 82 | 6 | 7.3% |
| horizontal | 1,342 | 90 | 6.7% |

So any breakdown by `content_type` is mostly a statement about long-form video — and Shorts are the views engine. This is the biggest structural limit in the analysis.

## `format` is a delivery method, not a content category

The three channel tabs (`UULF` → horizontal, `UUSH` → short, `UULV` → live) describe **video delivery**, not what kind of video it is.

Shorts really are different: they appear in a separate vertical feed that serves videos its own way, and that is what the format effect measures. But `live` and `horizontal` are the same video in the same feed — only the broadcast mode differs.

The duration test in [findings.md](findings.md#format) is what shows the Shorts effect is about the feed and not the length: inside a single content type, longer videos get *more* views, not fewer.

**The proof is Inside LAFC.** 135 numbered episodes, and no episode number appears under both formats — so this is a change in delivery, not the same video posted twice. The podcast moved to live streaming in early 2025. Same show, same length, different tab. It also explains the `live` bucket overall: it is mostly this one podcast.

Reporting three formats implies three kinds of content, when really the live bucket is one show and the horizontal bucket is everything else (except shorts). So I group live and horizontal together and compare them against Shorts.

## Controlling for publish quarter

The channel's audience changed size during the window, so two videos with the same view count are not comparable if they went out a year apart. Adding `C(published_quarter)` gives each quarter its own baseline, so every other number in the model compares a video against others published in the same quarter.

Same 1,703 videos, five ways of handling time:

| model | R² | shorts | Son |
|---|---|---|---|
| no time control | 0.468 | ×3.67 | ×37.45 |
| age as one continuous term | 0.515 | ×3.68 | ×25.26 |
| **quarter dummies** | **0.640** | **×3.90** | **×7.34** |
| quarter dummies, age ≥ 30d | 0.636 | ×4.01 | ×6.56 |
| month dummies | 0.716 | ×3.88 | ×3.26 |

Treating age as one number only gets partway, because views didn't drift up or down with age — they jumped once, when Son signed. A single slope can't fit a step. Month dummies fit best and I rejected them anyway: 39 of the 69 Son videos share one month, so an August-2025 term is close to a Son term and swallows the effect I'm trying to measure. The models also drop videos under 30 days old, which haven't finished collecting views.

**What this costs.** A quarter term absorbs everything that differs between quarters, so anything that stays the same *within* a quarter can no longer be measured — including what the signing did to the channel as a whole. That's the point: the era is what I'm controlling for, not what I'm estimating.

It does mean the Son effect appears twice in these documents at two different sizes. They measure different things. The channel-wide jump is in [findings.md](findings.md#context--what-the-team-did-not-control) — every video published that quarter did better, whether Son was in it or not. The ×6.6 is Son's videos compared against other videos published at the same time.

## Conventions

- **Median rather than mean** for every view comparison, because a few viral videos pull the mean away from the typical video.
- **Disjoint bins**, not cumulative ones. A cumulative "0–3 day" window was misleading at first because it counted the strong 0–1 day videos inside every wider window.
- **Views are modelled on a log scale**, so coefficients are raised back to a multiplier to read them. Engagement rate is modelled as-is and read in percentage points.
- **Bin boundaries are judgment calls**, picked as spans a person would recognise rather than derived from the data.
- **The video↔match join is by time**, not by id. Both timestamps are stored in the same UTC format, so the comparison is a plain string comparison.
- **A lot of models have been run against one dataset.** The two main models are the trustworthy part; anything else sitting just under p=0.05 should be treated as exploratory until it is tested on new data.
