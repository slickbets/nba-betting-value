"""SQLite database operations for NBA Betting Value Finder."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DB_PATH, DATA_DIR, ELO_INITIAL_RATING


def ensure_data_dir():
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    """Context manager for database connections."""
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Initialize the database with all required tables."""
    ensure_data_dir()

    with get_connection() as conn:
        cursor = conn.cursor()

        # Teams table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                team_id INTEGER PRIMARY KEY,
                abbreviation TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                current_elo REAL DEFAULT 1500.0,
                offense_elo REAL DEFAULT 1500.0,
                defense_elo REAL DEFAULT 1500.0,
                conference TEXT,
                division TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Games table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                season TEXT NOT NULL,
                game_date DATE NOT NULL,
                game_time TEXT,
                home_team_id INTEGER NOT NULL,
                away_team_id INTEGER NOT NULL,
                home_score INTEGER,
                away_score INTEGER,
                status TEXT DEFAULT 'scheduled',
                home_elo_pre REAL,
                away_elo_pre REAL,
                home_elo_post REAL,
                away_elo_post REAL,
                predicted_home_win_prob REAL,
                predicted_spread REAL,
                predicted_total REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
                FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
            )
        """)

        # Migration: Add game_time column if it doesn't exist
        cursor.execute("PRAGMA table_info(games)")
        game_columns = [row[1] for row in cursor.fetchall()]
        if 'game_time' not in game_columns:
            cursor.execute("ALTER TABLE games ADD COLUMN game_time TEXT")

        # Migration: Add O/D Elo columns to teams if they don't exist
        cursor.execute("PRAGMA table_info(teams)")
        team_columns = [row[1] for row in cursor.fetchall()]
        if 'offense_elo' not in team_columns:
            cursor.execute("ALTER TABLE teams ADD COLUMN offense_elo REAL DEFAULT 1500.0")
        if 'defense_elo' not in team_columns:
            cursor.execute("ALTER TABLE teams ADD COLUMN defense_elo REAL DEFAULT 1500.0")

        # Migration: Add O/D Elo snapshot columns to games if they don't exist
        if 'home_offense_elo_pre' not in game_columns:
            cursor.execute("ALTER TABLE games ADD COLUMN home_offense_elo_pre REAL")
            cursor.execute("ALTER TABLE games ADD COLUMN home_defense_elo_pre REAL")
            cursor.execute("ALTER TABLE games ADD COLUMN away_offense_elo_pre REAL")
            cursor.execute("ALTER TABLE games ADD COLUMN away_defense_elo_pre REAL")
            cursor.execute("ALTER TABLE games ADD COLUMN home_offense_elo_post REAL")
            cursor.execute("ALTER TABLE games ADD COLUMN home_defense_elo_post REAL")
            cursor.execute("ALTER TABLE games ADD COLUMN away_offense_elo_post REAL")
            cursor.execute("ALTER TABLE games ADD COLUMN away_defense_elo_post REAL")

        # Odds table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                sportsbook TEXT NOT NULL,
                market_type TEXT NOT NULL,
                home_odds INTEGER,
                away_odds INTEGER,
                spread_home REAL,
                spread_home_odds INTEGER,
                spread_away_odds INTEGER,
                total_line REAL,
                over_odds INTEGER,
                under_odds INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(game_id),
                UNIQUE(game_id, sportsbook, market_type, fetched_at)
            )
        """)

        # Bets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                bet_type TEXT NOT NULL,
                selection TEXT NOT NULL,
                line REAL,
                odds INTEGER NOT NULL,
                stake REAL NOT NULL,
                model_probability REAL,
                implied_probability REAL,
                edge REAL,
                sportsbook TEXT,
                result TEXT,
                payout REAL,
                profit_loss REAL,
                notes TEXT,
                placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                settled_at TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        """)

        # Elo history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elo_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                game_id TEXT NOT NULL,
                elo_before REAL NOT NULL,
                elo_after REAL NOT NULL,
                elo_change REAL NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(team_id),
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        """)

        # Player impact table for auto-calculated player ratings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_impact (
                player_id INTEGER PRIMARY KEY,
                player_name TEXT NOT NULL,
                player_name_normalized TEXT NOT NULL,
                team_abbr TEXT NOT NULL,
                net_rating REAL,
                minutes_per_game REAL,
                games_played INTEGER,
                usg_pct REAL,
                elo_impact REAL,
                season TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_impact_team ON player_impact(team_abbr)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_impact_name ON player_impact(player_name_normalized)")

        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_status ON games(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_season ON games(season)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_game ON odds(game_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bets_game ON bets(game_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_elo_history_team ON elo_history(team_id)")

        conn.commit()


# Team operations
def upsert_team(team_id: int, abbreviation: str, full_name: str,
                conference: str = None, division: str = None):
    """Insert or update a team."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teams (team_id, abbreviation, full_name, conference, division, current_elo)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                abbreviation = excluded.abbreviation,
                full_name = excluded.full_name,
                conference = excluded.conference,
                division = excluded.division,
                updated_at = CURRENT_TIMESTAMP
        """, (team_id, abbreviation, full_name, conference, division, ELO_INITIAL_RATING))
        conn.commit()


def get_all_teams() -> pd.DataFrame:
    """Get all teams as a DataFrame."""
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM teams ORDER BY current_elo DESC", conn)


def get_team_by_id(team_id: int) -> Optional[dict]:
    """Get a team by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teams WHERE team_id = ?", (int(team_id),))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_team_by_abbreviation(abbr: str) -> Optional[dict]:
    """Get a team by abbreviation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teams WHERE abbreviation = ?", (abbr,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_team_elo(team_id: int, new_elo: float):
    """Update a team's current Elo rating."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teams SET current_elo = ?, updated_at = CURRENT_TIMESTAMP
            WHERE team_id = ?
        """, (new_elo, team_id))
        conn.commit()


def update_team_od_elo(team_id: int, offense_elo: float, defense_elo: float):
    """Update a team's offensive and defensive Elo ratings.

    Also updates current_elo as the composite (average) for backward compatibility.
    """
    composite_elo = (offense_elo + defense_elo) / 2
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teams SET
                offense_elo = ?,
                defense_elo = ?,
                current_elo = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE team_id = ?
        """, (offense_elo, defense_elo, composite_elo, team_id))
        conn.commit()


# Game operations
def upsert_game(game_id: str, season: str, game_date: str,
                home_team_id: int, away_team_id: int,
                home_score: int = None, away_score: int = None,
                status: str = 'scheduled', game_time: str = None):
    """Insert or update a game."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO games (game_id, season, game_date, game_time, home_team_id, away_team_id,
                              home_score, away_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                game_time = COALESCE(excluded.game_time, games.game_time),
                home_score = COALESCE(excluded.home_score, games.home_score),
                away_score = COALESCE(excluded.away_score, games.away_score),
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP
        """, (game_id, season, game_date, game_time, home_team_id, away_team_id,
              home_score, away_score, status))
        conn.commit()


def get_games_by_date(game_date: str) -> pd.DataFrame:
    """Get all games for a specific date."""
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT g.*,
                   ht.abbreviation as home_abbr, ht.full_name as home_name, ht.current_elo as home_elo,
                   ht.offense_elo as home_offense_elo, ht.defense_elo as home_defense_elo,
                   at.abbreviation as away_abbr, at.full_name as away_name, at.current_elo as away_elo,
                   at.offense_elo as away_offense_elo, at.defense_elo as away_defense_elo
            FROM games g
            JOIN teams ht ON g.home_team_id = ht.team_id
            JOIN teams at ON g.away_team_id = at.team_id
            WHERE g.game_date = ?
            ORDER BY g.game_id
        """, conn, params=(game_date,))


