-- videos_vs_match.sql
-- Pairs every LAFC YouTube video with the most recent LAFC match that kicked
-- off at or before the video was published ("nearest preceding match"), and
-- computes how many days after that match the video went live.
--
-- One row per video. `days_since_match` is the key output: filter on it
-- downstream (e.g. < 3) to isolate genuine post-match content and exclude
-- videos stranded in schedule gaps like the 2026 World Cup break.
--
-- Join is on TIME, not an id: a video carries no match reference, so the only
-- bridge is that both timestamps are stored UTC-'Z', second precision, making
-- the comparison a plain string comparison. See derive_standings.py for how
-- lafc_match_context is built.

SELECT
  v.video_id,
  v.title,
  v.published_at,
  v.view_count,
  v.like_count,
  v.comment_count,

  m.kickoff_utc,
  m.opponent,
  m.result,                 -- 'W' / 'D' / 'L' (LAFC's perspective)
  m.home_away,              -- 'H' / 'A'

  -- Whole-day gap between kickoff and publish. julianday() converts each
  -- timestamp to a day-number, so subtracting gives a difference in days.
  ROUND(julianday(v.published_at) - julianday(m.kickoff_utc), 2) AS days_since_match

FROM videos v
JOIN lafc_match_context m
  ON m.kickoff_utc = (
       -- For this video, the latest kickoff that is still at/before it:
       SELECT MAX(kickoff_utc)
       FROM lafc_match_context
       WHERE kickoff_utc <= v.published_at
     )
ORDER BY v.published_at DESC;
