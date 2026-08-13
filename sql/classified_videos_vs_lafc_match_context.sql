-- This sql query joins the 'classified_videos' and the 'LAFC match context' tables, comparing kickoff times
-- to the published times of each video.

-- Also added a days since match column, and a days until match column.

-- THREE LABEL AXES come through from classified_videos:
--   format        short / horizontal / live -- how it is delivered (from the channel tabs)
--   playlist      which LAFC playlist it is filed under (NULL for ~22% of videos)
--   content_type  what kind of video it is  -- derived below from ml_label + ml_score

SELECT
  classified_videos.video_id,
  classified_videos.title,
  classified_videos.description,
  classified_videos.published_at,
  classified_videos.duration,
  classified_videos.duration_minutes,
  classified_videos.view_count,
  classified_videos.like_count,
  classified_videos.comment_count,
  classified_videos.engagement_rate,

  -- FORMAT axis and SUBJECT axis, both straight from YouTube.
  classified_videos.format,
  classified_videos.playlist,
  classified_videos.n_playlists,
  classified_videos.all_playlists,

  -- CONTENT TYPE axis, from the sentence-transformer classifier.
  -- ml_label is the model's raw best guess; ml_score is how confident it was.
  --
  -- THE THRESHOLD IS A JUDGMENT CALL, so it lives here rather than in the table
  -- -- changing it is one number and a re-run of this query, with no need to
  -- re-encode 3,648 titles.
  --
  -- Swept against the playlist labels, precision is nearly flat from 0.30 to
  -- 0.38 (76% -> 78%) and only starts climbing above it, so below 0.38 the
  -- score is not really discriminating and the coverage is close to free:
  --
  --     0.36   78% precision   79% coverage    <- chosen
  --     0.40   80% precision   71% coverage
  --     0.44   83% precision   62% coverage
  --
  -- 0.36 favours coverage because these labels are for comparing medians across
  -- hundreds of videos, where a little extra noise costs less than losing a
  -- fifth of the library. Below the threshold we return NULL -- an honest
  -- "we don't know" rather than a bad label.
  CASE
    WHEN classified_videos.ml_score >= 0.36 THEN classified_videos.ml_label
  END AS content_type,

  classified_videos.ml_label,   -- raw guess, so you can see what fell below
  classified_videos.ml_score,

  lafc_match_context.season,
  lafc_match_context.kickoff_utc,
  lafc_match_context.opponent,
  lafc_match_context.result,                 -- 'W' / 'D' / 'L' (from LAFC's perspective)
  lafc_match_context.home_away,              -- 'H' / 'A' (from LAFC's perspective)
  lafc_match_context.goals_for,
  lafc_match_context.goals_against,

  -- LAFC's form going INTO the match (result above NOT yet included):
  lafc_match_context.lafc_points,
  lafc_match_context.lafc_played,
  lafc_match_context.lafc_wins,

  -- Opponent's strength going INTO the match:
  lafc_match_context.opp_points,
  lafc_match_context.opp_played,
  lafc_match_context.opp_wins,

  -- Whole-day gap between kickoff and publish. julianday() converts each
  -- timestamp to a day-number, so subtracting gives a difference in days.

  ROUND(julianday(classified_videos.published_at) - julianday(lafc_match_context.kickoff_utc), 2) AS days_since_match,

  -- Whole-day gap to the NEXT kickoff after the video. Mirrors the join below,
  -- which only ever looks backward. Needed because a lot of content is build-up
  -- for the upcoming match, not follow-up to the last one.
  -- NULL when no later match exists in the table.

  ROUND(
    julianday((
      SELECT MIN(kickoff_utc)
      FROM lafc_match_context
      WHERE kickoff_utc > classified_videos.published_at
    )) - julianday(classified_videos.published_at),
  2) AS days_until_match

FROM classified_videos

LEFT JOIN lafc_match_context
  ON lafc_match_context.kickoff_utc = (
       -- For this video, the latest kickoff that is still at/before it:
       SELECT MAX(kickoff_utc)
       FROM lafc_match_context
       WHERE kickoff_utc <= classified_videos.published_at
     )

ORDER BY classified_videos.published_at DESC;
