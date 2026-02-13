"""Elo rating system for NBA teams."""

import math
from dataclasses import dataclass
from typing import Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import (
    ELO_K_FACTOR, ELO_HOME_ADVANTAGE, ELO_INITIAL_RATING, ELO_SPREAD_DIVISOR,
    LEAGUE_AVG_SCORE, USE_OD_ELO
)

# Season constants for K-decay
GAMES_PER_SEASON = 1230  # 30 teams × 82 games / 2
K_DECAY_GAMES = 300  # Games over which K decays from max to base
K_DECAY_MAX_MULTIPLIER = 2.0  # K is 100% higher at season start


def calculate_k_with_decay(games_played: int, base_k: float = ELO_K_FACTOR) -> float:
    """
    Calculate K-factor with seasonal decay.

    Early season games have higher K (more uncertainty about team quality).
    K decays to base value as season progresses.

    Args:
        games_played: Number of league-wide games played this season
        base_k: Base K-factor (default from config)

    Returns:
        Adjusted K-factor
    """
    if games_played >= K_DECAY_GAMES:
        return base_k

    # Linear decay from max to base over first K_DECAY_GAMES
    decay_progress = games_played / K_DECAY_GAMES
    multiplier = K_DECAY_MAX_MULTIPLIER - (K_DECAY_MAX_MULTIPLIER - 1.0) * decay_progress

    return base_k * multiplier


@dataclass
class EloResult:
    """Result of an Elo calculation."""
    home_new_elo: float
    away_new_elo: float
    home_elo_change: float
    away_elo_change: float
    expected_home_win_prob: float
    expected_away_win_prob: float


@dataclass
class ODEloResult:
    """Result of an Offensive/Defensive Elo calculation."""
    home_offense_elo_new: float
    home_defense_elo_new: float
    away_offense_elo_new: float
    away_defense_elo_new: float
    home_offense_change: float
    home_defense_change: float
    away_offense_change: float
    away_defense_change: float
    expected_home_score: float
    expected_away_score: float
    expected_home_win_prob: float
    expected_away_win_prob: float


def calculate_expected_win_prob(rating_self: float, rating_opponent: float,
                                home_advantage: float = 0) -> float:
    """
    Calculate expected win probability using Elo formula.

    The formula: 1 / (1 + 10^((R_opp - R_self - home_advantage) / 400))

    Args:
        rating_self: Elo rating of the team we're calculating for
        rating_opponent: Elo rating of the opponent
        home_advantage: Home court advantage in Elo points (default 0)

    Returns:
        Expected win probability (0 to 1)
    """
    exponent = (rating_opponent - rating_self - home_advantage) / 400
    return 1 / (1 + math.pow(10, exponent))


def calculate_win_probabilities(home_elo: float, away_elo: float,
                                home_advantage: float = ELO_HOME_ADVANTAGE
                                ) -> Tuple[float, float]:
    """
    Calculate win probabilities for both teams.

    Args:
        home_elo: Home team's Elo rating
        away_elo: Away team's Elo rating
        home_advantage: Home court advantage in Elo points

    Returns:
        Tuple of (home_win_prob, away_win_prob)
    """
    home_prob = calculate_expected_win_prob(home_elo, away_elo, home_advantage)
    away_prob = 1 - home_prob
    return home_prob, away_prob


def elo_to_spread(home_elo: float, away_elo: float,
                  home_advantage: float = ELO_HOME_ADVANTAGE) -> float:
    """
    Convert Elo difference to predicted point spread.

    Positive spread means home team is favored by that many points.

    Args:
        home_elo: Home team's Elo rating
        away_elo: Away team's Elo rating
        home_advantage: Home court advantage in Elo points

    Returns:
        Predicted spread (positive = home favored)
    """
    elo_diff = home_elo + home_advantage - away_elo
    return elo_diff / ELO_SPREAD_DIVISOR


def update_elo(home_elo: float, away_elo: float, home_won: bool,
               k_factor: float = ELO_K_FACTOR,
               home_advantage: float = ELO_HOME_ADVANTAGE) -> EloResult:
    """
    Update Elo ratings after a game.

    Args:
        home_elo: Home team's Elo rating before the game
        away_elo: Away team's Elo rating before the game
        home_won: Whether the home team won
        k_factor: Elo K-factor (sensitivity to results)
        home_advantage: Home court advantage in Elo points

    Returns:
        EloResult with new ratings and changes
    """
    # Calculate expected probabilities
    home_expected, away_expected = calculate_win_probabilities(
        home_elo, away_elo, home_advantage
    )

    # Actual results (1 for win, 0 for loss)
    home_actual = 1.0 if home_won else 0.0
    away_actual = 1.0 - home_actual

    # Calculate Elo changes
    home_change = k_factor * (home_actual - home_expected)
    away_change = k_factor * (away_actual - away_expected)

    return EloResult(
        home_new_elo=home_elo + home_change,
        away_new_elo=away_elo + away_change,
        home_elo_change=home_change,
        away_elo_change=away_change,
        expected_home_win_prob=home_expected,
        expected_away_win_prob=away_expected
    )


