"""Find value bets by comparing model predictions to sportsbook odds."""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import MIN_EDGE_PERCENT, MIN_ODDS, MAX_ODDS
from src.betting.odds_converter import (
    american_to_implied_prob,
    calculate_edge,
    calculate_expected_value,
    calculate_kelly_fraction,
    format_american_odds,
    format_probability,
)
from src.models.predictor import GamePrediction


@dataclass
class ValueBet:
    """A potential value betting opportunity."""
    game_id: str
    matchup: str
    selection: str  # "home" or "away"
    team: str  # Team abbreviation
    bet_type: str  # "moneyline", "spread", "total"
    line: Optional[float]  # Spread/total line if applicable
    odds: int  # American odds
    sportsbook: str
    model_prob: float
    implied_prob: float
    edge: float  # Percentage edge
    expected_value: float  # EV per $100 bet
    kelly_fraction: float  # Kelly bet fraction
    confidence: str  # "Low", "Medium", "High"

    def __str__(self) -> str:
        return (
            f"{self.matchup} | {self.team} {self.bet_type.upper()}\n"
            f"  Odds: {format_american_odds(self.odds)} @ {self.sportsbook}\n"
            f"  Model: {format_probability(self.model_prob)} vs "
            f"Implied: {format_probability(self.implied_prob)}\n"
            f"  Edge: {self.edge:.1f}% | EV: ${self.expected_value:.2f}/100 | "
            f"Confidence: {self.confidence}"
        )


def categorize_edge(edge: float) -> str:
    """Categorize edge into confidence level."""
    if edge >= 10:
        return "High"
    elif edge >= 5:
        return "Medium"
    else:
        return "Low"


def find_value_bets_for_game(
    prediction: GamePrediction,
    odds_df: pd.DataFrame,
    min_edge: float = MIN_EDGE_PERCENT,
    min_odds: int = MIN_ODDS,
    max_odds: int = MAX_ODDS,
) -> list[ValueBet]:
    """
    Find value bets for a single game.

    Args:
        prediction: Model prediction for the game
        odds_df: DataFrame with odds for this game from various sportsbooks
        min_edge: Minimum edge percentage to flag as value
        min_odds: Don't bet on odds below this (heavy favorites)
        max_odds: Don't bet on odds above this (extreme underdogs)

    Returns:
        List of ValueBet opportunities
    """
    if odds_df.empty:
        return []

    value_bets = []
    matchup = f"{prediction.away_team} @ {prediction.home_team}"

    for _, odds_row in odds_df.iterrows():
        sportsbook = odds_row.get("sportsbook", "unknown")

        # Check home team moneyline
        home_ml = odds_row.get("home_ml")
        if home_ml is not None and min_odds <= home_ml <= max_odds:
            edge = calculate_edge(prediction.home_win_prob, int(home_ml))

            if edge >= min_edge:
                implied = american_to_implied_prob(int(home_ml))
                ev = calculate_expected_value(prediction.home_win_prob, int(home_ml))
                kelly = calculate_kelly_fraction(prediction.home_win_prob, int(home_ml))

                value_bets.append(ValueBet(
                    game_id=prediction.game_id,
                    matchup=matchup,
                    selection="home",
                    team=prediction.home_team,
                    bet_type="moneyline",
                    line=None,
                    odds=int(home_ml),
                    sportsbook=sportsbook,
                    model_prob=prediction.home_win_prob,
                    implied_prob=implied,
                    edge=edge,
                    expected_value=ev,
                    kelly_fraction=kelly,
                    confidence=categorize_edge(edge),
                ))

        # Check away team moneyline
        away_ml = odds_row.get("away_ml")
        if away_ml is not None and min_odds <= away_ml <= max_odds:
            edge = calculate_edge(prediction.away_win_prob, int(away_ml))

            if edge >= min_edge:
                implied = american_to_implied_prob(int(away_ml))
                ev = calculate_expected_value(prediction.away_win_prob, int(away_ml))
                kelly = calculate_kelly_fraction(prediction.away_win_prob, int(away_ml))

                value_bets.append(ValueBet(
                    game_id=prediction.game_id,
                    matchup=matchup,
                    selection="away",
                    team=prediction.away_team,
                    bet_type="moneyline",
                    line=None,
                    odds=int(away_ml),
                    sportsbook=sportsbook,
                    model_prob=prediction.away_win_prob,
                    implied_prob=implied,
                    edge=edge,
                    expected_value=ev,
                    kelly_fraction=kelly,
                    confidence=categorize_edge(edge),
                ))

    # Sort by edge (highest first)
    value_bets.sort(key=lambda x: x.edge, reverse=True)

    return value_bets


