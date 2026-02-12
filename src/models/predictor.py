"""Game prediction using Elo ratings."""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models.elo import (
    calculate_win_probabilities,
    elo_to_spread,
    win_prob_to_american_odds,
    od_elo_to_spread,
    od_elo_to_total,
    od_elo_to_win_prob,
)
from src.data.database import (
    get_team_by_id,
    get_games_by_date,
    update_game_predictions,
)
from src.data.injury_fetcher import fetch_injuries_for_date, get_team_injuries
from src.models.player_impact import (
    calculate_injury_adjustment,
    get_injury_adjustment_for_team,
)
from src.models.rest_factor import (
    get_rest_adjustments_for_game,
    get_rest_description,
)
from config import ELO_HOME_ADVANTAGE, USE_OD_ELO


# Module-level cache for injuries data
_injuries_cache: dict[str, pd.DataFrame] = {}


@dataclass
class GamePrediction:
    """Prediction for a single game."""
    game_id: str
    home_team: str
    away_team: str
    home_elo: float
    away_elo: float
    home_win_prob: float
    away_win_prob: float
    predicted_spread: float
    home_implied_odds: int
    away_implied_odds: int
    # Injury-adjusted fields
    home_elo_base: float = 0.0  # Elo without injury adjustments
    away_elo_base: float = 0.0
    home_injury_adjustment: float = 0.0
    away_injury_adjustment: float = 0.0
    home_injuries: list = field(default_factory=list)  # List of injured player details
    away_injuries: list = field(default_factory=list)
    injuries_applied: bool = False
    # Rest factor fields
    home_rest_days: int = 1
    away_rest_days: int = 1
    home_rest_adjustment: float = 0.0
    away_rest_adjustment: float = 0.0
    rest_applied: bool = False
    # O/D Elo fields
    home_offense_elo: float = 0.0
    home_defense_elo: float = 0.0
    away_offense_elo: float = 0.0
    away_defense_elo: float = 0.0
    predicted_total: float = 0.0
    od_elo_applied: bool = False

    def __str__(self) -> str:
        spread_str = f"{self.home_team} {self.predicted_spread:+.1f}" if self.predicted_spread < 0 else f"{self.away_team} {-self.predicted_spread:+.1f}"
        result = (
            f"{self.away_team} @ {self.home_team}\n"
            f"  Win Prob: {self.home_team} {self.home_win_prob:.1%} | "
            f"{self.away_team} {self.away_win_prob:.1%}\n"
            f"  Spread: {spread_str}\n"
            f"  Fair Odds: {self.home_team} {self.home_implied_odds:+d} | "
            f"{self.away_team} {self.away_implied_odds:+d}"
        )
        if self.injuries_applied and (self.home_injury_adjustment != 0 or self.away_injury_adjustment != 0):
            result += f"\n  Injury Adj: {self.home_team} {self.home_injury_adjustment:+.0f} | {self.away_team} {self.away_injury_adjustment:+.0f}"
        if self.rest_applied and (self.home_rest_adjustment != 0 or self.away_rest_adjustment != 0):
            result += f"\n  Rest: {self.home_team} {self.home_rest_days}d ({self.home_rest_adjustment:+.0f}) | {self.away_team} {self.away_rest_days}d ({self.away_rest_adjustment:+.0f})"
        return result


def get_injuries_for_date(game_date: str) -> pd.DataFrame:
    """
    Get injuries for a date, using cache to avoid repeated fetches.

    Args:
        game_date: Date string in YYYY-MM-DD format

    Returns:
        DataFrame with injury data
    """
    global _injuries_cache

    if game_date not in _injuries_cache:
        _injuries_cache[game_date] = fetch_injuries_for_date(game_date)

    return _injuries_cache[game_date]


def clear_injuries_cache():
    """Clear the injuries cache (useful for refreshing data)."""
    global _injuries_cache
    _injuries_cache = {}


