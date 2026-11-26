-- Insert a game, resolving unknown player names to the existing Guest row.
-- Bind all named parameters; usernames are only looked up, never added here.
INSERT INTO Games (
    event,
    site,
    white_player_id,
    black_player_id,
    result,
    utc_date,
    utc_time,
    white_elo,
    black_elo,
    white_rating_diff,
    black_rating_diff,
    eco,
    opening,
    time_control,
    termination
)
VALUES (
    :event,
    :site,
    COALESCE(
        (SELECT id FROM Player WHERE Username = :white_username),
        (SELECT id FROM Player WHERE Username = 'Guest')
    ),
    COALESCE(
        (SELECT id FROM Player WHERE Username = :black_username),
        (SELECT id FROM Player WHERE Username = 'Guest')
    ),
    :result,
    :utc_date,
    :utc_time,
    :white_elo,
    :black_elo,
    :white_rating_diff,
    :black_rating_diff,
    :eco,
    :opening,
    :time_control,
    :termination
);