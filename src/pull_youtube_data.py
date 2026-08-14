"""
Pulls channel, video, playlist and format data for youtube.com/@LAFC using the
YouTube Data API v3, and saves everything into a local SQLite database.

Usage:
    python src/pull_youtube_data.py

Requires a YOUTUBE_API_KEY in a .env file at the project root (see .env.example).

WHAT GETS PULLED
    channel_snapshots  one row per pull, so channel growth can be tracked
    videos             one row per video, overwritten each pull
    playlists          the channel's PUBLIC playlists (private ones are invisible)
    playlist_items     which videos are in which playlists -- the SUBJECT label
    video_formats      short / horizontal / live -- the FORMAT label

TWO LABEL AXES
    Subject and format are different questions and are stored separately. A
    40-second interview clip is both "an interview" (subject, from its playlist)
    and "a Short" (format, from its channel tab). Collapsing them into one column loses
    one of those facts.

    Subject is many-to-many: a video can sit in several playlists, so membership
    lives in its own table keyed on the PAIR (playlist_id, video_id) rather than
    as a column on `videos`. Note that joining it to `videos` multiplies rows --
    see sql/ for queries that collapse it safely.

DETECTING SHORTS
    The API has no isShort field, and fileDetails.videoStreams[].aspectRatio is
    only returned to the video's owner. Instead we use the per-tab uploads
    playlists: swapping the "UC" prefix of a channel ID for UULF / UUSH / UULV
    yields the Videos / Shorts / Live tabs. These prefixes are UNDOCUMENTED, so
    fetch_formats() asserts they still reconstitute the full uploads playlist and
    warns loudly if they don't.

    Duration is not a usable substitute: on this channel it misclassifies ~15%
    of videos, and roughly half of everything under a minute is not a Short.
"""

import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CHANNEL_HANDLE = "LAFC"  # the @LAFC part of the channel URL, no "@"
API_BASE = "https://www.googleapis.com/youtube/v3"
REQUEST_TIMEOUT = 60

# A full pull is ~350 requests, so a single transient timeout must not throw the
# whole run away. Retries cover read/connect errors and the usual transient HTTP
# codes, backing off 1s, 2s, 4s... The session also reuses connections, which
# makes the pull noticeably faster.
SESSION = requests.Session()
SESSION.mount(
    "https://",
    HTTPAdapter(max_retries=Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )),
)

# Channel IDs start with "UC". Swapping that prefix gives the per-tab uploads
# playlists. Undocumented but stable; verified against the /shorts/ URL probe.
#
# NOTE ON NAMING: YouTube calls the UULF bucket "long form", but that describes
# it badly -- 509 of those videos are under a minute and the shortest is 11
# seconds. What actually separates a Short from the rest is ORIENTATION (Shorts
# are vertical, served in the swipe feed), not length, so we call it
# 'horizontal'. Live streams are horizontal too, but they are a distinct
# surface, so they keep their own value.
FORMAT_PREFIXES = {"UULF": "horizontal", "UUSH": "short", "UULV": "live"}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "lafc_content.db"

# Shared views the analysis queries join to. Read from the .sql file rather than
# repeated here, so the smallest-playlist rule has exactly one definition.
VIEWS_PATH = PROJECT_ROOT / "sql" / "views.sql"

# playlist -> content_type, hand-authored. The CSV is the source of truth and is
# tracked in git; the table below is only how SQL gets to read it.
PLAYLIST_TYPES_PATH = PROJECT_ROOT / "data" / "playlist_types.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS channel_snapshots (
    channel_id      TEXT NOT NULL,
    title           TEXT,
    handle          TEXT,
    published_at    TEXT,
    subscriber_count INTEGER,
    view_count      INTEGER,
    video_count     INTEGER,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (channel_id, fetched_at)
);

CREATE TABLE IF NOT EXISTS videos (
    video_id        TEXT PRIMARY KEY,
    channel_id      TEXT NOT NULL,
    title           TEXT,
    description     TEXT,
    published_at    TEXT,
    duration        TEXT,
    view_count      INTEGER,
    like_count      INTEGER,
    comment_count   INTEGER,
    fetched_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlists (
    playlist_id     TEXT PRIMARY KEY,
    channel_id      TEXT NOT NULL,
    title           TEXT,
    description     TEXT,
    item_count      INTEGER,
    fetched_at      TEXT NOT NULL
);

-- Many-to-many: the key is the PAIR, because a video can be in several
-- playlists (16% of covered videos are; one is in seven).
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id     TEXT NOT NULL,
    video_id        TEXT NOT NULL,
    position        INTEGER,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (playlist_id, video_id)
);

-- Lets "which playlists is this video in?" use an index instead of a scan.
CREATE INDEX IF NOT EXISTS idx_playlist_items_video
    ON playlist_items (video_id);

