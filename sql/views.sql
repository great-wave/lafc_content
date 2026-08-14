-- SHARED VIEWS -- run this once against data/lafc_content.db before any query
-- that references the views below. src/pull_youtube_data.py runs it
-- automatically at the end of every pull, so a rebuilt database always has them.
--
--   sqlite3 data/lafc_content.db < sql/views.sql
--
--
-- WHY THESE EXIST. video_labels.sql, classified_videos_vs_lafc_match_context.sql
-- and playlist_performance.sql all need the same logic, and SQL has no way for
-- one file to import another. Before this file existed the logic was
-- copy-pasted into each one, which meant a single rule had several definitions
-- that had to be kept in sync by hand.
--
-- Each view is dropped first, so this file is safe to re-run.


-- ---------------------------------------------------------------------------
-- videos_with_engagement -- every column of `videos`, plus engagement_rate.
--
-- Use this instead of `videos` anywhere the engagement rate is wanted. It is
-- computed here rather than stored as a column in the videos table because it
-- is derived from three values in the same row: storing it would create a copy
-- that can disagree with its own inputs after a re-pull. A division is cheap
-- enough to redo on every query, and keeping it here means changing the
-- definition of engagement is a one-line edit rather than a schema migration.
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS videos_with_engagement;

CREATE VIEW videos_with_engagement AS

  SELECT
    videos.*,

    -- * 1.0 forces decimal division; without it SQLite does integer division on
    -- these integer columns and truncates every result to 0. NULLIF turns a zero
    -- view_count into NULL, so a video nobody watched returns NULL -- an honest
    -- "unknown" -- rather than raising a division-by-zero error.
    ROUND(
      (videos.like_count + videos.comment_count) * 1.0
        / NULLIF(videos.view_count, 0),
    5) AS engagement_rate

  FROM videos;


-- ---------------------------------------------------------------------------
-- THE PROBLEM THE NEXT TWO VIEWS SOLVE
-- playlist_items is many-to-many: a video in three playlists has three rows.
-- Joining it to videos directly would triple that video and break every median
-- and count. Both views collapse it to exactly one row per video first -- one
-- by picking a single winner, one by concatenating them all.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- smallest_playlist_per_video -- the one playlist used as a video's SUBJECT label.
--
-- THE ONE JUDGMENT CALL IN THE PROJECT.
-- 84% of playlisted videos are in exactly one playlist, so most need no
-- decision. For the other ~16% we keep the SMALLEST playlist, because a niche
-- playlist is a more informative label than a catch-all: a video in both
-- "Highlights" (770 videos) and "The Vela Vault" (27) is better described as
-- Vela content than as a highlight.
--
-- To change the rule, edit the ORDER BY below. Every downstream cut follows.
-- This is the only place it is defined.
--
-- item_count ASC puts the smallest playlist first; playlist_id ASC is an
-- arbitrary but STABLE tiebreaker, so two playlists of equal size can never
-- resolve differently between runs.
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS smallest_playlist_per_video;

CREATE VIEW smallest_playlist_per_video AS

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

  WHERE ranked_playlists.rank_in_video = 1;


-- ---------------------------------------------------------------------------
-- every_playlist_per_video -- every playlist a video is in, as one string.
--
-- Keeps the labels the smallest-playlist rule discarded visible for
-- spot-checks, without multiplying rows. Display only: do not filter or group
-- on it, and do not rely on the order, which SQLite does not guarantee.
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS every_playlist_per_video;

CREATE VIEW every_playlist_per_video AS

  SELECT
    playlist_items.video_id,
    GROUP_CONCAT(playlists.title, ' | ') AS all_playlists

  FROM playlist_items

  JOIN playlists
    ON playlists.playlist_id = playlist_items.playlist_id

  GROUP BY playlist_items.video_id;
