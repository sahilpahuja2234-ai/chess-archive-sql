"""
import_games.py: load Lichess PGN games into the chess SQLite database.

Usage (from the project folder):
    python import/import_games.py sample/sample.pgn chess.db --limit 1000
    python import/import_games.py data/lichess_db_standard_rated_2017-02.pgn chess.db

Safe to run more than once: games already in the database are skipped,
because games.site is UNIQUE.
"""

import argparse
import os
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime

import chess.pgn  # pip install chess

VALID_RESULTS = {"1-0", "0-1", "1/2-1/2"}
ECO_PATTERN = re.compile(r"^[A-E][0-9][0-9]$")
BATCH_SIZE = 5000  # commit to the database after this many games


# ---------------------------------------------------------------------------
# Step 1: clean up the raw header values
# ---------------------------------------------------------------------------

def clean(value):
    """Return the header text, or None if it is missing or the placeholder '?'."""
    if value is None:
        return None
    value = value.strip()
    if value in ("", "?"):
        return None
    return value


def parse_elo(value):
    """'1850' -> 1850. '?' or anything unusable -> None (stored as NULL)."""
    value = clean(value)
    if value is None:
        return None
    try:
        elo = int(value)
    except ValueError:
        return None
    return elo if 0 <= elo <= 4000 else None  # same range as the CHECK in schema.sql