CREATE TABLE IF NOT EXISTS video_formats (
    video_id        TEXT PRIMARY KEY,
    format          TEXT NOT NULL,   -- 'short' | 'horizontal' | 'live'
    fetched_at      TEXT NOT NULL
);
"""


def get_api_key():
    """Load the API key from .env and fail loudly (without printing it) if missing."""
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        sys.exit("Missing YOUTUBE_API_KEY. Copy .env.example to .env and add your key.")
    return api_key


def paged_get(api_key, endpoint, **params):
    """Yield every item across all pages of a list endpoint (50 per request)."""
    page_token = None
    while True:
        query = {**params, "maxResults": 50, "key": api_key}
        if page_token:
            query["pageToken"] = page_token

        resp = SESSION.get(f"{API_BASE}/{endpoint}", params=query, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        yield from data.get("items", [])

        page_token = data.get("nextPageToken")
        if not page_token:
            break


def fetch_channel(api_key):
    """Look up the channel by its @handle and return its snippet/stats/contentDetails."""
    resp = SESSION.get(
        f"{API_BASE}/channels",
        params={
            "part": "snippet,statistics,contentDetails",
            "forHandle": CHANNEL_HANDLE,
            "key": api_key,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        sys.exit(f"No channel found for handle @{CHANNEL_HANDLE}")
    return items[0]


def fetch_playlist_video_ids(api_key, playlist_id):
    """Every video ID in a playlist, in order."""
    return [
        item["contentDetails"]["videoId"]
        for item in paged_get(api_key, "playlistItems",
                              part="contentDetails", playlistId=playlist_id)
    ]


def fetch_video_details(api_key, video_ids):
    """Fetch snippet/statistics/contentDetails for videos, 50 IDs at a time (API limit)."""
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = SESSION.get(
            f"{API_BASE}/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "key": api_key,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        videos.extend(resp.json().get("items", []))
    return videos


def fetch_playlists(api_key, channel_id):
    """The channel's PUBLIC playlists. Private/unlisted ones are invisible to an API key."""
    return list(paged_get(api_key, "playlists",
                          part="snippet,contentDetails", channelId=channel_id))


def fetch_playlist_memberships(api_key, playlists):
    """{playlist_id: [(video_id, position), ...]} for every playlist."""
    memberships = {}
    for i, playlist in enumerate(playlists, start=1):
        playlist_id = playlist["id"]
        # position lives in snippet, so we need it as well as contentDetails.
        memberships[playlist_id] = [
            (item["contentDetails"]["videoId"], item["snippet"].get("position"))
            for item in paged_get(api_key, "playlistItems",
                                  part="snippet,contentDetails", playlistId=playlist_id)
        ]
        # This loop is ~110 requests, so show progress rather than sitting silent.
        if i % 10 == 0 or i == len(playlists):
            done = sum(len(v) for v in memberships.values())
            print(f"  {i}/{len(playlists)} playlists, {done} memberships")
    return memberships


def fetch_formats(api_key, channel_id, all_video_ids):
    """
    Map every video to its delivery format ('short' / 'horizontal' / 'live').

    The values come from the channel's Videos / Shorts / Live tabs.

    Uses the undocumented per-tab uploads playlists (see module docstring). The
    three tabs should exactly reconstitute the uploads playlist; if they stop
    doing so, the prefix scheme has changed and we say so rather than silently
    returning partial data.
    """
    suffix = channel_id[2:]  # strip the leading "UC"
    formats = {}

    for prefix, video_format in FORMAT_PREFIXES.items():
        try:
            for video_id in fetch_playlist_video_ids(api_key, prefix + suffix):
                formats[video_id] = video_format
        except requests.HTTPError as exc:
            print(f"  WARNING: tab playlist {prefix}* unavailable ({exc}) — skipping.")

    missing = set(all_video_ids) - set(formats)
    if missing:
        print(f"  WARNING: {len(missing)} of {len(all_video_ids)} uploads have no format. "
              "The UULF/UUSH/UULV prefix scheme may have changed.")
    return formats


