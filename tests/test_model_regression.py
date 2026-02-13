"""Model regression tests.

Runs a full-season backtest with production parameters and asserts that
accuracy metrics meet minimum thresholds. This catches regressions when
model code or parameters change.

Skips if fewer than 100 completed games are in the database.
Thresholds should be updated as the model improves.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.params import EloParams
from src.backtesting.engine import load_season_data, run_backtest
from config import CURRENT_SEASON


# ---------------------------------------------------------------------------
# Thresholds (update as model improves)
# ---------------------------------------------------------------------------
MIN_PICK_ACCURACY = 62.0          # %
MAX_AVG_SPREAD_ERROR = 12.0       # points
MAX_BRIER_SCORE = 0.23
MIN_HIGH_CONF_ACCURACY = 69.0     # % for picks with >= 65% confidence
MIN_GAMES = 100                   # skip if DB has fewer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def backtest_metrics():
    """Run a single backtest for the module; reused across all tests."""
    games_df, teams = load_season_data(CURRENT_SEASON)
    if len(games_df) < MIN_GAMES:
        pytest.skip(f"Only {len(games_df)} completed games (need {MIN_GAMES})")

    params = EloParams.production()
    return run_backtest(games_df, teams, params)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModelRegression:

    def test_pick_accuracy(self, backtest_metrics):
        assert backtest_metrics.pick_accuracy >= MIN_PICK_ACCURACY, (
            f"Pick accuracy {backtest_metrics.pick_accuracy:.1f}% "
            f"below threshold {MIN_PICK_ACCURACY}%"
        )

    def test_avg_spread_error(self, backtest_metrics):
        assert backtest_metrics.avg_spread_error <= MAX_AVG_SPREAD_ERROR, (
            f"Avg spread error {backtest_metrics.avg_spread_error:.1f} "
            f"above threshold {MAX_AVG_SPREAD_ERROR}"
        )

    def test_brier_score(self, backtest_metrics):
        assert backtest_metrics.brier_score <= MAX_BRIER_SCORE, (
            f"Brier score {backtest_metrics.brier_score:.4f} "
            f"above threshold {MAX_BRIER_SCORE}"
        )

    def test_high_confidence_accuracy(self, backtest_metrics):
        if backtest_metrics.high_conf_games < 20:
            pytest.skip("Too few high-confidence games to test")
        assert backtest_metrics.high_conf_accuracy >= MIN_HIGH_CONF_ACCURACY, (
            f"High conf accuracy {backtest_metrics.high_conf_accuracy:.1f}% "
            f"below threshold {MIN_HIGH_CONF_ACCURACY}%"
        )

    def test_confidence_monotonicity(self, backtest_metrics):
        """Higher confidence should yield higher accuracy."""
        if backtest_metrics.high_conf_games < 20 or backtest_metrics.low_conf_games < 20:
            pytest.skip("Too few games in confidence buckets")
        assert backtest_metrics.high_conf_accuracy > backtest_metrics.low_conf_accuracy, (
            f"High conf {backtest_metrics.high_conf_accuracy:.1f}% "
            f"not greater than low conf {backtest_metrics.low_conf_accuracy:.1f}%"
        )

    def test_metrics_sanity(self, backtest_metrics):
        """Basic sanity checks on metric ranges."""
        m = backtest_metrics
        assert m.total_games > 0
        assert 0 <= m.pick_accuracy <= 100
        assert m.avg_spread_error >= 0
        assert 0 <= m.brier_score <= 1
        assert m.correct_picks <= m.total_games


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
