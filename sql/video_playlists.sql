-- LONG FORM: one row per (video, playlist) membership.
--
-- This is the raw subject axis. A video in three playlists appears THREE times
-- here -- that is correct, not a bug, but it means:
--
--   SAFE   : GROUP BY playlist_title  (each group answers its own question)
--   UNSAFE : any per-video statistic, or summing counts across playlists
--
-- For per-video work use video_primary_subject.sql or video_labels.sql instead,
-- both of which return exactly one row per video.
--
-- Note ~100 rows point at videos published by OTHER channels (LAFC added them
-- to their playlists). Those drop out when you join to `videos`, which is why
-- the row count shrinks from ~3,482 to ~3,370.

SELECT
  pi.video_id,
  pi.playlist_id,
  p.title          AS playlist_title,
  pi.position,                       -- order within the playlist (episode 1, 2, 3...)
  p.item_count     AS playlist_size  -- used by the "most specific label" rule

FROM playlist_items pi

JOIN playlists p
  ON p.playlist_id = pi.playlist_id

ORDER BY p.title, pi.position;
