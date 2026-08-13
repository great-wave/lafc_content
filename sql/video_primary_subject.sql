-- ONE ROW PER VIDEO: a single subject label, for charts and per-video stats.
--
-- THE JUDGMENT CALL
-- 84% of playlisted videos are in exactly one playlist, so most rows need no
-- decision. For the other ~16% we keep the SMALLEST playlist, on the theory
-- that a niche playlist is a more informative label than a catch-all: a video
-- in both "Highlights" (770 videos) and "The Vela Vault" (27) is better
-- described as Vela content than as a highlight.
--
-- This is an opinion, not a fact, which is why it lives in a query rather than
-- as a column in the database. To change the rule -- say, to a hand-ordered
-- priority list -- edit the ORDER BY below and every downstream cut follows.
--
-- Ties on item_count are broken by playlist_id so the result is deterministic.
-- Videos in no playlist are absent entirely; join with LEFT JOIN to keep them.

SELECT
  video_id,
  playlist_title AS primary_subject,
  n_playlists                    -- how many playlists this video is in

FROM (
  SELECT
    pi.video_id,
    p.title AS playlist_title,

    COUNT(*) OVER (PARTITION BY pi.video_id) AS n_playlists,

    -- Rank this video's playlists smallest-first; we keep rank 1.
    ROW_NUMBER() OVER (
      PARTITION BY pi.video_id
      ORDER BY p.item_count ASC, p.playlist_id ASC
    ) AS rank_in_video

  FROM playlist_items pi

  JOIN playlists p
    ON p.playlist_id = pi.playlist_id
)

WHERE rank_in_video = 1;
