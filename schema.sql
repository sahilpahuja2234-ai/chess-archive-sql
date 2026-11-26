-- Chess Archive Database: schema.sql
-- Stores rated Lichess games in normalized SQLite tables.
-- Run with foreign keys enforced (SQLite turns them off by default on every new connection).
PRAGMA foreign_keys = ON;

-- Players: one row per Lichess username
CREATE TABLE "players" (
    "player_id" INTEGER,
    "username"  TEXT NOT NULL UNIQUE,
    PRIMARY KEY("player_id")
);

-- Openings: one row per (ECO code, opening name) pair
CREATE TABLE "openings" (
    "opening_id" INTEGER,
    "eco"        TEXT NOT NULL CHECK("eco" GLOB '[A-E][0-9][0-9]'),
    "name"       TEXT NOT NULL,
    PRIMARY KEY("opening_id"),
    UNIQUE("eco", "name")
);

-- Games: one row per rated game
CREATE TABLE "games" (
    "game_id"      INTEGER,
    "site"         TEXT NOT NULL UNIQUE,      -- Lichess game URL
    "event"        TEXT NOT NULL,             -- e.g. 'Rated Blitz game'
    "played_at"    TEXT NOT NULL,             -- UTC, 'YYYY-MM-DD HH:MM:SS'
    "result"       TEXT NOT NULL CHECK("result" IN ('1-0', '0-1', '1/2-1/2')),
    "time_control" TEXT NOT NULL,             -- e.g. '300+0', or '-' when untimed
    "termination"  TEXT NOT NULL,             -- e.g. 'Normal', 'Time forfeit'
    "opening_id"   INTEGER,                   -- NULL when the source has no opening
    PRIMARY KEY("game_id"),
    FOREIGN KEY("opening_id") REFERENCES "openings"("opening_id")
);

-- Game players: which player took which side in which game, and at what rating
-- (implements the many-to-many "Plays" relationship)
CREATE TABLE "game_players" (
    "game_id"   INTEGER NOT NULL,
    "player_id" INTEGER NOT NULL,
    "color"     TEXT NOT NULL CHECK("color" IN ('White', 'Black')),
    "elo"       INTEGER CHECK("elo" IS NULL OR "elo" BETWEEN 0 AND 4000),  -- NULL when unknown ('?')
    PRIMARY KEY("game_id", "color"),
    UNIQUE("game_id", "player_id"),
    FOREIGN KEY("game_id")   REFERENCES "games"("game_id") ON DELETE CASCADE,
    FOREIGN KEY("player_id") REFERENCES "players"("player_id")
);

-- Moves: the full move list of a game (weak entity: cannot exist without its game)
CREATE TABLE "moves" (
    "game_id"  INTEGER,
    "movetext" TEXT NOT NULL,
    PRIMARY KEY("game_id"),
    FOREIGN KEY("game_id") REFERENCES "games"("game_id") ON DELETE CASCADE
);

-- Indexes
-- (players.username and games.site are already indexed by their UNIQUE constraints.)
-- All games by a player, and the basis of "most recent game of a player"
-- CREATE INDEX "game_players_player_index" ON "game_players"("player_id");
-- -- Ordering games by date
-- CREATE INDEX "games_played_at_index" ON "games"("played_at");
-- -- Joining games to openings and per-opening analysis
-- CREATE INDEX "games_opening_index" ON "games"("opening_id");

-- Views
-- One readable row per game, with both players, their ratings, and the opening
CREATE VIEW "game_details" AS
SELECT
    "games"."game_id",
    "games"."site",
    "games"."event",
    "games"."played_at",
    "games"."time_control",
    "games"."termination",
    "games"."result",
    "white_players"."username" AS "white_username",
    "white"."elo"              AS "white_elo",
    "black_players"."username" AS "black_username",
    "black"."elo"              AS "black_elo",
    "openings"."eco",
    "openings"."name"          AS "opening_name"
FROM "games"
JOIN "game_players" AS "white" ON "white"."game_id" = "games"."game_id" AND "white"."color" = 'White'
JOIN "players" AS "white_players" ON "white_players"."player_id" = "white"."player_id"
JOIN "game_players" AS "black" ON "black"."game_id" = "games"."game_id" AND "black"."color" = 'Black'
JOIN "players" AS "black_players" ON "black_players"."player_id" = "black"."player_id"
LEFT JOIN "openings" ON "openings"."opening_id" = "games"."opening_id";

-- Number of games and results for each opening
CREATE VIEW "opening_stats" AS
SELECT
    "openings"."opening_id",
    "openings"."eco",
    "openings"."name",
    COUNT("games"."game_id") AS "games",
    SUM(CASE WHEN "games"."result" = '1-0'     THEN 1 ELSE 0 END) AS "white_wins",
    SUM(CASE WHEN "games"."result" = '0-1'     THEN 1 ELSE 0 END) AS "black_wins",
    SUM(CASE WHEN "games"."result" = '1/2-1/2' THEN 1 ELSE 0 END) AS "draws"
FROM "openings"
LEFT JOIN "games" ON "games"."opening_id" = "openings"."opening_id"
GROUP BY "openings"."opening_id";