"""SQLite connection and schema management."""
import sqlite3
from contextlib import contextmanager

from src.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT,
    strength INTEGER,
    strength_overall_home INTEGER,
    strength_overall_away INTEGER,
    strength_attack_home INTEGER,
    strength_attack_away INTEGER,
    strength_defence_home INTEGER,
    strength_defence_away INTEGER,
    pulled_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    name TEXT,
    deadline_time TEXT,
    finished INTEGER,
    is_previous INTEGER,
    is_current INTEGER,
    is_next INTEGER,
    average_entry_score INTEGER,
    highest_score INTEGER,
    pulled_at TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL,
    first_name TEXT,
    second_name TEXT,
    web_name TEXT,
    element_type INTEGER,
    now_cost INTEGER,
    selected_by_percent REAL,
    form REAL,
    total_points INTEGER,
    minutes INTEGER,
    goals_scored INTEGER,
    assists INTEGER,
    clean_sheets INTEGER,
    goals_conceded INTEGER,
    expected_goals REAL,
    expected_assists REAL,
    expected_goal_involvements REAL,
    expected_goals_conceded REAL,
    ict_index REAL,
    influence REAL,
    creativity REAL,
    threat REAL,
    bonus INTEGER,
    bps INTEGER,
    saves INTEGER,
    status TEXT,
    chance_of_playing_next_round REAL,
    chance_of_playing_this_round REAL,
    points_per_game REAL,
    value_season REAL,
    pulled_at TEXT,
    FOREIGN KEY (team_id) REFERENCES teams (id)
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY,
    event INTEGER,
    team_h INTEGER,
    team_a INTEGER,
    team_h_score INTEGER,
    team_a_score INTEGER,
    kickoff_time TEXT,
    finished INTEGER,
    team_h_difficulty INTEGER,
    team_a_difficulty INTEGER,
    pulled_at TEXT,
    FOREIGN KEY (team_h) REFERENCES teams (id),
    FOREIGN KEY (team_a) REFERENCES teams (id)
);

CREATE TABLE IF NOT EXISTS gameweek_stats (
    player_id INTEGER NOT NULL,
    gw INTEGER NOT NULL,
    fixture_id INTEGER,
    opponent_team INTEGER,
    was_home INTEGER,
    total_points INTEGER,
    minutes INTEGER,
    goals_scored INTEGER,
    assists INTEGER,
    clean_sheets INTEGER,
    goals_conceded INTEGER,
    expected_goals REAL,
    expected_assists REAL,
    expected_goal_involvements REAL,
    expected_goals_conceded REAL,
    bps INTEGER,
    bonus INTEGER,
    saves INTEGER,
    influence REAL,
    creativity REAL,
    threat REAL,
    ict_index REAL,
    value INTEGER,
    pulled_at TEXT,
    PRIMARY KEY (player_id, gw),
    FOREIGN KEY (player_id) REFERENCES players (id)
);

CREATE TABLE IF NOT EXISTS player_projections (
    player_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    projected_points REAL,
    confidence REAL,
    computed_at TEXT,
    PRIMARY KEY (player_id, gameweek),
    FOREIGN KEY (player_id) REFERENCES players (id)
);

CREATE TABLE IF NOT EXISTS my_manager_snapshot (
    manager_id INTEGER NOT NULL,
    gw INTEGER NOT NULL,
    bank INTEGER,
    squad_value INTEGER,
    free_transfers INTEGER,
    pulled_at TEXT,
    PRIMARY KEY (manager_id, gw)
);

CREATE TABLE IF NOT EXISTS my_squad_history (
    manager_id INTEGER NOT NULL,
    gw INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    squad_position INTEGER,
    is_captain INTEGER,
    is_vice_captain INTEGER,
    multiplier INTEGER,
    purchase_price INTEGER,
    sell_price INTEGER,
    pulled_at TEXT,
    PRIMARY KEY (manager_id, gw, player_id),
    FOREIGN KEY (player_id) REFERENCES players (id)
);

CREATE INDEX IF NOT EXISTS idx_fixtures_event ON fixtures (event);
CREATE INDEX IF NOT EXISTS idx_gameweek_stats_gw ON gameweek_stats (gw);
CREATE INDEX IF NOT EXISTS idx_player_projections_gw ON player_projections (gameweek);
CREATE INDEX IF NOT EXISTS idx_my_squad_history_manager_gw ON my_squad_history (manager_id, gw);
"""

# Columns added after the initial release. Applied to existing databases (created
# before the column existed) since CREATE TABLE IF NOT EXISTS won't add them.
_MIGRATIONS = {
    "players": [("saves", "INTEGER")],
    "gameweek_stats": [("saves", "INTEGER")],
}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, coltype in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)
        _apply_migrations(conn)


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