def update_elo_with_mov(home_elo: float, away_elo: float,
                        home_score: int, away_score: int,
                        k_factor: float = ELO_K_FACTOR,
                        home_advantage: float = ELO_HOME_ADVANTAGE) -> EloResult:
    """
    Update Elo ratings with margin of victory adjustment.

    This is a more sophisticated update that gives more credit for blowout wins.
    Uses the formula: multiplier = ln(|margin| + 1) * (2.2 / ((elo_diff * 0.001) + 2.2))

    Args:
        home_elo: Home team's Elo rating before the game
        away_elo: Away team's Elo rating before the game
        home_score: Home team's final score
        away_score: Away team's final score
        k_factor: Base Elo K-factor
        home_advantage: Home court advantage in Elo points

    Returns:
        EloResult with new ratings and changes
    """
    home_won = home_score > away_score
    margin = abs(home_score - away_score)

    # Calculate expected probabilities
    home_expected, away_expected = calculate_win_probabilities(
        home_elo, away_elo, home_advantage
    )

    # Elo difference for MOV adjustment
    if home_won:
        elo_diff = home_elo + home_advantage - away_elo
    else:
        elo_diff = away_elo - (home_elo + home_advantage)

    # Margin of victory multiplier
    # This dampens the effect when the better team wins big (expected)
    # and amplifies it when the underdog wins big (upset)
    mov_multiplier = math.log(margin + 1) * (2.2 / (elo_diff * 0.001 + 2.2))
    mov_multiplier = max(0.5, min(mov_multiplier, 3.0))  # Clamp between 0.5 and 3.0

    # Actual results
    home_actual = 1.0 if home_won else 0.0
    away_actual = 1.0 - home_actual

    # Calculate Elo changes with MOV adjustment
    adjusted_k = k_factor * mov_multiplier
    home_change = adjusted_k * (home_actual - home_expected)
    away_change = adjusted_k * (away_actual - away_expected)

    return EloResult(
        home_new_elo=home_elo + home_change,
        away_new_elo=away_elo + away_change,
        home_elo_change=home_change,
        away_elo_change=away_change,
        expected_home_win_prob=home_expected,
        expected_away_win_prob=away_expected
    )


# ============================================================================
# Offensive/Defensive Elo Functions
# ============================================================================

def calculate_expected_score(offense_elo: float, defense_elo: float,
                             home_advantage_points: float = 0) -> float:
    """
    Calculate expected score based on O/D Elo matchup.

    Args:
        offense_elo: Offensive team's O-Elo rating
        defense_elo: Opposing team's D-Elo rating
        home_advantage_points: Points to add for home team (default 0)

    Returns:
        Expected points scored
    """
    # Formula: Expected = LEAGUE_AVG + (O_Elo - D_Elo) / 25 + home_advantage
    return LEAGUE_AVG_SCORE + (offense_elo - defense_elo) / ELO_SPREAD_DIVISOR + home_advantage_points


def od_elo_to_spread(home_offense_elo: float, home_defense_elo: float,
                     away_offense_elo: float, away_defense_elo: float,
                     home_advantage_points: float = ELO_HOME_ADVANTAGE / ELO_SPREAD_DIVISOR) -> float:
    """
    Convert O/D Elo to predicted spread.

    Args:
        home_offense_elo: Home team's offensive Elo
        home_defense_elo: Home team's defensive Elo
        away_offense_elo: Away team's offensive Elo
        away_defense_elo: Away team's defensive Elo
        home_advantage_points: Home court advantage in points (default from config)

    Returns:
        Predicted spread (positive = home favored)
    """
    home_expected = calculate_expected_score(home_offense_elo, away_defense_elo, home_advantage_points)
    away_expected = calculate_expected_score(away_offense_elo, home_defense_elo, 0)

    return home_expected - away_expected


def od_elo_to_total(home_offense_elo: float, home_defense_elo: float,
                    away_offense_elo: float, away_defense_elo: float,
                    home_advantage_points: float = ELO_HOME_ADVANTAGE / ELO_SPREAD_DIVISOR) -> float:
    """
    Calculate predicted total points from O/D Elo.

    Args:
        home_offense_elo: Home team's offensive Elo
        home_defense_elo: Home team's defensive Elo
        away_offense_elo: Away team's offensive Elo
        away_defense_elo: Away team's defensive Elo
        home_advantage_points: Home court advantage in points (default from config)

    Returns:
        Predicted total points
    """
    home_expected = calculate_expected_score(home_offense_elo, away_defense_elo, home_advantage_points)
    away_expected = calculate_expected_score(away_offense_elo, home_defense_elo, 0)

    return home_expected + away_expected


