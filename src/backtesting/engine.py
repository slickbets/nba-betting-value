"""Core backtest engine for replaying a season and measuring model accuracy.

All computation is in-memory. No database writes. Every calculation uses the
EloParams object explicitly — never reads config globals.

Usage:
    from src.models.params import EloParams
    from src.backtesting.engine import run_backtest, load_season_data

    games_df, teams = load_season_data("2025-26")
    metrics = run_backtest(games_df, teams, EloParams.production())
    print(f"Accuracy: {metrics.pick_accuracy:.1f}%")
"""

import math
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from src.models.params import EloParams


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class GameResult:
    """Per-game backtest result."""
    game_id: str
    game_date: str
    home_abbr: str
    away_abbr: str
    home_score: int
    away_score: int
    predicted_home_win_prob: float
    predicted_spread: float
    predicted_total: float | None
    actual_spread: float  # home_score - away_score
    actual_total: int
    correct_pick: bool
    spread_error: float
    total_error: float | None
    brier_component: float


@dataclass
class BacktestMetrics:
    """Aggregate backtest results."""
    total_games: int = 0
    correct_picks: int = 0
    pick_accuracy: float = 0.0
    avg_spread_error: float = 0.0
    median_spread_error: float = 0.0
    brier_score: float = 0.0

    # Confidence-bucketed accuracy
    high_conf_games: int = 0    # >= 65% predicted prob
    high_conf_correct: int = 0
    high_conf_accuracy: float = 0.0
    med_conf_games: int = 0     # 55% - 65%
    med_conf_correct: int = 0
    med_conf_accuracy: float = 0.0
    low_conf_games: int = 0     # < 55%
    low_conf_correct: int = 0
    low_conf_accuracy: float = 0.0

    # O/D Elo total predictions
    avg_total_error: float = 0.0
    median_total_error: float = 0.0
    total_games_with_od: int = 0

    # Per-game detail (optional)
    game_results: list[GameResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private math functions (self-contained, parameterized by EloParams)
# ---------------------------------------------------------------------------

def _win_prob(rating_self: float, rating_opponent: float,
              home_advantage: float) -> float:
    """Elo win probability."""
    exponent = (rating_opponent - rating_self - home_advantage) / 400
    return 1 / (1 + math.pow(10, exponent))


def _elo_to_spread(home_elo: float, away_elo: float,
                   params: EloParams) -> float:
    """Composite Elo to predicted spread (positive = home favored)."""
    elo_diff = home_elo + params.home_advantage - away_elo
    return elo_diff / params.spread_divisor


def _mov_multiplier(margin: int, elo_diff: float,
                    params: EloParams) -> float:
    """Margin of victory multiplier for Elo updates."""
    mult = math.log(abs(margin) + 1) * (2.2 / (elo_diff * 0.001 + 2.2))
    return max(params.mov_min, min(mult, params.mov_max))


def _update_elo_mov(home_elo: float, away_elo: float,
                    home_score: int, away_score: int,
                    params: EloParams, k: float) -> tuple[float, float]:
    """Update composite Elo with MOV. Returns (new_home_elo, new_away_elo)."""
    home_won = home_score > away_score
    margin = abs(home_score - away_score)

    home_expected = _win_prob(home_elo, away_elo, params.home_advantage)

    if home_won:
        elo_diff = home_elo + params.home_advantage - away_elo
    else:
        elo_diff = away_elo - (home_elo + params.home_advantage)

    mov_mult = _mov_multiplier(margin, elo_diff, params)

    home_actual = 1.0 if home_won else 0.0
    away_actual = 1.0 - home_actual
    away_expected = 1.0 - home_expected

    adjusted_k = k * mov_mult
    home_change = adjusted_k * (home_actual - home_expected)
    away_change = adjusted_k * (away_actual - away_expected)

    return home_elo + home_change, away_elo + away_change


def _expected_score(offense_elo: float, defense_elo: float,
                    home_adv_pts: float, params: EloParams) -> float:
    """O/D Elo expected score for one team."""
    return params.league_avg_score + (offense_elo - defense_elo) / params.spread_divisor + home_adv_pts


def _od_spread(h_o: float, h_d: float, a_o: float, a_d: float,
               params: EloParams) -> float:
    """O/D Elo predicted spread."""
    home_exp = _expected_score(h_o, a_d, params.home_advantage_points, params)
    away_exp = _expected_score(a_o, h_d, 0, params)
    return home_exp - away_exp


def _od_total(h_o: float, h_d: float, a_o: float, a_d: float,
              params: EloParams) -> float:
    """O/D Elo predicted total."""
    home_exp = _expected_score(h_o, a_d, params.home_advantage_points, params)
    away_exp = _expected_score(a_o, h_d, 0, params)
    return home_exp + away_exp


def _update_od_elo(h_o: float, h_d: float, a_o: float, a_d: float,
                   home_score: int, away_score: int,
                   params: EloParams, k: float
                   ) -> tuple[float, float, float, float]:
    """Update O/D Elo. Returns (h_o_new, h_d_new, a_o_new, a_d_new)."""
    home_exp = _expected_score(h_o, a_d, params.home_advantage_points, params)
    away_exp = _expected_score(a_o, h_d, 0, params)

    k_pts = k / 2

    h_o_change = k_pts * (home_score - home_exp) / 10
    a_o_change = k_pts * (away_score - away_exp) / 10
    h_d_change = k_pts * (away_exp - away_score) / 10
    a_d_change = k_pts * (home_exp - home_score) / 10

    return h_o + h_o_change, h_d + h_d_change, a_o + a_o_change, a_d + a_d_change


def _calc_rest_days(last_date_str: str | None, current_date_str: str) -> int:
    """Calculate rest days between games. Returns 1 (normal) if no previous game."""
    if not last_date_str:
        return 1
    try:
        last = datetime.strptime(last_date_str, "%Y-%m-%d")
        current = datetime.strptime(current_date_str, "%Y-%m-%d")
        return max(0, (current - last).days - 1)
    except (ValueError, TypeError):
        return 1


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_season_data(season: str) -> tuple[pd.DataFrame, dict]:
    """Load completed games and team initial ratings from database.

    Returns:
        (games_df, teams_dict) where teams_dict maps team_id -> {abbr, initial composite elo=1500}
    """
    from src.data.database import get_games_by_season, get_all_teams

    games_df = get_games_by_season(season, status="final")
    if games_df.empty:
        return games_df, {}

    # Sort chronologically
    games_df = games_df.sort_values(["game_date", "game_id"]).reset_index(drop=True)

    # Build teams dict (all start at initial_rating — engine will regress/init fresh)
    teams_raw = get_all_teams()
    teams = {}
    for _, row in teams_raw.iterrows():
        teams[row["team_id"]] = {"abbr": row["abbreviation"]}

    return games_df, teams


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

def run_backtest(games_df: pd.DataFrame, teams: dict, params: EloParams,
                 use_od_elo: bool = True, include_rest: bool = True,
                 include_game_results: bool = False) -> BacktestMetrics:
    """Replay a season's games and measure prediction accuracy.

    Args:
        games_df: DataFrame of completed games sorted by date (from load_season_data)
        teams: Dict mapping team_id -> {abbr: str}
        params: EloParams with all tunable parameters
        use_od_elo: Whether to use O/D Elo for spread/total predictions
        include_rest: Whether to include rest-day adjustments
        include_game_results: Whether to populate metrics.game_results

    Returns:
        BacktestMetrics with accuracy, spread error, Brier score, etc.
    """
    if games_df.empty:
        return BacktestMetrics()

    # Initialize Elo state for all teams
    elo = {}            # team_id -> composite elo
    o_elo = {}          # team_id -> offense elo
    d_elo = {}          # team_id -> defense elo
    last_game = {}      # team_id -> last game date string

    for tid in teams:
        elo[tid] = params.initial_rating
        o_elo[tid] = params.initial_rating
        d_elo[tid] = params.initial_rating

    # Tracking
    games_played_league = 0
    correct_picks = 0
    spread_errors = []
    total_errors = []
    brier_components = []
    game_results = []

    # Confidence buckets
    high_conf = [0, 0]  # [games, correct]
    med_conf = [0, 0]
    low_conf = [0, 0]

    for _, game in games_df.iterrows():
        h_id = game["home_team_id"]
        a_id = game["away_team_id"]
        h_score = int(game["home_score"])
        a_score = int(game["away_score"])
        game_date = str(game["game_date"])

        # Skip if teams aren't in our dict (shouldn't happen)
        if h_id not in elo or a_id not in elo:
            continue

        # --- Predict ---
        h_elo = elo[h_id]
        a_elo = elo[a_id]

        # Rest adjustments
        rest_adj_h = 0.0
        rest_adj_a = 0.0
        if include_rest:
            h_rest = _calc_rest_days(last_game.get(h_id), game_date)
            a_rest = _calc_rest_days(last_game.get(a_id), game_date)
            rest_adj_h = params.rest_adjustment(h_rest)
            rest_adj_a = params.rest_adjustment(a_rest)

        adj_h_elo = h_elo + rest_adj_h
        adj_a_elo = a_elo + rest_adj_a

        # Win probability (composite Elo + rest)
        home_win_prob = _win_prob(adj_h_elo, adj_a_elo, params.home_advantage)

        # Spread prediction
        if use_od_elo:
            adj_h_o = o_elo[h_id] + rest_adj_h
            adj_h_d = d_elo[h_id] + rest_adj_h
            adj_a_o = a_elo + rest_adj_a  # fallback composite for non-OD
            adj_a_d = a_elo + rest_adj_a
            # Proper O/D: rest splits evenly to offense/defense
            adj_h_o = o_elo[h_id] + rest_adj_h / 2
            adj_h_d = d_elo[h_id] + rest_adj_h / 2
            adj_a_o = o_elo[a_id] + rest_adj_a / 2
            adj_a_d = d_elo[a_id] + rest_adj_a / 2

            predicted_spread = _od_spread(adj_h_o, adj_h_d, adj_a_o, adj_a_d, params)
            predicted_total = _od_total(adj_h_o, adj_h_d, adj_a_o, adj_a_d, params)
        else:
            predicted_spread = _elo_to_spread(adj_h_elo, adj_a_elo, params)
            predicted_total = None

        # --- Compare ---
        actual_spread = h_score - a_score
        actual_total = h_score + a_score
        home_won = h_score > a_score

        # Correct pick: did we predict the right winner?
        predicted_home_win = home_win_prob > 0.5
        correct = predicted_home_win == home_won
        if correct:
            correct_picks += 1

        spread_error = abs(predicted_spread - actual_spread)
        spread_errors.append(spread_error)

        total_error = None
        if predicted_total is not None:
            total_error = abs(predicted_total - actual_total)
            total_errors.append(total_error)

        # Brier score component: (predicted_prob - actual_outcome)^2
        actual_outcome = 1.0 if home_won else 0.0
        brier_comp = (home_win_prob - actual_outcome) ** 2
        brier_components.append(brier_comp)

        # Confidence bucket
        conf = max(home_win_prob, 1 - home_win_prob)
        if conf >= 0.65:
            high_conf[0] += 1
            if correct:
                high_conf[1] += 1
        elif conf >= 0.55:
            med_conf[0] += 1
            if correct:
                med_conf[1] += 1
        else:
            low_conf[0] += 1
            if correct:
                low_conf[1] += 1

        if include_game_results:
            game_results.append(GameResult(
                game_id=str(game.get("game_id", "")),
                game_date=game_date,
                home_abbr=str(game.get("home_abbr", "")),
                away_abbr=str(game.get("away_abbr", "")),
                home_score=h_score,
                away_score=a_score,
                predicted_home_win_prob=home_win_prob,
                predicted_spread=predicted_spread,
                predicted_total=predicted_total,
                actual_spread=float(actual_spread),
                actual_total=actual_total,
                correct_pick=correct,
                spread_error=spread_error,
                total_error=total_error,
                brier_component=brier_comp,
            ))

        # --- Update Elo ---
        k = params.k_with_decay(games_played_league)

        # Composite Elo update with MOV
        new_h_elo, new_a_elo = _update_elo_mov(h_elo, a_elo, h_score, a_score, params, k)
        elo[h_id] = new_h_elo
        elo[a_id] = new_a_elo

        # O/D Elo update
        if use_od_elo:
            new_h_o, new_h_d, new_a_o, new_a_d = _update_od_elo(
                o_elo[h_id], d_elo[h_id], o_elo[a_id], d_elo[a_id],
                h_score, a_score, params, k
            )
            o_elo[h_id] = new_h_o
            d_elo[h_id] = new_h_d
            o_elo[a_id] = new_a_o
            d_elo[a_id] = new_a_d

        # Track last game date and league games count
        last_game[h_id] = game_date
        last_game[a_id] = game_date
        games_played_league += 1

    # --- Aggregate metrics ---
    total_games = len(spread_errors)
    if total_games == 0:
        return BacktestMetrics()

    sorted_spread = sorted(spread_errors)
    mid = total_games // 2
    median_spread = (sorted_spread[mid] if total_games % 2 == 1
                     else (sorted_spread[mid - 1] + sorted_spread[mid]) / 2)

    median_total = 0.0
    if total_errors:
        sorted_total = sorted(total_errors)
        tmid = len(sorted_total) // 2
        median_total = (sorted_total[tmid] if len(sorted_total) % 2 == 1
                        else (sorted_total[tmid - 1] + sorted_total[tmid]) / 2)

    return BacktestMetrics(
        total_games=total_games,
        correct_picks=correct_picks,
        pick_accuracy=100.0 * correct_picks / total_games,
        avg_spread_error=sum(spread_errors) / total_games,
        median_spread_error=median_spread,
        brier_score=sum(brier_components) / total_games,

        high_conf_games=high_conf[0],
        high_conf_correct=high_conf[1],
        high_conf_accuracy=100.0 * high_conf[1] / high_conf[0] if high_conf[0] else 0.0,
        med_conf_games=med_conf[0],
        med_conf_correct=med_conf[1],
        med_conf_accuracy=100.0 * med_conf[1] / med_conf[0] if med_conf[0] else 0.0,
        low_conf_games=low_conf[0],
        low_conf_correct=low_conf[1],
        low_conf_accuracy=100.0 * low_conf[1] / low_conf[0] if low_conf[0] else 0.0,

        avg_total_error=sum(total_errors) / len(total_errors) if total_errors else 0.0,
        median_total_error=median_total,
        total_games_with_od=len(total_errors),

        game_results=game_results if include_game_results else [],
    )
