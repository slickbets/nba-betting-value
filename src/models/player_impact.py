"""Player impact calculations using database ratings for injury adjustments.

This module calculates Elo adjustments for injured players based on their
impact rating (NET_RATING * playing_time_factor). Data comes from the
player_impact database table, auto-populated from NBA API.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

import pandas as pd

# Add project root to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Elo impact is pre-calculated in the database using:
# elo_impact = NET_RATING * (MPG / 48) * (USG% / 0.20) * 1.5

# Fuzzy match threshold (0-1, higher = stricter)
FUZZY_MATCH_THRESHOLD = 0.85


def normalize_player_name(name: str) -> str:
    """Normalize player name for matching."""
    if not name:
        return ""
    return re.sub(r"[^\w\s]", "", name.lower().strip())


def fuzzy_match_name(name1: str, name2: str) -> float:
    """
    Calculate fuzzy match score between two names.

    Args:
        name1: First name (normalized)
        name2: Second name (normalized)

    Returns:
        Match score between 0 and 1
    """
    return SequenceMatcher(None, name1, name2).ratio()


def get_player_elo_impact(player_name: str, team_abbr: Optional[str] = None) -> float:
    """
    Get player's Elo impact from database.

    Tries exact/partial match first, then fuzzy matching (85% threshold).
    Returns 0.0 if player is not found (conservative fallback).

    Args:
        player_name: Player's name
        team_abbr: Optional team abbreviation for disambiguation

    Returns:
        Elo impact value (>= 0), or 0.0 if not found
    """
    try:
        from src.data.database import get_player_impact_by_name, get_all_player_impacts

        impact = None

        # Try exact/partial match first
        player = get_player_impact_by_name(player_name, team_abbr)
        if player:
            impact = player.get('elo_impact', 0.0)
        else:
            # If no match, try fuzzy matching
            normalized_name = normalize_player_name(player_name)
            all_players = get_all_player_impacts()

            if not all_players.empty:
                best_match = None
                best_score = 0.0

                for _, row in all_players.iterrows():
                    db_name = row.get('player_name_normalized', '')
                    if not db_name:
                        continue

                    score = fuzzy_match_name(normalized_name, db_name)

                    # If team matches, boost the score slightly
                    if team_abbr and row.get('team_abbr') == team_abbr:
                        score += 0.05

                    if score > best_score and score >= FUZZY_MATCH_THRESHOLD:
                        best_score = score
                        best_match = row

                if best_match is not None:
                    impact = best_match.get('elo_impact', 0.0)

        if impact is None:
            return 0.0

        # Clamp negative impact to 0: if a player has negative NET_RATING
        # (team is worse with them on court), losing them shouldn't penalize the team
        return max(impact, 0.0)

    except Exception as e:
        logger.error("Error getting player impact for %s: %s", player_name, e)
        return 0.0


def calculate_injury_adjustment(injured_players: list[dict]) -> float:
    """
    Calculate total Elo adjustment for a list of injured players.

    Args:
        injured_players: List of dicts with keys:
            - player_name: str
            - status_multiplier: float (1.0 for Out, 0.5 for Questionable, etc.)
            - team_abbr: str (optional, for disambiguation)

    Returns:
        Total Elo points to subtract from team's rating.
        Negative value (subtract from Elo when player is OUT).

    Example:
        SGA (elo_impact +27.6) is Out -> returns -27.6 Elo points
    """
    total_adjustment = 0.0

    for player in injured_players:
        player_name = player.get("player_name", "")
        status_multiplier = player.get("status_multiplier", 1.0)
        team_abbr = player.get("team_abbr")

        elo_impact = get_player_elo_impact(player_name, team_abbr)

        adjustment = -abs(elo_impact) * status_multiplier
        total_adjustment += adjustment

    return total_adjustment


def get_injury_adjustment_for_team(
    team_abbr: str,
    injuries_df: pd.DataFrame
) -> tuple[float, list[dict]]:
    """
    Calculate Elo adjustment for a team based on their injuries.

    Args:
        team_abbr: Team abbreviation (e.g., "LAL")
        injuries_df: DataFrame from fetch_injuries_for_date()

    Returns:
        Tuple of (total_adjustment, player_details):
            - total_adjustment: Elo points to add (negative for injuries)
            - player_details: List of dicts with player impact info
    """
    from src.data.injury_fetcher import get_team_injuries

    injured_players = get_team_injuries(team_abbr, injuries_df)

    if not injured_players:
        return 0.0, []

    player_details = []
    for player in injured_players:
        player_name = player["player_name"]
        status_multiplier = player.get("status_multiplier", 1.0)

        impact = get_player_elo_impact(player_name, team_abbr)
        elo_adjustment = -abs(impact) * status_multiplier

        player_details.append({
            "player_name": player_name,
            "status": player.get("status", "Out"),
            "reason": player.get("reason", ""),
            "elo_impact": elo_adjustment,
            "status_multiplier": status_multiplier,
        })

    # Sort by impact (most negative first)
    player_details.sort(key=lambda x: x["elo_impact"])

    total_adjustment = sum(p["elo_impact"] for p in player_details)

    return total_adjustment, player_details