def od_elo_to_win_prob(home_offense_elo: float, home_defense_elo: float,
                       away_offense_elo: float, away_defense_elo: float,
                       home_advantage: float = ELO_HOME_ADVANTAGE) -> Tuple[float, float]:
    """
    Calculate win probability from O/D Elo using composite ratings.

    Uses the average of offense and defense Elo as the composite rating,
    then applies standard Elo win probability formula.

    Args:
        home_offense_elo: Home team's offensive Elo
        home_defense_elo: Home team's defensive Elo
        away_offense_elo: Away team's offensive Elo
        away_defense_elo: Away team's defensive Elo
        home_advantage: Home court advantage in Elo points

    Returns:
        Tuple of (home_win_prob, away_win_prob)
    """
    home_composite = (home_offense_elo + home_defense_elo) / 2
    away_composite = (away_offense_elo + away_defense_elo) / 2

    return calculate_win_probabilities(home_composite, away_composite, home_advantage)


def update_od_elo(home_offense_elo: float, home_defense_elo: float,
                  away_offense_elo: float, away_defense_elo: float,
                  home_score: int, away_score: int,
                  k_factor: float = ELO_K_FACTOR,
                  home_advantage_points: float = ELO_HOME_ADVANTAGE / ELO_SPREAD_DIVISOR) -> ODEloResult:
    """
    Update Offensive/Defensive Elo ratings after a game.

    Each team's offense is judged against the opponent's defense.
    Each team's defense is judged against the opponent's offense.

    Args:
        home_offense_elo: Home team's offensive Elo before game
        home_defense_elo: Home team's defensive Elo before game
        away_offense_elo: Away team's offensive Elo before game
        away_defense_elo: Away team's defensive Elo before game
        home_score: Home team's final score
        away_score: Away team's final score
        k_factor: Base Elo K-factor
        home_advantage_points: Home court advantage in points (default from config)

    Returns:
        ODEloResult with updated ratings
    """
    # Calculate expected scores
    home_expected = calculate_expected_score(home_offense_elo, away_defense_elo, home_advantage_points)
    away_expected = calculate_expected_score(away_offense_elo, home_defense_elo, 0)

    # Scale K for point-based updates (smaller changes per point)
    k_points = k_factor / 2

    # Update offense based on actual vs expected scoring
    # Positive difference = scored more than expected = offense did well
    home_offense_change = k_points * (home_score - home_expected) / 10
    away_offense_change = k_points * (away_score - away_expected) / 10

    # Update defense based on opponent's actual vs expected scoring
    # If opponent scored less than expected, defense did well (positive change)
    home_defense_change = k_points * (away_expected - away_score) / 10
    away_defense_change = k_points * (home_expected - home_score) / 10

    # Calculate win probabilities for reference
    home_composite = (home_offense_elo + home_defense_elo) / 2
    away_composite = (away_offense_elo + away_defense_elo) / 2
    home_win_prob, away_win_prob = calculate_win_probabilities(home_composite, away_composite)

    return ODEloResult(
        home_offense_elo_new=home_offense_elo + home_offense_change,
        home_defense_elo_new=home_defense_elo + home_defense_change,
        away_offense_elo_new=away_offense_elo + away_offense_change,
        away_defense_elo_new=away_defense_elo + away_defense_change,
        home_offense_change=home_offense_change,
        home_defense_change=home_defense_change,
        away_offense_change=away_offense_change,
        away_defense_change=away_defense_change,
        expected_home_score=home_expected,
        expected_away_score=away_expected,
        expected_home_win_prob=home_win_prob,
        expected_away_win_prob=away_win_prob,
    )


def season_regression_od(offense_elo: float, defense_elo: float,
                         regression_factor: float = 0.33) -> Tuple[float, float]:
    """
    Apply season-to-season regression to O/D Elo ratings.

    Args:
        offense_elo: Team's end-of-season offensive Elo
        defense_elo: Team's end-of-season defensive Elo
        regression_factor: How much to regress (0.33 = 1/3 toward mean)

    Returns:
        Tuple of (regressed_offense_elo, regressed_defense_elo)
    """
    new_offense = offense_elo + regression_factor * (ELO_INITIAL_RATING - offense_elo)
    new_defense = defense_elo + regression_factor * (ELO_INITIAL_RATING - defense_elo)
    return new_offense, new_defense


def season_regression(current_elo: float, regression_factor: float = 0.33) -> float:
    """
    Apply season-to-season regression to mean.

    Teams regress toward 1500 between seasons to account for roster changes.

    Args:
        current_elo: Team's end-of-season Elo
        regression_factor: How much to regress (0.33 = 1/3 toward mean)

    Returns:
        Regressed Elo rating for new season
    """
    return current_elo + regression_factor * (ELO_INITIAL_RATING - current_elo)


# Utility functions for testing and display
def win_prob_to_american_odds(prob: float) -> int:
    """Convert win probability to American odds."""
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def elo_diff_to_description(elo_diff: float) -> str:
    """Convert Elo difference to human-readable description."""
    if abs(elo_diff) < 25:
        return "Toss-up"
    elif abs(elo_diff) < 75:
        return "Slight edge"
    elif abs(elo_diff) < 150:
        return "Clear favorite"
    elif abs(elo_diff) < 250:
        return "Strong favorite"
    else:
        return "Dominant favorite"
