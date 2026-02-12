"""Fetch odds from The Odds API."""

import logging
import requests
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import ODDS_API_KEY, ODDS_API_BASE_URL, NBA_SPORT_KEY, PREFERRED_BOOKMAKERS
from src.data.database import insert_odds, get_team_by_abbreviation


# Team name mapping: The Odds API uses full names, we use abbreviations
ODDS_API_TEAM_MAP = {
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


def get_team_abbr(full_name: str) -> Optional[str]:
    """Convert full team name to abbreviation."""
    return ODDS_API_TEAM_MAP.get(full_name)


def fetch_nba_odds(markets: list[str] = None) -> Optional[dict]:
    """
    Fetch current NBA odds from The Odds API.

    Args:
        markets: List of market types to fetch. Defaults to ["h2h", "spreads", "totals"]

    Returns:
        API response dict or None if error
    """
    if not ODDS_API_KEY or ODDS_API_KEY == "your_key_here":
        logger.warning("ODDS_API_KEY not configured. Set it in .env file.")
        return None

    if markets is None:
        markets = ["h2h", "spreads", "totals"]

    url = f"{ODDS_API_BASE_URL}/sports/{NBA_SPORT_KEY}/odds"

    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": ",".join(markets),
        "oddsFormat": "american",
        "bookmakers": ",".join(PREFERRED_BOOKMAKERS),
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        # Check remaining requests
        remaining = response.headers.get("x-requests-remaining", "unknown")
        logger.info("API requests remaining this month: %s", remaining)

        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error("Error fetching odds: %s", e)
        return None


def parse_odds_response(odds_data: list[dict], save_to_db: bool = True) -> pd.DataFrame:
    """
    Parse odds API response into structured format.

    Args:
        odds_data: List of game dicts from API
        save_to_db: Whether to save odds snapshots to database

    Returns:
        DataFrame with parsed odds
    """
    if not odds_data:
        return pd.DataFrame()

    all_odds = []

    for game in odds_data:
        game_id = game.get("id", "")
        commence_time = game.get("commence_time", "")
        home_team = game.get("home_team", "")
        away_team = game.get("away_team", "")

        home_abbr = get_team_abbr(home_team)
        away_abbr = get_team_abbr(away_team)

        # Parse each bookmaker's odds
        for bookmaker in game.get("bookmakers", []):
            book_name = bookmaker.get("key", "")

            odds_entry = {
                "api_game_id": game_id,
                "commence_time": commence_time,
                "home_team": home_abbr,
                "away_team": away_abbr,
                "sportsbook": book_name,
                "home_ml": None,
                "away_ml": None,
                "spread_home": None,
                "spread_home_odds": None,
                "spread_away_odds": None,
                "total_line": None,
                "over_odds": None,
                "under_odds": None,
            }

            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                outcomes = market.get("outcomes", [])

                if market_key == "h2h":
                    # Moneyline
                    for outcome in outcomes:
                        if get_team_abbr(outcome.get("name")) == home_abbr:
                            odds_entry["home_ml"] = outcome.get("price")
                        elif get_team_abbr(outcome.get("name")) == away_abbr:
                            odds_entry["away_ml"] = outcome.get("price")

                elif market_key == "spreads":
                    # Point spread
                    for outcome in outcomes:
                        if get_team_abbr(outcome.get("name")) == home_abbr:
                            odds_entry["spread_home"] = outcome.get("point")
                            odds_entry["spread_home_odds"] = outcome.get("price")
                        elif get_team_abbr(outcome.get("name")) == away_abbr:
                            odds_entry["spread_away_odds"] = outcome.get("price")

                elif market_key == "totals":
                    # Over/under
                    for outcome in outcomes:
                        if outcome.get("name") == "Over":
                            odds_entry["total_line"] = outcome.get("point")
                            odds_entry["over_odds"] = outcome.get("price")
                        elif outcome.get("name") == "Under":
                            odds_entry["under_odds"] = outcome.get("price")

            all_odds.append(odds_entry)

    df = pd.DataFrame(all_odds)

    # Save to database if requested
    if save_to_db and not df.empty:
        save_odds_to_db(df)

    return df


def save_odds_to_db(odds_df: pd.DataFrame):
    """
    Save parsed odds to database.

    Note: We need to match API game IDs to our internal game IDs.
    For now, we'll use the API game ID as a fallback.
    """
    for _, row in odds_df.iterrows():
        # TODO: Match to internal game_id using teams + date
        game_id = row.get("api_game_id", "")

        if row.get("home_ml") is not None:
            insert_odds(
                game_id=game_id,
                sportsbook=row["sportsbook"],
                market_type="h2h",
                home_odds=row.get("home_ml"),
                away_odds=row.get("away_ml"),
            )

        if row.get("spread_home") is not None:
            insert_odds(
                game_id=game_id,
                sportsbook=row["sportsbook"],
                market_type="spreads",
                spread_home=row.get("spread_home"),
                spread_home_odds=row.get("spread_home_odds"),
                spread_away_odds=row.get("spread_away_odds"),
            )

        if row.get("total_line") is not None:
            insert_odds(
                game_id=game_id,
                sportsbook=row["sportsbook"],
                market_type="totals",
                total_line=row.get("total_line"),
                over_odds=row.get("over_odds"),
                under_odds=row.get("under_odds"),
            )


def get_current_odds() -> pd.DataFrame:
    """
    Fetch and parse current NBA odds.

    Returns:
        DataFrame with current odds from all configured sportsbooks
    """
    data = fetch_nba_odds()
    if data:
        return parse_odds_response(data, save_to_db=True)
    return pd.DataFrame()


def get_odds_for_game(home_abbr: str, away_abbr: str,
                      odds_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Get odds for a specific game.

    Args:
        home_abbr: Home team abbreviation
        away_abbr: Away team abbreviation
        odds_df: Optional pre-fetched odds DataFrame

    Returns:
        DataFrame with odds for this game from all sportsbooks
    """
    if odds_df is None:
        odds_df = get_current_odds()

    if odds_df.empty:
        return pd.DataFrame()

    game_odds = odds_df[
        (odds_df["home_team"] == home_abbr) &
        (odds_df["away_team"] == away_abbr)
    ]

    return game_odds


def get_best_odds(odds_df: pd.DataFrame, selection: str,
                  market: str = "h2h") -> Optional[dict]:
    """
    Find the best available odds across all sportsbooks.

    Args:
        odds_df: DataFrame with game odds
        selection: "home" or "away"
        market: "h2h" for moneyline

    Returns:
        Dict with best odds info or None
    """
    if odds_df.empty:
        return None

    if market == "h2h":
        col = "home_ml" if selection == "home" else "away_ml"
    else:
        return None  # Add spread/total support later

    # Filter to rows with this market
    valid = odds_df[odds_df[col].notna()]

    if valid.empty:
        return None

    # Best odds = highest value (whether positive or negative)
    best_idx = valid[col].idxmax()
    best_row = valid.loc[best_idx]

    return {
        "odds": int(best_row[col]),
        "sportsbook": best_row["sportsbook"],
        "home_team": best_row["home_team"],
        "away_team": best_row["away_team"],
    }
