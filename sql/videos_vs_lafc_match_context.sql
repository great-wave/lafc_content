-- This sql query joins the 'videos' and the 'LAFC match context' tables, looking for the latest match kickoff time relative
-- to the publish time of each video. 

-- Also added a days since match column for later analysis. 

SELECT
  videos.video_id,
  videos.title,
  videos.description,
  videos.published_at,
  videos.duration,
  videos.view_count,
  videos.like_count,
  videos.comment_count,

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

  ROUND(julianday(videos.published_at) - julianday(lafc_match_context.kickoff_utc), 2) AS days_since_match

FROM videos

JOIN lafc_match_context
  ON lafc_match_context.kickoff_utc = (
       -- For this video, the latest kickoff that is still at/before it:
       SELECT MAX(kickoff_utc)
       FROM lafc_match_context
       WHERE kickoff_utc <= videos.published_at
     )

ORDER BY videos.published_at DESC;
