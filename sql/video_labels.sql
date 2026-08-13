-- THE MAIN ANALYSIS TABLE: every video, with both label axes attached.
-- Exactly one row per video, so medians and counts are safe.
--
-- TWO INDEPENDENT AXES
--   tab             FORMAT  -- short / longform / live, from the channel's tabs
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

WITH primary_subject AS (
  -- Mirrors sql/video_primary_subject.sql -- smallest playlist wins.
  -- Duplicated rather than imported so this file runs standalone.
  SELECT video_id, playlist_title, n_playlists
  FROM (
    SELECT
      pi.video_id,
      p.title AS playlist_title,
      COUNT(*) OVER (PARTITION BY pi.video_id) AS n_playlists,
      ROW_NUMBER() OVER (
        PARTITION BY pi.video_id
        ORDER BY p.item_count ASC, p.playlist_id ASC
      ) AS rank_in_video
    FROM playlist_items pi
    JOIN playlists p ON p.playlist_id = pi.playlist_id
  )
  WHERE rank_in_video = 1
),

all_subjects AS (
  -- Every playlist a video belongs to, flattened to one string. Keeps the
  -- labels the primary_subject rule discarded, without multiplying rows.
  SELECT
    pi.video_id,
    GROUP_CONCAT(p.title, ' | ') AS all_playlists
  FROM playlist_items pi
  JOIN playlists p ON p.playlist_id = pi.playlist_id
  GROUP BY pi.video_id
)

SELECT
  v.video_id,
  v.title,
  v.description,
  v.published_at,
  v.duration,
  v.view_count,
  v.like_count,
  v.comment_count,

  -- NULLIF guards against a zero-view video making this a division by zero.
  ROUND((v.like_count + v.comment_count) * 1.0 / NULLIF(v.view_count, 0), 5)
    AS engagement_rate,

  t.tab,                                  -- FORMAT axis
  ps.playlist_title AS primary_subject,   -- SUBJECT axis
  ps.n_playlists,
  s.all_playlists

FROM videos v

LEFT JOIN video_tabs t
  ON t.video_id = v.video_id

LEFT JOIN primary_subject ps
  ON ps.video_id = v.video_id

LEFT JOIN all_subjects s
  ON s.video_id = v.video_id

ORDER BY v.published_at DESC;
