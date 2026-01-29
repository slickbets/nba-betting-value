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
)
from config import ELO_INITIAL_RATING, ELO_HOME_ADVANTAGE


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