def get_games_by_season(season: str, status: str = None) -> pd.DataFrame:
    """Get all games for a season, optionally filtered by status."""
    with get_connection() as conn:
        if status:
            return pd.read_sql_query("""
                SELECT g.*,
                       ht.abbreviation as home_abbr, ht.full_name as home_name,
                       at.abbreviation as away_abbr, at.full_name as away_name
                FROM games g
                JOIN teams ht ON g.home_team_id = ht.team_id
                JOIN teams at ON g.away_team_id = at.team_id
                WHERE g.season = ? AND g.status = ?
                ORDER BY g.game_date, g.game_id
            """, conn, params=(season, status))
        else:
            return pd.read_sql_query("""
                SELECT g.*,
                       ht.abbreviation as home_abbr, ht.full_name as home_name,
                       at.abbreviation as away_abbr, at.full_name as away_name
                FROM games g
                JOIN teams ht ON g.home_team_id = ht.team_id
                JOIN teams at ON g.away_team_id = at.team_id
                WHERE g.season = ?
                ORDER BY g.game_date, g.game_id
            """, conn, params=(season,))


def update_game_predictions(game_id: str, home_win_prob: float,
                           predicted_spread: float, predicted_total: float = None):
    """Update game predictions."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE games SET
                predicted_home_win_prob = ?,
                predicted_spread = ?,
                predicted_total = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE game_id = ?
        """, (home_win_prob, predicted_spread, predicted_total, game_id))
        conn.commit()