def save_playlists(conn, channel_id, playlists, memberships, fetched_at):
    """Write playlists and their memberships."""
    for playlist in playlists:
        snippet = playlist["snippet"]
        conn.execute(
            """
            INSERT OR REPLACE INTO playlists
                (playlist_id, channel_id, title, description, item_count, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                playlist["id"],
                channel_id,
                snippet.get("title"),
                snippet.get("description"),
                playlist["contentDetails"].get("itemCount"),
                fetched_at,
            ),
        )

        # Replace memberships wholesale. INSERT OR REPLACE can update a row that
        # still exists but cannot remove one that doesn't, so a video pulled out
        # of a playlist upstream would otherwise linger here forever.
        conn.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist["id"],))

        # YouTube allows the same video to sit in a playlist more than once (35
        # cases on this channel, mostly in Highlights). For labelling purposes
        # that is still ONE membership, so keep the first appearance -- the API
        # returns items in playlist order, so that is also the lowest position.
        deduped = {}
        for video_id, position in memberships.get(playlist["id"], []):
            if video_id not in deduped:
                deduped[video_id] = position

        conn.executemany(
            """
            INSERT INTO playlist_items (playlist_id, video_id, position, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            [(playlist["id"], video_id, position, fetched_at)
             for video_id, position in deduped.items()],
        )


def save_formats(conn, formats, fetched_at):
    """Write the short/horizontal/live format label for each video."""
    conn.executemany(
        "INSERT OR REPLACE INTO video_formats (video_id, format, fetched_at) VALUES (?, ?, ?)",
        [(video_id, video_format, fetched_at) for video_id, video_format in formats.items()],
    )


def load_playlist_types(conn):
    """Load data/playlist_types.csv into the playlist_types table.

    This is the CONTENT TYPE label: 56 hand-authored rows, one per playlist,
    which the analysis query joins through whichever playlist labelled a video.
    It replaced a title classifier that read the topic of a video rather than
    its format (Finding 7 in docs/findings.md).

    The table is dropped and rewritten so the CSV is unambiguously the source of
    truth -- editing a row and re-running the pull is the whole update path, and
    a row deleted from the CSV disappears here too.
    """
    with open(PLAYLIST_TYPES_PATH, newline="", encoding="utf-8") as f:
        rows = [
            (r["playlist_title"], r["content_type"], r.get("kind"), r.get("status"))
            for r in csv.DictReader(f)
        ]

    conn.execute("DROP TABLE IF EXISTS playlist_types")
    conn.execute(
        """
        CREATE TABLE playlist_types (
            playlist_title TEXT PRIMARY KEY,
            content_type   TEXT,
            kind           TEXT,
            status         TEXT
        )
        """
    )
    conn.executemany("INSERT INTO playlist_types VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def create_views(conn):
    """(Re)create the shared views from sql/views.sql.

    Views store no rows, so rebuilding them is free and they always reflect the
    playlist data we just wrote. The file drops each view before creating it,
    which makes this safe to run on every pull.
    """
    conn.executescript(VIEWS_PATH.read_text())


def save_to_database(channel, videos, playlists, memberships, formats, fetched_at):
    """Write every table for this pull, creating them if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    snippet = channel["snippet"]
    stats = channel["statistics"]
    conn.execute(
        """
        INSERT OR REPLACE INTO channel_snapshots
            (channel_id, title, handle, published_at, subscriber_count,
             view_count, video_count, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            channel["id"],
            snippet.get("title"),
            CHANNEL_HANDLE,
            snippet.get("publishedAt"),
            int(stats.get("subscriberCount", 0)),
            int(stats.get("viewCount", 0)),
            int(stats.get("videoCount", 0)),
            fetched_at,
        ),
    )

    for video in videos:
        v_snippet = video["snippet"]
        v_stats = video.get("statistics", {})
        conn.execute(
            """
            INSERT OR REPLACE INTO videos
                (video_id, channel_id, title, description, published_at,
                 duration, view_count, like_count, comment_count, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video["id"],
                channel["id"],
                v_snippet.get("title"),
                v_snippet.get("description"),
                v_snippet.get("publishedAt"),
                video.get("contentDetails", {}).get("duration"),
                int(v_stats.get("viewCount", 0)),
                int(v_stats.get("likeCount", 0)),
                int(v_stats.get("commentCount", 0)),
                fetched_at,
            ),
        )

    save_playlists(conn, channel["id"], playlists, memberships, fetched_at)
    save_formats(conn, formats, fetched_at)
    load_playlist_types(conn)
    create_views(conn)

    conn.commit()
    conn.close()


def main():
    api_key = get_api_key()
    fetched_at = datetime.now(timezone.utc).isoformat()

    print(f"Looking up channel @{CHANNEL_HANDLE}...")
    channel = fetch_channel(api_key)
    channel_id = channel["id"]

    uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    print("Collecting video IDs from the uploads playlist...")
    video_ids = fetch_playlist_video_ids(api_key, uploads_playlist_id)
    print(f"Found {len(video_ids)} videos. Fetching stats...")
    videos = fetch_video_details(api_key, video_ids)

    print("Collecting video formats (short / horizontal / live)...")
    formats = fetch_formats(api_key, channel_id, video_ids)
    counts = {f: sum(1 for v in formats.values() if v == f) for f in FORMAT_PREFIXES.values()}
    print(f"  {counts}")

    print("Collecting playlists...")
    playlists = fetch_playlists(api_key, channel_id)
    memberships = fetch_playlist_memberships(api_key, playlists)
    total_memberships = sum(len(v) for v in memberships.values())
    print(f"  {len(playlists)} playlists, {total_memberships} memberships.")

    save_to_database(channel, videos, playlists, memberships, formats, fetched_at)
    print(f"Saved {len(videos)} videos, {len(playlists)} playlists, "
          f"{total_memberships} memberships and {len(formats)} format labels to {DB_PATH}")


if __name__ == "__main__":
    main()
