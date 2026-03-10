"""BallDontLie API client — primary data source for games, stats, odds, injuries."""

import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import BDL_API_KEY, BDL_BASE_URL, CURRENT_SEASON, now_ct

logger = logging.getLogger(__name__)

# Rate-limit: 0.3s between calls
_last_call_time = 0.0

# ── Team ID mappings ──────────────────────────────────────────────────────────
# BDL team ID  →  NBA API team ID (used in our DB)
BDL_TO_NBA_TEAM_ID = {
    1: 1610612737,   # ATL
    2: 1610612738,   # BOS
    3: 1610612751,   # BKN
    4: 1610612766,   # CHA
    5: 1610612741,   # CHI
    6: 1610612739,   # CLE
    7: 1610612742,   # DAL
    8: 1610612743,   # DEN
    9: 1610612765,   # DET
    10: 1610612744,  # GSW
    11: 1610612745,  # HOU
    12: 1610612754,  # IND
    13: 1610612746,  # LAC
    14: 1610612747,  # LAL
    15: 1610612763,  # MEM
    16: 1610612748,  # MIA
    17: 1610612749,  # MIL
    18: 1610612750,  # MIN
    19: 1610612740,  # NOP
    20: 1610612752,  # NYK
    21: 1610612760,  # OKC
    22: 1610612753,  # ORL
    23: 1610612755,  # PHI
    24: 1610612756,  # PHX
    25: 1610612757,  # POR
    26: 1610612758,  # SAC
    27: 1610612759,  # SAS
    28: 1610612761,  # TOR
    29: 1610612762,  # UTA
    30: 1610612764,  # WAS
}

NBA_TO_BDL_TEAM_ID = {v: k for k, v in BDL_TO_NBA_TEAM_ID.items()}

BDL_TO_ABBR = {
    1: "ATL", 2: "BOS", 3: "BKN", 4: "CHA", 5: "CHI",
    6: "CLE", 7: "DAL", 8: "DEN", 9: "DET", 10: "GSW",
    11: "HOU", 12: "IND", 13: "LAC", 14: "LAL", 15: "MEM",
    16: "MIA", 17: "MIL", 18: "MIN", 19: "NOP", 20: "NYK",
    21: "OKC", 22: "ORL", 23: "PHI", 24: "PHX", 25: "POR",
    26: "SAC", 27: "SAS", 28: "TOR", 29: "UTA", 30: "WAS",
}

ABBR_TO_BDL = {v: k for k, v in BDL_TO_ABBR.items()}


def bdl_season(season_str: str) -> int:
    """Convert '2025-26' → 2025 (BDL format)."""
    return int(season_str.split("-")[0])


# ── Core HTTP helpers ─────────────────────────────────────────────────────────

def _bdl_get(endpoint: str, params: dict = None, version: str = "v1",
             max_retries: int = 3) -> Optional[dict]:
    """Authenticated GET with rate limiting and retry on transient errors."""
    global _last_call_time
    if not BDL_API_KEY:
        logger.warning("BDL_API_KEY not configured")
        return None

    url = f"{BDL_BASE_URL}/{version}/{endpoint}"
    headers = {"Authorization": BDL_API_KEY}

    for attempt in range(max_retries):
        elapsed = time.time() - _last_call_time
        if elapsed < 0.3:
            time.sleep(0.3 - elapsed)

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            _last_call_time = time.time()
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            _last_call_time = time.time()
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s backoff
                logger.warning("BDL API retry %d/%d [%s]: %s (waiting %ds)",
                               attempt + 1, max_retries, endpoint, type(e).__name__, wait)
                time.sleep(wait)
            else:
                logger.error("BDL API error [%s] after %d retries: %s", endpoint, max_retries, e)
                return None
        except requests.exceptions.RequestException as e:
            _last_call_time = time.time()
            logger.error("BDL API error [%s]: %s", endpoint, e)
            return None