def predict_game(
    home_team_id: int,
    away_team_id: int,
    home_elo: float = None,
    away_elo: float = None,
    game_id: str = None,
    game_date: str = None,
    apply_injuries: bool = True,
    apply_rest: bool = True,
    home_offense_elo: float = None,
    home_defense_elo: float = None,
    away_offense_elo: float = None,
    away_defense_elo: float = None,
) -> Optional[GamePrediction]:
    """
    Generate prediction for a game.

    Args:
        home_team_id: Home team's database ID
        away_team_id: Away team's database ID
        home_elo: Optional override for home Elo (uses current if not provided)
        away_elo: Optional override for away Elo (uses current if not provided)
        game_id: Optional game ID for tracking
        game_date: Date string for fetching injuries (YYYY-MM-DD)
        apply_injuries: Whether to apply injury adjustments (default True)
        apply_rest: Whether to apply rest day adjustments (default True)
        home_offense_elo: Optional home team offensive Elo
        home_defense_elo: Optional home team defensive Elo
        away_offense_elo: Optional away team offensive Elo
        away_defense_elo: Optional away team defensive Elo

    Returns:
        GamePrediction object or None if teams not found
    """
    # Get team info
    home_team = get_team_by_id(home_team_id)
    away_team = get_team_by_id(away_team_id)

    if not home_team or not away_team:
        return None

    # Use provided Elo or current ratings
    home_elo_base = home_elo if home_elo is not None else home_team['current_elo']
    away_elo_base = away_elo if away_elo is not None else away_team['current_elo']

    # Get O/D Elo ratings
    home_o_elo = home_offense_elo if home_offense_elo is not None else home_team.get('offense_elo', 1500.0)
    home_d_elo = home_defense_elo if home_defense_elo is not None else home_team.get('defense_elo', 1500.0)
    away_o_elo = away_offense_elo if away_offense_elo is not None else away_team.get('offense_elo', 1500.0)
    away_d_elo = away_defense_elo if away_defense_elo is not None else away_team.get('defense_elo', 1500.0)

    # Ensure we have valid values (not None)
    home_o_elo = home_o_elo or 1500.0
    home_d_elo = home_d_elo or 1500.0
    away_o_elo = away_o_elo or 1500.0
    away_d_elo = away_d_elo or 1500.0

    # Check if O/D Elo is available (not default values)
    od_elo_available = USE_OD_ELO and (
        home_o_elo != 1500.0 or home_d_elo != 1500.0 or
        away_o_elo != 1500.0 or away_d_elo != 1500.0
    )

    # Initialize injury tracking
    home_injury_adj = 0.0
    away_injury_adj = 0.0
    home_injuries = []
    away_injuries = []
    injuries_applied = False

    # Initialize rest tracking
    home_rest_adj = 0.0
    away_rest_adj = 0.0
    home_rest_days = 1
    away_rest_days = 1
    rest_applied = False

    # Apply injury adjustments if requested
    if apply_injuries and game_date:
        try:
            injuries_df = get_injuries_for_date(game_date)

            if not injuries_df.empty:
                home_abbr = home_team['abbreviation']
                away_abbr = away_team['abbreviation']

                # Get injury adjustments for each team
                home_injury_adj, home_injuries = get_injury_adjustment_for_team(
                    home_abbr, injuries_df
                )
                away_injury_adj, away_injuries = get_injury_adjustment_for_team(
                    away_abbr, injuries_df
                )
                injuries_applied = True
        except Exception as e:
            # Fall back to unadjusted Elo if injury fetch fails
            logger.warning("Could not apply injury adjustments: %s", e)

    # Apply rest day adjustments if requested
    if apply_rest and game_date:
        try:
            home_rest_adj, away_rest_adj, home_rest_days, away_rest_days = \
                get_rest_adjustments_for_game(home_team_id, away_team_id, game_date)
            rest_applied = True
        except Exception as e:
            # Fall back to no adjustment if rest calculation fails
            logger.warning("Could not apply rest adjustments: %s", e)

    # Apply all adjustments to composite Elo
    home_elo_adjusted = home_elo_base + home_injury_adj + home_rest_adj
    away_elo_adjusted = away_elo_base + away_injury_adj + away_rest_adj

    # Calculate predictions
    if od_elo_available:
        # Use O/D Elo for predictions (apply adjustments to both O and D)
        # Injury/rest adjustments are split evenly between O and D
        adj_split = (home_injury_adj + home_rest_adj) / 2
        home_o_adj = home_o_elo + adj_split
        home_d_adj = home_d_elo + adj_split
        adj_split = (away_injury_adj + away_rest_adj) / 2
        away_o_adj = away_o_elo + adj_split
        away_d_adj = away_d_elo + adj_split

        # Calculate spread and total from O/D Elo
        spread = od_elo_to_spread(home_o_adj, home_d_adj, away_o_adj, away_d_adj)
        predicted_total = od_elo_to_total(home_o_adj, home_d_adj, away_o_adj, away_d_adj)

        # Win probability still uses composite (average of adjusted O and D)
        home_prob, away_prob = od_elo_to_win_prob(
            home_o_adj, home_d_adj, away_o_adj, away_d_adj
        )
    else:
        # Fall back to composite Elo
        home_prob, away_prob = calculate_win_probabilities(home_elo_adjusted, away_elo_adjusted)
        spread = elo_to_spread(home_elo_adjusted, away_elo_adjusted)
        predicted_total = 0.0  # Not available without O/D Elo

    # Convert to fair odds
    home_odds = win_prob_to_american_odds(home_prob)
    away_odds = win_prob_to_american_odds(away_prob)

    return GamePrediction(
        game_id=game_id or "",
        home_team=home_team['abbreviation'],
        away_team=away_team['abbreviation'],
        home_elo=home_elo_adjusted,
        away_elo=away_elo_adjusted,
        home_win_prob=home_prob,
        away_win_prob=away_prob,
        predicted_spread=spread,
        home_implied_odds=home_odds,
        away_implied_odds=away_odds,
        home_elo_base=home_elo_base,
        away_elo_base=away_elo_base,
        home_injury_adjustment=home_injury_adj,
        away_injury_adjustment=away_injury_adj,
        home_injuries=home_injuries,
        away_injuries=away_injuries,
        injuries_applied=injuries_applied,
        home_rest_days=home_rest_days,
        away_rest_days=away_rest_days,
        home_rest_adjustment=home_rest_adj,
        away_rest_adjustment=away_rest_adj,
        rest_applied=rest_applied,
        home_offense_elo=home_o_elo,
        home_defense_elo=home_d_elo,
        away_offense_elo=away_o_elo,
        away_defense_elo=away_d_elo,
        predicted_total=predicted_total,
        od_elo_applied=od_elo_available,
    )


