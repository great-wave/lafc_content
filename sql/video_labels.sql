-- ONE ROW PER VIDEO -- this is the main analysis table.
--

--
-- All videos - one row each, so medians and counts are safe.
--
--   format          FORMAT  -- short / horizontal / live, from the channel's tabs
--   playlist        SUBJECT -- which LAFC playlist it is filed under
--
-- Everything is LEFT JOINed, so all videos survive:
--   format          NULL if the tab prefixes ever stop covering the uploads
--   playlist        NULL for the ~22% of videos in no playlist (mostly Shorts)
--
-- To compare playlists against each other instead, use playlist_performance.sql,
-- which gives one row per membership so a video counts in every playlist it is in.


-- WITH creates named temporary results (CTEs) that the main query below can
-- treat as tables. They exist only for the life of this query.

WITH smallest_playlist_per_video AS (

  -- THE ONE JUDGMENT CALL IN THIS FILE.
  -- 84% of playlisted videos are in exactly one playlist, so most need no
  -- decision. For the other ~16% we keep the SMALLEST playlist, because a
  -- niche playlist is a more informative label than a catch-all: a video in
  -- both "Highlights" (770 videos) and "The Vela Vault" (27) is better
  -- described as Vela content than as a highlight.
  --
  -- To change that rule, edit the ORDER BY below and every downstream cut
  -- follows. This is the only place it is defined.

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

  -- Every playlist a video belongs to, flattened into one string. Keeps the
  -- labels the smallest-playlist rule discarded, without multiplying rows.
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

  -- NULLIF turns a zero view_count into NULL, so this returns NULL instead of
  -- raising a division-by-zero error.

  ROUND(
    (videos.like_count + videos.comment_count) * 1.0
      / NULLIF(videos.view_count, 0),
  5) AS engagement_rate,

  video_formats.format,                                         -- FORMAT axis
  smallest_playlist_per_video.playlist_title AS playlist,          -- SUBJECT axis
  smallest_playlist_per_video.n_playlists,
  every_playlist_per_video.all_playlists

FROM videos

-- LEFT JOIN keeps every row from `videos` even when the right side has no
-- match. A plain JOIN would silently drop the 815 videos with no playlist.

LEFT JOIN video_formats
  ON video_formats.video_id = videos.video_id

LEFT JOIN smallest_playlist_per_video
  ON smallest_playlist_per_video.video_id = videos.video_id

LEFT JOIN every_playlist_per_video
  ON every_playlist_per_video.video_id = videos.video_id

ORDER BY videos.published_at DESC;
