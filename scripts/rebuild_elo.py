#!/usr/bin/env python3
"""Full Elo rebuild: resets all ratings and replays every game from scratch.

Uses production logic (MOV + K-decay + O/D Elo) so the rebuild matches
what daily_update.py would have produced if it had been running from day one.

Usage:
    python scripts/rebuild_elo.py                    # Rebuild current season
    python scripts/rebuild_elo.py --all              # Rebuild all seasons
    python scripts/rebuild_elo.py --dry-run          # Preview without saving
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from config import (
    DB_PATH, CURRENT_SEASON, ELO_INITIAL_RATING,
)
from src.data.database import (
    init_database,
    get_all_teams,
    get_games_by_season,
    get_league_avg_score,
    update_team_elo,
    update_team_od_elo,
    update_game_elo_snapshots,
    update_game_od_elo_snapshots,
    record_elo_change,
)
from src.models.elo import (
    update_elo_with_mov,
    update_od_elo,
    calculate_k_with_decay,
    season_regression,
    season_regression_od,
)


def reset_all(conn):
    """Reset all Elo to 1500, clear history and game snapshots."""
    conn.execute(
        'UPDATE teams SET current_elo=?, offense_elo=?, defense_elo=?',
        (ELO_INITIAL_RATING, ELO_INITIAL_RATING, ELO_INITIAL_RATING)
    )
    conn.execute('DELETE FROM elo_history')
    conn.execute('''
        UPDATE games SET
            home_elo_pre=NULL, away_elo_pre=NULL,
            home_elo_post=NULL, away_elo_post=NULL,
            home_offense_elo_pre=NULL, home_defense_elo_pre=NULL,
            away_offense_elo_pre=NULL, away_defense_elo_pre=NULL,
            home_offense_elo_post=NULL, home_defense_elo_post=NULL,
            away_offense_elo_post=NULL, away_defense_elo_post=NULL
    ''')
    conn.commit()


def rebuild_elo(seasons: list[str], dry_run: bool = False):
    init_database()

    teams_df = get_all_teams()
    team_abbr = {row['team_id']: row['abbreviation'] for _, row in teams_df.iterrows()}

    # Reset
    if not dry_run:
        print("Resetting all Elo to 1500 and clearing history...")
        conn = sqlite3.connect(DB_PATH)
        reset_all(conn)
        conn.close()

    # Initialize ratings
    elo = {row['team_id']: ELO_INITIAL_RATING for _, row in teams_df.iterrows()}
    od = {row['team_id']: {'o': ELO_INITIAL_RATING, 'd': ELO_INITIAL_RATING}
          for _, row in teams_df.iterrows()}

    total_processed = 0
    prev_season = None

    for season in seasons:
        # Season regression between seasons
        if prev_season is not None:
            print(f"  Applying season regression ({prev_season} -> {season})...")
            for tid in elo:
                elo[tid] = season_regression(elo[tid])
                od[tid]['o'], od[tid]['d'] = season_regression_od(od[tid]['o'], od[tid]['d'])

        # Set league avg score from DB
        actual_avg = get_league_avg_score(season)
        if actual_avg is not None:
            config.LEAGUE_AVG_SCORE = actual_avg
            print(f"  League avg score: {actual_avg:.1f}")

        # Load games
        games_df = get_games_by_season(season, status='final')
        if games_df.empty:
            print(f"  {season}: no games")
            prev_season = season
            continue

        games_df = games_df.sort_values('game_date')
        print(f"  {season}: {len(games_df)} games ({games_df['game_date'].min()} to {games_df['game_date'].max()})")

        season_processed = 0
        for _, game in games_df.iterrows():
            home_id = game['home_team_id']
            away_id = game['away_team_id']

            if home_id not in elo or away_id not in elo:
                continue

            home_score = int(game['home_score'])
            away_score = int(game['away_score'])
            game_id = game['game_id']

            # K-factor with decay (per-season game count)
            k = calculate_k_with_decay(season_processed)

            # --- Composite Elo (with MOV) ---
            home_elo_pre = elo[home_id]
            away_elo_pre = elo[away_id]

            result = update_elo_with_mov(
                home_elo_pre, away_elo_pre,
                home_score, away_score,
                k_factor=k
            )
            elo[home_id] = result.home_new_elo
            elo[away_id] = result.away_new_elo

            # --- O/D Elo ---
            ho, hd = od[home_id]['o'], od[home_id]['d']
            ao, ad = od[away_id]['o'], od[away_id]['d']

            od_result = update_od_elo(ho, hd, ao, ad, home_score, away_score, k_factor=k)

            od[home_id]['o'] = od_result.home_offense_elo_new
            od[home_id]['d'] = od_result.home_defense_elo_new
            od[away_id]['o'] = od_result.away_offense_elo_new
            od[away_id]['d'] = od_result.away_defense_elo_new

            # --- Save to DB ---
            if not dry_run:
                update_game_elo_snapshots(
                    game_id=game_id,
                    home_elo_pre=home_elo_pre,
                    away_elo_pre=away_elo_pre,
                    home_elo_post=result.home_new_elo,
                    away_elo_post=result.away_new_elo,
                )
                record_elo_change(home_id, game_id, home_elo_pre, result.home_new_elo)
                record_elo_change(away_id, game_id, away_elo_pre, result.away_new_elo)

                update_game_od_elo_snapshots(
                    game_id=game_id,
                    home_offense_elo_pre=ho, home_defense_elo_pre=hd,
                    away_offense_elo_pre=ao, away_defense_elo_pre=ad,
                    home_offense_elo_post=od_result.home_offense_elo_new,
                    home_defense_elo_post=od_result.home_defense_elo_new,
                    away_offense_elo_post=od_result.away_offense_elo_new,
                    away_defense_elo_post=od_result.away_defense_elo_new,
                )

            season_processed += 1

        total_processed += season_processed
        print(f"    Processed {season_processed} games")
        prev_season = season

    # Save final team ratings
    if not dry_run:
        for tid in elo:
            update_team_elo(tid, elo[tid])
            update_team_od_elo(tid, od[tid]['o'], od[tid]['d'])

    # Print results
    print(f"\nTotal: {total_processed} games processed")

    sorted_teams = sorted(elo.items(), key=lambda x: x[1], reverse=True)
    print(f"\n{'Team':<5} {'Elo':>6} {'O-Elo':>7} {'D-Elo':>7}")
    print("-" * 27)
    for tid, rating in sorted_teams:
        abbr = team_abbr.get(tid, '???')
        print(f"{abbr:<5} {rating:>6.0f} {od[tid]['o']:>7.0f} {od[tid]['d']:>7.0f}")

    if dry_run:
        print("\nDRY RUN — no changes saved")


def main():
    parser = argparse.ArgumentParser(description='Full Elo rebuild from scratch')
    parser.add_argument('--all', action='store_true',
                        help='Rebuild all seasons (with regression between)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without saving')
    args = parser.parse_args()

    if args.all:
        seasons = ['2024-25', '2025-26']
    else:
        seasons = [CURRENT_SEASON]

    print("=" * 50)
    print(f"Full Elo Rebuild: {', '.join(seasons)}")
    print("=" * 50)

    rebuild_elo(seasons, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