def predict_games_for_date(
    game_date: str,
    save_to_db: bool = True,
    apply_injuries: bool = True,
    apply_rest: bool = True,
) -> list[GamePrediction]:
    """
    Generate predictions for all games on a given date.

    Args:
        game_date: Date string in YYYY-MM-DD format
        save_to_db: Whether to save predictions to database
        apply_injuries: Whether to apply injury adjustments (default True)
        apply_rest: Whether to apply rest day adjustments (default True)

    Returns:
        List of GamePrediction objects
    """
    games_df = get_games_by_date(game_date)
    predictions = []

    for _, game in games_df.iterrows():
        pred = predict_game(
            home_team_id=game['home_team_id'],
            away_team_id=game['away_team_id'],
            home_elo=game.get('home_elo'),
            away_elo=game.get('away_elo'),
            game_id=game['game_id'],
            game_date=game_date,
            apply_injuries=apply_injuries,
            apply_rest=apply_rest,
            home_offense_elo=game.get('home_offense_elo'),
            home_defense_elo=game.get('home_defense_elo'),
            away_offense_elo=game.get('away_offense_elo'),
            away_defense_elo=game.get('away_defense_elo'),
        )

        if pred:
            predictions.append(pred)

            if save_to_db:
                # Only save predictions for games that haven't started yet
                # Don't overwrite existing predictions for in_progress or final games
                game_status = game.get('status', 'scheduled')
                existing_prediction = game.get('predicted_home_win_prob')

                if game_status == 'scheduled' or existing_prediction is None:
                    update_game_predictions(
                        game_id=game['game_id'],
                        home_win_prob=pred.home_win_prob,
                        predicted_spread=pred.predicted_spread
                    )

    return predictions


