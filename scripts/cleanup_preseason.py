"""Remove preseason games and their elo_history entries from the database.

Preseason games (before regular season tipoff) were accidentally included
in the database, contaminating Elo ratings. This script removes them.

After running this, rebuild Elo with:
    python scripts/backfill_history.py
    python scripts/backfill_od_elo.py --season 2025-26
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

# Regular season start dates (first day of regular season games)
SEASON_STARTS = {
    '2024-25': '2024-10-22',
    '2025-26': '2025-10-21',
}


def cleanup_preseason(dry_run: bool = False):
    conn = sqlite3.connect(DB_PATH)

    for season, start_date in SEASON_STARTS.items():
        # Count preseason games
        c = conn.execute(
            'SELECT COUNT(*) FROM games WHERE season=? AND game_date < ?',
            (season, start_date)
        )
        game_count = c.fetchone()[0]

        # Count elo_history entries for those games
        c = conn.execute('''
            SELECT COUNT(*) FROM elo_history
            WHERE game_id IN (
                SELECT game_id FROM games WHERE season=? AND game_date < ?
            )
        ''', (season, start_date))
        elo_count = c.fetchone()[0]

        print(f'{season}: {game_count} preseason games, {elo_count} elo_history entries')

        if dry_run:
            # Show sample
            c = conn.execute('''
                SELECT game_date,
                       (SELECT abbreviation FROM teams WHERE team_id = home_team_id) as home,
                       (SELECT abbreviation FROM teams WHERE team_id = away_team_id) as away,
                       home_score, away_score
                FROM games WHERE season=? AND game_date < ?
                ORDER BY game_date LIMIT 5
            ''', (season, start_date))
            for row in c.fetchall():
                print(f'  {row[0]} {row[2]}@{row[1]} {row[3]}-{row[4]}')
            continue

        # Delete elo_history entries first (FK reference)
        conn.execute('''
            DELETE FROM elo_history
            WHERE game_id IN (
                SELECT game_id FROM games WHERE season=? AND game_date < ?
            )
        ''', (season, start_date))
        print(f'  Deleted {elo_count} elo_history entries')

        # Delete preseason games
        conn.execute(
            'DELETE FROM games WHERE season=? AND game_date < ?',
            (season, start_date)
        )
        print(f'  Deleted {game_count} preseason games')

    if not dry_run:
        conn.commit()
        print('\nPreseason data cleaned. Now rebuild Elo:')
        print('  python scripts/backfill_history.py')
        print('  python scripts/backfill_od_elo.py --season 2025-26')

    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print('=== DRY RUN (no changes) ===\n')
    cleanup_preseason(dry_run=dry_run)
