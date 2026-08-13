-- PER-LABEL REPORTING: one row per (video, playlist), for grouping BY playlist.
--
-- Overlapping groups are fine here, because each group is answering its own
-- separate question ("among videos tagged Highlights, what is the median?").
-- A video in two playlists legitimately contributes to both answers.
--
-- THE RULE: never combine the groups. Their counts sum to MORE than the number
-- of videos (~3,370 rows over ~2,800 videos), so any total, share, or "% of
-- output" built from them is wrong. Report each playlist on its own line and
-- footnote the overlap.
--
-- Medians are left to pandas -- SQLite has no MEDIAN(), and AVG() is misleading
-- on view counts, which are dominated by a handful of viral videos:
--
--   stats = (df.groupby('playlist_title')
--              .agg(n=('video_id', 'size'),
--                   median_views=('view_count', 'median'),
--                   median_eng=('engagement_rate', 'median'))
--              .query('n >= 20')
--              .sort_values('median_views', ascending=False))

SELECT
  playlists.title       AS playlist_title,
  playlists.item_count  AS playlist_size,

  videos.video_id,
  videos.title          AS video_title,
  videos.published_at,
  videos.view_count,
  videos.like_count,
  videos.comment_count,

  ROUND(
    (videos.like_count + videos.comment_count) * 1.0
      / NULLIF(videos.view_count, 0),
  5) AS engagement_rate,

  video_tabs.tab        -- lets you cut subject BY format: "Match Previews as a Short"

FROM playlist_items

JOIN playlists
  ON playlists.playlist_id = playlist_items.playlist_id

-- Plain JOIN on purpose, unlike video_labels.sql: this drops the ~100 playlist
-- entries pointing at videos from OTHER channels, which have no stats of ours
-- to report. That is why 3,482 memberships become 3,370 rows here.
JOIN videos
  ON videos.video_id = playlist_items.video_id

LEFT JOIN video_tabs
  ON video_tabs.video_id = videos.video_id

ORDER BY playlists.title, videos.published_at DESC;
