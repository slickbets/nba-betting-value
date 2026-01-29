"""NBA data fetcher using nba_api package."""

import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from nba_api.stats.endpoints import (
    leaguegamefinder,
    scoreboardv2,
    leaguedashplayerstats,
    leaguedashteamstats,
)
from nba_api.stats.static import teams as nba_teams

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import CURRENT_SEASON


# NBA team ID to abbreviation mapping (nba_api uses different IDs)
def get_all_nba_teams() -> list[dict]:
    """Get all NBA teams with their info."""
    teams = nba_teams.get_teams()
    return teams


def get_team_id_by_abbreviation(abbr: str) -> Optional[int]:
    """Get team ID from abbreviation."""
    teams = nba_teams.get_teams()
    for team in teams:
        if team['abbreviation'] == abbr:
            return team['id']
    return None


def fetch_season_games(season: str = CURRENT_SEASON,
                       team_id: int = None) -> pd.DataFrame:
    """
    Fetch all games for a season.

    Args:
        season: NBA season string (e.g., "2024-25")
        team_id: Optional team ID to filter games

    Returns:
        DataFrame with game information
    """
    try:
        # LeagueGameFinder gets historical and scheduled games
        finder = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            league_id_nullable="00",  # NBA
            team_id_nullable=team_id,
        )
        time.sleep(0.6)  # Rate limiting

        games_df = finder.get_data_frames()[0]

        if games_df.empty:
            return pd.DataFrame()

        # Process the data
        games_df['GAME_DATE'] = pd.to_datetime(games_df['GAME_DATE'])

        return games_df

    except Exception as e:
        print(f"Error fetching season games: {e}")
        return pd.DataFrame()


