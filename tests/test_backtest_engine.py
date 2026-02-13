"""Unit tests for the backtest engine.

Tests the engine's internal math functions and verifies consistency
with the production elo.py for the same inputs/params.
"""

import math
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.models.params import EloParams
from src.backtesting.engine import (
    _win_prob,
    _elo_to_spread,
    _mov_multiplier,
    _update_elo_mov,
    _expected_score,
    _od_spread,
    _od_total,
    _update_od_elo,
    _calc_rest_days,
    run_backtest,
    BacktestMetrics,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def prod_params():
    return EloParams.production()


def _make_games_df(games: list[dict]) -> pd.DataFrame:
    """Build a minimal games DataFrame from a list of dicts."""
    defaults = {
        "game_id": "TEST001",
        "season": "2025-26",
        "game_date": "2025-11-01",
        "home_team_id": 1,
        "away_team_id": 2,
        "home_score": 110,
        "away_score": 105,
        "status": "final",
        "home_abbr": "HOM",
        "away_abbr": "AWY",
    }
    rows = []
    for i, g in enumerate(games):
        row = {**defaults, **g}
        if "game_id" not in g:
            row["game_id"] = f"TEST{i:03d}"
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Win probability
# ---------------------------------------------------------------------------

class TestWinProb:

    def test_equal_elo_no_hca(self, prod_params):
        prob = _win_prob(1500, 1500, 0)
        assert abs(prob - 0.5) < 0.001

    def test_equal_elo_with_hca(self, prod_params):
        prob = _win_prob(1500, 1500, prod_params.home_advantage)
        assert prob > 0.5

    def test_higher_rated_team_wins_more(self):
        prob = _win_prob(1600, 1400, 0)
        assert prob > 0.7

    def test_100_elo_diff(self):
        prob = _win_prob(1600, 1500, 0)
        assert 0.63 < prob < 0.65

    def test_matches_production(self, prod_params):
        """Engine win_prob matches production elo.py."""
        from src.models.elo import calculate_expected_win_prob
        for h, a, hca in [(1500, 1500, 0), (1600, 1400, 35), (1450, 1550, 35)]:
            engine = _win_prob(h, a, hca)
            prod = calculate_expected_win_prob(h, a, hca)
            assert abs(engine - prod) < 1e-9, f"Mismatch for ({h}, {a}, {hca})"


# ---------------------------------------------------------------------------
# Spread
# ---------------------------------------------------------------------------

class TestSpread:

    def test_equal_elo_no_hca(self, prod_params):
        params = EloParams(home_advantage=0)
        spread = _elo_to_spread(1500, 1500, params)
        assert abs(spread) < 0.001

    def test_100_elo_diff(self, prod_params):
        params = EloParams(home_advantage=0)
        spread = _elo_to_spread(1600, 1500, params)
        assert 3.5 < spread < 4.5

    def test_matches_production(self, prod_params):
        from src.models.elo import elo_to_spread
        for h, a in [(1500, 1500), (1600, 1400), (1450, 1550)]:
            engine = _elo_to_spread(h, a, prod_params)
            prod = elo_to_spread(h, a)
            assert abs(engine - prod) < 1e-9


# ---------------------------------------------------------------------------
# MOV multiplier
# ---------------------------------------------------------------------------

class TestMOV:

    def test_clamp_min(self, prod_params):
        # Very small margin
        mult = _mov_multiplier(1, 200, prod_params)
        assert mult >= prod_params.mov_min

    def test_clamp_max(self, prod_params):
        # Huge upset margin
        mult = _mov_multiplier(40, -200, prod_params)
        assert mult <= prod_params.mov_max

    def test_bigger_margin_bigger_multiplier(self, prod_params):
        small = _mov_multiplier(3, 0, prod_params)
        big = _mov_multiplier(20, 0, prod_params)
        assert big > small


# ---------------------------------------------------------------------------
# Composite Elo update with MOV
# ---------------------------------------------------------------------------

class TestEloUpdate:

    def test_winner_gains(self, prod_params):
        new_h, new_a = _update_elo_mov(1500, 1500, 110, 100, prod_params, 20)
        assert new_h > 1500
        assert new_a < 1500

    def test_symmetric(self, prod_params):
        new_h, new_a = _update_elo_mov(1500, 1500, 110, 100, prod_params, 20)
        assert abs((new_h - 1500) + (new_a - 1500)) < 0.001

    def test_upset_bigger_change(self, prod_params):
        # Favorite wins
        fav_h, fav_a = _update_elo_mov(1600, 1400, 110, 100, prod_params, 20)
        fav_gain = fav_h - 1600
        # Underdog wins
        und_h, und_a = _update_elo_mov(1400, 1600, 110, 100, prod_params, 20)
        und_gain = und_h - 1400
        assert und_gain > fav_gain


# ---------------------------------------------------------------------------
# O/D Elo functions
# ---------------------------------------------------------------------------

class TestODElo:

    def test_expected_score_at_league_avg(self, prod_params):
        score = _expected_score(1500, 1500, 0, prod_params)
        assert abs(score - prod_params.league_avg_score) < 0.001

    def test_od_spread_equal_elo_no_hca(self):
        params = EloParams(home_advantage=0)
        spread = _od_spread(1500, 1500, 1500, 1500, params)
        assert abs(spread) < 0.001

    def test_od_total_equal_elo_no_hca(self, prod_params):
        params = EloParams(home_advantage=0)
        total = _od_total(1500, 1500, 1500, 1500, params)
        assert abs(total - 2 * params.league_avg_score) < 0.001

    def test_od_update_directions(self, prod_params):
        """Home blowout: home O up, home D up, away O down, away D down."""
        h_o, h_d, a_o, a_d = _update_od_elo(
            1500, 1500, 1500, 1500, 130, 100, prod_params, 20)
        assert h_o > 1500  # home offense scored more
        assert h_d > 1500  # home defense held opponent
        assert a_o < 1500  # away offense scored less
        assert a_d < 1500  # away defense gave up more

    def test_matches_production(self, prod_params):
        """Engine O/D spread matches production elo.py."""
        from src.models.elo import od_elo_to_spread
        for h_o, h_d, a_o, a_d in [(1500, 1500, 1500, 1500), (1550, 1480, 1470, 1530)]:
            engine = _od_spread(h_o, h_d, a_o, a_d, prod_params)
            prod = od_elo_to_spread(h_o, h_d, a_o, a_d)
            assert abs(engine - prod) < 1e-9


# ---------------------------------------------------------------------------
# Rest days calculation
# ---------------------------------------------------------------------------

class TestRestDays:

    def test_back_to_back(self):
        assert _calc_rest_days("2025-11-01", "2025-11-02") == 0

    def test_one_day_rest(self):
        assert _calc_rest_days("2025-11-01", "2025-11-03") == 1

    def test_two_day_rest(self):
        assert _calc_rest_days("2025-11-01", "2025-11-04") == 2

    def test_no_previous_game(self):
        assert _calc_rest_days(None, "2025-11-01") == 1

    def test_invalid_date(self):
        assert _calc_rest_days("bad-date", "2025-11-01") == 1


# ---------------------------------------------------------------------------
# EloParams helpers
# ---------------------------------------------------------------------------

class TestEloParams:

    def test_frozen(self):
        p = EloParams()
        with pytest.raises(AttributeError):
            p.k_factor = 99

    def test_hashable(self):
        p1 = EloParams()
        p2 = EloParams(k_factor=25)
        s = {p1, p2}
        assert len(s) == 2

    def test_production_defaults(self):
        p = EloParams.production()
        assert p.k_factor == 15.0
        assert p.home_advantage == 35.0
        assert p.spread_divisor == 25.0

    def test_home_advantage_points(self):
        p = EloParams(home_advantage=35, spread_divisor=25)
        assert abs(p.home_advantage_points - 1.4) < 0.001

    def test_k_with_decay_at_start(self):
        p = EloParams(k_factor=15, k_decay_max_multiplier=2.0, k_decay_games=300)
        assert abs(p.k_with_decay(0) - 30.0) < 0.001

    def test_k_with_decay_at_end(self):
        p = EloParams(k_factor=15, k_decay_max_multiplier=2.0, k_decay_games=300)
        assert abs(p.k_with_decay(300) - 15.0) < 0.001

    def test_k_with_decay_past_end(self):
        p = EloParams(k_factor=15, k_decay_max_multiplier=2.0, k_decay_games=300)
        assert abs(p.k_with_decay(1000) - 15.0) < 0.001

    def test_rest_adjustment(self):
        p = EloParams.production()
        assert p.rest_adjustment(0) == -25.0
        assert p.rest_adjustment(1) == 0.0
        assert p.rest_adjustment(2) == 5.0
        assert p.rest_adjustment(3) == 8.0
        assert p.rest_adjustment(5) == 8.0  # capped at 3-day value


# ---------------------------------------------------------------------------
# Full backtest with synthetic data
# ---------------------------------------------------------------------------

class TestRunBacktest:

    def _teams(self):
        return {1: {"abbr": "HOM"}, 2: {"abbr": "AWY"}}

    def test_single_game(self, prod_params):
        games = _make_games_df([{"home_score": 110, "away_score": 100}])
        metrics = run_backtest(games, self._teams(), prod_params)
        assert metrics.total_games == 1
        assert metrics.correct_picks in (0, 1)
        assert 0.0 <= metrics.pick_accuracy <= 100.0

    def test_empty_df(self, prod_params):
        metrics = run_backtest(pd.DataFrame(), {}, prod_params)
        assert metrics.total_games == 0

    def test_dominant_team_predicted_to_win(self):
        """If one team wins by 30 every game, after a few games the model
        should predict them to win with high confidence."""
        games = []
        for i in range(20):
            date = f"2025-11-{i+1:02d}"
            games.append({
                "game_date": date,
                "home_team_id": 1, "away_team_id": 2,
                "home_score": 130, "away_score": 100,
            })
        df = _make_games_df(games)
        params = EloParams.production()
        metrics = run_backtest(df, self._teams(), params, include_game_results=True)

        # After a few updates, model should correctly pick the dominant team
        assert metrics.total_games == 20
        # At least the later games should be correctly predicted
        late_correct = sum(1 for g in metrics.game_results[5:] if g.correct_pick)
        assert late_correct >= 10  # most of the last 15 should be correct

    def test_metrics_ranges(self, prod_params):
        """All metric values should be in valid ranges."""
        games = []
        for i in range(10):
            date = f"2025-11-{i+1:02d}"
            games.append({
                "game_date": date,
                "home_score": 105 + i, "away_score": 100 + (i % 3),
            })
        df = _make_games_df(games)
        metrics = run_backtest(df, self._teams(), prod_params)

        assert 0.0 <= metrics.pick_accuracy <= 100.0
        assert metrics.avg_spread_error >= 0
        assert metrics.median_spread_error >= 0
        assert 0.0 <= metrics.brier_score <= 1.0
        assert metrics.correct_picks <= metrics.total_games

    def test_game_results_populated(self, prod_params):
        games = _make_games_df([{"home_score": 110, "away_score": 100}])
        metrics = run_backtest(games, self._teams(), prod_params,
                               include_game_results=True)
        assert len(metrics.game_results) == 1
        assert metrics.game_results[0].home_score == 110

    def test_game_results_not_populated_by_default(self, prod_params):
        games = _make_games_df([{"home_score": 110, "away_score": 100}])
        metrics = run_backtest(games, self._teams(), prod_params)
        assert len(metrics.game_results) == 0

    def test_no_od_elo_mode(self, prod_params):
        games = _make_games_df([{"home_score": 110, "away_score": 100}])
        metrics = run_backtest(games, self._teams(), prod_params,
                               use_od_elo=False)
        assert metrics.total_games == 1
        assert metrics.total_games_with_od == 0

    def test_no_rest_mode(self, prod_params):
        games = _make_games_df([
            {"game_date": "2025-11-01", "home_score": 110, "away_score": 100},
            {"game_date": "2025-11-02", "home_score": 108, "away_score": 102},
        ])
        metrics_rest = run_backtest(games, self._teams(), prod_params,
                                    include_rest=True)
        metrics_no = run_backtest(games, self._teams(), prod_params,
                                  include_rest=False)
        # Both should complete; results may differ due to rest adjustments
        assert metrics_rest.total_games == 2
        assert metrics_no.total_games == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
