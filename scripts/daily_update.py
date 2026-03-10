#!/usr/bin/env python3
"""Daily update script - refresh games, settle bets, update Elo."""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR, now_ct

logger = logging.getLogger(__name__)

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
        return last_run_date == now_ct().strftime("%Y-%m-%d")
    except Exception:
        return False


def mark_as_ran():
    """Mark that we ran today with full timestamp."""
    LAST_RUN_FILE.write_text(now_ct().strftime("%Y-%m-%d %H:%M:%S"))


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

        ran_today = last_run_dt.date() == now_ct().date()

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
    clear_old_player_impacts,
    get_league_avg_score,
)
from src.data.bdl_fetcher import (
    fetch_games_bdl,
    fetch_player_impact_bdl,
    fetch_team_ratings_bdl,
)
from src.data.nba_fetcher import (
    fetch_scoreboard_espn,
    fetch_team_offensive_defensive_ratings,
)
from src.data.odds_fetcher import get_current_odds
from src.data.injury_fetcher import fetch_injuries_for_date
from src.models.elo import update_elo_with_mov, update_od_elo, calculate_k_with_decay
from src.models.predictor import predict_games_for_date, clear_injuries_cache
from src.betting.odds_converter import american_to_decimal
from config import CURRENT_SEASON, USE_OD_ELO, LEAGUE_AVG_SCORE


def update_game_results():
    """Fetch and update recent game results (BDL primary, ESPN fallback)."""
    logger.info("1. Updating game results...")

    today = now_ct()

    for days_ago in range(3):
        check_date = today - timedelta(days=days_ago)
        date_str = check_date.strftime("%Y-%m-%d")

        logger.info("Checking %s...", date_str)

        # Primary: BallDontLie API
        bdl_games = fetch_games_bdl(date_str)

        if bdl_games:
            updated = 0
            for game in bdl_games:
                if game['status'] == 'final' and game['home_score'] and game['away_score']:
                    # upsert handles both insert and update
                    upsert_game(**game)
                    update_game_result(
                        game_id=game['game_id'],
                        home_score=game['home_score'],
                        away_score=game['away_score']
                    )
                    updated += 1
                    logger.info("Updated (BDL): %s (%s-%s)", game['game_id'], game['home_score'], game['away_score'])
            logger.info("BDL results for %s: %d updated", date_str, updated)
            continue

        # ESPN fallback when BDL returns empty
        logger.info("BDL returned no data for %s, trying ESPN fallback...", date_str)
        espn_games = fetch_scoreboard_espn(date_str)
        if not espn_games:
            logger.info("No games found for %s", date_str)
            continue

        teams_df = get_all_teams()
        team_map = {row['abbreviation']: int(row['team_id']) for _, row in teams_df.iterrows()}
        existing_games = get_games_by_date(date_str)

        updated = 0
        inserted = 0
        for espn_game in espn_games:
            if espn_game['status'] != 'final' or not espn_game['home_score'] or not espn_game['away_score']:
                continue

            home_abbr = espn_game['home_abbr']
            away_abbr = espn_game['away_abbr']

            if not existing_games.empty:
                match = existing_games[
                    (existing_games['home_abbr'] == home_abbr) &
                    (existing_games['away_abbr'] == away_abbr)
                ]
                if not match.empty:
                    game_id = match.iloc[0]['game_id']
                    update_game_result(
                        game_id=game_id,
                        home_score=espn_game['home_score'],
                        away_score=espn_game['away_score']
                    )
                    updated += 1
                    continue

            home_id = team_map.get(home_abbr)
            away_id = team_map.get(away_abbr)
            if not home_id or not away_id:
                logger.warning("Unknown team abbreviation: %s or %s", home_abbr, away_abbr)
                continue

            date_compact = date_str.replace("-", "")
            game_id = f"ESPN_{date_compact}_{away_abbr}_{home_abbr}"
            upsert_game(
                game_id=game_id, season=CURRENT_SEASON, game_date=date_str,
                home_team_id=home_id, away_team_id=away_id,
                home_score=espn_game['home_score'], away_score=espn_game['away_score'],
                status='final',
            )
            inserted += 1

        logger.info("ESPN results for %s: %d updated, %d inserted", date_str, updated, inserted)


