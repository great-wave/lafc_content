# lafc_content

LAFC Content Scoreboard — analyzes LAFC's YouTube content performance against
the MLS match calendar to find what drives fan engagement.

## Data pipeline

```bash
python src/pull_youtube_data.py                    # YouTube channel + videos
python src/pull_match_data.py   --season 2018-2026 # MLS matches from ESPN
python src/derive_standings.py  --season 2018-2026 # point-in-time standings per LAFC match
```

Everything lands in `data/lafc_content.db` (SQLite, gitignored).

## Docs

- [Match data — caveats & conventions](docs/data_caveats.md) — read before
  trusting a standings number or joining videos to match context (2020 ESPN feed
  quirk, ranking convention, timestamp formats).
