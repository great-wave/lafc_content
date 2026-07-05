"""
LAYER 1 (raw pull) — LAFC's MLS match data from the undocumented public ESPN API.

This is the ONLY script that touches the network. It pulls, for each requested
season, the WHOLE league's match results (not just LAFC's). We need the whole
league because the standings-derivation step (src/derive_standings.py) walks a
league-wide running tally to reconstruct every team's point-in-time standing —
and that is impossible from LAFC's games alone. LAFC's own match log is simply
the LAFC-filtered subset of the league-wide `matches` table.

Nothing is computed here beyond flattening ESPN's JSON into tidy rows. All
result/standings logic lives in the separate derivation step.

The ESPN endpoints are undocumented and brittle, so the parser is deliberately
defensive: it fails LOUDLY (ESPNShapeError) if the response *shape* changes,
while still tolerating legitimately-absent data (e.g. a not-yet-played match has
no score). No API key is required.

Usage:
    python src/pull_match_data.py --season 2024
    python src/pull_match_data.py --season 2018-2026   # inclusive range

Writes three raw tables into data/lafc_content.db:
    teams              one row per team per season (id, name, conference)
    matches            one row per MLS match (league-wide, team-neutral)
    standings_official ESPN's own final/current table, kept for verification
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ESPN uses two different API hosts/paths for these resources. Kept as constants
# so a future shape/host change is a one-line edit, not a hunt through the code.
LEAGUE = "usa.1"  # ESPN's league slug for Major League Soccer
SCHEDULE_API = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LEAGUE}"
STANDINGS_API = f"https://site.api.espn.com/apis/v2/sports/soccer/{LEAGUE}"
LAFC_ABBR = "LAFC"  # we resolve LAFC's numeric team id from the data, never hardcode it

# A polite User-Agent; some ESPN edge nodes reject the bare python-requests UA.
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (LAFC-Content-Scoreboard portfolio project)"}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "lafc_content.db"

# kickoff_utc is stored to match videos.published_at exactly: UTC, ISO-8601 with a
# 'Z' suffix, SECOND precision (e.g. 2024-02-25T00:30:00Z). That lets the later
# video<->match join be a plain string comparison in one timezone.
SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id     TEXT NOT NULL,
    season      INTEGER NOT NULL,
    name        TEXT,
    abbr        TEXT,
    conference  TEXT,               -- 'Western Conference' / 'Eastern Conference'
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (team_id, season)
);

CREATE TABLE IF NOT EXISTS matches (
    event_id     TEXT PRIMARY KEY,  -- ESPN event id; stable => idempotent upserts
    season       INTEGER NOT NULL,
    season_type  TEXT,              -- ESPN seasonType.name, e.g. 'Regular Season'
    kickoff_utc  TEXT,              -- UTC 'Z' second precision, like videos.published_at
    completed    INTEGER,           -- 1 if the match has finished, else 0
    status       TEXT,              -- ESPN status name, e.g. STATUS_FULL_TIME
    home_team_id TEXT,
    home_team    TEXT,
    home_abbr    TEXT,
    away_team_id TEXT,
    away_team    TEXT,
    away_abbr    TEXT,
    home_score   INTEGER,           -- NULL when the match has not been played yet
    away_score   INTEGER,
    fetched_at   TEXT NOT NULL
);

-- ESPN's authoritative table as it stood at pull time. Not used to compute our
-- standings (that is derived independently); kept purely as a verification oracle.
CREATE TABLE IF NOT EXISTS standings_official (
    season       INTEGER NOT NULL,
    team_id      TEXT NOT NULL,
    conference   TEXT,
    rank         INTEGER,
    points       INTEGER,
    games_played INTEGER,
    wins         INTEGER,
    goals_for    INTEGER,           -- ESPN calls this 'pointsFor' in soccer JSON
    goals_against INTEGER,          -- ESPN calls this 'pointsAgainst'
    fetched_at   TEXT NOT NULL,
    PRIMARY KEY (season, team_id)
);
"""


class ESPNShapeError(RuntimeError):
    """Raised when ESPN's JSON does not match the shape we parse. Fail loudly."""


def _require(condition, msg):
    """Assert an assumption about the ESPN payload, raising a clear error if broken."""
    if not condition:
        raise ESPNShapeError(msg)


def fetch_json(url):
    """GET a URL and return parsed JSON, failing loudly on HTTP or decode errors."""
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as exc:  # not JSON => the endpoint changed or is erroring
        raise ESPNShapeError(f"Expected JSON from {url}, got something else") from exc