def update_elo_ratings():
    """Update Elo ratings for newly completed games (including O/D Elo)."""
    logger.info("2. Updating Elo ratings...")

    # Get all final games without post-game Elo
    games_df = get_games_by_season(CURRENT_SEASON, status='final')

    if games_df.empty:
        logger.info("No completed games to process")
        return

    # Filter to games without post-game Elo
    games_to_update = games_df[games_df['home_elo_post'].isna()]

    if games_to_update.empty:
        logger.info("All games already have Elo calculated")
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

        logger.info("Updated Elo for game %s", game['game_id'])

    # Save final ratings
    for team_id, elo in elo_ratings.items():
        update_team_elo(team_id, elo)

    # Save O/D Elo ratings
    if USE_OD_ELO:
        for team_id, od in od_ratings.items():
            update_team_od_elo(team_id, od['offense'], od['defense'])

    logger.info("Processed %d games", len(games_to_update))


def fetch_todays_games():
    """Fetch today's scheduled games (BDL primary, ESPN fallback)."""
    logger.info("3. Fetching today's games...")

    today = now_ct().strftime("%Y-%m-%d")

    # Primary: BallDontLie API
    bdl_games = fetch_games_bdl(today)

    if bdl_games:
        for game in bdl_games:
            upsert_game(**game)
        logger.info("BDL: loaded %d games for today", len(bdl_games))
        return

    # ESPN fallback
    logger.info("BDL returned no data for today, trying ESPN fallback...")
    espn_games = fetch_scoreboard_espn(today)
    if not espn_games:
        logger.info("No games scheduled today")
        return

    teams_df = get_all_teams()
    team_map = {row['abbreviation']: int(row['team_id']) for _, row in teams_df.iterrows()}
    existing_games = get_games_by_date(today)

    updated = 0
    inserted = 0
    for espn_game in espn_games:
        home_abbr = espn_game['home_abbr']
        away_abbr = espn_game['away_abbr']

        if not existing_games.empty:
            match = existing_games[
                (existing_games['home_abbr'] == home_abbr) &
                (existing_games['away_abbr'] == away_abbr)
            ]
            if not match.empty:
                game_row = match.iloc[0]
                upsert_game(
                    game_id=game_row['game_id'], season=game_row['season'],
                    game_date=today, game_time=espn_game.get('game_time'),
                    home_team_id=int(game_row['home_team_id']),
                    away_team_id=int(game_row['away_team_id']),
                    home_score=espn_game['home_score'], away_score=espn_game['away_score'],
                    status=espn_game['status'],
                )
                updated += 1
                continue

        home_id = team_map.get(home_abbr)
        away_id = team_map.get(away_abbr)
        if not home_id or not away_id:
            continue

        date_compact = today.replace("-", "")
        game_id = f"ESPN_{date_compact}_{away_abbr}_{home_abbr}"
        upsert_game(
            game_id=game_id, season=CURRENT_SEASON, game_date=today,
            game_time=espn_game.get('game_time'), home_team_id=home_id,
            away_team_id=away_id, home_score=espn_game['home_score'],
            away_score=espn_game['away_score'], status=espn_game['status'],
        )
        inserted += 1

    logger.info("ESPN today: %d updated, %d inserted", updated, inserted)


