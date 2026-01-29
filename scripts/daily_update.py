#!/usr/bin/env python3
"""Daily update script - refresh games, settle bets, update Elo."""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR

# File to track last run date
LAST_RUN_FILE = DATA_DIR / ".last_daily_update"


def already_ran_today() -> bool:
    """Check if we already ran today (skip duplicate runs)."""
    if not LAST_RUN_FILE.exists():
        return False

    try:
        last_run = LAST_RUN_FILE.read_text().strip()
        # Handle both old format (date only) and new format (datetime)
        last_run_date = last_run[:10]  # Extract just the date part
        return last_run_date == datetime.now().strftime("%Y-%m-%d")
    except Exception:
        return False


def mark_as_ran():
    """Mark that we ran today with full timestamp."""
    LAST_RUN_FILE.write_text(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def get_last_run_info() -> dict:
    """Get information about the last daily update run.

    Returns:
        dict with 'ran_today', 'last_run_date', 'last_run_time', 'last_run_datetime'
    """
    if not LAST_RUN_FILE.exists():
        return {
            'ran_today': False,
            'last_run_date': None,
            'last_run_time': None,
            'last_run_datetime': None,
        }

    try:
        last_run = LAST_RUN_FILE.read_text().strip()

        # Parse the datetime
        if ' ' in last_run:
            # New format: "2025-01-25 09:30:00"
            last_run_dt = datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
        else:
            # Old format: "2025-01-25" (no time)
            last_run_dt = datetime.strptime(last_run, "%Y-%m-%d")

        ran_today = last_run_dt.date() == datetime.now().date()

        return {
            'ran_today': ran_today,
            'last_run_date': last_run_dt.strftime("%Y-%m-%d"),
            'last_run_time': last_run_dt.strftime("%I:%M %p") if ' ' in last_run else None,
            'last_run_datetime': last_run_dt,
        }
    except Exception:
        return {
            'ran_today': False,
            'last_run_date': None,
            'last_run_time': None,
            'last_run_datetime': None,
        }

from src.data.database import (
    init_database,
    get_games_by_season,
    get_games_by_date,
    update_game_result,
    update_team_elo,
    update_team_od_elo,
    update_game_elo_snapshots,
    update_game_od_elo_snapshots,
    record_elo_change,
    get_all_teams,
    get_unsettled_bets,
    settle_bet,
    upsert_game,
    upsert_player_impact,
)
from src.data.nba_fetcher import (
    fetch_season_games,
    fetch_games_by_date,
    process_games_for_db,
    process_scoreboard_for_db,
    fetch_player_impact_stats,
    fetch_team_offensive_defensive_ratings,
)
from src.data.odds_fetcher import get_current_odds
from src.data.injury_fetcher import fetch_injuries_for_date
from src.models.elo import update_elo_with_mov, update_od_elo, calculate_k_with_decay
from src.models.predictor import predict_games_for_date, clear_injuries_cache
from src.betting.odds_converter import american_to_decimal
from config import CURRENT_SEASON, USE_OD_ELO


def update_game_results():
    """Fetch and update recent game results."""
    print("\n1. Updating game results...")

    # Check games from the last 3 days
    today = datetime.now()

    for days_ago in range(3):
        check_date = today - timedelta(days=days_ago)
        date_str = check_date.strftime("%Y-%m-%d")

        print(f"   Checking {date_str}...")

        # Fetch from NBA API
        games = fetch_games_by_date(date_str)

        if games.empty:
            print(f"   No games found for {date_str}")
            continue

        processed = process_scoreboard_for_db(games, CURRENT_SEASON)

        for game in processed:
            if game['status'] == 'final' and game['home_score'] and game['away_score']:
                # Update game result
                update_game_result(
                    game_id=game['game_id'],
                    home_score=game['home_score'],
                    away_score=game['away_score']
                )
                print(f"   Updated: {game['game_id']} ({game['home_score']}-{game['away_score']})")


def update_elo_ratings():
    """Update Elo ratings for newly completed games (including O/D Elo)."""
    print("\n2. Updating Elo ratings...")

    # Get all final games without post-game Elo
    games_df = get_games_by_season(CURRENT_SEASON, status='final')

    if games_df.empty:
        print("   No completed games to process")
        return

    # Filter to games without post-game Elo
    games_to_update = games_df[games_df['home_elo_post'].isna()]

    if games_to_update.empty:
        print("   All games already have Elo calculated")
        return

    # Count games already processed this season (for K-decay)
    games_already_processed = len(games_df[games_df['home_elo_post'].notna()])

    # Load current team ratings (including O/D Elo)
    teams_df = get_all_teams()
    elo_ratings = {row['team_id']: row['current_elo'] for _, row in teams_df.iterrows()}

    # O/D Elo ratings
    od_ratings = {}
    for _, row in teams_df.iterrows():
        od_ratings[row['team_id']] = {
            'offense': row.get('offense_elo', 1500.0) or 1500.0,
            'defense': row.get('defense_elo', 1500.0) or 1500.0,
        }

    # Sort by date and process
    games_to_update = games_to_update.sort_values('game_date')

    games_processed = 0
    for _, game in games_to_update.iterrows():
        home_id = game['home_team_id']
        away_id = game['away_team_id']

        if home_id not in elo_ratings or away_id not in elo_ratings:
            continue

        home_elo = elo_ratings[home_id]
        away_elo = elo_ratings[away_id]
        home_score = int(game['home_score'])
        away_score = int(game['away_score'])

        # Calculate K-factor with seasonal decay
        total_games_so_far = games_already_processed + games_processed
        k_factor = calculate_k_with_decay(total_games_so_far)

        # Update composite Elo with margin of victory adjustment
        result = update_elo_with_mov(home_elo, away_elo, home_score, away_score, k_factor=k_factor)
        games_processed += 1

        # Save composite Elo to database
        update_game_elo_snapshots(
            game_id=game['game_id'],
            home_elo_pre=home_elo,
            away_elo_pre=away_elo,
            home_elo_post=result.home_new_elo,
            away_elo_post=result.away_new_elo
        )

        record_elo_change(home_id, game['game_id'], home_elo, result.home_new_elo)
        record_elo_change(away_id, game['game_id'], away_elo, result.away_new_elo)

        # Update in-memory composite Elo
        elo_ratings[home_id] = result.home_new_elo
        elo_ratings[away_id] = result.away_new_elo

        # Update O/D Elo if enabled
        if USE_OD_ELO:
            home_o = od_ratings[home_id]['offense']
            home_d = od_ratings[home_id]['defense']
            away_o = od_ratings[away_id]['offense']
            away_d = od_ratings[away_id]['defense']

            od_result = update_od_elo(
                home_o, home_d, away_o, away_d,
                home_score, away_score, k_factor=k_factor
            )

            # Save O/D Elo snapshots
            update_game_od_elo_snapshots(
                game_id=game['game_id'],
                home_offense_elo_pre=home_o,
                home_defense_elo_pre=home_d,
                away_offense_elo_pre=away_o,
                away_defense_elo_pre=away_d,
                home_offense_elo_post=od_result.home_offense_elo_new,
                home_defense_elo_post=od_result.home_defense_elo_new,
                away_offense_elo_post=od_result.away_offense_elo_new,
                away_defense_elo_post=od_result.away_defense_elo_new,
            )

            # Update in-memory O/D Elo
            od_ratings[home_id]['offense'] = od_result.home_offense_elo_new
            od_ratings[home_id]['defense'] = od_result.home_defense_elo_new
            od_ratings[away_id]['offense'] = od_result.away_offense_elo_new
            od_ratings[away_id]['defense'] = od_result.away_defense_elo_new

        print(f"   Updated Elo for game {game['game_id']}")

    # Save final ratings
    for team_id, elo in elo_ratings.items():
        update_team_elo(team_id, elo)

    # Save O/D Elo ratings
    if USE_OD_ELO:
        for team_id, od in od_ratings.items():
            update_team_od_elo(team_id, od['offense'], od['defense'])

    print(f"   Processed {len(games_to_update)} games")


def fetch_todays_games():
    """Fetch today's scheduled games."""
    print("\n3. Fetching today's games...")

    today = datetime.now().strftime("%Y-%m-%d")
    games = fetch_games_by_date(today)

    if games.empty:
        print("   No games scheduled today")
        return

    processed = process_scoreboard_for_db(games, CURRENT_SEASON)

    for game in processed:
        upsert_game(**game)

    print(f"   Loaded {len(processed)} games for today")


def fetch_injuries():
    """Fetch injury reports for today's games from ESPN."""
    print("\n4. Fetching injury reports...")

    today = datetime.now().strftime("%Y-%m-%d")

    # Clear cache to ensure fresh data
    clear_injuries_cache()

    try:
        injuries_df = fetch_injuries_for_date(today)

        if injuries_df.empty:
            print("   No injury reports available for today")
            return

        # Count injuries by team
        if "team_abbr" in injuries_df.columns:
            team_counts = injuries_df["team_abbr"].value_counts()
            print(f"   Fetched {len(injuries_df)} injury reports across {len(team_counts)} teams")

            # Show significant injuries (where status is Out or Doubtful)
            if "status" in injuries_df.columns:
                significant = injuries_df[
                    injuries_df["status"].str.lower().str.contains("out|doubtful", na=False)
                ]
                if not significant.empty:
                    print("   Notable injuries:")
                    for _, row in significant.head(10).iterrows():
                        player = row.get("player_name", "Unknown")
                        team = row.get("team_abbr", "???")
                        status = row.get("status", "Out")
                        print(f"     - {player} ({team}): {status}")
                    if len(significant) > 10:
                        print(f"     ... and {len(significant) - 10} more")
        else:
            print(f"   Fetched {len(injuries_df)} injury reports")

    except Exception as e:
        print(f"   Error fetching injuries: {e}")


def generate_predictions():
    """Generate predictions for today's games with injury adjustments."""
    print("\n5. Generating predictions...")

    today = datetime.now().strftime("%Y-%m-%d")
    predictions = predict_games_for_date(today, save_to_db=True, apply_injuries=True)

    if not predictions:
        print("   No predictions to generate")
        return

    print(f"   Generated {len(predictions)} predictions")

    for pred in predictions:
        spread_str = f"{pred.home_team} {pred.predicted_spread:.1f}" if pred.predicted_spread < 0 else f"{pred.away_team} {-pred.predicted_spread:.1f}"
        injury_note = ""
        if pred.injuries_applied:
            total_adj = abs(pred.home_injury_adjustment) + abs(pred.away_injury_adjustment)
            if total_adj >= 20:
                injury_note = f" [Inj: {pred.home_team} {pred.home_injury_adjustment:+.0f}, {pred.away_team} {pred.away_injury_adjustment:+.0f}]"
        print(f"   {pred.away_team} @ {pred.home_team}: {pred.home_team} {pred.home_win_prob:.1%} | Spread: {spread_str}{injury_note}")


def fetch_odds():
    """Fetch current odds for today's games."""
    print("\n6. Fetching current odds...")

    try:
        odds_df = get_current_odds()
        if odds_df.empty:
            print("   No odds available (check API key)")
        else:
            print(f"   Fetched odds for {len(odds_df)} game/book combinations")
    except Exception as e:
        print(f"   Error fetching odds: {e}")


def seed_od_elo_from_api():
    """Seed initial O/D Elo values from NBA API team ratings."""
    print("\n   Seeding O/D Elo from NBA API...")

    try:
        od_df = fetch_team_offensive_defensive_ratings(CURRENT_SEASON)

        if od_df.empty:
            print("   Could not fetch team ratings from API")
            return False

        # Get existing teams from database
        teams_df = get_all_teams()
        team_map = {row['abbreviation']: row['team_id'] for _, row in teams_df.iterrows()}

        updated = 0
        for _, row in od_df.iterrows():
            team_abbr = row['team_abbr']
            if team_abbr in team_map:
                team_id = team_map[team_abbr]
                update_team_od_elo(team_id, row['offense_elo'], row['defense_elo'])
                updated += 1
                print(f"   {team_abbr}: O-Elo={row['offense_elo']:.0f}, D-Elo={row['defense_elo']:.0f}")

        print(f"   Seeded O/D Elo for {updated} teams")
        return True

    except Exception as e:
        print(f"   Error seeding O/D Elo: {e}")
        return False


def update_player_impact():
    """Update player impact ratings from NBA API."""
    print("\n7. Updating player impact ratings...")

    try:
        impact_df = fetch_player_impact_stats(CURRENT_SEASON)

        if impact_df.empty:
            print("   No player impact data available")
            return

        # Save to database
        for _, row in impact_df.iterrows():
            upsert_player_impact(
                player_id=int(row['player_id']),
                player_name=row['player_name'],
                team_abbr=row['team_abbr'],
                net_rating=row['net_rating'],
                minutes_per_game=row['minutes_per_game'],
                games_played=int(row['games_played']),
                elo_impact=row['elo_impact'],
                season=CURRENT_SEASON,
                usg_pct=row.get('usg_pct'),
            )

        # Show top players by impact
        top_players = impact_df.nlargest(5, 'elo_impact')
        print(f"   Updated {len(impact_df)} players. Top 5 by impact:")
        for _, p in top_players.iterrows():
            print(f"     {p['player_name']} ({p['team_abbr']}): {p['elo_impact']:+.1f} Elo")

    except Exception as e:
        print(f"   Error updating player impact: {e}")


def auto_settle_bets():
    """Auto-settle bets where possible."""
    print("\n7. Checking for bets to settle...")

    unsettled = get_unsettled_bets()

    if unsettled.empty:
        print("   No unsettled bets")
        return

    settled_count = 0

    for _, bet in unsettled.iterrows():
        if bet['status'] != 'final':
            continue

        # Auto-settle moneyline bets
        if bet['bet_type'] == 'moneyline':
            home_won = bet['home_score'] > bet['away_score']
            selection_is_home = bet['selection'] == bet['home_abbr']

            if (home_won and selection_is_home) or (not home_won and not selection_is_home):
                result = 'win'
                decimal_odds = american_to_decimal(int(bet['odds']))
                payout = bet['stake'] * decimal_odds
                profit = payout - bet['stake']
            else:
                result = 'loss'
                payout = 0
                profit = -bet['stake']

            settle_bet(bet['bet_id'], result, payout, profit)
            print(f"   Settled bet {bet['bet_id']}: {result} (${profit:+.2f})")
            settled_count += 1

    print(f"   Auto-settled {settled_count} bets")


def check_and_seed_od_elo():
    """Check if O/D Elo needs seeding and seed if necessary."""
    teams_df = get_all_teams()

    # Check if any team has O/D Elo set (not default 1500 or null)
    needs_seeding = True
    for _, row in teams_df.iterrows():
        o_elo = row.get('offense_elo')
        d_elo = row.get('defense_elo')
        # If any team has non-default O/D Elo, we don't need to seed
        if o_elo and d_elo and (o_elo != 1500.0 or d_elo != 1500.0):
            needs_seeding = False
            break

    if needs_seeding and USE_OD_ELO:
        print("\n   O/D Elo not initialized - seeding from NBA API...")
        seed_od_elo_from_api()


def main(force: bool = False):
    # Check if already ran today (unless --force)
    if not force and already_ran_today():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Already ran today, skipping. Use --force to override.")
        return

    print("=" * 50)
    print("NBA Betting Value - Daily Update")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Initialize database
    init_database()

    # Check if O/D Elo needs seeding (first run with new feature)
    check_and_seed_od_elo()

    # Run updates
    update_game_results()
    update_elo_ratings()
    fetch_todays_games()
    fetch_injuries()
    generate_predictions()
    fetch_odds()
    update_player_impact()
    auto_settle_bets()

    # Mark as completed
    mark_as_ran()

    print("\n" + "=" * 50)
    print("Daily update complete!")
    print("=" * 50)


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
