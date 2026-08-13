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
  p.title       AS playlist_title,
  p.item_count  AS playlist_size,

  v.video_id,
  v.title       AS video_title,
  v.published_at,
  v.view_count,
  v.like_count,
  v.comment_count,

  ROUND((v.like_count + v.comment_count) * 1.0 / NULLIF(v.view_count, 0), 5)
    AS engagement_rate,

  t.tab         -- lets you cut subject BY format: "Match Previews as a Short"

FROM playlist_items pi

JOIN playlists p
  ON p.playlist_id = pi.playlist_id

-- INNER JOIN on purpose: drops the ~100 playlist entries that point at videos
-- from other channels, which have no stats of ours to report.
JOIN videos v
  ON v.video_id = pi.video_id

LEFT JOIN video_tabs t
  ON t.video_id = v.video_id

ORDER BY p.title, v.published_at DESC;