def parse_played_at(date_text, time_text):
    """('2017.02.01', '00:00:01') -> '2017-02-01 00:00:01'. Returns None if invalid."""
    date_text, time_text = clean(date_text), clean(time_text)
    if date_text is None or time_text is None:
        return None
    try:
        parsed = datetime.strptime(f"{date_text} {time_text}", "%Y.%m.%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Step 2: turn one game's headers into a record, or explain why we skip it
# ---------------------------------------------------------------------------

def parse_game(headers):
    """Return (record, None) if the game is usable, or (None, reason) if not.

    All checks happen here, BEFORE anything is written, so a bad game never
    leaves half its rows in the database.
    """
    site = clean(headers.get("Site"))
    if site is None:
        return None, "missing site"

    white = clean(headers.get("White"))
    black = clean(headers.get("Black"))
    if white is None or black is None:
        return None, "missing player name"
    if white == black:
        return None, "same player on both sides"

    result = headers.get("Result")
    if result not in VALID_RESULTS:
        return None, f"unusual result {result!r}"

    played_at = parse_played_at(headers.get("UTCDate"), headers.get("UTCTime"))
    if played_at is None:
        return None, "missing or invalid date/time"

    event = clean(headers.get("Event"))
    time_control = clean(headers.get("TimeControl"))  # '-' (untimed) is kept
    termination = clean(headers.get("Termination"))
    if event is None or time_control is None or termination is None:
        return None, "missing event, time control, or termination"

    # The opening is optional: no usable opening just means opening_id = NULL.
    eco = clean(headers.get("ECO"))
    opening_name = clean(headers.get("Opening"))
    opening = None
    if eco and opening_name and ECO_PATTERN.match(eco):
        opening = (eco, opening_name)

    record = {
        "site": site,
        "event": event,
        "played_at": played_at,
        "result": result,
        "time_control": time_control,
        "termination": termination,
        "opening": opening,
        "white": white,
        "black": black,
        "white_elo": parse_elo(headers.get("WhiteElo")),
        "black_elo": parse_elo(headers.get("BlackElo")),
    }
    return record, None


# ---------------------------------------------------------------------------
# Step 3: write to the database
# ---------------------------------------------------------------------------

def get_player_id(cur, cache, username):
    """Find the player's id, creating the player the first time we see them."""
    if username not in cache:
        cur.execute("INSERT OR IGNORE INTO players (username) VALUES (?)", (username,))
        cur.execute("SELECT player_id FROM players WHERE username = ?", (username,))
        cache[username] = cur.fetchone()[0]
    return cache[username]


def get_opening_id(cur, cache, eco, name):
    """Same idea as get_player_id, for the (eco, name) pair."""
    key = (eco, name)
    if key not in cache:
        cur.execute("INSERT OR IGNORE INTO openings (eco, name) VALUES (?, ?)", key)
        cur.execute("SELECT opening_id FROM openings WHERE eco = ? AND name = ?", key)
        cache[key] = cur.fetchone()[0]
    return cache[key]


def insert_game(cur, record, player_cache, opening_cache):
    """Insert one game and its two game_players rows. Return False if it already existed."""
    opening_id = None
    if record["opening"]:
        opening_id = get_opening_id(cur, opening_cache, *record["opening"])

    # INSERT OR IGNORE: if this site (URL) is already stored, nothing is inserted.
    cur.execute(
        """
        INSERT OR IGNORE INTO games
            (site, event, played_at, result, time_control, termination, opening_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["site"], record["event"], record["played_at"], record["result"],
            record["time_control"], record["termination"], opening_id,
        ),
    )
    if cur.rowcount == 0:
        return False  # duplicate game
    game_id = cur.lastrowid

    white_id = get_player_id(cur, player_cache, record["white"])
    black_id = get_player_id(cur, player_cache, record["black"])
    cur.executemany(
        "INSERT INTO game_players (game_id, player_id, color, elo) VALUES (?, ?, ?, ?)",
        [
            (game_id, white_id, "White", record["white_elo"]),
            (game_id, black_id, "Black", record["black_elo"]),
        ],
    )
    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import Lichess PGN games into SQLite.")
    parser.add_argument("pgn", help="path to the .pgn file")
    parser.add_argument("db", help="path to the SQLite database (created if missing)")
    parser.add_argument("--schema", default="schema.sql", help="schema file used for a new database")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many games (0 = all)")
    parser.add_argument("--log", default="import_skipped.log", help="where skipped games are listed")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite forgets this on every new connection

    has_tables = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'games'"
    ).fetchone()
    if not has_tables:
        with open(args.schema, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.execute("PRAGMA foreign_keys = ON")

    cur = conn.cursor()
    # Remember ids already in the database so re-runs and big files stay fast.
    player_cache = dict(cur.execute("SELECT username, player_id FROM players"))
    opening_cache = {
        (eco, name): opening_id
        for opening_id, eco, name in cur.execute("SELECT opening_id, eco, name FROM openings")
    }

    seen = inserted = 0
    skipped = Counter()
    started = time.perf_counter()

    try:
        with open(args.pgn, encoding="utf-8", errors="replace") as pgn, \
             open(args.log, "w", encoding="utf-8") as log:
            while True:
                # read_headers reads only the [Tag "value"] lines and skips the moves,
                # which is much faster than read_game. It returns None at end of file.
                headers = chess.pgn.read_headers(pgn)
                if headers is None:
                    break
                seen += 1

                record, reason = parse_game(headers)
                if record is None:
                    skipped[reason] += 1
                    log.write(f"game #{seen} {headers.get('Site', '?')}: {reason}\n")
                elif insert_game(cur, record, player_cache, opening_cache):
                    inserted += 1
                else:
                    skipped["already in database"] += 1

                if seen % BATCH_SIZE == 0:
                    conn.commit()
                if seen % 50_000 == 0:
                    print(f"  {seen:,} games read, {inserted:,} inserted ...")
                if args.limit and seen >= args.limit:
                    break
    finally:
        conn.commit()  # keep everything committed so far, even if we stop early
        conn.close()

    elapsed = time.perf_counter() - started
    print(f"\nDone in {elapsed:.1f}s ({seen / max(elapsed, 0.001):,.0f} games/s)")
    print(f"Games read:     {seen:,}")
    print(f"Games inserted: {inserted:,}")
    for reason, count in skipped.most_common():
        print(f"Skipped {count:,}: {reason}")
    print(f"Skipped games are listed in {args.log}")


if __name__ == "__main__":
    main()