def update_game_elo_snapshots(game_id: str, home_elo_pre: float, away_elo_pre: float,
                              home_elo_post: float = None, away_elo_post: float = None):
    """Update Elo snapshots for a game."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE games SET
                home_elo_pre = ?,
                away_elo_pre = ?,
                home_elo_post = ?,
                away_elo_post = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE game_id = ?
        """, (home_elo_pre, away_elo_pre, home_elo_post, away_elo_post, game_id))
        conn.commit()


def update_game_od_elo_snapshots(
    game_id: str,
    home_offense_elo_pre: float, home_defense_elo_pre: float,
    away_offense_elo_pre: float, away_defense_elo_pre: float,
    home_offense_elo_post: float = None, home_defense_elo_post: float = None,
    away_offense_elo_post: float = None, away_defense_elo_post: float = None
):
    """Update O/D Elo snapshots for a game."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE games SET
                home_offense_elo_pre = ?,
                home_defense_elo_pre = ?,
                away_offense_elo_pre = ?,
                away_defense_elo_pre = ?,
                home_offense_elo_post = ?,
                home_defense_elo_post = ?,
                away_offense_elo_post = ?,
                away_defense_elo_post = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE game_id = ?
        """, (home_offense_elo_pre, home_defense_elo_pre,
              away_offense_elo_pre, away_defense_elo_pre,
              home_offense_elo_post, home_defense_elo_post,
              away_offense_elo_post, away_defense_elo_post, game_id))
        conn.commit()


def update_game_result(game_id: str, home_score: int, away_score: int):
    """Update game score and mark as final."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE games SET
                home_score = ?,
                away_score = ?,
                status = 'final',
                updated_at = CURRENT_TIMESTAMP
            WHERE game_id = ?
        """, (home_score, away_score, game_id))
        conn.commit()


def get_team_last_game_date(team_id: int, before_date: str) -> str | None:
    """
    Get the date of a team's most recent game before a given date.

    Args:
        team_id: Team's database ID
        before_date: Date to look before (YYYY-MM-DD)

    Returns:
        Date string of last game (YYYY-MM-DD) or None if no previous game
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT game_date FROM games
            WHERE (home_team_id = ? OR away_team_id = ?)
            AND game_date < ?
            AND status = 'final'
            ORDER BY game_date DESC
            LIMIT 1
        """, (team_id, team_id, before_date))
        result = cursor.fetchone()
        return result[0] if result else None


