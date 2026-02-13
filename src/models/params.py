"""Parameter container for Elo model backtesting and sweep optimization.

Frozen dataclass holding every tunable parameter. Immutable and hashable
so instances are safe for parallel sweeps and can be used as cache keys.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EloParams:
    """All tunable Elo model parameters."""

    # Core Elo
    k_factor: float = 15.0
    home_advantage: float = 35.0
    spread_divisor: float = 25.0
    initial_rating: float = 1500.0
    league_avg_score: float = 115.5
    season_regression_factor: float = 0.33

    # K-factor decay
    k_decay_games: int = 300
    k_decay_max_multiplier: float = 2.0

    # Margin of victory clamps
    mov_min: float = 0.5
    mov_max: float = 3.0

    # Rest day adjustments (Elo points)
    rest_b2b: float = -25.0
    rest_normal: float = 0.0
    rest_2day: float = 5.0
    rest_3day: float = 8.0

    # Player impact scaling (not used in backtest, stored for completeness)
    player_impact_scaling: float = 1.5

    @classmethod
    def production(cls) -> "EloParams":
        """Return current production defaults (matches config.py / elo.py)."""
        return cls()

    @property
    def home_advantage_points(self) -> float:
        """Home advantage converted to points."""
        return self.home_advantage / self.spread_divisor

    def k_with_decay(self, games_played: int) -> float:
        """Calculate K-factor with seasonal decay."""
        if games_played >= self.k_decay_games:
            return self.k_factor
        decay_progress = games_played / self.k_decay_games
        multiplier = self.k_decay_max_multiplier - (self.k_decay_max_multiplier - 1.0) * decay_progress
        return self.k_factor * multiplier

    def rest_adjustment(self, rest_days: int) -> float:
        """Get Elo adjustment for given rest days."""
        if rest_days < 0:
            return 0.0
        if rest_days == 0:
            return self.rest_b2b
        if rest_days == 1:
            return self.rest_normal
        if rest_days == 2:
            return self.rest_2day
        return self.rest_3day  # 3+ days capped