def find_all_value_bets(
    predictions: list[GamePrediction],
    all_odds: pd.DataFrame,
    min_edge: float = MIN_EDGE_PERCENT,
) -> list[ValueBet]:
    """
    Find value bets across all games.

    Args:
        predictions: List of game predictions
        all_odds: DataFrame with odds for all games
        min_edge: Minimum edge percentage to flag

    Returns:
        List of all value bets, sorted by edge
    """
    all_value_bets = []

    for pred in predictions:
        # Filter odds to this game
        game_odds = all_odds[
            (all_odds["home_team"] == pred.home_team) &
            (all_odds["away_team"] == pred.away_team)
        ]

        bets = find_value_bets_for_game(pred, game_odds, min_edge)
        all_value_bets.extend(bets)

    # Sort by edge
    all_value_bets.sort(key=lambda x: x.edge, reverse=True)

    return all_value_bets


def value_bets_to_dataframe(value_bets: list[ValueBet]) -> pd.DataFrame:
    """Convert value bets to a DataFrame for display."""
    if not value_bets:
        return pd.DataFrame()

    data = []
    for bet in value_bets:
        data.append({
            "game_id": bet.game_id,
            "matchup": bet.matchup,
            "team": bet.team,
            "selection": bet.selection,
            "bet_type": bet.bet_type,
            "odds": format_american_odds(bet.odds),
            "odds_raw": bet.odds,
            "sportsbook": bet.sportsbook,
            "model_prob": bet.model_prob,
            "model_prob_display": format_probability(bet.model_prob),
            "implied_prob": bet.implied_prob,
            "implied_prob_display": format_probability(bet.implied_prob),
            "edge": bet.edge,
            "edge_display": f"{bet.edge:.1f}%",
            "ev_per_100": bet.expected_value,
            "ev_display": f"${bet.expected_value:.2f}",
            "kelly": bet.kelly_fraction,
            "kelly_display": f"{bet.kelly_fraction:.1%}",
            "confidence": bet.confidence,
        })

    return pd.DataFrame(data)


def filter_best_odds(value_bets: list[ValueBet]) -> list[ValueBet]:
    """
    Filter to show only the best odds for each team/bet type.

    When multiple sportsbooks have value on the same bet,
    only keep the one with the best odds.
    """
    best = {}

    for bet in value_bets:
        key = (bet.game_id, bet.team, bet.bet_type)

        if key not in best or bet.odds > best[key].odds:
            best[key] = bet

    return sorted(best.values(), key=lambda x: x.edge, reverse=True)


def get_value_summary(value_bets: list[ValueBet]) -> dict:
    """Get summary statistics for value bets."""
    if not value_bets:
        return {
            "total_bets": 0,
            "avg_edge": 0,
            "avg_ev": 0,
            "high_confidence": 0,
            "medium_confidence": 0,
            "low_confidence": 0,
        }

    return {
        "total_bets": len(value_bets),
        "avg_edge": sum(b.edge for b in value_bets) / len(value_bets),
        "avg_ev": sum(b.expected_value for b in value_bets) / len(value_bets),
        "high_confidence": sum(1 for b in value_bets if b.confidence == "High"),
        "medium_confidence": sum(1 for b in value_bets if b.confidence == "Medium"),
        "low_confidence": sum(1 for b in value_bets if b.confidence == "Low"),
    }
