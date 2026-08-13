-- THE MAIN ANALYSIS TABLE: every video, with both label axes attached.
-- Exactly one row per video, so medians and counts are safe.
--
-- TWO INDEPENDENT AXES
--   tab             FORMAT  -- short / horizontal / live, from the channel's tabs
--   primary_subject SUBJECT -- what it is about, from its playlist
--
-- Keeping them separate is the point: a 40-second interview clip is both "an
-- interview" and "a Short". The old format_family fused the two, which is why
-- `social` became a catch-all.
--
-- Everything is LEFT JOINed, so all videos survive:
--   tab             NULL if the tab prefixes ever stop covering the uploads
--   primary_subject NULL for the ~22% of videos in no playlist (mostly Shorts)
--
-- NOTE: `duration` is raw ISO-8601 ("PT1M30S"). Parse it in pandas:
--   df['dur_min'] = pd.to_timedelta(df['duration']).dt.total_seconds() / 60


-- WITH creates named temporary results (CTEs) that the main query below can
-- treat as tables. They exist only for the life of this query.
WITH smallest_playlist_per_video AS (

  -- Mirrors sql/video_primary_subject.sql -- smallest playlist wins.
  -- Duplicated rather than imported so this file runs standalone.
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

  video_tabs.tab,                                         -- FORMAT axis
  smallest_playlist_per_video.playlist_title AS primary_subject,   -- SUBJECT axis
  smallest_playlist_per_video.n_playlists,
  every_playlist_per_video.all_playlists

FROM videos

-- LEFT JOIN keeps every row from `videos` even when the right side has no
-- match. A plain JOIN would silently drop the 815 videos with no playlist.
LEFT JOIN video_tabs
  ON video_tabs.video_id = videos.video_id

LEFT JOIN smallest_playlist_per_video
  ON smallest_playlist_per_video.video_id = videos.video_id

LEFT JOIN every_playlist_per_video
  ON every_playlist_per_video.video_id = videos.video_id

ORDER BY videos.published_at DESC;
