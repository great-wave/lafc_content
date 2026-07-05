"""
LAYER 2 (derivation) — point-in-time league standings, embedded per LAFC match.

This script does NO network I/O. It reads the raw `matches` + `teams` tables
written by src/pull_match_data.py and reconstructs, for every LAFC match, the
standings context that existed *going into* that match — for both LAFC and its
opponent.

THE CORE IDEA (and the easy bug to avoid)
We walk the season's completed regular-season matches in chronological order,
carrying a league-wide running tally for EVERY team. For each match:

    1. If LAFC is playing, we first SNAPSHOT LAFC's and the opponent's tally as
       it stands right now — i.e. BEFORE this match is counted. That snapshot is
       the "pre-match" predictor state.
    2. THEN we fold this match's result into the tally.

Doing it in that order is what prevents a match's own result from leaking into
its own predictor row. A model trained on these rows only ever "sees" what was
known before kickoff.

We store the raw INGREDIENTS of each team's standing (points, games played,
wins, goals for, goals against) plus conference — never a single collapsed rank
number — so downstream you can compute points-per-game, form, rank, or anything
else yourself.

Usage:
    python src/derive_standings.py --season 2024
    python src/derive_standings.py --season 2018-2026
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

LAFC_ABBR = "LAFC"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "lafc_content.db"

# One row per LAFC regular-season match: the match facts (LAFC's perspective)
# plus BOTH teams' pre-match standing ingredients. Everything here is derived
# from the raw `matches` table; no network access was involved.
SCHEMA = """
CREATE TABLE IF NOT EXISTS lafc_match_context (
    event_id        TEXT PRIMARY KEY,   -- FK to matches.event_id
    season          INTEGER NOT NULL,
    kickoff_utc     TEXT,               -- same format as videos.published_at
    opponent_id     TEXT,
    opponent        TEXT,
    home_away       TEXT,               -- 'H' or 'A' (LAFC's perspective)
    goals_for       INTEGER,            -- LAFC goals in this match
    goals_against   INTEGER,
    result          TEXT,               -- 'W' / 'D' / 'L' (LAFC's perspective)

    -- LAFC's standing GOING INTO this match (result above NOT yet included):
    lafc_conf       TEXT,
    lafc_points     INTEGER,
    lafc_played     INTEGER,
    lafc_wins       INTEGER,
    lafc_gf         INTEGER,
    lafc_ga         INTEGER,

    -- Opponent's standing GOING INTO this match:
    opp_conf        TEXT,
    opp_points      INTEGER,
    opp_played      INTEGER,
    opp_wins        INTEGER,
    opp_gf          INTEGER,
    opp_ga          INTEGER,

    derived_at      TEXT NOT NULL
);
"""


def new_tally():
    """A fresh, zeroed standing for a team (the running-tally unit)."""
    return {"points": 0, "played": 0, "wins": 0, "gf": 0, "ga": 0}


def snapshot(tally, team_id):
    """Copy a team's CURRENT standing ingredients (its pre-match state)."""
    t = tally.get(team_id, new_tally())
    return dict(t)  # copy so later updates can't mutate the stored snapshot


def apply_result(tally, team_id, goals_for, goals_against):
    """Fold one match into a team's running tally (MLS points: W=3, D=1, L=0)."""
    t = tally.setdefault(team_id, new_tally())
    t["played"] += 1
    t["gf"] += goals_for
    t["ga"] += goals_against
    if goals_for > goals_against:
        t["wins"] += 1
        t["points"] += 3
    elif goals_for == goals_against:
        t["points"] += 1
    # a loss adds nothing beyond the played/goals bookkeeping above


def mls_rank_key(t):
    """
    Sort key implementing MLS's actual tiebreakers (higher tuple = better).

    MLS order — deliberately NOT goal-difference-first like Europe:
        1. points per game   (PPG, because games played differ mid-season —
                              and even end-of-season if a match was unplayed)
        2. total wins        (MLS breaks ties on WINS before goal difference)
        3. goal differential
        4. goals for

    Deeper MLS tiebreakers (disciplinary points, then away/home goals & wins)
    are intentionally SKIPPED: ESPN's aggregate feed doesn't reliably expose the
    inputs, and they almost never bind mid-season. Left as an explicit note so a
    reader knows the tail is incomplete by design, not by oversight.
    """
    ppg = t["points"] / t["played"] if t["played"] else 0.0
    goal_diff = t["gf"] - t["ga"]
    return (ppg, t["wins"], goal_diff, t["gf"])


def load_teams(conn, season):
    """Return {team_id: {'conference', 'abbr', 'name'}} for a season."""
    rows = conn.execute(
        "SELECT team_id, name, abbr, conference FROM teams WHERE season = ?",
        (season,),
    ).fetchall()
    return {
        r[0]: {"name": r[1], "abbr": r[2], "conference": r[3]}
        for r in rows
    }


def load_regular_season_matches(conn, season):
    """
    Return this season's COMPLETED regular-season matches in chronological order.

    Ordering by kickoff, then event_id, makes the walk deterministic even when
    two matches share the exact same kickoff timestamp.
    """
    return conn.execute(
        """
        SELECT event_id, kickoff_utc, home_team_id, away_team_id,
               home_score, away_score
        FROM matches
        WHERE season = ?
          AND season_type = 'Regular Season'
          AND completed = 1
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
        ORDER BY kickoff_utc, event_id
        """,
        (season,),
    ).fetchall()


def derive_season(conn, season, derived_at):
    """
    Walk one season chronologically and write LAFC's per-match context rows.

    Returns (final_tally, lafc_id, teams) so the caller can run verification.
    """
    teams = load_teams(conn, season)
    lafc_id = next((tid for tid, t in teams.items() if t["abbr"] == LAFC_ABBR), None)
    if lafc_id is None:
        sys.exit(f"season {season}: LAFC not found in `teams`. Run the pull step first.")

    matches = load_regular_season_matches(conn, season)

    tally = {}          # team_id -> running standing ingredients
    context_rows = []   # LAFC match rows to write
    ambiguous = []      # matches we couldn't fully attribute (flagged to the user)

    for event_id, kickoff, home_id, away_id, home_score, away_score in matches:
        lafc_playing = lafc_id in (home_id, away_id)

        # STEP 1 — snapshot BEFORE folding this match in (only when LAFC plays).
        if lafc_playing:
            is_home = home_id == lafc_id
            opp_id = away_id if is_home else home_id
            gf, ga = (home_score, away_score) if is_home else (away_score, home_score)

            lafc_pre = snapshot(tally, lafc_id)
            opp_pre = snapshot(tally, opp_id)

            lafc_conf = teams.get(lafc_id, {}).get("conference")
            opp_meta = teams.get(opp_id)
            if opp_meta is None:
                # Opponent isn't in this season's team list — data gap; flag it.
                ambiguous.append(event_id)
            opp_conf = (opp_meta or {}).get("conference")
            opponent = (opp_meta or {}).get("name")

            if gf > ga:
                result = "W"
            elif gf == ga:
                result = "D"
            else:
                result = "L"

            context_rows.append({
                "event_id": event_id,
                "season": season,
                "kickoff_utc": kickoff,
                "opponent_id": opp_id,
                "opponent": opponent,
                "home_away": "H" if is_home else "A",
                "goals_for": gf,
                "goals_against": ga,
                "result": result,
                "lafc_conf": lafc_conf,
                "lafc_points": lafc_pre["points"], "lafc_played": lafc_pre["played"],
                "lafc_wins": lafc_pre["wins"],
                "lafc_gf": lafc_pre["gf"], "lafc_ga": lafc_pre["ga"],
                "opp_conf": opp_conf,
                "opp_points": opp_pre["points"], "opp_played": opp_pre["played"],
                "opp_wins": opp_pre["wins"],
                "opp_gf": opp_pre["gf"], "opp_ga": opp_pre["ga"],
                "derived_at": derived_at,
            })

        # STEP 2 — now fold this match into BOTH teams' running tallies. This runs
        # for every league match (LAFC or not) so opponents' standings reflect
        # their full league schedule, not just their games against LAFC.
        apply_result(tally, home_id, home_score, away_score)
        apply_result(tally, away_id, away_score, home_score)

    _write_context(conn, context_rows)
    conn.commit()

    print(f"\n=== Season {season} ===")
    print(f"  regular-season matches walked: {len(matches)}")
    print(f"  LAFC context rows written:     {len(context_rows)}")
    if ambiguous:
        print(f"  ⚠ opponent metadata missing for event(s): {', '.join(ambiguous)}")

    return tally, lafc_id, teams


def _write_context(conn, rows):
    """Idempotently write the derived rows (PK = event_id => re-runnable)."""
    conn.executemany(
        """
        INSERT OR REPLACE INTO lafc_match_context
            (event_id, season, kickoff_utc, opponent_id, opponent, home_away,
             goals_for, goals_against, result,
             lafc_conf, lafc_points, lafc_played, lafc_wins, lafc_gf, lafc_ga,
             opp_conf, opp_points, opp_played, opp_wins, opp_gf, opp_ga, derived_at)
        VALUES
            (:event_id, :season, :kickoff_utc, :opponent_id, :opponent, :home_away,
             :goals_for, :goals_against, :result,
             :lafc_conf, :lafc_points, :lafc_played, :lafc_wins, :lafc_gf, :lafc_ga,
             :opp_conf, :opp_points, :opp_played, :opp_wins, :opp_gf, :opp_ga, :derived_at)
        """,
        rows,
    )


def verify_season(conn, season, tally, lafc_id, teams):
    """
    Print LAFC's computed final standing and cross-check it against ESPN's own
    table (stored in standings_official). This is a sanity check, not ground truth.
    """
    lafc_conf = teams.get(lafc_id, {}).get("conference")

    # Rank LAFC within its own conference using the MLS tiebreakers above.
    conf_teams = [tid for tid, meta in teams.items() if meta["conference"] == lafc_conf]
    ranked = sorted(conf_teams, key=lambda tid: mls_rank_key(tally.get(tid, new_tally())),
                    reverse=True)
    computed_rank = ranked.index(lafc_id) + 1
    lt = tally.get(lafc_id, new_tally())
    ppg = lt["points"] / lt["played"] if lt["played"] else 0.0

    print(f"\n--- Verification: LAFC {season} ({lafc_conf}) ---")
    print(f"  COMPUTED  rank #{computed_rank} | pts {lt['points']} | GP {lt['played']} "
          f"| W {lt['wins']} | GF {lt['gf']} | GA {lt['ga']} | PPG {ppg:.2f}")

    official = conn.execute(
        """
        SELECT rank, points, games_played, wins, goals_for, goals_against
        FROM standings_official WHERE season = ? AND team_id = ?
        """,
        (season, lafc_id),
    ).fetchone()

    if official is None:
        print("  OFFICIAL  (no standings_official row found for LAFC)")
        return

    o_rank, o_pts, o_gp, o_wins, o_gf, o_ga = official
    print(f"  OFFICIAL  rank #{o_rank} | pts {o_pts} | GP {o_gp} "
          f"| W {o_wins} | GF {o_gf} | GA {o_ga}   (ESPN, at pull time)")

    # Compare the pieces we can. Rank can legitimately differ if ESPN applies a
    # deeper tiebreaker we skipped, so we report rather than assert.
    checks = {
        "points": (lt["points"], o_pts),
        "games_played": (lt["played"], o_gp),
        "wins": (lt["wins"], o_wins),
        "goals_for": (lt["gf"], o_gf),
        "goals_against": (lt["ga"], o_ga),
        "rank": (computed_rank, o_rank),
    }
    diffs = {k: v for k, v in checks.items() if v[0] != v[1]}
    if not diffs:
        print("  ✅ computed standing matches ESPN exactly.")
    else:
        for k, (mine, theirs) in diffs.items():
            note = " (may be a deeper tiebreaker we skip)" if k == "rank" else ""
            print(f"  ⚠ {k}: computed {mine} vs ESPN {theirs}{note}")


def get_connection():
    """Open the DB and ensure the derived table exists."""
    if not DB_PATH.exists():
        sys.exit(f"No database at {DB_PATH}. Run src/pull_match_data.py first.")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


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
    parser = argparse.ArgumentParser(
        description="Derive point-in-time MLS standings for each LAFC match.")
    parser.add_argument(
        "--season", required=True,
        help="Season year (e.g. 2024) or inclusive range (e.g. 2018-2026).",
    )
    args = parser.parse_args()

    try:
        seasons = parse_seasons(args.season)
    except ValueError:
        sys.exit(f"Could not parse --season {args.season!r}; use e.g. 2024 or 2018-2026.")

    derived_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        for season in seasons:
            tally, lafc_id, teams = derive_season(conn, season, derived_at)
            verify_season(conn, season, tally, lafc_id, teams)
    finally:
        conn.close()

    print(f"\nDone. Wrote lafc_match_context to {DB_PATH}")
    print("Sanity-check tip: compare the COMPUTED rows above against the official "
          "MLS table at https://www.mlssoccer.com/standings/ for each season.")


if __name__ == "__main__":
    main()
