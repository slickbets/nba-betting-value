#!/usr/bin/env python3
"""Backfill historical games and calculate Elo ratings."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime

from src.data.database import (
    get_games_by_season,
    get_all_teams,
    update_team_elo,
    update_game_elo_snapshots,
    record_elo_change,
    reset_all_elos,
    upsert_game,
)
from src.data.nba_fetcher import (
    fetch_season_games,
    process_games_for_db,
    get_historical_seasons,
)
from src.models.elo import update_elo, season_regression
from config import ELO_INITIAL_RATING, CURRENT_SEASON


def backfill_season_games(seasons: list[str] = None):
    """
    Fetch and store games for multiple seasons.

    Args:
        seasons: List of season strings to fetch. Defaults to last 3 seasons.
    """
    if seasons is None:
        seasons = get_historical_seasons(3)

    print(f"Fetching games for seasons: {seasons}")

    for season in seasons:
        print(f"\nFetching {season} season...")
        games_df = fetch_season_games(season)

        if games_df.empty:
            print(f"  No games found for {season}")
            continue

        processed = process_games_for_db(games_df, season)
        print(f"  Found {len(processed)} games")

        for game in processed:
            upsert_game(**game)

        print(f"  Loaded {len(processed)} games")


def calculate_historical_elo(seasons: list[str] = None, reset: bool = True):
    """
    Calculate Elo ratings for all historical games.

    Games are processed in chronological order to build up accurate ratings.

    Args:
        seasons: List of seasons to process. Defaults to last 3 seasons.
        reset: Whether to reset all Elos to initial before calculating.
    """
    if seasons is None:
        seasons = get_historical_seasons(3)
        seasons.reverse()  # Process oldest first

    print("\nCalculating historical Elo ratings...")

    if reset:
        print("  Resetting all Elo ratings to 1500...")
        reset_all_elos()

    # Load current team ratings into memory
    teams_df = get_all_teams()
    elo_ratings = {row['team_id']: row['current_elo'] for _, row in teams_df.iterrows()}

    total_games = 0
    last_season = None

    for season in seasons:
        print(f"\nProcessing {season}...")

        # Apply season regression if switching seasons
        if last_season is not None and last_season != season:
            print(f"  Applying season regression...")
            for team_id in elo_ratings:
                elo_ratings[team_id] = season_regression(elo_ratings[team_id])

        # Get all completed games for this season
        games_df = get_games_by_season(season, status='final')

        if games_df.empty:
            print(f"  No completed games found")
            continue

        # Sort by date to process chronologically
        games_df = games_df.sort_values('game_date')
        season_games = 0

        for _, game in games_df.iterrows():
            home_id = game['home_team_id']
            away_id = game['away_team_id']

            if home_id not in elo_ratings or away_id not in elo_ratings:
                continue

            home_elo = elo_ratings[home_id]
            away_elo = elo_ratings[away_id]

            # Determine winner
            home_won = game['home_score'] > game['away_score']

            # Update Elo
            result = update_elo(home_elo, away_elo, home_won)

            # Store pre-game Elos and update
            update_game_elo_snapshots(
                game_id=game['game_id'],
                home_elo_pre=home_elo,
                away_elo_pre=away_elo,
                home_elo_post=result.home_new_elo,
                away_elo_post=result.away_new_elo
            )

            # Record Elo history
            record_elo_change(home_id, game['game_id'], home_elo, result.home_new_elo)
            record_elo_change(away_id, game['game_id'], away_elo, result.away_new_elo)

            # Update in-memory ratings
            elo_ratings[home_id] = result.home_new_elo
            elo_ratings[away_id] = result.away_new_elo

            season_games += 1

        print(f"  Processed {season_games} games")
        total_games += season_games
        last_season = season

    # Save final Elo ratings to database
    print("\nSaving final Elo ratings...")
    for team_id, elo in elo_ratings.items():
        update_team_elo(team_id, elo)

    print(f"\nBackfill complete!")
    print(f"  Total games processed: {total_games}")

    # Show top teams
    teams_df = get_all_teams()
    print("\nTop 10 teams by Elo:")
    print(teams_df[['abbreviation', 'current_elo']].head(10).to_string(index=False))


def main():
    print("=" * 50)
    print("NBA Betting Value - Historical Backfill")
    print("=" * 50)

    # Get seasons to process
    seasons = get_historical_seasons(2)  # Last 2 seasons for faster processing
    seasons.reverse()

    print(f"\nWill process seasons: {seasons}")

    # First, fetch the games
    print("\n" + "-" * 50)
    print("Step 1: Fetching historical games")
    print("-" * 50)
    backfill_season_games(seasons)

    # Then calculate Elo
    print("\n" + "-" * 50)
    print("Step 2: Calculating Elo ratings")
    print("-" * 50)
    calculate_historical_elo(seasons)

    print("\n" + "=" * 50)
    print("Backfill complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