def _bdl_paginate(endpoint: str, params: dict = None, version: str = "v1") -> list[dict]:
    """Auto-paginate cursor-based results."""
    if params is None:
        params = {}
    params["per_page"] = 100

    all_data = []
    cursor = None

    while True:
        if cursor:
            params["cursor"] = cursor
        result = _bdl_get(endpoint, params, version)
        if not result:
            break

        data = result.get("data", [])
        all_data.extend(data)

        meta = result.get("meta", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break

    return all_data


# ── Game ID matching ──────────────────────────────────────────────────────────

def _match_or_create_game_id(bdl_game_id: int, game_date: str,
                              home_nba_id: int, away_nba_id: int) -> str:
    """Match BDL game to existing DB game by date+teams, or generate BDL_ ID."""
    from src.data.database import get_games_by_date

    existing = get_games_by_date(game_date)
    if not existing.empty:
        match = existing[
            (existing['home_team_id'] == home_nba_id) &
            (existing['away_team_id'] == away_nba_id)
        ]
        if not match.empty:
            return match.iloc[0]['game_id']

    return f"BDL_{bdl_game_id}"


# ── Phase 2: Games & Scores ──────────────────────────────────────────────────

def _parse_bdl_game(game: dict, queried_date: str = None) -> Optional[dict]:
    """Parse a single BDL game dict into our DB format."""
    home_team = game.get("home_team", {})
    away_team = game.get("visitor_team", {})

    home_bdl_id = home_team.get("id")
    away_bdl_id = away_team.get("id")

    if not home_bdl_id or not away_bdl_id:
        return None

    home_nba_id = BDL_TO_NBA_TEAM_ID.get(home_bdl_id)
    away_nba_id = BDL_TO_NBA_TEAM_ID.get(away_bdl_id)

    if not home_nba_id or not away_nba_id:
        logger.warning("Unknown BDL team ID: %s or %s", home_bdl_id, away_bdl_id)
        return None

    # BDL "date" can be UTC-shifted; prefer the queried date when available
    game_date = queried_date or game.get("date", "")[:10]
    bdl_datetime = game.get("datetime") or ""

    # Extract game time — BDL returns UTC, convert to ET for display
    game_time = None
    if bdl_datetime and "T" in bdl_datetime:
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.fromisoformat(bdl_datetime.replace("Z", "+00:00"))
            et = dt.astimezone(ZoneInfo("America/New_York"))
            game_time = et.strftime("%-I:%M %p ET")
        except Exception:
            pass

    # Scores
    home_score = game.get("home_team_score")
    away_score = game.get("visitor_team_score")

    # Status
    bdl_status = (game.get("status") or "").lower()
    if bdl_status == "final":
        status = "final"
    elif bdl_status in ("1st qtr", "2nd qtr", "3rd qtr", "4th qtr", "halftime", "ot"):
        status = "in_progress"
    else:
        status = "scheduled"
        if not home_score:
            home_score = None
        if not away_score:
            away_score = None

    # Zero scores on scheduled games mean no score yet
    if status == "scheduled":
        home_score = None
        away_score = None
    elif home_score == 0 and away_score == 0 and status == "final":
        # Edge case: BDL may return 0-0 for games without scores
        home_score = None
        away_score = None
        status = "scheduled"

    bdl_game_id = game.get("id")
    game_id = _match_or_create_game_id(bdl_game_id, game_date, home_nba_id, away_nba_id)

    return {
        "game_id": game_id,
        "season": CURRENT_SEASON,
        "game_date": game_date,
        "game_time": game_time,
        "home_team_id": home_nba_id,
        "away_team_id": away_nba_id,
        "home_score": int(home_score) if home_score else None,
        "away_score": int(away_score) if away_score else None,
        "status": status,
    }


def fetch_games_bdl(date_str: str) -> list[dict]:
    """Fetch games for a specific date from BDL."""
    result = _bdl_get("games", {"dates[]": date_str})
    if not result:
        return []

    games = result.get("data", [])
    parsed = []
    for g in games:
        p = _parse_bdl_game(g, queried_date=date_str)
        if p:
            parsed.append(p)

    logger.info("BDL: fetched %d games for %s", len(parsed), date_str)
    return parsed


def fetch_season_games_bdl(season_str: str) -> list[dict]:
    """Fetch all games for a season from BDL (paginated)."""
    year = bdl_season(season_str)
    games = _bdl_paginate("games", {"seasons[]": year})

    parsed = []
    for g in games:
        p = _parse_bdl_game(g)
        if p:
            parsed.append(p)

    logger.info("BDL: fetched %d games for season %s", len(parsed), season_str)
    return parsed


def fetch_live_scores_bdl() -> list[dict]:
    """Fetch live box scores from BDL. Returns same format as fetch_scoreboard_espn()."""
    result = _bdl_get("box_scores/live")
    if not result:
        return []

    games = result.get("data", [])
    results = []

    for game_data in games:
        game = game_data.get("game", game_data)

        home_team = game.get("home_team", {})
        away_team = game.get("visitor_team", {})

        home_bdl_id = home_team.get("id")
        away_bdl_id = away_team.get("id")

        home_abbr = BDL_TO_ABBR.get(home_bdl_id, "")
        away_abbr = BDL_TO_ABBR.get(away_bdl_id, "")

        if not home_abbr or not away_abbr:
            continue

        bdl_status = (game.get("status") or "").lower()
        if bdl_status == "final":
            status = "final"
        elif bdl_status in ("1st qtr", "2nd qtr", "3rd qtr", "4th qtr", "halftime", "ot"):
            status = "in_progress"
        else:
            status = "scheduled"

        home_score = game.get("home_team_score")
        away_score = game.get("visitor_team_score")

        if status == "scheduled":
            home_score = None
            away_score = None

        results.append({
            "home_abbr": home_abbr,
            "away_abbr": away_abbr,
            "home_score": int(home_score) if home_score else None,
            "away_score": int(away_score) if away_score else None,
            "status": status,
            "game_time": None,
        })

    logger.info("BDL live: fetched %d games", len(results))
    return results


def fetch_standings_bdl(season_str: str) -> dict:
    """Fetch W/L standings from BDL. Returns {team_abbr: (wins, losses)}."""
    year = bdl_season(season_str)
    result = _bdl_get("standings", {"season": year})
    if not result:
        return {}

    records = {}
    for entry in result.get("data", []):
        team = entry.get("team", {})
        bdl_id = team.get("id")
        abbr = BDL_TO_ABBR.get(bdl_id, "")
        if abbr:
            wins = entry.get("wins", 0)
            losses = entry.get("losses", 0)
            records[abbr] = (wins, losses)

    logger.info("BDL standings: %d teams", len(records))
    return records


def fetch_home_road_splits_bdl(season_str: str) -> dict:
    """Fetch home/road records from BDL standings.

    Returns:
        {team_abbr: {"home_wins": int, "home_losses": int,
                     "road_wins": int, "road_losses": int}}
    """
    year = bdl_season(season_str)
    result = _bdl_get("standings", {"season": year})
    if not result:
        return {}

    splits = {}
    for entry in result.get("data", []):
        team = entry.get("team", {})
        bdl_id = team.get("id")
        abbr = BDL_TO_ABBR.get(bdl_id, "")
        if not abbr:
            continue

        # Parse "20-11" format records
        home_rec = entry.get("home_record", "0-0")
        road_rec = entry.get("road_record", "0-0")
        try:
            hw, hl = (int(x) for x in home_rec.split("-"))
            rw, rl = (int(x) for x in road_rec.split("-"))
        except (ValueError, AttributeError):
            continue

        splits[abbr] = {
            "home_wins": hw, "home_losses": hl,
            "road_wins": rw, "road_losses": rl,
        }

    logger.info("BDL home/road splits: %d teams", len(splits))
    return splits


# ── Phase 3: Player Advanced Stats ───────────────────────────────────────────

def _parse_minutes(min_val) -> float:
    """Parse BDL minutes field (string 'MM:SS', int, or float) → float minutes."""
    if not min_val:
        return 0.0
    if isinstance(min_val, (int, float)):
        return float(min_val)
    if isinstance(min_val, str):
        try:
            parts = min_val.split(":")
            return float(parts[0]) + float(parts[1]) / 60 if len(parts) == 2 else float(parts[0])
        except (ValueError, IndexError):
            return 0.0
    return 0.0


def fetch_player_impact_bdl(season_str: str,
                             min_mpg: float = 15.0,
                             min_gp: int = 20) -> pd.DataFrame:
    """
    Fetch player advanced stats from BDL for injury impact calculations.

    Uses per-team queries: for each team, fetches base stats (for minutes) and
    advanced stats (for net_rating, usage_percentage), then aggregates by player.

    Returns DataFrame with columns: player_id, player_name, team_abbr,
    net_rating, minutes_per_game, games_played, usg_pct, elo_impact
    """
    year = bdl_season(season_str)
    all_records = []
    consecutive_failures = 0
    max_consecutive_failures = 3

    for bdl_team_id, team_abbr in BDL_TO_ABBR.items():
        logger.debug("BDL player stats: processing %s...", team_abbr)

        # Fetch base stats (has minutes) for this team's season
        base_entries = _bdl_paginate("stats", {"seasons[]": year, "team_ids[]": bdl_team_id})

        # Fetch advanced stats (has net_rating, usage_percentage)
        adv_entries = _bdl_paginate("stats/advanced", {"seasons[]": year, "team_ids[]": bdl_team_id})

        # Track consecutive failures to abort early on widespread API issues
        if not base_entries and not adv_entries:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                logger.warning("BDL player impact: %d consecutive team failures, aborting early", consecutive_failures)
                break
        else:
            consecutive_failures = 0

        # Index advanced stats by (player_id, game_id) for joining
        adv_by_key = {}
        for entry in adv_entries:
            pid = entry.get("player", {}).get("id")
            gid = entry.get("game", {}).get("id")
            if pid and gid:
                adv_by_key[(pid, gid)] = entry

        # Aggregate by player
        player_agg = {}
        for entry in base_entries:
            player = entry.get("player", {})
            pid = player.get("id")
            gid = entry.get("game", {}).get("id")
            if not pid:
                continue

            mins = _parse_minutes(entry.get("min", 0))

            # Look up advanced stats for this player+game
            adv = adv_by_key.get((pid, gid), {})

            if pid not in player_agg:
                player_agg[pid] = {
                    "player_name": f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
                    "team_abbr": team_abbr,
                    "total_min": 0,
                    "games": 0,
                    "net_ratings": [],
                    "usg_pcts": [],
                }

            player_agg[pid]["total_min"] += mins
            player_agg[pid]["games"] += 1

            nr = adv.get("net_rating")
            usg = adv.get("usage_percentage")
            if nr is not None:
                player_agg[pid]["net_ratings"].append(nr)
            if usg is not None:
                player_agg[pid]["usg_pcts"].append(usg)

        # Filter qualified players and compute impact
        for pid, agg in player_agg.items():
            gp = agg["games"]
            mpg = agg["total_min"] / gp if gp > 0 else 0

            if mpg < min_mpg or gp < min_gp:
                continue

            net_rating = sum(agg["net_ratings"]) / len(agg["net_ratings"]) if agg["net_ratings"] else 0
            usg_pct = sum(agg["usg_pcts"]) / len(agg["usg_pcts"]) if agg["usg_pcts"] else 0

            # Same formula: NET_RATING * (MPG/48) * (USG%/0.20) * 1.5
            if usg_pct > 0:
                elo_impact = net_rating * (mpg / 48) * (usg_pct / 0.20) * 1.5
            else:
                elo_impact = net_rating * (mpg / 48) * 1.5

            # Scale by games-played confidence — reduces noise from small samples
            gp_confidence = min(gp / 50, 1.0)
            elo_impact *= gp_confidence

            all_records.append({
                "player_id": pid,
                "player_name": agg["player_name"],
                "team_abbr": agg["team_abbr"],
                "net_rating": net_rating,
                "minutes_per_game": mpg,
                "games_played": gp,
                "usg_pct": usg_pct,
                "elo_impact": elo_impact,
            })

    df = pd.DataFrame(all_records)
    logger.info("BDL: fetched impact stats for %d qualified players", len(df))
    return df


def fetch_team_ratings_bdl(season_str: str) -> pd.DataFrame:
    """
    Fetch team OFF/DEF ratings from BDL standings for O/D Elo seeding.

    Computes team offensive/defensive ratings by aggregating per-game
    advanced stats across all players on each team.

    Returns DataFrame with columns: team_id, team_abbr, off_rating, def_rating,
    offense_elo, defense_elo
    """
    year = bdl_season(season_str)
    league_avg_rating = 114.7

    records = []
    for bdl_team_id, team_abbr in BDL_TO_ABBR.items():
        nba_id = BDL_TO_NBA_TEAM_ID.get(bdl_team_id)
        if not nba_id:
            continue

        # Fetch advanced stats for team (paginated)
        adv_entries = _bdl_paginate("stats/advanced", {"seasons[]": year, "team_ids[]": bdl_team_id})
        if not adv_entries:
            continue

        # Average offensive and defensive ratings across all game entries
        off_ratings = [e.get("offensive_rating", 0) for e in adv_entries if e.get("offensive_rating")]
        def_ratings = [e.get("defensive_rating", 0) for e in adv_entries if e.get("defensive_rating")]

        if not off_ratings or not def_ratings:
            continue

        off_rating = sum(off_ratings) / len(off_ratings)
        def_rating = sum(def_ratings) / len(def_ratings)

        offense_elo = 1500 + (off_rating - league_avg_rating) * 25
        defense_elo = 1500 + (league_avg_rating - def_rating) * 25

        records.append({
            "team_id": nba_id,
            "team_abbr": team_abbr,
            "off_rating": off_rating,
            "def_rating": def_rating,
            "offense_elo": offense_elo,
            "defense_elo": defense_elo,
        })

    df = pd.DataFrame(records)
    logger.info("BDL: fetched O/D ratings for %d teams", len(df))
    return df


# ── Phase 4: Odds ─────────────────────────────────────────────────────────────

def fetch_odds_bdl(date_str: str) -> list[dict]:
    """
    Fetch odds from BDL for a given date.

    Returns list of dicts in the same format as parse_odds_response() output:
    {home_team, away_team, sportsbook, home_ml, away_ml, spread_home,
     spread_home_odds, spread_away_odds, total_line, over_odds, under_odds}
    """
    # First get games for the date to map BDL game IDs to teams
    games_result = _bdl_get("games", {"dates[]": date_str})
    if not games_result:
        return []

    game_teams = {}
    for g in games_result.get("data", []):
        gid = g.get("id")
        home = g.get("home_team", {})
        visitor = g.get("visitor_team", {})
        game_teams[gid] = {
            "home_abbr": BDL_TO_ABBR.get(home.get("id"), ""),
            "away_abbr": BDL_TO_ABBR.get(visitor.get("id"), ""),
            "home_nba_id": BDL_TO_NBA_TEAM_ID.get(home.get("id")),
            "away_nba_id": BDL_TO_NBA_TEAM_ID.get(visitor.get("id")),
        }

    # Fetch odds
    odds_data = _bdl_paginate("odds", {"dates[]": date_str}, version="v2")
    if not odds_data:
        return []

    from config import PREFERRED_BOOKMAKERS
    preferred = set(PREFERRED_BOOKMAKERS)

    all_odds = []
    for entry in odds_data:
        bdl_game_id = entry.get("game_id")
        teams = game_teams.get(bdl_game_id)
        if not teams or not teams["home_abbr"]:
            continue

        vendor = (entry.get("vendor") or "").lower()
        # Map BDL vendor names to our preferred bookmaker keys
        if vendor not in preferred:
            continue

        # Match to our game ID
        game_id = _match_or_create_game_id(
            bdl_game_id, date_str,
            teams["home_nba_id"], teams["away_nba_id"]
        )

        # Parse spread (BDL gives home spread value)
        spread_home = entry.get("spread_home_value")
        if spread_home is not None:
            try:
                spread_home = float(spread_home)
            except (ValueError, TypeError):
                spread_home = None

        # Parse total
        total_line = entry.get("total_value")
        if total_line is not None:
            try:
                total_line = float(total_line)
            except (ValueError, TypeError):
                total_line = None

        # BDL odds are already American format integers
        # BDL provides spread_away_odds directly
        spread_away_odds = entry.get("spread_away_odds")

        all_odds.append({
            "api_game_id": game_id,
            "home_team": teams["home_abbr"],
            "away_team": teams["away_abbr"],
            "sportsbook": vendor,
            "home_ml": entry.get("moneyline_home_odds"),
            "away_ml": entry.get("moneyline_away_odds"),
            "spread_home": spread_home,
            "spread_home_odds": entry.get("spread_home_odds"),
            "spread_away_odds": spread_away_odds,
            "total_line": total_line,
            "over_odds": entry.get("total_over_odds"),
            "under_odds": entry.get("total_under_odds"),
        })

    logger.info("BDL odds: fetched %d entries for %s", len(all_odds), date_str)
    return all_odds


# ── Phase 5: Injuries ─────────────────────────────────────────────────────────

# Map BDL injury statuses to our status multipliers
_BDL_STATUS_MAP = {
    "out": ("Out", 1.0),
    "doubtful": ("Doubtful", 0.8),
    "questionable": ("Questionable", 0.5),
    "day-to-day": ("Day-To-Day", 0.3),
    "probable": ("Probable", 0.1),
    "out for season": ("Out", 1.0),
}


def fetch_injuries_bdl() -> pd.DataFrame:
    """
    Fetch current injuries from BDL.

    Returns DataFrame matching fetch_injuries_from_espn() format:
    player_name, team, team_abbr, status, status_multiplier, reason
    """
    injuries = _bdl_paginate("player_injuries")
    if not injuries:
        return pd.DataFrame()

    records = []
    for inj in injuries:
        player = inj.get("player", {})
        # BDL injuries have team_id directly on the player, not nested team object
        bdl_id = player.get("team_id") or player.get("team", {}).get("id")
        abbr = BDL_TO_ABBR.get(bdl_id, "")

        if not abbr:
            continue

        raw_status = (inj.get("status") or "out").lower().strip()
        mapped = _BDL_STATUS_MAP.get(raw_status, ("Out", 1.0))

        player_name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()

        records.append({
            "player_name": player_name,
            "team": "",  # BDL doesn't include full team name in injury data
            "team_abbr": abbr,
            "status": mapped[0],
            "status_multiplier": mapped[1],
            "reason": inj.get("description", "") or inj.get("comment", "") or "",
        })

    df = pd.DataFrame(records)
    logger.info("BDL injuries: fetched %d entries", len(df))
    return df
