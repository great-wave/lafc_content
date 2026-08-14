-- This SQL query joins data from the video table with data from the playlists table.
-- If a video exists in multiple playlists, it choooses the playlist with the smallest
-- number of videos. That way, each video shows up only once in the table.

-- Everything is LEFT JOINed, so all videos survive:
--   format          NULL if the tab prefixes ever stop covering the uploads
--   playlist        NULL for the ~22% of videos in no playlist (mostly Shorts)

-- To compare playlists against each other instead, use playlist_performance.sql,
-- which gives one row per membership so a video counts in every playlist it is in.

-- REQUIRES sql/views.sql, which defines the three views this query reads:
--
--   videos_with_engagement       the videos table plus engagement_rate
--   smallest_playlist_per_video  one playlist per video (the labelling rule)
--   every_playlist_per_video     all of its playlists, as one string
--
-- The last two collapse the many-to-many playlist_items down to one row per
-- video before it is joined here -- without that, a video in three playlists
-- would come back three times. All three definitions live in views.sql and
-- only there, so this file and the other queries cannot drift apart.
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

  video_formats.format,                                         -- FORMAT axis
  smallest_playlist_per_video.playlist_title AS playlist,        -- SUBJECT axis
  smallest_playlist_per_video.n_playlists,
  every_playlist_per_video.all_playlists

FROM videos_with_engagement

-- LEFT JOIN keeps every row from `videos` even when the right side has no
-- match. A plain JOIN would silently drop the 815 videos with no playlist.

LEFT JOIN video_formats
  ON video_formats.video_id = videos_with_engagement.video_id

LEFT JOIN smallest_playlist_per_video
  ON smallest_playlist_per_video.video_id = videos_with_engagement.video_id

LEFT JOIN every_playlist_per_video
  ON every_playlist_per_video.video_id = videos_with_engagement.video_id

ORDER BY videos_with_engagement.published_at DESC;
