"""Auto-refresh live game scores (BDL primary, ESPN fallback)."""

import logging
import streamlit as st
from src.data.bdl_fetcher import fetch_live_scores_bdl
from src.data.nba_fetcher import fetch_scoreboard_espn
from src.data.database import get_games_by_date, upsert_game

logger = logging.getLogger(__name__)


@st.cache_data(ttl=60)
def refresh_live_scores(date_str: str) -> int:
    """Fetch latest scores and update DB. Returns count of games updated."""
    # Try BDL live scores first
    live_games = fetch_live_scores_bdl()

    # Fall back to ESPN if BDL returns empty
    if not live_games:
        live_games = fetch_scoreboard_espn(date_str)

    if not live_games:
        return 0

    existing_games = get_games_by_date(date_str)

    updated = 0

    for game in live_games:
        home_abbr = game['home_abbr']
        away_abbr = game['away_abbr']

        # Try to match against existing DB game
        if not existing_games.empty:
            match = existing_games[
                (existing_games['home_abbr'] == home_abbr) &
                (existing_games['away_abbr'] == away_abbr)
            ]
            if not match.empty:
                game_row = match.iloc[0]
                db_status = game_row.get('status', 'scheduled')

                # Skip games already final in DB
                if db_status == 'final':
                    continue

                # Only update if new info
                if game['status'] != db_status or game['home_score'] != game_row.get('home_score'):
                    upsert_game(
                        game_id=game_row['game_id'],
                        season=game_row['season'],
                        game_date=date_str,
                        game_time=game.get('game_time') or game_row.get('game_time'),
                        home_team_id=int(game_row['home_team_id']),
                        away_team_id=int(game_row['away_team_id']),
                        home_score=game['home_score'],
                        away_score=game['away_score'],
                        status=game['status'],
                    )
                    updated += 1
                continue

        # No existing game found — skip. Game creation is daily_update's job.
        # The live endpoint returns games without dates, so inserting here
        # would misattribute games from other dates to the selected date.

    return updated
