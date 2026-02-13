#!/usr/bin/env python3
"""Backfill O/D Elo ratings by replaying all season games."""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import (
    init_database,
    get_games_by_season,
    get_all_teams,
    get_league_avg_score,
    update_team_od_elo,
    update_game_od_elo_snapshots,
)
from src.models.elo import update_od_elo, calculate_k_with_decay
import config
from config import CURRENT_SEASON, ELO_INITIAL_RATING


def backfill_od_elo(season: str = CURRENT_SEASON, dry_run: bool = False):
    """
    Backfill O/D Elo by replaying all games in chronological order.

    Args:
        season: Season to backfill (e.g., "2024-25")
        dry_run: If True, don't save to database
    """
    print("=" * 60)
    print("O/D Elo Backfill")
    print(f"Season: {season}")
    print(f"Dry run: {dry_run}")
    print("=" * 60)

    # Initialize database
    init_database()

    # Auto-update league avg score from DB
    actual_avg = get_league_avg_score(season)
    if actual_avg is not None:
        config.LEAGUE_AVG_SCORE = actual_avg
        print(f"   League avg score set to {actual_avg:.1f} from DB")

    # Step 1: Reset all O/D Elo to 1500
    print("\n1. Resetting all team O/D Elo to 1500...")
    teams_df = get_all_teams()

    od_ratings = {}
    for _, row in teams_df.iterrows():
        team_id = row['team_id']
        od_ratings[team_id] = {
            'offense': ELO_INITIAL_RATING,
            'defense': ELO_INITIAL_RATING,
        }

    print(f"   Initialized {len(od_ratings)} teams")

    # Step 2: Get all completed games in chronological order
    print("\n2. Loading completed games...")
    games_df = get_games_by_season(season, status='final')

    if games_df.empty:
        print("   No completed games found!")
        return

    # Sort by date
    games_df = games_df.sort_values('game_date')
    print(f"   Found {len(games_df)} completed games")
    print(f"   Date range: {games_df['game_date'].min()} to {games_df['game_date'].max()}")

    # Step 3: Replay each game
    print("\n3. Replaying games...")

    games_processed = 0
    for idx, game in games_df.iterrows():
        home_id = game['home_team_id']
        away_id = game['away_team_id']
        home_score = int(game['home_score'])
        away_score = int(game['away_score'])
        game_id = game['game_id']

        if home_id not in od_ratings or away_id not in od_ratings:
            print(f"   Warning: Unknown team in game {game_id}")
            continue

        # Get current O/D ratings
        home_o = od_ratings[home_id]['offense']
        home_d = od_ratings[home_id]['defense']
        away_o = od_ratings[away_id]['offense']
        away_d = od_ratings[away_id]['defense']

        # Calculate K-factor with decay
        k_factor = calculate_k_with_decay(games_processed)

        # Update O/D Elo
        result = update_od_elo(
            home_o, home_d, away_o, away_d,
            home_score, away_score,
            k_factor=k_factor
        )

        # Save O/D snapshots to game record
        if not dry_run:
            update_game_od_elo_snapshots(
                game_id=game_id,
                home_offense_elo_pre=home_o,
                home_defense_elo_pre=home_d,
                away_offense_elo_pre=away_o,
                away_defense_elo_pre=away_d,
                home_offense_elo_post=result.home_offense_elo_new,
                home_defense_elo_post=result.home_defense_elo_new,
                away_offense_elo_post=result.away_offense_elo_new,
                away_defense_elo_post=result.away_defense_elo_new,
            )

        # Update in-memory ratings
        od_ratings[home_id]['offense'] = result.home_offense_elo_new
        od_ratings[home_id]['defense'] = result.home_defense_elo_new
        od_ratings[away_id]['offense'] = result.away_offense_elo_new
        od_ratings[away_id]['defense'] = result.away_defense_elo_new

        games_processed += 1

        # Progress indicator every 100 games
        if games_processed % 100 == 0:
            print(f"   Processed {games_processed} games...")

    print(f"   Completed {games_processed} games")

    # Step 4: Save final ratings
    print("\n4. Saving final O/D Elo ratings...")

    if not dry_run:
        for team_id, ratings in od_ratings.items():
            update_team_od_elo(team_id, ratings['offense'], ratings['defense'])

    # Step 5: Show results
    print("\n5. Final O/D Elo ratings:")

    # Get team abbreviations for display
    team_abbr = {row['team_id']: row['abbreviation'] for _, row in teams_df.iterrows()}

    # Sort by composite (offense + defense)
    sorted_teams = sorted(
        od_ratings.items(),
        key=lambda x: x[1]['offense'] + x[1]['defense'],
        reverse=True
    )

    print(f"\n   {'Team':<5} {'O-Elo':>8} {'D-Elo':>8} {'Total':>8}")
    print("   " + "-" * 32)

    for team_id, ratings in sorted_teams:
        abbr = team_abbr.get(team_id, '???')
        total = ratings['offense'] + ratings['defense']
        print(f"   {abbr:<5} {ratings['offense']:>8.1f} {ratings['defense']:>8.1f} {total:>8.1f}")

    print("\n" + "=" * 60)
    if dry_run:
        print("DRY RUN - No changes saved to database")
    else:
        print("O/D Elo backfill complete!")
    print("=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Backfill O/D Elo ratings')
    parser.add_argument('--season', default=CURRENT_SEASON, help='Season to backfill')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')

    args = parser.parse_args()

    backfill_od_elo(season=args.season, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