def fetch_injuries():
    """Fetch injury reports for today's games from ESPN."""
    logger.info("4. Fetching injury reports...")

    today = now_ct().strftime("%Y-%m-%d")

    # Clear cache to ensure fresh data
    clear_injuries_cache()

    try:
        injuries_df = fetch_injuries_for_date(today)

        if injuries_df.empty:
            logger.info("No injury reports available for today")
            return

        # Count injuries by team
        if "team_abbr" in injuries_df.columns:
            team_counts = injuries_df["team_abbr"].value_counts()
            logger.info("Fetched %d injury reports across %d teams", len(injuries_df), len(team_counts))

            # Show significant injuries (where status is Out or Doubtful)
            if "status" in injuries_df.columns:
                significant = injuries_df[
                    injuries_df["status"].str.lower().str.contains("out|doubtful", na=False)
                ]
                if not significant.empty:
                    logger.info("Notable injuries:")
                    for _, row in significant.head(10).iterrows():
                        player = row.get("player_name", "Unknown")
                        team = row.get("team_abbr", "???")
                        status = row.get("status", "Out")
                        logger.info("  - %s (%s): %s", player, team, status)
                    if len(significant) > 10:
                        logger.info("  ... and %d more", len(significant) - 10)
        else:
            logger.info("Fetched %d injury reports", len(injuries_df))

    except Exception as e:
        logger.error("Error fetching injuries: %s", e)


def generate_predictions():
    """Generate predictions for today's games with injury adjustments."""
    logger.info("5. Generating predictions...")

    today = now_ct().strftime("%Y-%m-%d")
    predictions = predict_games_for_date(today, save_to_db=True, apply_injuries=True)

    if not predictions:
        logger.info("No predictions to generate")
        return

    logger.info("Generated %d predictions", len(predictions))

    for pred in predictions:
        spread_str = f"{pred.home_team} {pred.predicted_spread:.1f}" if pred.predicted_spread < 0 else f"{pred.away_team} {-pred.predicted_spread:.1f}"
        injury_note = ""
        if pred.injuries_applied:
            total_adj = abs(pred.home_injury_adjustment) + abs(pred.away_injury_adjustment)
            if total_adj >= 20:
                injury_note = f" [Inj: {pred.home_team} {pred.home_injury_adjustment:+.0f}, {pred.away_team} {pred.away_injury_adjustment:+.0f}]"
        logger.info("%s @ %s: %s %.1f%% | Spread: %s%s", pred.away_team, pred.home_team, pred.home_team, pred.home_win_prob * 100, spread_str, injury_note)


def fetch_odds():
    """Fetch current odds for today's games."""
    logger.info("6. Fetching current odds...")

    try:
        odds_df = get_current_odds()
        if odds_df.empty:
            logger.warning("No odds available (check API key)")
        else:
            logger.info("Fetched odds for %d game/book combinations", len(odds_df))
    except Exception as e:
        logger.error("Error fetching odds: %s", e)


def seed_od_elo_from_api():
    """Seed initial O/D Elo values (BDL primary, NBA API fallback)."""
    logger.info("Seeding O/D Elo...")

    try:
        # Try BDL first
        od_df = fetch_team_ratings_bdl(CURRENT_SEASON)

        # Fall back to NBA API if BDL doesn't return data
        if od_df.empty:
            logger.info("BDL team ratings unavailable, trying NBA API fallback...")
            od_df = fetch_team_offensive_defensive_ratings(CURRENT_SEASON)

        if od_df.empty:
            logger.warning("Could not fetch team ratings from any source")
            return False

        teams_df = get_all_teams()
        team_map = {row['abbreviation']: row['team_id'] for _, row in teams_df.iterrows()}

        updated = 0
        for _, row in od_df.iterrows():
            team_abbr = row['team_abbr']
            if team_abbr in team_map:
                team_id = team_map[team_abbr]
                update_team_od_elo(team_id, row['offense_elo'], row['defense_elo'])
                updated += 1
                logger.info("%s: O-Elo=%.0f, D-Elo=%.0f", team_abbr, row['offense_elo'], row['defense_elo'])

        logger.info("Seeded O/D Elo for %d teams", updated)
        return True

    except Exception as e:
        logger.error("Error seeding O/D Elo: %s", e)
        return False


