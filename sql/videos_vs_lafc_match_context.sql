-- THE FULL ANALYSIS TABLE: every video, all three label axes, plus the match
-- context around it. One row per video.
--
-- Every stat is live. Nothing here is a stored copy -- view counts, engagement
-- rate, playlist, format and content type are all derived on read, so re-running
-- src/pull_youtube_data.py is immediately reflected here.
--
-- THREE LABEL AXES
--   format        short / horizontal / live -- how it is delivered
--   playlist      which LAFC playlist it is filed under (NULL for ~22%)
--   content_type  what kind of video it is  -- from the playlist mapping below
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
--
-- ALSO REQUIRES the playlist_types table, loaded from data/playlist_types.csv
-- by src/pull_youtube_data.py. Edit the CSV, re-run the pull, done.


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

  video_formats.format,                                       -- FORMAT axis
  smallest_playlist_per_video.playlist_title AS playlist,     -- SUBJECT axis
  smallest_playlist_per_video.n_playlists,
  every_playlist_per_video.all_playlists,

  -- CONTENT TYPE axis, from data/playlist_types.csv -- 56 hand-authored rows,
  -- one per playlist, joined through whichever playlist labelled the video.
  --
  -- This replaced a sentence-transformer classifier that read the title. On
  -- serialized shows the title is boilerplate plus a topic phrase, so the model
  -- classified the topic and returned it as the format -- four episodes of one
  -- podcast came back as match_preview, recap, highlights and presser. Worse,
  -- it was MORE confident on those (median score 0.519 vs 0.472 elsewhere), so
  -- no threshold could filter them out. See Finding 7 in docs/findings.md.
  --
  -- A human filing a video into a playlist knows what a title cannot say.
  --
  -- Three values are load-bearing and deliberate:
  --   'unclassified'  the playlist is a theme whose videos span formats
  --                   (BMO Stadium, Major News) -- an answer, not a gap
  --   NULL            no playlist at all, so nothing to look up. 815 videos,
  --                   86% of Shorts -- this is a LONG-FORM label system
  --   status column   'active'/'dormant' in the CSV; 38 of 56 playlists have
  --                   published nothing since 2025 and are low-stakes
  playlist_types.content_type,

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
-- content type, or no preceding match.
LEFT JOIN video_formats
  ON video_formats.video_id = videos_with_engagement.video_id

LEFT JOIN smallest_playlist_per_video
  ON smallest_playlist_per_video.video_id = videos_with_engagement.video_id

LEFT JOIN every_playlist_per_video
  ON every_playlist_per_video.video_id = videos_with_engagement.video_id

-- The content type comes from the playlist, so the join hangs off the labelling
-- view rather than the video: one lookup per playlist, applied to every video
-- filed under it. A video added to a playlist tomorrow inherits its type with
-- no re-run of anything.
LEFT JOIN playlist_types
  ON playlist_types.playlist_title = smallest_playlist_per_video.playlist_title

LEFT JOIN lafc_match_context
  ON lafc_match_context.kickoff_utc = (
       -- For this video, the latest kickoff that is still at/before it:
       SELECT MAX(kickoff_utc)
       FROM lafc_match_context
       WHERE kickoff_utc <= videos_with_engagement.published_at
     )

ORDER BY videos_with_engagement.published_at DESC;
