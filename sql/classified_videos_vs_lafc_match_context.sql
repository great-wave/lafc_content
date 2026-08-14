-- THE FULL ANALYSIS TABLE: every video, all three label axes, plus the match
-- context around it. One row per video.
--
-- Every stat is live. Nothing here is a stored copy -- the only thing read from
-- a derived table is the classifier's output (ml_label / ml_score), because
-- that is genuinely expensive to recompute. View counts, engagement rate,
-- playlist and format are all derived fresh (views compute on read, they do not
-- store rows), so re-running src/pull_youtube_data.py is immediately reflected
-- here.
--
-- THREE LABEL AXES
--   format        short / horizontal / live -- how it is delivered
--   playlist      which LAFC playlist it is filed under (NULL for ~21%)
--   content_type  what kind of video it is  -- from the classifier, thresholded below
--
-- MATCH CONTEXT
--   days_since_match gap back to the previous kickoff
--   days_until_match gap forward to the next one
-- Both are needed because a lot of content is build-up for the NEXT match
-- rather than follow-up to the last one -- 44% of videos are closer to the
-- upcoming fixture. Downstream, take whichever is smaller and give it a sign.


-- REQUIRES sql/views.sql, which defines the three views this query reads:
--
--   videos_with_engagement       the videos table plus engagement_rate
--   smallest_playlist_per_video  one playlist per video (the labelling rule)
--   every_playlist_per_video     all of its playlists, as one string
--
-- The last two collapse the many-to-many playlist_items down to one row per
-- video before it is joined here. All three definitions live in views.sql and
-- only there, so this file and video_labels.sql cannot drift apart on them.
--
--   sqlite3 data/lafc_content.db < sql/views.sql


SELECT
  videos_with_engagement.video_id,
  videos_with_engagement.title,
  videos_with_engagement.description,
  videos_with_engagement.published_at,
  videos_with_engagement.duration,
  videos_with_engagement.view_count,
  videos_with_engagement.like_count,
  videos_with_engagement.comment_count,

  -- (likes + comments) / views, computed in sql/views.sql so all three query
  -- files share one definition. NULL when a video has no views.
  videos_with_engagement.engagement_rate,

  video_formats.format,                                        -- FORMAT axis
  smallest_playlist_per_video.playlist_title AS playlist,     -- SUBJECT axis
  smallest_playlist_per_video.n_playlists,
  every_playlist_per_video.all_playlists,

  -- CONTENT TYPE axis, from the sentence-transformer classifier.
  --
  -- THE THRESHOLD IS A JUDGMENT CALL, so it lives here rather than in the
  -- table -- changing it is one number and a re-run of this query, with no
  -- need to re-encode 3,648 titles.
  --
  -- Swept against the playlist labels, precision is nearly flat from 0.30 to
  -- 0.38 (76% -> 78%) and only climbs above it, so below 0.38 the score is
  -- barely discriminating and the coverage is close to free:
  --
  --     0.36   78% precision   79% coverage    <- chosen
  --     0.40   80% precision   71% coverage
  --     0.44   83% precision   62% coverage
  --
  -- 0.36 favours coverage because these labels are for comparing medians over
  -- hundreds of videos, where a little noise costs less than losing a fifth of
  -- the library. Below it we return NULL -- an honest "we don't know".
  
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
  ROUND(
    julianday(videos_with_engagement.published_at) - julianday(lafc_match_context.kickoff_utc),
  2) AS days_since_match,

  -- Whole-day gap to the NEXT kickoff after the video. Mirrors the join below,
  -- which only ever looks backward.
  -- NULL when no later match exists in the table.
  ROUND(
    julianday((
      SELECT MIN(kickoff_utc)
      FROM lafc_match_context
      WHERE kickoff_utc > videos_with_engagement.published_at
    )) - julianday(videos_with_engagement.published_at),
  2) AS days_until_match

FROM videos_with_engagement

-- All LEFT JOINs: every video survives even with no format, no playlist, no
-- classifier output, or no preceding match.
LEFT JOIN video_formats
  ON video_formats.video_id = videos_with_engagement.video_id

LEFT JOIN smallest_playlist_per_video
  ON smallest_playlist_per_video.video_id = videos_with_engagement.video_id

LEFT JOIN every_playlist_per_video
  ON every_playlist_per_video.video_id = videos_with_engagement.video_id

LEFT JOIN classified_videos
  ON classified_videos.video_id = videos_with_engagement.video_id

LEFT JOIN lafc_match_context
  ON lafc_match_context.kickoff_utc = (
       -- For this video, the latest kickoff that is still at/before it:
       SELECT MAX(kickoff_utc)
       FROM lafc_match_context
       WHERE kickoff_utc <= videos_with_engagement.published_at
     )

ORDER BY videos_with_engagement.published_at DESC;
