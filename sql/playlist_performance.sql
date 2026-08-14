-- ONE ROW PER MEMBERSHIP -- use this to compare playlists against each other.
--
-- A video in three playlists appears three times, once for each. That is the
-- point: it belongs to all three, so it should count in all three.
--
-- THE ONE RULE: never add the groups together. Their counts sum to more than
-- the number of videos (3,370 rows over ~2,800 videos), so any total, share or
-- "% of output" built from them double-counts. Report each playlist on its own
-- line and note the overlap.
--
-- For anything per-video -- medians across the channel, timing, format --
-- use video_labels.sql, which returns exactly one row per video.
--
-- Medians are left to pandas: SQLite has no MEDIAN(), and AVG() is misleading
-- on view counts, which a handful of viral videos dominate.
--
-- REQUIRES sql/views.sql, for videos_with_engagement -- the videos table plus
-- engagement_rate, computed on read so it is shared by every query file:
--
--   sqlite3 data/lafc_content.db < sql/views.sql

SELECT
  playlists.title       AS playlist_title,
  playlists.item_count  AS playlist_size,   -- how big the playlist is overall
  playlist_items.position,                  -- order within it (episode 1, 2, 3...)

  videos_with_engagement.video_id,
  videos_with_engagement.title          AS video_title,
  videos_with_engagement.published_at,
  videos_with_engagement.view_count,
  videos_with_engagement.like_count,
  videos_with_engagement.comment_count,

  -- (likes + comments) / views, computed in sql/views.sql so all three query
  -- files share one definition. NULL when a video has no views.
  videos_with_engagement.engagement_rate,

  video_formats.format        -- lets you cut a playlist BY format: "Match Previews as a Short"

FROM playlist_items

JOIN playlists
  ON playlists.playlist_id = playlist_items.playlist_id

-- Plain JOIN on purpose: this drops the ~100 playlist entries pointing at
-- videos from OTHER channels, which have no stats of ours to report. That is
-- why 3,482 memberships come out as 3,370 rows.
JOIN videos_with_engagement
  ON videos_with_engagement.video_id = playlist_items.video_id

LEFT JOIN video_formats
  ON video_formats.video_id = videos_with_engagement.video_id

ORDER BY playlists.title, videos_with_engagement.published_at DESC;
