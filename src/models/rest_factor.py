"""Rest day factors for NBA game predictions.

Teams on back-to-backs (0 rest days) perform worse, while well-rested teams
have a slight advantage. This module calculates Elo adjustments based on
days of rest for each team.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Rest day Elo adjustments (in Elo points)
# Based on research showing B2B teams win ~3-4% less often
# 18 Elo = 1 point spread, so -35 = ~1.9 point penalty (sweep-optimized)
REST_ADJUSTMENTS = {
    0: -35,   # Back-to-back: ~1.9 point penalty (sweep-optimized from -25)
    1: 0,     # Normal rest: no adjustment
    2: 5,     # Extra rest: slight boost
    3: 8,     # Well rested: moderate boost
}
# 4+ days defaults to same as 3 (diminishing returns)
MAX_REST_BONUS = 8


def get_rest_adjustment(rest_days: int) -> float:
    """
    Get Elo adjustment based on days of rest.

    Args:
        rest_days: Number of days since last game (0 = back-to-back)

    Returns:
        Elo adjustment (negative for B2B, positive for extra rest)
    """
    if rest_days < 0:
        return 0  # Invalid, no adjustment

    if rest_days in REST_ADJUSTMENTS:
        return REST_ADJUSTMENTS[rest_days]

    # 4+ days: cap at max bonus
    return MAX_REST_BONUS


def calculate_rest_days(last_game_date: str, current_game_date: str) -> int:
    """
    Calculate days of rest between games.

    Args:
        last_game_date: Date of previous game (YYYY-MM-DD)
        current_game_date: Date of current game (YYYY-MM-DD)

    Returns:
        Days of rest (0 = back-to-back, 1 = normal, etc.)
    """
    try:
        last_date = datetime.strptime(last_game_date, "%Y-%m-%d")
        current_date = datetime.strptime(current_game_date, "%Y-%m-%d")

        # Days between games minus 1 (if played yesterday, that's 0 rest days)
        days_diff = (current_date - last_date).days - 1

        return max(0, days_diff)  # Can't have negative rest
    except (ValueError, TypeError):
        return 1  # Default to normal rest if dates are invalid


def get_rest_description(rest_days: int) -> str:
    """Get human-readable description of rest situation."""
    if rest_days == 0:
        return "B2B"
    elif rest_days == 1:
        return "1 day"
    elif rest_days == 2:
        return "2 days"
    elif rest_days >= 3:
        return f"{rest_days} days"
    return "?"


def get_rest_adjustments_for_game(
    home_team_id: int,
    away_team_id: int,
    game_date: str,
) -> Tuple[float, float, int, int]:
    """
    Get rest adjustments for both teams in a game.

    Args:
        home_team_id: Home team's database ID
        away_team_id: Away team's database ID
        game_date: Date of the game (YYYY-MM-DD)

    Returns:
        Tuple of (home_rest_adj, away_rest_adj, home_rest_days, away_rest_days)
    """
    from src.data.database import get_team_last_game_date

    # Get last game dates for each team
    home_last_game = get_team_last_game_date(home_team_id, game_date)
    away_last_game = get_team_last_game_date(away_team_id, game_date)

    # Calculate rest days
    if home_last_game:
        home_rest_days = calculate_rest_days(home_last_game, game_date)
    else:
        home_rest_days = 1  # Season opener or no data - assume normal rest (0 adjustment)

    if away_last_game:
        away_rest_days = calculate_rest_days(away_last_game, game_date)
    else:
        away_rest_days = 1  # Season opener or no data - assume normal rest (0 adjustment)

    # Get Elo adjustments
    home_rest_adj = get_rest_adjustment(home_rest_days)
    away_rest_adj = get_rest_adjustment(away_rest_days)

    return home_rest_adj, away_rest_adj, home_rest_days, away_rest_days
