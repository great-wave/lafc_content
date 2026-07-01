"""
Pulls channel and video data for youtube.com/@LAFC using the YouTube Data API v3,
and saves everything into a local SQLite database.

Usage:
    python src/pull_youtube_data.py

Requires a YOUTUBE_API_KEY in a .env file at the project root (see .env.example).
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

CHANNEL_HANDLE = "LAFC"  # the @LAFC part of the channel URL, no "@"
API_BASE = "https://www.googleapis.com/youtube/v3"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "lafc_content.db"

# Channel-level snapshot: one row per pull, so we can track growth over time.
# Video rows: one per video, overwritten each pull so stats stay current.
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
"""


def get_api_key():
    """Load the API key from .env and fail loudly (without printing it) if missing."""
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        sys.exit("Missing YOUTUBE_API_KEY. Copy .env.example to .env and add your key.")
    return api_key


def fetch_channel(api_key):
    """Look up the channel by its @handle and return its snippet/stats/contentDetails."""
    resp = requests.get(
        f"{API_BASE}/channels",
        params={
            "part": "snippet,statistics,contentDetails",
            "forHandle": CHANNEL_HANDLE,
            "key": api_key,
        },
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        sys.exit(f"No channel found for handle @{CHANNEL_HANDLE}")
    return items[0]


def fetch_all_video_ids(api_key, uploads_playlist_id):
    """Page through the channel's uploads playlist and collect every video ID."""
    video_ids = []
    page_token = None
    while True:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(f"{API_BASE}/playlistItems", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        video_ids.extend(item["contentDetails"]["videoId"] for item in data.get("items", []))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def fetch_video_details(api_key, video_ids):
    """Fetch snippet/statistics/contentDetails for videos, 50 IDs at a time (API limit)."""
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = requests.get(
            f"{API_BASE}/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "key": api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        videos.extend(resp.json().get("items", []))
    return videos


def save_to_database(channel, videos, fetched_at):
    """Write the channel snapshot and video rows into SQLite, creating tables if needed."""
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

    conn.commit()
    conn.close()


def main():
    api_key = get_api_key()
    fetched_at = datetime.now(timezone.utc).isoformat()

    print(f"Looking up channel @{CHANNEL_HANDLE}...")
    channel = fetch_channel(api_key)

    uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    print("Collecting video IDs from the uploads playlist...")
    video_ids = fetch_all_video_ids(api_key, uploads_playlist_id)
    print(f"Found {len(video_ids)} videos. Fetching stats...")

    videos = fetch_video_details(api_key, video_ids)

    save_to_database(channel, videos, fetched_at)
    print(f"Saved channel snapshot and {len(videos)} videos to {DB_PATH}")


if __name__ == "__main__":
    main()
