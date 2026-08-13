-- ONE ROW PER MEMBERSHIP -- use this to compare playlists against each other.
--
-- A video in three playlists appears three times, once for each. That is the
-- point: it belongs to all three, so it should count in all three.
--
--   perf = load_sql('playlist_performance')
--   perf.groupby('playlist_title')['view_count'].median()
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

SELECT
  playlists.title       AS playlist_title,
  playlists.item_count  AS playlist_size,   -- how big the playlist is overall
  playlist_items.position,                  -- order within it (episode 1, 2, 3...)

  videos.video_id,
  videos.title          AS video_title,
  videos.published_at,
  videos.view_count,
  videos.like_count,
  videos.comment_count,

  -- * 1.0 forces decimal division; without it SQLite would do integer division
  -- and truncate everything to 0. NULLIF turns a zero view_count into NULL so
  -- this returns NULL rather than erroring.
  ROUND(
    (videos.like_count + videos.comment_count) * 1.0
      / NULLIF(videos.view_count, 0),
  5) AS engagement_rate,

  video_formats.format        -- lets you cut a playlist BY format: "Match Previews as a Short"

FROM playlist_items

JOIN playlists
  ON playlists.playlist_id = playlist_items.playlist_id

-- Plain JOIN on purpose: this drops the ~100 playlist entries pointing at
-- videos from OTHER channels, which have no stats of ours to report. That is
-- why 3,482 memberships come out as 3,370 rows.
JOIN videos
  ON videos.video_id = playlist_items.video_id

LEFT JOIN video_formats
  ON video_formats.video_id = videos.video_id

ORDER BY playlists.title, videos.published_at DESC;
