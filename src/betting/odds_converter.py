"""Odds format conversions and calculations."""

from typing import Tuple


def american_to_decimal(american_odds: int) -> float:
    """
    Convert American odds to decimal odds.

    Args:
        american_odds: American format odds (e.g., -150, +200)

    Returns:
        Decimal odds (e.g., 1.67, 3.00)
    """
    if american_odds > 0:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1


def decimal_to_american(decimal_odds: float) -> int:
    """
    Convert decimal odds to American odds.

    Args:
        decimal_odds: Decimal format odds (e.g., 1.67, 3.00)

    Returns:
        American odds (e.g., -150, +200)
    """
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1) * 100))
    else:
        return int(round(-100 / (decimal_odds - 1)))


def american_to_implied_prob(american_odds: int) -> float:
    """
    Convert American odds to implied probability.

    Args:
        american_odds: American format odds

    Returns:
        Implied probability (0 to 1)
    """
    if american_odds > 0:
        return 100 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)


def implied_prob_to_american(prob: float) -> int:
    """
    Convert implied probability to American odds.

    Args:
        prob: Probability (0 to 1)

    Returns:
        American odds
    """
    if prob <= 0 or prob >= 1:
        raise ValueError("Probability must be between 0 and 1 (exclusive)")

    if prob >= 0.5:
        return int(round(-100 * prob / (1 - prob)))
    else:
        return int(round(100 * (1 - prob) / prob))


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """
    Convert decimal odds to implied probability.

    Args:
        decimal_odds: Decimal format odds

    Returns:
        Implied probability (0 to 1)
    """
    return 1 / decimal_odds


def implied_prob_to_decimal(prob: float) -> float:
    """
    Convert implied probability to decimal odds.

    Args:
        prob: Probability (0 to 1)

    Returns:
        Decimal odds
    """
    if prob <= 0 or prob >= 1:
        raise ValueError("Probability must be between 0 and 1 (exclusive)")
    return 1 / prob


def calculate_vig(prob1: float, prob2: float) -> float:
    """
    Calculate the vigorish (juice/margin) for a two-way market.

    Args:
        prob1: Implied probability of outcome 1
        prob2: Implied probability of outcome 2

    Returns:
        Vigorish as a percentage (e.g., 4.5 for 4.5%)
    """
    total_implied = prob1 + prob2
    vig = (total_implied - 1) * 100
    return vig


def remove_vig(american_odds1: int, american_odds2: int) -> Tuple[float, float]:
    """
    Remove the vig from a two-way market to get true probabilities.

    Args:
        american_odds1: American odds for outcome 1
        american_odds2: American odds for outcome 2

    Returns:
        Tuple of (true_prob1, true_prob2) without vig
    """
    implied1 = american_to_implied_prob(american_odds1)
    implied2 = american_to_implied_prob(american_odds2)

    total = implied1 + implied2

    # Normalize to remove vig
    true_prob1 = implied1 / total
    true_prob2 = implied2 / total

    return true_prob1, true_prob2


def calculate_edge(model_prob: float, odds: int) -> float:
    """
    Calculate the edge (advantage) for a bet.

    Edge = Model Probability - Implied Probability

    Args:
        model_prob: Your model's probability for this outcome
        odds: American odds offered by the sportsbook

    Returns:
        Edge as a percentage (e.g., 5.5 for 5.5% edge)
    """
    implied = american_to_implied_prob(odds)
    return (model_prob - implied) * 100


def calculate_expected_value(model_prob: float, odds: int, stake: float = 100) -> float:
    """
    Calculate expected value of a bet.

    EV = (Win Probability × Profit) - (Lose Probability × Stake)

    Args:
        model_prob: Your model's probability for this outcome
        odds: American odds offered by the sportsbook
        stake: Amount wagered

    Returns:
        Expected value in currency units
    """
    decimal_odds = american_to_decimal(odds)
    profit_if_win = stake * (decimal_odds - 1)
    lose_prob = 1 - model_prob

    ev = (model_prob * profit_if_win) - (lose_prob * stake)
    return ev


def calculate_kelly_fraction(model_prob: float, odds: int) -> float:
    """
    Calculate Kelly Criterion bet fraction.

    Kelly = (bp - q) / b
    where: b = decimal odds - 1, p = win prob, q = lose prob

    Args:
        model_prob: Your model's probability for this outcome
        odds: American odds offered by the sportsbook

    Returns:
        Optimal fraction of bankroll to wager (can be negative = don't bet)
    """
    decimal_odds = american_to_decimal(odds)
    b = decimal_odds - 1
    p = model_prob
    q = 1 - p

    kelly = (b * p - q) / b

    return kelly


def format_american_odds(odds: int) -> str:
    """
    Format American odds for display.

    Args:
        odds: American odds

    Returns:
        Formatted string (e.g., "+150", "-200")
    """
    if odds > 0:
        return f"+{odds}"
    else:
        return str(odds)


def format_probability(prob: float) -> str:
    """
    Format probability for display.

    Args:
        prob: Probability (0 to 1)

    Returns:
        Formatted percentage string (e.g., "55.5%")
    """
    return f"{prob * 100:.1f}%"


def format_spread(spread: float) -> str:
    """
    Format point spread for display.

    Args:
        spread: Point spread (negative = favorite)

    Returns:
        Formatted spread string (e.g., "-3.5", "+7")
    """
    if spread > 0:
        return f"+{spread:.1f}"
    elif spread < 0:
        return f"{spread:.1f}"
    else:
        return "PK"  # Pick 'em
