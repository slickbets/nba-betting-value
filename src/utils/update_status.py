"""Utility to check daily update status without heavy imports."""

from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import DATA_DIR

LAST_RUN_FILE = DATA_DIR / ".last_daily_update"


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