def predictions_to_dataframe(predictions: list[GamePrediction]) -> pd.DataFrame:
    """Convert list of predictions to a DataFrame."""
    if not predictions:
        return pd.DataFrame()

    data = []
    for pred in predictions:
        # Determine favorite
        if pred.home_win_prob > 0.5:
            favorite = pred.home_team
            favorite_prob = pred.home_win_prob
            spread_display = f"{pred.home_team} {pred.predicted_spread:.1f}"
        else:
            favorite = pred.away_team
            favorite_prob = pred.away_win_prob
            spread_display = f"{pred.away_team} {-pred.predicted_spread:.1f}"

        # Calculate total injury impact
        total_injury_impact = abs(pred.home_injury_adjustment) + abs(pred.away_injury_adjustment)

        # Format rest info
        home_rest_str = f"{pred.home_rest_days}d" if pred.rest_applied else "-"
        away_rest_str = f"{pred.away_rest_days}d" if pred.rest_applied else "-"

        data.append({
            'game_id': pred.game_id,
            'matchup': f"{pred.away_team} @ {pred.home_team}",
            'home_team': pred.home_team,
            'away_team': pred.away_team,
            'home_elo': round(pred.home_elo),
            'away_elo': round(pred.away_elo),
            'home_elo_base': round(pred.home_elo_base) if pred.home_elo_base else round(pred.home_elo),
            'away_elo_base': round(pred.away_elo_base) if pred.away_elo_base else round(pred.away_elo),
            'home_injury_adj': pred.home_injury_adjustment,
            'away_injury_adj': pred.away_injury_adjustment,
            'home_rest_days': pred.home_rest_days,
            'away_rest_days': pred.away_rest_days,
            'home_rest_adj': pred.home_rest_adjustment,
            'away_rest_adj': pred.away_rest_adjustment,
            'home_rest_str': home_rest_str,
            'away_rest_str': away_rest_str,
            'home_win_prob': pred.home_win_prob,
            'away_win_prob': pred.away_win_prob,
            'favorite': favorite,
            'favorite_prob': favorite_prob,
            'spread': pred.predicted_spread,
            'spread_display': spread_display,
            'home_fair_odds': pred.home_implied_odds,
            'away_fair_odds': pred.away_implied_odds,
            'injuries_applied': pred.injuries_applied,
            'rest_applied': pred.rest_applied,
            'total_injury_impact': total_injury_impact,
            'home_injuries': pred.home_injuries,
            'away_injuries': pred.away_injuries,
            # O/D Elo fields
            'home_offense_elo': round(pred.home_offense_elo) if pred.home_offense_elo else None,
            'home_defense_elo': round(pred.home_defense_elo) if pred.home_defense_elo else None,
            'away_offense_elo': round(pred.away_offense_elo) if pred.away_offense_elo else None,
            'away_defense_elo': round(pred.away_defense_elo) if pred.away_defense_elo else None,
            'predicted_total': round(pred.predicted_total, 1) if pred.predicted_total else None,
            'od_elo_applied': pred.od_elo_applied,
        })

    return pd.DataFrame(data)


def get_prediction_summary(pred: GamePrediction) -> dict:
    """Get a summary dict for display purposes."""
    summary = {
        'matchup': f"{pred.away_team} @ {pred.home_team}",
        'home_team': pred.home_team,
        'away_team': pred.away_team,
        'home_prob': f"{pred.home_win_prob:.1%}",
        'away_prob': f"{pred.away_win_prob:.1%}",
        'spread': f"{pred.predicted_spread:+.1f}",
        'home_fair_odds': f"{pred.home_implied_odds:+d}",
        'away_fair_odds': f"{pred.away_implied_odds:+d}",
    }

    # Add injury info if available
    if pred.injuries_applied:
        summary['home_injury_adj'] = f"{pred.home_injury_adjustment:+.0f}" if pred.home_injury_adjustment else "0"
        summary['away_injury_adj'] = f"{pred.away_injury_adjustment:+.0f}" if pred.away_injury_adjustment else "0"
        summary['home_injuries'] = pred.home_injuries
        summary['away_injuries'] = pred.away_injuries

    return summary
