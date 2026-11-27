"""
Chess Archive dashboard: a small Streamlit front end for chess.db.

Run from the project folder (the one that contains chess.db):
    pip install streamlit pandas
    streamlit run dashboard/app.py

The database is opened read-only. Each panel has a "Show the SQL" box with the
query behind it, and the query plan SQLite uses, so you can see the indexes at work.
"""

import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Chess Archive", layout="wide")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


@st.cache_resource
def get_connection(db_path):
    """Open the database read-only, so the dashboard can never change your data."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


@st.cache_data(show_spinner=False)
def run_query(db_path, sql, params=()):
    """Run a SELECT and return the result as a table. Results are cached."""
    return pd.read_sql_query(sql, get_connection(db_path), params=params)


def show_sql(db_path, sql, params=()):
    """Show the query and SQLite's plan for it (SEARCH = uses an index, SCAN = reads the table)."""
    plan_rows = get_connection(db_path).execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    with st.expander("Show the SQL and query plan"):
        st.code(sql.strip(), language="sql")
        st.caption("Query plan")
        st.code("\n".join(row[3] for row in plan_rows), language="text")


# ---------------------------------------------------------------------------
# Sidebar and page header
# ---------------------------------------------------------------------------

st.title("Chess Archive")
st.caption("Rated Lichess games stored in a normalized SQLite database.")

db_path = st.sidebar.text_input("Database file", value=os.environ.get("CHESS_DB", "chess.db"))
if not Path(db_path).is_file():
    st.error(f"Could not find the database file '{db_path}'. Run the import script first, "
             "or change the path in the sidebar.")
    st.stop()
st.sidebar.caption("Opened read-only.")

overview_tab, openings_tab, player_tab, types_tab = st.tabs(
    ["Overview", "Openings", "Player", "Game types"]
)

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

with overview_tab:
    sql = """
        SELECT
            (SELECT COUNT(*) FROM games)     AS games,
            (SELECT COUNT(*) FROM players)   AS players,
            (SELECT COUNT(*) FROM openings)  AS openings,
            (SELECT MIN(played_at) FROM games) AS first_game,
            (SELECT MAX(played_at) FROM games) AS last_game
    """
    totals = run_query(db_path, sql).iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Games", f"{int(totals['games']):,}")
    c2.metric("Players", f"{int(totals['players']):,}")
    c3.metric("Openings", f"{int(totals['openings']):,}")
    if totals["first_game"]:
        st.caption(f"Games played between {totals['first_game']} and {totals['last_game']} (UTC).")
    show_sql(db_path, sql)

    st.subheader("Games per day")
    sql = """
        SELECT substr(played_at, 1, 10) AS day, COUNT(*) AS games
        FROM games
        GROUP BY day
        ORDER BY day
    """
    per_day = run_query(db_path, sql)
    if not per_day.empty:
        per_day["day"] = pd.to_datetime(per_day["day"])
        st.line_chart(per_day.set_index("day")["games"])
    show_sql(db_path, sql)

    st.subheader("Results")
    sql = """
        SELECT
            CASE result
                WHEN '1-0' THEN 'White wins'
                WHEN '0-1' THEN 'Black wins'
                ELSE 'Draw'
            END AS outcome,
            COUNT(*) AS games
        FROM games
        GROUP BY outcome
        ORDER BY games DESC
    """
    results = run_query(db_path, sql)
    if not results.empty:
        st.bar_chart(results.set_index("outcome")["games"])
    show_sql(db_path, sql)

# ---------------------------------------------------------------------------
# Openings
# ---------------------------------------------------------------------------

with openings_tab:
    st.subheader("How openings perform")
    left, right = st.columns(2)
    rating_low, rating_high = left.slider(
        "Both players' ratings between", 400, 3000, (400, 3000), step=50, key="rating_range"
    )
    min_games = right.slider("Minimum games per opening", 1, 1000, 20, key="min_games")
    top_n = st.slider("Number of openings to show", 5, 30, 10, key="top_n")
    st.caption("Games where either player's rating is unknown are left out.")

    sql = """
        SELECT
            o.eco,
            o.name,
            COUNT(*) AS games,
            ROUND(100.0 * SUM(g.result = '1-0')     / COUNT(*), 1) AS white_win_pct,
            ROUND(100.0 * SUM(g.result = '1/2-1/2') / COUNT(*), 1) AS draw_pct,
            ROUND(100.0 * SUM(g.result = '0-1')     / COUNT(*), 1) AS black_win_pct
        FROM games AS g
        JOIN openings AS o ON o.opening_id = g.opening_id
        JOIN game_players AS w ON w.game_id = g.game_id AND w.color = 'White'
        JOIN game_players AS b ON b.game_id = g.game_id AND b.color = 'Black'
        WHERE w.elo BETWEEN ? AND ?
          AND b.elo BETWEEN ? AND ?
        GROUP BY o.opening_id
        HAVING COUNT(*) >= ?
        ORDER BY games DESC
        LIMIT ?
    """
    params = (rating_low, rating_high, rating_low, rating_high, min_games, top_n)
    openings = run_query(db_path, sql, params)
    if openings.empty:
        st.info("No openings match these filters. Try a lower minimum or a wider rating range.")
    else:
        openings["opening"] = openings["eco"] + " " + openings["name"]
        st.bar_chart(
            openings.set_index("opening")[["white_win_pct", "draw_pct", "black_win_pct"]],
            y_label="% of games",
        )
        st.dataframe(openings.drop(columns="opening"), hide_index=True)
    show_sql(db_path, sql, params)

# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

with player_tab:
    sql = """
        SELECT p.username, COUNT(*) AS games
        FROM game_players AS gp
        JOIN players AS p ON p.player_id = gp.player_id
        GROUP BY p.player_id
        ORDER BY games DESC
        LIMIT 10
    """
    top_players = run_query(db_path, sql)
    default_player = top_players["username"].iloc[0] if not top_players.empty else ""
    username = st.text_input("Lichess username", value=default_player, key="player_name").strip()
    with st.expander("Most active players in the database"):
        st.dataframe(top_players, hide_index=True)
        show_sql(db_path, sql)

    if username:
        sql = """
            SELECT
                g.played_at,
                gp.color,
                opp.username AS opponent,
                gp.elo AS rating,
                og.elo AS opponent_rating,
                CASE
                    WHEN g.result = '1/2-1/2' THEN 'Draw'
                    WHEN (gp.color = 'White' AND g.result = '1-0')
                      OR (gp.color = 'Black' AND g.result = '0-1') THEN 'Win'
                    ELSE 'Loss'
                END AS outcome,
                g.event,
                g.time_control,
                o.name AS opening,
                g.site
            FROM players AS p
            JOIN game_players AS gp  ON gp.player_id = p.player_id
            JOIN games AS g          ON g.game_id = gp.game_id
            JOIN game_players AS og  ON og.game_id = g.game_id AND og.color <> gp.color
            JOIN players AS opp      ON opp.player_id = og.player_id
            LEFT JOIN openings AS o  ON o.opening_id = g.opening_id
            WHERE p.username = ?
            ORDER BY g.played_at DESC
        """
        history = run_query(db_path, sql, (username,))

        if history.empty:
            st.warning(f"No games found for '{username}'.")
        else:
            wins = int((history["outcome"] == "Win").sum())
            draws = int((history["outcome"] == "Draw").sum())
            losses = int((history["outcome"] == "Loss").sum())

            rated = history.dropna(subset=["rating"]).sort_values("played_at")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Games", f"{len(history):,}")
            m2.metric("Win / Draw / Loss", f"{wins} / {draws} / {losses}")
            if rated.empty:
                m3.metric("Latest rating", "unknown")
                m4.metric("Peak rating", "unknown")
            else:
                m3.metric("Latest rating", int(rated["rating"].iloc[-1]))
                m4.metric("Peak rating", int(rated["rating"].max()))

            st.subheader("Rating over time")
            if rated.empty:
                st.info("No ratings are recorded for this player's games.")
            else:
                chart = rated.assign(played_at=pd.to_datetime(rated["played_at"]))
                st.line_chart(chart.set_index("played_at")["rating"], y_label="Elo")

            st.subheader("Most recent games")
            st.dataframe(history.head(20), hide_index=True)
            st.caption("This query starts from the player, so SQLite can find their games "
                       "through the index on game_players(player_id) instead of scanning every game.")
            show_sql(db_path, sql, (username,))

# ---------------------------------------------------------------------------
# Game types
# ---------------------------------------------------------------------------

with types_tab:
    st.subheader("Most popular event and time-control combinations")
    sql = """
        SELECT
            event,
            time_control,
            COUNT(*) AS games,
            ROUND(100.0 * SUM(result = '1-0')     / COUNT(*), 1) AS white_win_pct,
            ROUND(100.0 * SUM(result = '1/2-1/2') / COUNT(*), 1) AS draw_pct,
            ROUND(100.0 * SUM(result = '0-1')     / COUNT(*), 1) AS black_win_pct
        FROM games
        GROUP BY event, time_control
        ORDER BY games DESC
        LIMIT 15
    """
    types = run_query(db_path, sql)
    if not types.empty:
        types["game type"] = types["event"] + " " + types["time_control"]
        st.bar_chart(types.set_index("game type")["games"])
        st.dataframe(types.drop(columns="game type"), hide_index=True)
    show_sql(db_path, sql)
