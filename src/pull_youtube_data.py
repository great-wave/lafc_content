"""
Pulls channel, video, playlist and tab data for youtube.com/@LAFC using the
YouTube Data API v3, and saves everything into a local SQLite database.

Usage:
    python src/pull_youtube_data.py

Requires a YOUTUBE_API_KEY in a .env file at the project root (see .env.example).

WHAT GETS PULLED
    channel_snapshots  one row per pull, so channel growth can be tracked
    videos             one row per video, overwritten each pull
    playlists          the channel's PUBLIC playlists (private ones are invisible)
    playlist_items     which videos are in which playlists -- the SUBJECT label
    video_tabs         short / longform / live -- the FORMAT label

TWO LABEL AXES
    Subject and format are different questions and are stored separately. A
    40-second interview clip is both "an interview" (subject, from its playlist)
    and "a Short" (format, from its tab). Collapsing them into one column loses
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
    fetch_tabs() asserts they still reconstitute the full uploads playlist and
    warns loudly if they don't.

    Duration is not a usable substitute: on this channel it misclassifies ~15%
    of videos, and roughly half of everything under a minute is not a Short.
"""

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
TAB_PREFIXES = {"UULF": "longform", "UUSH": "short", "UULV": "live"}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "lafc_content.db"

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

CREATE TABLE IF NOT EXISTS video_tabs (
    video_id        TEXT PRIMARY KEY,
    tab             TEXT NOT NULL,   -- 'short' | 'longform' | 'live'
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


def fetch_tabs(api_key, channel_id, all_video_ids):
    """
    Map every video to its channel tab ('short' / 'longform' / 'live').

    Uses the undocumented per-tab uploads playlists (see module docstring). The
    three tabs should exactly reconstitute the uploads playlist; if they stop
    doing so, the prefix scheme has changed and we say so rather than silently
    returning partial data.
    """
    suffix = channel_id[2:]  # strip the leading "UC"
    tabs = {}

    for prefix, tab in TAB_PREFIXES.items():
        try:
            for video_id in fetch_playlist_video_ids(api_key, prefix + suffix):
                tabs[video_id] = tab
        except requests.HTTPError as exc:
            print(f"  WARNING: tab playlist {prefix}* unavailable ({exc}) — skipping.")

    missing = set(all_video_ids) - set(tabs)
    if missing:
        print(f"  WARNING: {len(missing)} of {len(all_video_ids)} uploads have no tab. "
              "The UULF/UUSH/UULV prefix scheme may have changed.")
    return tabs


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


def save_tabs(conn, tabs, fetched_at):
    """Write the short/longform/live label for each video."""
    conn.executemany(
        "INSERT OR REPLACE INTO video_tabs (video_id, tab, fetched_at) VALUES (?, ?, ?)",
        [(video_id, tab, fetched_at) for video_id, tab in tabs.items()],
    )


def save_to_database(channel, videos, playlists, memberships, tabs, fetched_at):
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
    save_tabs(conn, tabs, fetched_at)

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

    print("Collecting channel tabs (short / longform / live)...")
    tabs = fetch_tabs(api_key, channel_id, video_ids)
    counts = {tab: sum(1 for t in tabs.values() if t == tab) for tab in TAB_PREFIXES.values()}
    print(f"  {counts}")

    print("Collecting playlists...")
    playlists = fetch_playlists(api_key, channel_id)
    memberships = fetch_playlist_memberships(api_key, playlists)
    total_memberships = sum(len(v) for v in memberships.values())
    print(f"  {len(playlists)} playlists, {total_memberships} memberships.")

    save_to_database(channel, videos, playlists, memberships, tabs, fetched_at)
    print(f"Saved {len(videos)} videos, {len(playlists)} playlists, "
          f"{total_memberships} memberships and {len(tabs)} tab labels to {DB_PATH}")


if __name__ == "__main__":
    main()
