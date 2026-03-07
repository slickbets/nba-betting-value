"""Fetch NBA injury data using ESPN's public API."""

import logging
from datetime import datetime
from typing import Optional, Union

logger = logging.getLogger(__name__)

import pandas as pd
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ESPN API endpoint for NBA injuries
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"


# Map team names to standard abbreviations
TEAM_NAME_TO_ABBR = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "LA Clippers": "LAC",
    "LA Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

# Also map abbreviations for direct lookup
ABBR_TO_ABBR = {v: v for v in TEAM_NAME_TO_ABBR.values()}


# Status multipliers for Elo adjustment
# Higher = more likely to miss the game
STATUS_MULTIPLIERS = {
    "out": 1.0,
    "doubtful": 0.8,
    "questionable": 0.5,
    "probable": 0.1,
    "available": 0.0,
    "game time decision": 0.5,
    "gtd": 0.5,
    "day-to-day": 0.3,
}


def normalize_status(status: str) -> str:
    """Normalize injury status string to lowercase key."""
    if not status:
        return "out"
    status_lower = status.lower().strip()
    # Handle common variations
    if "out" in status_lower:
        return "out"
    if "doubtful" in status_lower:
        return "doubtful"
    if "questionable" in status_lower:
        return "questionable"
    if "probable" in status_lower:
        return "probable"
    if "available" in status_lower:
        return "available"
    if "gtd" in status_lower or "game time" in status_lower:
        return "game time decision"
    if "day-to-day" in status_lower or "day to day" in status_lower:
        return "day-to-day"
    return "out"  # Default to most conservative


def get_status_multiplier(status: str) -> float:
    """Get the Elo adjustment multiplier for a given injury status."""
    normalized = normalize_status(status)
    return STATUS_MULTIPLIERS.get(normalized, 1.0)


def normalize_team_name(team_name: str) -> Optional[str]:
    """Convert team name to standard abbreviation."""
    if not team_name:
        return None
    # Direct abbreviation match
    if team_name in ABBR_TO_ABBR:
        return team_name
    # Full name match
    if team_name in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[team_name]
    # Try partial match
    team_lower = team_name.lower()
    for full_name, abbr in TEAM_NAME_TO_ABBR.items():
        if full_name.lower() in team_lower or team_lower in full_name.lower():
            return abbr
    return None


def fetch_injuries_from_espn() -> pd.DataFrame:
    """
    Fetch current injury data from ESPN's public API.

    Returns:
        DataFrame with columns: player_name, team, team_abbr, status,
        status_multiplier, reason
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        response = requests.get(ESPN_INJURIES_URL, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        teams_injuries = data.get("injuries", [])

        if not teams_injuries:
            return pd.DataFrame()

        # Parse injury data
        records = []
        for team_data in teams_injuries:
            team_name = team_data.get("displayName", "")
            team_abbr = normalize_team_name(team_name)

            team_injuries = team_data.get("injuries", [])
            for injury in team_injuries:
                athlete = injury.get("athlete", {})
                player_name = athlete.get("displayName", "")
                status = injury.get("status", "Out")
                reason = injury.get("shortComment", "") or injury.get("longComment", "")

                records.append({
                    "player_name": player_name,
                    "team": team_name,
                    "team_abbr": team_abbr,
                    "status": status,
                    "status_multiplier": get_status_multiplier(status),
                    "reason": reason,
                })

        return pd.DataFrame(records)

    except requests.exceptions.RequestException as e:
        logger.error("Error fetching injuries from ESPN: %s", e)
        return pd.DataFrame()
    except Exception as e:
        logger.error("Error processing injury data: %s", e)
        return pd.DataFrame()


def fetch_injuries_for_date(game_date: Union[str, datetime] = None) -> pd.DataFrame:
    """
    Fetch injury report data (BDL primary, ESPN fallback).

    Args:
        game_date: Date parameter (ignored - APIs return current data only)

    Returns:
        DataFrame with columns: player_name, team, team_abbr, status,
        status_multiplier, reason
    """
    try:
        from src.data.bdl_fetcher import fetch_injuries_bdl
        df = fetch_injuries_bdl()
        if not df.empty:
            return df
    except Exception as e:
        logger.warning("BDL injuries failed, falling back to ESPN: %s", e)

    return fetch_injuries_from_espn()


def get_team_injuries(team_abbr: str, injuries_df: pd.DataFrame) -> list[dict]:
    """
    Get all injured players for a specific team.

    Args:
        team_abbr: Team abbreviation (e.g., "LAL")
        injuries_df: DataFrame from fetch_injuries_for_date()

    Returns:
        List of dicts with player injury info:
        [{"player_name": ..., "status": ..., "status_multiplier": ..., "reason": ...}, ...]
    """
    if injuries_df.empty or "team_abbr" not in injuries_df.columns:
        return []

    team_injuries = injuries_df[injuries_df["team_abbr"] == team_abbr]

    result = []
    for _, row in team_injuries.iterrows():
        result.append({
            "player_name": row.get("player_name", "Unknown"),
            "status": row.get("status", "Out"),
            "status_multiplier": row.get("status_multiplier", 1.0),
            "reason": row.get("reason", ""),
        })

    return result