def normalize_kickoff(espn_date):
    """
    Turn ESPN's kickoff string into UTC 'Z' second-precision to match videos.published_at.

    ESPN returns minute precision like '2024-02-25T00:30Z'; we normalise any
    precision to '2024-02-25T00:30:00Z' so the column is uniform and directly
    comparable to the YouTube timestamps.
    """
    if not espn_date:
        return None
    # fromisoformat understands the offset form but not a trailing 'Z', so swap it.
    dt = datetime.fromisoformat(espn_date.replace("Z", "+00:00"))
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _stats_by_name(entry):
    """Flatten a standings entry's stats list into a {name: value} dict."""
    stats = entry.get("stats")
    _require(isinstance(stats, list), "standings entry missing 'stats' list")
    return {s.get("name"): s.get("value") for s in stats if "name" in s}


def parse_standings(payload, season):
    """
    Parse the standings payload into (teams, official_rows).

    Returns:
        teams: list of dicts {team_id, name, abbr, conference} — one per team,
               and the definitive list of teams to pull schedules for.
        official_rows: list of dicts capturing ESPN's own table for verification.
    ESPN nests teams under `children` (one child per conference).
    """
    children = payload.get("children")
    _require(isinstance(children, list) and children,
             f"standings for {season}: expected a non-empty 'children' (conferences) list")

    teams, official_rows = [], []
    for child in children:
        conference = child.get("name")
        entries = child.get("standings", {}).get("entries")
        _require(isinstance(entries, list) and entries,
                 f"standings for {season}: conference '{conference}' has no entries")

        for entry in entries:
            team = entry.get("team", {})
            team_id = team.get("id")
            _require(team_id, f"standings for {season}: an entry is missing team.id")

            teams.append({
                "team_id": str(team_id),
                "name": team.get("displayName"),
                "abbr": team.get("abbreviation"),
                "conference": conference,
            })

            # ESPN soccer naming quirk: the 'points' stat is league table points;
            # 'pointsFor'/'pointsAgainst' are GOALS for/against (not points).
            s = _stats_by_name(entry)
            official_rows.append({
                "season": season,
                "team_id": str(team_id),
                "conference": conference,
                "rank": _as_int(s.get("rank")),
                "points": _as_int(s.get("points")),
                "games_played": _as_int(s.get("gamesPlayed")),
                "wins": _as_int(s.get("wins")),
                "goals_for": _as_int(s.get("pointsFor")),
                "goals_against": _as_int(s.get("pointsAgainst")),
            })
    return teams, official_rows


def _as_int(value):
    """Coerce ESPN's float-ish stat values (e.g. 34.0) to int, tolerating None."""
    if value is None:
        return None
    return int(round(float(value)))


def _score_value(competitor):
    """
    Pull an integer score out of a competitor, or None if the match is unplayed.

    ESPN usually gives score as {'value': 2.0, 'displayValue': '2', ...}; we treat
    a missing/None value as 'not played yet' rather than an error, because that is
    a legitimate state for future fixtures.
    """
    score = competitor.get("score")
    if score is None:
        return None
    if isinstance(score, dict):
        return _as_int(score.get("value"))
    # Fallback for the occasional bare numeric/string score.
    try:
        return int(float(score))
    except (TypeError, ValueError):
        return None


def parse_event(event, season):
    """
    Flatten one ESPN schedule event into a team-neutral `matches` row (dict).

    Returns None for anything that isn't a two-team competition we can read.
    Raises ESPNShapeError if the parts we *do* rely on are structurally missing.
    """
    event_id = event.get("id")
    _require(event_id, f"{season}: a schedule event is missing its 'id'")

    competitions = event.get("competitions")
    _require(isinstance(competitions, list) and competitions,
             f"event {event_id}: missing 'competitions'")
    comp = competitions[0]

    competitors = comp.get("competitors")
    _require(isinstance(competitors, list) and len(competitors) == 2,
             f"event {event_id}: expected exactly 2 competitors, got "
             f"{len(competitors) if isinstance(competitors, list) else 'none'}")

    # Split the two competitors by their home/away role.
    sides = {}
    for c in competitors:
        role = c.get("homeAway")
        _require(role in ("home", "away"),
                 f"event {event_id}: competitor has unexpected homeAway={role!r}")
        team = c.get("team", {})
        _require(team.get("id"), f"event {event_id}: a competitor is missing team.id")
        sides[role] = {
            "team_id": str(team["id"]),
            "team": team.get("displayName"),
            "abbr": team.get("abbreviation"),
            "score": _score_value(c),
        }
    _require("home" in sides and "away" in sides,
             f"event {event_id}: could not identify both a home and an away side")

    status_type = comp.get("status", {}).get("type", {})
    home, away = sides["home"], sides["away"]
    return {
        "event_id": str(event_id),
        "season": season,
        "season_type": event.get("seasonType", {}).get("name"),
        "kickoff_utc": normalize_kickoff(comp.get("date") or event.get("date")),
        "completed": 1 if status_type.get("completed") else 0,
        "status": status_type.get("name"),
        "home_team_id": home["team_id"],
        "home_team": home["team"],
        "home_abbr": home["abbr"],
        "away_team_id": away["team_id"],
        "away_team": away["team"],
        "away_abbr": away["abbr"],
        "home_score": home["score"],
        "away_score": away["score"],
    }


