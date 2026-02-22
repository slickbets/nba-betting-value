#!/usr/bin/env python3
"""Backfill missing days (2/19-2/22) from NBA CDN schedule.

The NBA API (stats.nba.com) has been timing out since ~2/12, so the daily
update hasn't been able to fetch game data. This script uses the CDN schedule
(cdn.nba.com) which is on a different host and still works.

For each date, it:
  1. Inserts games as 'scheduled' (preserves existing DB data via COALESCE)
  2. Generates predictions (saves only for scheduled/no-prediction games)
  3. Marks final games with scores from CDN
  4. Updates Elo ratings for newly finalized games

This order ensures predictions use the Elo state from BEFORE that date's games.

Usage:
    /opt/homebrew/bin/python3.11 scripts/backfill_missing_days.py
"""

import json
import logging
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON, now_ct
from src.data.database import (
    init_database,
    upsert_game,
    update_game_result,
    get_games_by_date,
)
from src.models.predictor import predict_games_for_date
from scripts.daily_update import update_elo_ratings, check_league_avg_score

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

# Dates to backfill (post-All-Star break through today)
TARGET_DATES = ['2026-02-19', '2026-02-20', '2026-02-21', '2026-02-22']

CDN_SCHEDULE_URL = 'https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json'


def parse_game_time_et(time_est_str: str) -> str | None:
    """Parse CDN gameTimeEst (e.g. '1900-01-01T19:00:00Z') to '7:00 pm ET'."""
    if not time_est_str:
        return None
    try:
        t = datetime.strptime(time_est_str, '1900-01-01T%H:%M:%SZ')
        hour = t.hour
        minute = t.minute
        ampm = 'am' if hour < 12 else 'pm'
        if hour > 12:
            hour -= 12
        elif hour == 0:
            hour = 12
        return f"{hour}:{minute:02d} {ampm} ET"
    except ValueError:
        return None


def fetch_nba_cdn_schedule() -> dict[str, list[dict]]:
    """Fetch schedule from NBA CDN, return {date_str: [game_dicts]}.

    Each game dict has keys:
      game_id, home_team_id, away_team_id, home_tricode, away_tricode,
      home_score, away_score, status, game_time
    """
    logger.info("Fetching NBA CDN schedule...")
    req = urllib.request.Request(CDN_SCHEDULE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())

    game_dates = data['leagueSchedule']['gameDates']

    target_set = set(TARGET_DATES)
    status_map = {1: 'scheduled', 2: 'in_progress', 3: 'final'}
    result = {}

    for gd in game_dates:
        # Parse date from "02/19/2026 00:00:00" format
        date_raw = gd['gameDate']
        date_parsed = datetime.strptime(date_raw.split()[0], '%m/%d/%Y')
        date_str = date_parsed.strftime('%Y-%m-%d')

        if date_str not in target_set:
            continue

        games = []
        for g in gd['games']:
            ht = g['homeTeam']
            at = g['awayTeam']

            game_status = status_map.get(g['gameStatus'], 'scheduled')
            game_time = parse_game_time_et(g.get('gameTimeEst', ''))

            # Only trust scores for final games (in-progress shows 0-0 in static CDN)
            home_score = None
            away_score = None
            if game_status == 'final':
                raw_home = ht.get('score')
                raw_away = at.get('score')
                if raw_home is not None and raw_away is not None:
                    home_score = int(raw_home)
                    away_score = int(raw_away)

            games.append({
                'game_id': g['gameId'],
                'home_team_id': ht['teamId'],
                'away_team_id': at['teamId'],
                'home_tricode': ht['teamTricode'],
                'away_tricode': at['teamTricode'],
                'home_score': home_score,
                'away_score': away_score,
                'status': game_status,
                'game_time': game_time,
            })

        result[date_str] = games
        logger.info("  %s: %d games (%d final)",
                     date_str, len(games),
                     sum(1 for g in games if g['status'] == 'final'))

    return result