def _player_impact_is_fresh(max_age_days: int = 3) -> bool:
    """Check if player impact data was updated recently enough."""
    from src.data.database import get_connection
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(updated_at) FROM player_impact WHERE season = ?", (CURRENT_SEASON,))
        row = cursor.fetchone()
        if not row or not row[0]:
            return False
        try:
            last_update = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            age = (now_ct().replace(tzinfo=None) - last_update).days
            return age < max_age_days
        except Exception:
            return False


def update_player_impact():
    """Update player impact ratings (BDL primary, cloud-friendly)."""
    logger.info("8. Updating player impact ratings...")

    # Skip if data is fresh — BDL per-team fetch takes ~3 minutes
    if _player_impact_is_fresh(max_age_days=3):
        logger.info("Player impact data is less than 3 days old, skipping refresh")
        return

    try:
        deleted = clear_old_player_impacts(CURRENT_SEASON)
        if deleted > 0:
            logger.info("Cleared %d stale player impact entries from previous seasons", deleted)

        impact_df = fetch_player_impact_bdl(CURRENT_SEASON)

        if impact_df.empty:
            logger.warning("No player impact data available from BDL")
            return

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

        top_players = impact_df.nlargest(5, 'elo_impact')
        logger.info("Updated %d players. Top 5 by impact:", len(impact_df))
        for _, p in top_players.iterrows():
            logger.info("  %s (%s): %+.1f Elo", p['player_name'], p['team_abbr'], p['elo_impact'])

    except Exception as e:
        logger.error("Error updating player impact: %s", e)


def auto_settle_bets():
    """Auto-settle bets where possible."""
    logger.info("7. Checking for bets to settle...")

    unsettled = get_unsettled_bets()

    if unsettled.empty:
        logger.info("No unsettled bets")
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
            logger.info("Settled bet %s: %s ($%+.2f)", bet['bet_id'], result, profit)
            settled_count += 1

    logger.info("Auto-settled %d bets", settled_count)


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
        logger.info("O/D Elo not initialized - seeding from NBA API...")
        seed_od_elo_from_api()


def check_league_avg_score():
    """Update LEAGUE_AVG_SCORE at runtime from actual DB data."""
    import config

    actual_avg = get_league_avg_score(CURRENT_SEASON)
    if actual_avg is None:
        logger.info("No league avg score in DB yet, using config default (%.1f)", config.LEAGUE_AVG_SCORE)
        return

    old_val = config.LEAGUE_AVG_SCORE
    config.LEAGUE_AVG_SCORE = actual_avg
    diff = abs(actual_avg - old_val)
    if diff > 1.0:
        logger.warning(
            "League avg score auto-updated: %.1f → %.1f (config default was %.1f, diff %.1f)",
            old_val, actual_avg, old_val, diff,
        )
    else:
        logger.info("League avg score: %.1f (config default: %.1f)", actual_avg, old_val)


def main(force: bool = False):
    # Check if already ran today (unless --force)
    if not force and already_ran_today():
        logger.info("[%s] Already ran today, skipping. Use --force to override.",
                     now_ct().strftime('%Y-%m-%d %H:%M:%S'))
        return

    logger.info("=" * 50)
    logger.info("NBA Betting Value - Daily Update")
    logger.info("Run time: %s", now_ct().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 50)

    # Initialize database
    init_database()

    # Check if O/D Elo needs seeding (first run with new feature)
    check_and_seed_od_elo()

    # Auto-update league avg score before Elo/predictions use it
    check_league_avg_score()

    # Run updates (critical pipeline)
    update_game_results()
    update_elo_ratings()
    fetch_todays_games()
    fetch_injuries()
    generate_predictions()
    fetch_odds()
    auto_settle_bets()

    # Mark as completed — critical pipeline is done
    mark_as_ran()

    # Non-critical: player impact (slow, can fail without blocking next run)
    update_player_impact()

    logger.info("=" * 50)
    logger.info("Daily update complete!")
    logger.info("=" * 50)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )
    force = "--force" in sys.argv
    main(force=force)
