"""Auto-refresh live game scores (BDL primary, ESPN fallback)."""

import logging
import streamlit as st
from src.data.bdl_fetcher import fetch_games_bdl, fetch_live_scores_bdl
from src.data.nba_fetcher import fetch_scoreboard_espn
from src.data.database import get_games_by_date, get_stale_in_progress_dates, upsert_game

logger = logging.getLogger(__name__)


@st.cache_data(ttl=300)
def resolve_stale_games() -> int:
    """Resolve games stuck as 'in_progress' using the BDL games endpoint.

    Checks the DB for any dates with in_progress games, then fetches the
    real status from BDL (or ESPN fallback) and updates accordingly.
    Cached for 5 minutes since stale games aren't time-sensitive.
    """
    stale_dates = get_stale_in_progress_dates()
    if not stale_dates:
        return 0

    resolved = 0
    for date_str in stale_dates:
        games = fetch_games_bdl(date_str)

        # ESPN fallback: match by abbreviation against DB games
        if not games:
            espn_games = fetch_scoreboard_espn(date_str)
            if not espn_games:
                continue
            db_games = get_games_by_date(date_str)
            if db_games.empty:
                continue
            for eg in espn_games:
                match = db_games[
                    (db_games['home_abbr'] == eg['home_abbr'])
                    & (db_games['away_abbr'] == eg['away_abbr'])
                ]
                if match.empty or eg['status'] == 'in_progress':
                    continue
                row = match.iloc[0]
                if row['status'] == 'in_progress':
                    upsert_game(
                        game_id=row['game_id'],
                        season=row['season'],
                        game_date=date_str,
                        home_team_id=int(row['home_team_id']),
                        away_team_id=int(row['away_team_id']),
                        home_score=eg.get('home_score'),
                        away_score=eg.get('away_score'),
                        status=eg['status'],
                    )
                    resolved += 1
            continue

        for game in games:
            if game['status'] != 'in_progress':
                upsert_game(**game)
                resolved += 1

    if resolved:
        logger.info("Resolved %d stale in_progress games", resolved)
    return resolved


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
