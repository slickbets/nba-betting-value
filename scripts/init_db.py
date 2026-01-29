#!/usr/bin/env python3
"""Initialize the database with teams and recent games."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import (
    init_database,
    upsert_team,
    upsert_game,
    get_all_teams,
)
from src.data.nba_fetcher import (
    get_all_nba_teams,
    fetch_season_games,
    process_games_for_db,
    fetch_todays_games,
    process_scoreboard_for_db,
)
from config import CURRENT_SEASON


def main():
    print("Initializing NBA Betting Value database...")

    # Create tables
    print("\n1. Creating database tables...")
    init_database()
    print("   Tables created successfully!")

    # Load teams
    print("\n2. Loading NBA teams...")
    nba_teams = get_all_nba_teams()

    for team in nba_teams:
        upsert_team(
            team_id=team['id'],
            abbreviation=team['abbreviation'],
            full_name=team['full_name'],
            conference=None,  # Could be added if needed
            division=None
        )

    teams_df = get_all_teams()
    print(f"   Loaded {len(teams_df)} teams")

    # Load current season games
    print(f"\n3. Fetching {CURRENT_SEASON} season games...")
    games_df = fetch_season_games(CURRENT_SEASON)

    if not games_df.empty:
        processed = process_games_for_db(games_df, CURRENT_SEASON)
        print(f"   Found {len(processed)} games")

        for game in processed:
            upsert_game(**game)

        print(f"   Loaded {len(processed)} games into database")
    else:
        print("   No games found for current season")

    # Also try to get today's scheduled games
    print("\n4. Checking today's games...")
    today_df = fetch_todays_games()

    if not today_df.empty:
        today_games = process_scoreboard_for_db(today_df, CURRENT_SEASON)
        print(f"   Found {len(today_games)} games today")

        for game in today_games:
            upsert_game(**game)
    else:
        print("   No games scheduled today")

    print("\n" + "="*50)
    print("Database initialization complete!")
    print(f"  - Teams: {len(teams_df)}")
    print(f"  - Games: {len(processed) if 'processed' in dir() else 0}")
    print("="*50)


if __name__ == "__main__":
    main()
