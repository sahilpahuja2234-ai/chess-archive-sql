CREATE TABLE Player (
id INTEGER Primary key,
Username VARCHAR(11),
Cureent_elo as elo INTEGER,
);

CREATE TABLE games (
    id INTEGER PRIMARY KEY,
    event TEXT,
    site TEXT UNIQUE,
    white TEXT NOT NULL DEFAULT 'guest' REFERENCES Player(Username),
    black TEXT NOT NULL DEFAULT 'guest' REFERENCES Player(Username),
    result TEXT CHECK (result IN ('1-0', '0-1', '1/2-1/2')),
    utc_date DATE,
    utc_time TIME,
    white_elo INTEGER,
    black_elo INTEGER,
    white_rating_diff INTEGER,
    black_rating_diff INTEGER,
    eco TEXT,
    opening TEXT,
    time_control TEXT,
    termination TEXT CHECK (termination IN ('Time forfeit', 'Normal', 'Abandoned')
);