def get_connection():
    """Open the SQLite DB (creating the data dir + tables if needed)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def upsert_teams(conn, teams, season, fetched_at):
    """Idempotently write the season's teams (PK = team_id+season)."""
    conn.executemany(
        """
        INSERT OR REPLACE INTO teams
            (team_id, season, name, abbr, conference, fetched_at)
        VALUES (:team_id, :season, :name, :abbr, :conference, :fetched_at)
        """,
        [{**t, "season": season, "fetched_at": fetched_at} for t in teams],
    )


def upsert_official(conn, official_rows, fetched_at):
    """Idempotently write ESPN's official table snapshot (PK = season+team_id)."""
    conn.executemany(
        """
        INSERT OR REPLACE INTO standings_official
            (season, team_id, conference, rank, points, games_played,
             wins, goals_for, goals_against, fetched_at)
        VALUES (:season, :team_id, :conference, :rank, :points, :games_played,
                :wins, :goals_for, :goals_against, :fetched_at)
        """,
        [{**r, "fetched_at": fetched_at} for r in official_rows],
    )


def upsert_match(conn, row, fetched_at):
    """Idempotently write one match (PK = event_id, so re-pulls never duplicate)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO matches
            (event_id, season, season_type, kickoff_utc, completed, status,
             home_team_id, home_team, home_abbr,
             away_team_id, away_team, away_abbr,
             home_score, away_score, fetched_at)
        VALUES (:event_id, :season, :season_type, :kickoff_utc, :completed, :status,
                :home_team_id, :home_team, :home_abbr,
                :away_team_id, :away_team, :away_abbr,
                :home_score, :away_score, :fetched_at)
        """,
        {**row, "fetched_at": fetched_at},
    )


def pull_season(conn, season, fetched_at):
    """Pull one season's teams, official table, and every league match."""
    print(f"\n=== Season {season} ===")

    # 1) Standings gives us the definitive team list + conference + official table.
    standings = fetch_json(f"{STANDINGS_API}/standings?season={season}")
    teams, official_rows = parse_standings(standings, season)
    upsert_teams(conn, teams, season, fetched_at)
    upsert_official(conn, official_rows, fetched_at)
    print(f"  teams: {len(teams)} across "
          f"{len({t['conference'] for t in teams})} conferences")

    lafc = next((t for t in teams if t["abbr"] == LAFC_ABBR), None)
    _require(lafc, f"season {season}: could not find LAFC (abbr {LAFC_ABBR}) in standings")
    print(f"  LAFC resolved to team_id={lafc['team_id']} ({lafc['conference']})")

    # 2) Pull every team's schedule and union the matches (dedupe via event_id PK).
    #    A match appears in both teams' schedules; INSERT OR REPLACE collapses them.
    seen_events, flagged = set(), []
    for t in teams:
        payload = fetch_json(f"{SCHEDULE_API}/teams/{t['team_id']}/schedule?season={season}")
        events = payload.get("events", [])
        for event in events:
            row = parse_event(event, season)
            if row is None:
                continue
            upsert_match(conn, row, fetched_at)
            seen_events.add(row["event_id"])
            # Flag data that looks internally inconsistent: a 'finished' match with
            # a missing score is ambiguous and should not be trusted downstream.
            if row["completed"] and (row["home_score"] is None or row["away_score"] is None):
                flagged.append(row["event_id"])

    conn.commit()
    print(f"  matches stored (unique events): {len(seen_events)}")
    if flagged:
        print(f"  ⚠ {len(flagged)} completed match(es) missing a score: "
              f"{', '.join(sorted(set(flagged)))}")


def parse_seasons(arg):
    """Parse '2024' or an inclusive range '2018-2026' into a list of years."""
    if "-" in arg:
        start_s, end_s = arg.split("-", 1)
        start, end = int(start_s), int(end_s)
        if start > end:
            start, end = end, start
        return list(range(start, end + 1))
    return [int(arg)]


def main():
    parser = argparse.ArgumentParser(description="Pull LAFC/MLS match data from ESPN.")
    parser.add_argument(
        "--season", required=True,
        help="Season year (e.g. 2024) or inclusive range (e.g. 2018-2026).",
    )
    args = parser.parse_args()

    try:
        seasons = parse_seasons(args.season)
    except ValueError:
        sys.exit(f"Could not parse --season {args.season!r}; use e.g. 2024 or 2018-2026.")

    # Pull-time bookkeeping stamp, matching the existing code's fetched_at style.
    fetched_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        for season in seasons:
            pull_season(conn, season, fetched_at)
    except ESPNShapeError as exc:
        # A shape change is a hard failure: better to stop loudly than store garbage.
        sys.exit(f"\nESPN response shape changed — aborting:\n  {exc}")
    finally:
        conn.close()

    print(f"\nDone. Wrote to {DB_PATH}")
    print("Next: python src/derive_standings.py --season " + args.season)


if __name__ == "__main__":
    main()
