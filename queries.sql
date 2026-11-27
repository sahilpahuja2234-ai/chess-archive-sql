-- 1. A player's games, including opponent, game details, and ratings.
-- Replace 'some_username' with the player's username.
SELECT
    "played_at",
    "white_username",
    "white_elo",
    "black_username",
    "black_elo",
    "result",
    "event",
    "time_control",
    "opening_name",
    "site"
FROM "game_details"
WHERE "white_username" = 'some_username'
   OR "black_username" = 'some_username'
ORDER BY "played_at";

-- 2. All openings and their ECO codes.
SELECT "eco", "name"
FROM "openings"
ORDER BY "eco", "name";

-- 3. Full details for game 1. Replace 1 with the game ID.
SELECT *
FROM "game_details"
WHERE "game_id" = 1;

-- 4. The most recent game played by a player.
SELECT *
FROM "game_details"
WHERE "white_username" = 'some_username'
   OR "black_username" = 'some_username'
ORDER BY "played_at" DESC
LIMIT 1;

-- 5. The event type and time control for game 1.
SELECT "event", "time_control"
FROM "games"
WHERE "game_id" = 1;

-- 6. A player's Elo rating and color in game 1.
SELECT "players"."username", "game_players"."color", "game_players"."elo"
FROM "game_players"
JOIN "players" ON "players"."player_id" = "game_players"."player_id"
WHERE "players"."username" = 'some_username'
  AND "game_players"."game_id" = 1;

-- 7. Find opening name(s) for an ECO code.
SELECT "eco", "name"
FROM "openings"
WHERE "eco" = 'A00'
ORDER BY "name";

-- 8. Find the ECO code(s) for an opening name.
SELECT "eco", "name"
FROM "openings"
WHERE "name" = 'Sicilian Defense'
ORDER BY "eco";

-- 9. Results and white/black win rates by opening.
SELECT
    "eco",
    "name",
    "games",
    "white_wins",
    ROUND(100.0 * "white_wins" / "games", 2) AS "white_win_percent",
    "black_wins",
    ROUND(100.0 * "black_wins" / "games", 2) AS "black_win_percent",
    "draws",
    ROUND(100.0 * "draws" / "games", 2) AS "draw_percent"
FROM "opening_stats"
WHERE "games" > 0
ORDER BY "games" DESC, "eco", "name";

-- 10. Popular event and time-control combinations, including results.
SELECT
    "event",
    "time_control",
    COUNT(*) AS "game_count",
    SUM(CASE WHEN "result" = '1-0' THEN 1 ELSE 0 END) AS "white_wins",
    SUM(CASE WHEN "result" = '0-1' THEN 1 ELSE 0 END) AS "black_wins",
    SUM(CASE WHEN "result" = '1/2-1/2' THEN 1 ELSE 0 END) AS "draws"
FROM "games"
GROUP BY "event", "time_control"
ORDER BY "game_count" DESC, "event", "time_control";

-- 11. Add a player only if the username is not already in use.
INSERT INTO "players" ("username")
SELECT 'new_player'
WHERE NOT EXISTS (
    SELECT 1
    FROM "players"
    WHERE "username" = 'new_player'
);

-- 12. Rename the player if the new username is available.
UPDATE "players"
SET "username" = 'updated_player'
WHERE "username" = 'new_player'
  AND NOT EXISTS (
      SELECT 1
      FROM "players"
      WHERE "username" = 'updated_player'
  );

-- 13. Delete the example player only if they have no games.
DELETE FROM "players"
WHERE "username" = 'updated_player'
  AND NOT EXISTS (
      SELECT 1
      FROM "game_players"
      WHERE "game_players"."player_id" = "players"."player_id"
  );
