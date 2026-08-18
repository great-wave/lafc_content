# lafc_content

LAFC Content Analysis — analyzes LAFC's YouTube content for 2025 and 2026.
I examined views and engagement rate by format, content_type, and timing
against the match calendar. 

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