# Odds operations
def insert_odds(game_id: str, sportsbook: str, market_type: str, **kwargs):
    """Insert odds snapshot."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO odds (game_id, sportsbook, market_type, home_odds, away_odds,
                             spread_home, spread_home_odds, spread_away_odds,
                             total_line, over_odds, under_odds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_id, sportsbook, market_type,
            kwargs.get('home_odds'), kwargs.get('away_odds'),
            kwargs.get('spread_home'), kwargs.get('spread_home_odds'), kwargs.get('spread_away_odds'),
            kwargs.get('total_line'), kwargs.get('over_odds'), kwargs.get('under_odds')
        ))
        conn.commit()


def get_latest_odds(game_id: str) -> pd.DataFrame:
    """Get the most recent odds for a game from all sportsbooks."""
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT * FROM odds
            WHERE game_id = ?
            AND fetched_at = (
                SELECT MAX(fetched_at) FROM odds o2
                WHERE o2.game_id = odds.game_id AND o2.sportsbook = odds.sportsbook
            )
            ORDER BY sportsbook
        """, conn, params=(game_id,))


# Bet operations
def insert_bet(game_id: str, bet_type: str, selection: str, odds: int, stake: float,
               line: float = None, model_probability: float = None,
               implied_probability: float = None, edge: float = None,
               sportsbook: str = None, notes: str = None) -> int:
    """Insert a new bet and return its ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bets (game_id, bet_type, selection, line, odds, stake,
                             model_probability, implied_probability, edge, sportsbook, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (game_id, bet_type, selection, line, odds, stake,
              model_probability, implied_probability, edge, sportsbook, notes))
        conn.commit()
        return cursor.lastrowid


def settle_bet(bet_id: int, result: str, payout: float, profit_loss: float):
    """Settle a bet with result."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE bets SET
                result = ?,
                payout = ?,
                profit_loss = ?,
                settled_at = CURRENT_TIMESTAMP
            WHERE bet_id = ?
        """, (result, payout, profit_loss, bet_id))
        conn.commit()


def get_all_bets() -> pd.DataFrame:
    """Get all bets."""
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT b.*, g.game_date, g.home_score, g.away_score,
                   ht.abbreviation as home_abbr, at.abbreviation as away_abbr
            FROM bets b
            JOIN games g ON b.game_id = g.game_id
            JOIN teams ht ON g.home_team_id = ht.team_id
            JOIN teams at ON g.away_team_id = at.team_id
            ORDER BY b.placed_at DESC
        """, conn)


def get_unsettled_bets() -> pd.DataFrame:
    """Get all unsettled bets."""
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT b.*, g.game_date, g.home_score, g.away_score, g.status,
                   ht.abbreviation as home_abbr, at.abbreviation as away_abbr
            FROM bets b
            JOIN games g ON b.game_id = g.game_id
            JOIN teams ht ON g.home_team_id = ht.team_id
            JOIN teams at ON g.away_team_id = at.team_id
            WHERE b.result IS NULL
            ORDER BY g.game_date
        """, conn)


# Elo history operations
def record_elo_change(team_id: int, game_id: str, elo_before: float, elo_after: float):
    """Record an Elo rating change."""
    elo_change = elo_after - elo_before
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO elo_history (team_id, game_id, elo_before, elo_after, elo_change)
            VALUES (?, ?, ?, ?, ?)
        """, (team_id, game_id, elo_before, elo_after, elo_change))
        conn.commit()


def get_team_elo_history(team_id: int) -> pd.DataFrame:
    """Get Elo history for a team."""
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT eh.*, g.game_date
            FROM elo_history eh
            JOIN games g ON eh.game_id = g.game_id
            WHERE eh.team_id = ?
            ORDER BY g.game_date
        """, conn, params=(team_id,))


def reset_all_elos():
    """Reset all team Elos to initial rating."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE teams SET current_elo = ?", (ELO_INITIAL_RATING,))
        cursor.execute("UPDATE teams SET offense_elo = ?", (ELO_INITIAL_RATING,))
        cursor.execute("UPDATE teams SET defense_elo = ?", (ELO_INITIAL_RATING,))
        cursor.execute("DELETE FROM elo_history")
        conn.commit()


