-- THE FULL ANALYSIS TABLE: every video, all three label axes, plus the match
-- context around it. One row per video.
--
-- Starts FROM videos so every stat is live. Nothing here is a stored copy --
-- the only thing read from a derived table is the classifier's output
-- (ml_label / ml_score), because that is genuinely expensive to recompute.
-- View counts, engagement rate, playlist and format are all derived fresh, so
-- re-running src/pull_youtube_data.py is immediately reflected here.
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


WITH smallest_playlist_per_video AS (

  -- Mirrors sql/video_labels.sql -- smallest playlist wins, because a niche
  -- playlist is a more informative label than a catch-all. Duplicated rather
  -- than imported so this file runs standalone; if you change the rule, change
  -- it in both places.

  SELECT
    ranked_playlists.video_id,
    ranked_playlists.playlist_title,
    ranked_playlists.n_playlists

  FROM (
    SELECT
      playlist_items.video_id,
      playlists.title AS playlist_title,
      COUNT(*) OVER (PARTITION BY playlist_items.video_id) AS n_playlists,
      ROW_NUMBER() OVER (
        PARTITION BY playlist_items.video_id
        ORDER BY playlists.item_count ASC, playlists.playlist_id ASC
      ) AS rank_in_video
    FROM playlist_items
    JOIN playlists
      ON playlists.playlist_id = playlist_items.playlist_id
  ) AS ranked_playlists

  WHERE ranked_playlists.rank_in_video = 1
),

every_playlist_per_video AS (

  -- Every playlist a video is in, flattened to one string, so the labels the
  -- smallest-playlist rule discarded are still visible.
  SELECT
    playlist_items.video_id,
    GROUP_CONCAT(playlists.title, ' | ') AS all_playlists
  FROM playlist_items
  JOIN playlists
    ON playlists.playlist_id = playlist_items.playlist_id
  GROUP BY playlist_items.video_id
)


SELECT
  videos.video_id,
  videos.title,
  videos.description,
  videos.published_at,
  videos.duration,
  videos.view_count,
  videos.like_count,
  videos.comment_count,

  -- * 1.0 forces decimal division; NULLIF turns a zero view_count into NULL so
  -- this returns NULL rather than erroring.
  ROUND(
    (videos.like_count + videos.comment_count) * 1.0
      / NULLIF(videos.view_count, 0),
  5) AS engagement_rate,

  video_formats.format,                                        -- FORMAT axis
  smallest_playlist_per_video.playlist_title AS playlist,       -- SUBJECT axis
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
    julianday(videos.published_at) - julianday(lafc_match_context.kickoff_utc),
  2) AS days_since_match,

  -- Whole-day gap to the NEXT kickoff after the video. Mirrors the join below,
  -- which only ever looks backward.
  -- NULL when no later match exists in the table.
  ROUND(
    julianday((
      SELECT MIN(kickoff_utc)
      FROM lafc_match_context
      WHERE kickoff_utc > videos.published_at
    )) - julianday(videos.published_at),
  2) AS days_until_match

FROM videos

-- All LEFT JOINs: every video survives even with no format, no playlist, no
-- classifier output, or no preceding match.
LEFT JOIN video_formats
  ON video_formats.video_id = videos.video_id

LEFT JOIN smallest_playlist_per_video
  ON smallest_playlist_per_video.video_id = videos.video_id

LEFT JOIN every_playlist_per_video
  ON every_playlist_per_video.video_id = videos.video_id

LEFT JOIN classified_videos
  ON classified_videos.video_id = videos.video_id

LEFT JOIN lafc_match_context
  ON lafc_match_context.kickoff_utc = (
       -- For this video, the latest kickoff that is still at/before it:
       SELECT MAX(kickoff_utc)
       FROM lafc_match_context
       WHERE kickoff_utc <= videos.published_at
     )

ORDER BY videos.published_at DESC;
