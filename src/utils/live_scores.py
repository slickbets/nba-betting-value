"""Auto-refresh live game scores from ESPN."""

import streamlit as st
from src.data.nba_fetcher import fetch_scoreboard_espn
from src.data.database import get_games_by_date, upsert_game


@st.cache_data(ttl=60)
def refresh_live_scores(date_str: str) -> int:
    """Fetch latest scores from ESPN and update DB. Returns count of games updated."""
    espn_games = fetch_scoreboard_espn(date_str)
    if not espn_games:
        return 0

    existing_games = get_games_by_date(date_str)
    if existing_games.empty:
        return 0

    updated = 0
    for espn_game in espn_games:
        match = existing_games[
            (existing_games['home_abbr'] == espn_game['home_abbr']) &
            (existing_games['away_abbr'] == espn_game['away_abbr'])
        ]
        if not match.empty:
            game_row = match.iloc[0]
            db_status = game_row.get('status', 'scheduled')

            # Skip games already final in DB
            if db_status == 'final':
                continue

            # Only update if ESPN has new info
            if espn_game['status'] != db_status or espn_game['home_score'] != game_row.get('home_score'):
                upsert_game(
                    game_id=game_row['game_id'],
                    season=game_row['season'],
                    game_date=date_str,
                    game_time=espn_game.get('game_time') or game_row.get('game_time'),
                    home_team_id=int(game_row['home_team_id']),
                    away_team_id=int(game_row['away_team_id']),
                    home_score=espn_game['home_score'],
                    away_score=espn_game['away_score'],
                    status=espn_game['status'],
                )
                updated += 1

    return updated