def fetch_todays_games() -> pd.DataFrame:
    """
    Fetch today's games from the NBA scoreboard.

    Returns:
        DataFrame with today's games
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        board = scoreboardv2.ScoreboardV2(game_date=today)
        time.sleep(0.6)

        games_df = board.get_data_frames()[0]  # GameHeader

        return games_df

    except Exception as e:
        print(f"Error fetching today's games: {e}")
        return pd.DataFrame()


def fetch_games_by_date(game_date: str) -> pd.DataFrame:
    """
    Fetch games for a specific date.

    Args:
        game_date: Date string in YYYY-MM-DD format

    Returns:
        DataFrame with games for that date including scores
    """
    try:
        board = scoreboardv2.ScoreboardV2(game_date=game_date)
        time.sleep(0.6)

        dfs = board.get_data_frames()
        games_df = dfs[0]  # GameHeader
        line_score_df = dfs[1]  # LineScore with actual scores

        if games_df.empty:
            return games_df

        # Pivot line scores to get home and away scores per game
        if not line_score_df.empty and 'PTS' in line_score_df.columns:
            # Group by game and get scores for each team
            for _, game_row in games_df.iterrows():
                game_id = game_row['GAME_ID']
                home_team_id = game_row['HOME_TEAM_ID']
                away_team_id = game_row['VISITOR_TEAM_ID']

                game_scores = line_score_df[line_score_df['GAME_ID'] == game_id]

                home_score = game_scores[game_scores['TEAM_ID'] == home_team_id]['PTS'].values
                away_score = game_scores[game_scores['TEAM_ID'] == away_team_id]['PTS'].values

                games_df.loc[games_df['GAME_ID'] == game_id, 'HOME_TEAM_SCORE'] = home_score[0] if len(home_score) > 0 else None
                games_df.loc[games_df['GAME_ID'] == game_id, 'AWAY_TEAM_SCORE'] = away_score[0] if len(away_score) > 0 else None

        return games_df

    except Exception as e:
        print(f"Error fetching games for {game_date}: {e}")
        return pd.DataFrame()


def process_games_for_db(games_df: pd.DataFrame, season: str) -> list[dict]:
    """
    Process raw game data into format for database insertion.

    This handles the fact that LeagueGameFinder returns one row per team per game,
    so we need to combine them into single game records.
    """
    if games_df.empty:
        return []

    # Group by game ID and process
    processed = []
    game_ids = games_df['GAME_ID'].unique()

    for game_id in game_ids:
        game_rows = games_df[games_df['GAME_ID'] == game_id]

        if len(game_rows) < 2:
            continue  # Need both teams

        # Determine home vs away (MATCHUP contains @ for away team)
        for _, row in game_rows.iterrows():
            matchup = row['MATCHUP']

            if '@' in matchup:
                # This is the away team
                away_team_id = row['TEAM_ID']
                away_score = row.get('PTS')
            else:
                # This is the home team
                home_team_id = row['TEAM_ID']
                home_score = row.get('PTS')
                game_date = row['GAME_DATE']

        # Determine status
        if pd.notna(home_score) and pd.notna(away_score):
            status = 'final'
        else:
            status = 'scheduled'
            home_score = None
            away_score = None

        processed.append({
            'game_id': game_id,
            'season': season,
            'game_date': game_date.strftime('%Y-%m-%d') if hasattr(game_date, 'strftime') else str(game_date)[:10],
            'home_team_id': int(home_team_id),
            'away_team_id': int(away_team_id),
            'home_score': int(home_score) if pd.notna(home_score) else None,
            'away_score': int(away_score) if pd.notna(away_score) else None,
            'status': status
        })

    return processed


def process_scoreboard_for_db(scoreboard_df: pd.DataFrame, season: str) -> list[dict]:
    """
    Process scoreboard data (from Scoreboard endpoint) into format for database.
    """
    if scoreboard_df.empty:
        return []

    processed = []

    for _, row in scoreboard_df.iterrows():
        game_id = row['GAME_ID']
        game_date = row.get('GAME_DATE_EST', datetime.now().strftime('%Y-%m-%d'))

        # Parse game date
        if isinstance(game_date, str):
            game_date = game_date[:10]  # Just the date part
        elif hasattr(game_date, 'strftime'):
            game_date = game_date.strftime('%Y-%m-%d')

        home_team_id = row['HOME_TEAM_ID']
        away_team_id = row['VISITOR_TEAM_ID']

        # Check for scores (may not exist for scheduled games)
        home_score = row.get('HOME_TEAM_SCORE')
        away_score = row.get('AWAY_TEAM_SCORE')

        # Handle NaN values
        if pd.isna(home_score):
            home_score = None
        if pd.isna(away_score):
            away_score = None

        # Determine status and extract game time
        # GAME_STATUS_ID: 1 = scheduled, 2 = in progress, 3 = final
        game_status = row.get('GAME_STATUS_TEXT', 'Scheduled')
        game_status_id = row.get('GAME_STATUS_ID', 1)
        game_time = None

        if game_status_id == 3 or 'Final' in str(game_status):
            status = 'final'
        elif game_status_id == 2:
            status = 'in_progress'
        else:
            status = 'scheduled'
            home_score = None
            away_score = None
            # Extract game time from status text for scheduled games (e.g., "7:00 pm ET")
            if 'ET' in str(game_status):
                game_time = str(game_status).strip()

        processed.append({
            'game_id': game_id,
            'season': season,
            'game_date': game_date,
            'game_time': game_time,
            'home_team_id': int(home_team_id),
            'away_team_id': int(away_team_id),
            'home_score': int(home_score) if home_score else None,
            'away_score': int(away_score) if away_score else None,
            'status': status
        })

    return processed


def get_historical_seasons(num_seasons: int = 3) -> list[str]:
    """
    Generate a list of recent NBA season strings.

    Args:
        num_seasons: Number of seasons to generate

    Returns:
        List of season strings like ["2024-25", "2023-24", "2022-23"]
    """
    current_year = datetime.now().year
    current_month = datetime.now().month

    # NBA season starts in October
    if current_month >= 10:
        start_year = current_year
    else:
        start_year = current_year - 1

    seasons = []
    for i in range(num_seasons):
        year = start_year - i
        season = f"{year}-{str(year + 1)[-2:]}"
        seasons.append(season)

    return seasons


def fetch_player_impact_stats(season: str = CURRENT_SEASON,
                              min_minutes: float = 15.0,
                              min_games: int = 10) -> pd.DataFrame:
    """
    Fetch player advanced stats for impact calculations.

    Uses NBA API LeagueDashPlayerStats to get NET_RATING, minutes, and games played.

    Args:
        season: NBA season string (e.g., "2024-25")
        min_minutes: Minimum minutes per game to qualify (default 15)
        min_games: Minimum games played to qualify (default 10)

    Returns:
        DataFrame with columns: player_id, player_name, team_abbr, net_rating,
        minutes_per_game, games_played, usg_pct, elo_impact
    """
    try:
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            measure_type_detailed_defense='Advanced',
            per_mode_detailed='PerGame',
        )
        time.sleep(0.6)  # Rate limiting

        df = stats.get_data_frames()[0]

        if df.empty:
            print("No player stats returned from API")
            return pd.DataFrame()

        # Filter to qualified players
        df = df[df['MIN'] >= min_minutes]
        df = df[df['GP'] >= min_games]

        if df.empty:
            print(f"No players qualify with {min_minutes}+ MPG and {min_games}+ GP")
            return pd.DataFrame()

        # Calculate Elo impact: NET_RATING * (MPG / 48) * (USG% / 0.20) * 1.5
        # - NET_RATING: team point diff per 100 possessions with player on court
        # - MPG / 48: playing time factor
        # - USG% / 0.20: usage weighting (20% is ~league avg) - separates stars from
        #   role players who inflate NET_RATING by playing on good teams
        # - 1.5: scaling factor to convert to Elo points
        df['elo_impact'] = (df['NET_RATING'] * (df['MIN'] / 48)
                            * (df['USG_PCT'] / 0.20) * 1.5)

        # Select and rename columns
        result = df[['PLAYER_ID', 'PLAYER_NAME', 'TEAM_ABBREVIATION', 'NET_RATING',
                     'MIN', 'GP', 'USG_PCT', 'elo_impact']].copy()
        result.columns = ['player_id', 'player_name', 'team_abbr', 'net_rating',
                         'minutes_per_game', 'games_played', 'usg_pct', 'elo_impact']

        print(f"Fetched impact stats for {len(result)} qualified players")
        return result

    except Exception as e:
        print(f"Error fetching player impact stats: {e}")
        return pd.DataFrame()


def fetch_team_offensive_defensive_ratings(season: str = CURRENT_SEASON) -> pd.DataFrame:
    """
    Fetch team offensive and defensive ratings for O/D Elo seeding.

    Uses NBA API LeagueDashTeamStats to get OFF_RATING and DEF_RATING.

    Args:
        season: NBA season string (e.g., "2024-25")

    Returns:
        DataFrame with columns: team_id, team_abbr, off_rating, def_rating,
        offense_elo, defense_elo
    """
    try:
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense='Advanced',
            per_mode_detailed='PerGame',
        )
        time.sleep(0.6)  # Rate limiting

        df = stats.get_data_frames()[0]

        if df.empty:
            print("No team stats returned from API")
            return pd.DataFrame()

        # Build team_id to abbreviation mapping from static data
        all_teams = get_all_nba_teams()
        team_id_to_abbr = {team['id']: team['abbreviation'] for team in all_teams}

        # Add abbreviation column
        df['team_abbr'] = df['TEAM_ID'].map(team_id_to_abbr)

        # League average for reference (approximately 114.5-115 in recent seasons)
        league_avg_rating = 114.7

        # Calculate O/D Elo from ratings
        # o_elo = 1500 + (OFF_RATING - league_avg) * 25
        # d_elo = 1500 + (league_avg - DEF_RATING) * 25 (lower DEF_RATING = better defense)
        df['offense_elo'] = 1500 + (df['OFF_RATING'] - league_avg_rating) * 25
        df['defense_elo'] = 1500 + (league_avg_rating - df['DEF_RATING']) * 25

        # Select and rename columns
        result = df[['TEAM_ID', 'team_abbr', 'OFF_RATING', 'DEF_RATING',
                     'offense_elo', 'defense_elo']].copy()
        result.columns = ['team_id', 'team_abbr', 'off_rating', 'def_rating',
                         'offense_elo', 'defense_elo']

        print(f"Fetched O/D ratings for {len(result)} teams")
        return result

    except Exception as e:
        print(f"Error fetching team O/D ratings: {e}")
        return pd.DataFrame()
