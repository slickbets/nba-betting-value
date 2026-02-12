"""Tests for Elo rating system."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.elo import (
    calculate_expected_win_prob,
    calculate_win_probabilities,
    elo_to_spread,
    update_elo,
    update_elo_with_mov,
    season_regression,
    win_prob_to_american_odds,
    calculate_expected_score,
    od_elo_to_spread,
    od_elo_to_total,
    od_elo_to_win_prob,
    update_od_elo,
    season_regression_od,
)
from config import ELO_INITIAL_RATING, ELO_HOME_ADVANTAGE, ELO_SPREAD_DIVISOR, LEAGUE_AVG_SCORE


class TestWinProbability:
    """Tests for win probability calculations."""

    def test_equal_ratings_gives_50_percent(self):
        """Equal ratings should give 50% win probability."""
        prob = calculate_expected_win_prob(1500, 1500, home_advantage=0)
        assert abs(prob - 0.5) < 0.001

    def test_higher_rating_gives_higher_prob(self):
        """Higher rated team should have higher win probability."""
        prob = calculate_expected_win_prob(1600, 1500, home_advantage=0)
        assert prob > 0.5

    def test_lower_rating_gives_lower_prob(self):
        """Lower rated team should have lower win probability."""
        prob = calculate_expected_win_prob(1400, 1500, home_advantage=0)
        assert prob < 0.5

    def test_100_elo_difference_gives_about_64_percent(self):
        """100 Elo difference should give roughly 64% win probability."""
        prob = calculate_expected_win_prob(1600, 1500, home_advantage=0)
        assert 0.63 < prob < 0.65  # Approximately 64%

    def test_home_advantage_increases_prob(self):
        """Home advantage should increase win probability."""
        prob_neutral = calculate_expected_win_prob(1500, 1500, home_advantage=0)
        prob_home = calculate_expected_win_prob(1500, 1500, home_advantage=100)

        assert prob_home > prob_neutral

    def test_win_probabilities_sum_to_one(self):
        """Home and away probabilities should sum to 1."""
        home_prob, away_prob = calculate_win_probabilities(1550, 1480)
        assert abs(home_prob + away_prob - 1.0) < 0.001


class TestEloSpread:
    """Tests for Elo to spread conversion."""

    def test_equal_ratings_at_home_gives_positive_spread(self):
        """Equal ratings with home advantage should favor home team."""
        spread = elo_to_spread(1500, 1500)
        assert spread > 0  # Home team favored

    def test_100_elo_advantage_gives_about_4_points(self):
        """100 Elo advantage should be roughly 4 point spread."""
        spread = elo_to_spread(1600, 1500, home_advantage=0)
        assert 3.5 < spread < 4.5

    def test_200_elo_advantage_gives_about_8_points(self):
        """200 Elo advantage should be roughly 8 point spread."""
        spread = elo_to_spread(1700, 1500, home_advantage=0)
        assert 7.5 < spread < 8.5

    def test_negative_spread_when_away_team_better(self):
        """Away team with higher Elo should have negative spread."""
        spread = elo_to_spread(1400, 1600, home_advantage=0)
        assert spread < 0


class TestEloUpdate:
    """Tests for Elo rating updates."""

    def test_winner_gains_elo(self):
        """Winner should gain Elo points."""
        result = update_elo(1500, 1500, home_won=True)
        assert result.home_new_elo > 1500
        assert result.home_elo_change > 0

    def test_loser_loses_elo(self):
        """Loser should lose Elo points."""
        result = update_elo(1500, 1500, home_won=True)
        assert result.away_new_elo < 1500
        assert result.away_elo_change < 0

    def test_elo_changes_are_symmetric(self):
        """Winner's gain should equal loser's loss."""
        result = update_elo(1500, 1500, home_won=True)
        assert abs(result.home_elo_change + result.away_elo_change) < 0.001

    def test_upset_gives_more_points(self):
        """Upset (underdog winning) should give more Elo points."""
        # Favorite wins (expected)
        expected_result = update_elo(1600, 1400, home_won=True)

        # Underdog wins (upset)
        upset_result = update_elo(1400, 1600, home_won=True)

        assert abs(upset_result.home_elo_change) > abs(expected_result.home_elo_change)

    def test_expected_probabilities_stored(self):
        """Result should contain expected probabilities."""
        result = update_elo(1550, 1450, home_won=True)
        assert 0 < result.expected_home_win_prob < 1
        assert 0 < result.expected_away_win_prob < 1
        assert abs(result.expected_home_win_prob + result.expected_away_win_prob - 1) < 0.001


class TestMOVElo:
    """Tests for margin of victory Elo adjustment."""

    def test_blowout_win_gives_more_points(self):
        """Blowout win should give more Elo points than close game."""
        close_result = update_elo_with_mov(1500, 1500, 100, 98)
        blowout_result = update_elo_with_mov(1500, 1500, 120, 90)

        assert blowout_result.home_elo_change > close_result.home_elo_change

    def test_upset_blowout_gives_even_more_points(self):
        """Underdog blowout should give lots of points."""
        underdog_blowout = update_elo_with_mov(1400, 1600, 130, 100)
        favorite_blowout = update_elo_with_mov(1600, 1400, 130, 100)

        assert underdog_blowout.home_elo_change > favorite_blowout.home_elo_change


class TestSeasonRegression:
    """Tests for season-to-season regression."""

    def test_above_average_regresses_down(self):
        """Above average team should regress toward mean."""
        new_elo = season_regression(1600)
        assert 1500 < new_elo < 1600

    def test_below_average_regresses_up(self):
        """Below average team should regress toward mean."""
        new_elo = season_regression(1400)
        assert 1400 < new_elo < 1500

    def test_average_stays_same(self):
        """Average team should stay at mean."""
        new_elo = season_regression(1500)
        assert abs(new_elo - 1500) < 0.001

    def test_one_third_regression(self):
        """Default regression should be 1/3 toward mean."""
        new_elo = season_regression(1600, regression_factor=0.33)
        expected = 1600 + 0.33 * (1500 - 1600)  # 1567
        assert abs(new_elo - expected) < 1


class TestOddsConversion:
    """Tests for Elo to American odds conversion."""

    def test_50_percent_gives_even_odds(self):
        """50% probability should give +100 or -100."""
        odds = win_prob_to_american_odds(0.5)
        assert odds == -100 or odds == 100

    def test_favorite_gives_negative_odds(self):
        """Probability > 50% should give negative odds."""
        odds = win_prob_to_american_odds(0.7)
        assert odds < 0

    def test_underdog_gives_positive_odds(self):
        """Probability < 50% should give positive odds."""
        odds = win_prob_to_american_odds(0.3)
        assert odds > 0


class TestODElo:
    """Tests for Offensive/Defensive Elo system."""

    def test_expected_score_equal_elo_gives_league_avg(self):
        """Equal O/D Elo should give league average score."""
        score = calculate_expected_score(1500, 1500, home_advantage_points=0)
        assert abs(score - LEAGUE_AVG_SCORE) < 0.001

    def test_expected_score_home_advantage_adds_points(self):
        """Home advantage should add to expected score."""
        neutral = calculate_expected_score(1500, 1500, home_advantage_points=0)
        home = calculate_expected_score(1500, 1500, home_advantage_points=1.4)
        assert home > neutral
        assert abs(home - neutral - 1.4) < 0.001

    def test_spread_zero_when_equal(self):
        """Equal O/D Elo should give spread of 0 (no home advantage)."""
        spread = od_elo_to_spread(1500, 1500, 1500, 1500, home_advantage_points=0)
        assert abs(spread) < 0.001

    def test_spread_with_home_advantage(self):
        """Equal teams should show home advantage in spread."""
        spread = od_elo_to_spread(1500, 1500, 1500, 1500)
        expected_ha = ELO_HOME_ADVANTAGE / ELO_SPREAD_DIVISOR
        assert abs(spread - expected_ha) < 0.001

    def test_total_equal_elo_gives_double_league_avg(self):
        """Equal O/D Elo should give total near 2x league average."""
        total = od_elo_to_total(1500, 1500, 1500, 1500, home_advantage_points=0)
        assert abs(total - 2 * LEAGUE_AVG_SCORE) < 0.001

    def test_od_elo_update_correct_direction(self):
        """O/D Elo updates should move in correct direction after game."""
        # Home team scores more than expected -> offense should improve
        result = update_od_elo(1500, 1500, 1500, 1500, 130, 100)
        assert result.home_offense_change > 0  # Scored more than expected
        assert result.home_defense_change > 0  # Held opponent below expected
        assert result.away_offense_change < 0  # Scored less than expected
        assert result.away_defense_change < 0  # Allowed more than expected

    def test_win_prob_equal_elo_gives_50_percent(self):
        """Equal O/D Elo with no home advantage should give 50% each."""
        home_prob, away_prob = od_elo_to_win_prob(1500, 1500, 1500, 1500, home_advantage=0)
        assert abs(home_prob - 0.5) < 0.001
        assert abs(away_prob - 0.5) < 0.001

    def test_season_regression_od_toward_1500(self):
        """Season regression should move O/D Elo toward 1500."""
        new_o, new_d = season_regression_od(1600, 1400)
        assert 1500 < new_o < 1600  # Regressed toward mean
        assert 1400 < new_d < 1500  # Regressed toward mean

    def test_home_advantage_default_matches_config(self):
        """Default home advantage should match config (catches Fix #1 regression)."""
        # With equal Elo, spread should be exactly ELO_HOME_ADVANTAGE / ELO_SPREAD_DIVISOR
        spread = od_elo_to_spread(1500, 1500, 1500, 1500)
        expected = ELO_HOME_ADVANTAGE / ELO_SPREAD_DIVISOR
        assert abs(spread - expected) < 0.001, (
            f"Default home advantage {spread:.2f} doesn't match config "
            f"({ELO_HOME_ADVANTAGE}/{ELO_SPREAD_DIVISOR}={expected:.2f})"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