def process_date(date_str: str, games: list[dict], is_today: bool):
    """Process a single date: insert games, predict, mark finals, update Elo."""
    logger.info("")
    logger.info("=" * 40)
    logger.info("Processing %s (%d games)%s", date_str, len(games),
                " [TODAY]" if is_today else "")
    logger.info("=" * 40)

    # Check which games are already final in DB (don't overwrite)
    existing = get_games_by_date(date_str)
    existing_final_ids = set()
    if not existing.empty:
        existing_final_ids = set(
            existing[existing['status'] == 'final']['game_id'].tolist()
        )

    # Step 1: Insert games as 'scheduled' so predictions can be generated
    inserted = 0
    for g in games:
        if g['game_id'] in existing_final_ids:
            logger.info("  Skip (already final): %s %s@%s",
                        g['game_id'], g['away_tricode'], g['home_tricode'])
            continue

        upsert_game(
            game_id=g['game_id'],
            season=CURRENT_SEASON,
            game_date=date_str,
            game_time=g['game_time'],
            home_team_id=g['home_team_id'],
            away_team_id=g['away_team_id'],
            status='scheduled',
        )
        inserted += 1
    logger.info("  Inserted/upserted %d games as scheduled", inserted)

    # Step 2: Generate predictions (uses current Elo state, which reflects
    # all prior dates' Elo updates thanks to chronological processing)
    predictions = predict_games_for_date(
        date_str,
        save_to_db=True,
        apply_injuries=is_today,
        apply_rest=True,
    )
    logger.info("  Generated %d predictions:", len(predictions))
    for pred in predictions:
        if pred.predicted_spread < 0:
            spread_str = f"{pred.home_team} {pred.predicted_spread:.1f}"
        else:
            spread_str = f"{pred.away_team} {-pred.predicted_spread:.1f}"
        logger.info("    %s @ %s: %s %.1f%% | Spread: %s",
                     pred.away_team, pred.home_team,
                     pred.home_team, pred.home_win_prob * 100, spread_str)

    # Step 3: Mark final games with scores
    finals_updated = 0
    for g in games:
        if (g['status'] == 'final'
                and g['home_score'] is not None
                and g['away_score'] is not None
                and g['game_id'] not in existing_final_ids):
            update_game_result(g['game_id'], g['home_score'], g['away_score'])
            finals_updated += 1
            logger.info("  Final: %s %s@%s %d-%d",
                        g['game_id'], g['away_tricode'], g['home_tricode'],
                        g['away_score'], g['home_score'])
    logger.info("  Marked %d games as final", finals_updated)

    # Step 4: Update Elo ratings for newly finalized games
    if finals_updated > 0:
        update_elo_ratings()


def main():
    logger.info("=" * 50)
    logger.info("NBA Betting Value - Backfill Missing Days")
    logger.info("Run time: %s", now_ct().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 50)

    init_database()

    # Update league avg score before Elo/predictions use it
    check_league_avg_score()

    # Fetch CDN schedule for all target dates
    schedule = fetch_nba_cdn_schedule()

    today = now_ct().strftime('%Y-%m-%d')

    # Process each date chronologically
    for date_str in TARGET_DATES:
        if date_str not in schedule:
            logger.info("No CDN data for %s, skipping", date_str)
            continue

        process_date(date_str, schedule[date_str], is_today=(date_str == today))

    # Verification
    logger.info("")
    logger.info("=" * 50)
    logger.info("Backfill complete! Verification:")
    logger.info("=" * 50)
    for date_str in TARGET_DATES:
        df = get_games_by_date(date_str)
        if df.empty:
            logger.info("  %s: no games", date_str)
            continue
        finals = len(df[df['status'] == 'final'])
        preds = df['predicted_home_win_prob'].notna().sum()
        elo_done = df['home_elo_post'].notna().sum()
        logger.info("  %s: %d games, %d final, %d predictions, %d with post-Elo",
                     date_str, len(df), finals, preds, elo_done)


if __name__ == "__main__":
    main()