# Player impact operations
def upsert_player_impact(
    player_id: int,
    player_name: str,
    team_abbr: str,
    net_rating: float,
    minutes_per_game: float,
    games_played: int,
    elo_impact: float,
    season: str,
    usg_pct: float = None,
):
    """Insert or update a player's impact rating."""
    import re
    player_name_normalized = re.sub(r"[^\w\s]", "", player_name.lower().strip())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO player_impact (
                player_id, player_name, player_name_normalized,
                team_abbr, net_rating, minutes_per_game,
                games_played, usg_pct, elo_impact, season
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                player_name = excluded.player_name,
                player_name_normalized = excluded.player_name_normalized,
                team_abbr = excluded.team_abbr,
                net_rating = excluded.net_rating,
                minutes_per_game = excluded.minutes_per_game,
                games_played = excluded.games_played,
                usg_pct = excluded.usg_pct,
                elo_impact = excluded.elo_impact,
                season = excluded.season,
                updated_at = CURRENT_TIMESTAMP
        """, (player_id, player_name, player_name_normalized,
              team_abbr, net_rating, minutes_per_game,
              games_played, usg_pct, elo_impact, season))
        conn.commit()


def get_player_impact_by_name(player_name: str, team_abbr: str = None) -> Optional[dict]:
    """Get player impact by name with optional team disambiguation."""
    import re
    normalized_name = re.sub(r"[^\w\s]", "", player_name.lower().strip())

    with get_connection() as conn:
        cursor = conn.cursor()

        # Try exact match first
        if team_abbr:
            cursor.execute("""
                SELECT * FROM player_impact
                WHERE player_name_normalized = ? AND team_abbr = ?
            """, (normalized_name, team_abbr))
        else:
            cursor.execute("""
                SELECT * FROM player_impact
                WHERE player_name_normalized = ?
            """, (normalized_name,))

        row = cursor.fetchone()
        if row:
            return dict(row)

        # Try partial match (contains)
        if team_abbr:
            cursor.execute("""
                SELECT * FROM player_impact
                WHERE player_name_normalized LIKE ? AND team_abbr = ?
                ORDER BY elo_impact DESC
            """, (f"%{normalized_name}%", team_abbr))
        else:
            cursor.execute("""
                SELECT * FROM player_impact
                WHERE player_name_normalized LIKE ?
                ORDER BY elo_impact DESC
            """, (f"%{normalized_name}%",))

        row = cursor.fetchone()
        if row:
            return dict(row)

        # Try last name only
        last_name = normalized_name.split()[-1] if normalized_name else ""
        if last_name:
            if team_abbr:
                cursor.execute("""
                    SELECT * FROM player_impact
                    WHERE player_name_normalized LIKE ? AND team_abbr = ?
                    ORDER BY elo_impact DESC
                """, (f"% {last_name}", team_abbr))
            else:
                cursor.execute("""
                    SELECT * FROM player_impact
                    WHERE player_name_normalized LIKE ?
                    ORDER BY elo_impact DESC
                """, (f"% {last_name}",))

            row = cursor.fetchone()
            if row:
                return dict(row)

        return None


def get_all_player_impacts(season: str = None) -> pd.DataFrame:
    """Get all player impacts, optionally filtered by season."""
    with get_connection() as conn:
        if season:
            return pd.read_sql_query(
                "SELECT * FROM player_impact WHERE season = ? ORDER BY elo_impact DESC",
                conn, params=(season,)
            )
        else:
            return pd.read_sql_query(
                "SELECT * FROM player_impact ORDER BY elo_impact DESC",
                conn
            )


def clear_player_impacts():
    """Clear all player impact data."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM player_impact")
        conn.commit()


def clear_old_player_impacts(current_season: str) -> int:
    """Remove player impact entries from previous seasons.

    Args:
        current_season: The current season string (e.g., "2025-26")

    Returns:
        Number of rows deleted
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM player_impact WHERE season != ?", (current_season,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted


def get_league_avg_score(season: str) -> Optional[float]:
    """Calculate the actual league average score from completed games.

    Args:
        season: Season string (e.g., "2025-26")

    Returns:
        Average points per team per game, or None if no data
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(score) FROM (
                SELECT home_score AS score FROM games
                WHERE season = ? AND status = 'final' AND home_score IS NOT NULL
                UNION ALL
                SELECT away_score AS score FROM games
                WHERE season = ? AND status = 'final' AND away_score IS NOT NULL
            )
        """, (season, season))
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else None
