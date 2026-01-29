"""Tests for odds conversion functions."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.betting.odds_converter import (
    american_to_decimal,
    decimal_to_american,
    american_to_implied_prob,
    implied_prob_to_american,
    decimal_to_implied_prob,
    implied_prob_to_decimal,
    calculate_vig,
    remove_vig,
    calculate_edge,
    calculate_expected_value,
    calculate_kelly_fraction,
    format_american_odds,
    format_probability,
    format_spread,
)


class TestAmericanToDecimal:
    """Tests for American to decimal odds conversion."""

    def test_minus_110(self):
        """Standard -110 juice should convert correctly."""
        decimal = american_to_decimal(-110)
        assert abs(decimal - 1.909) < 0.01

    def test_minus_150(self):
        """-150 favorite should convert correctly."""
        decimal = american_to_decimal(-150)
        assert abs(decimal - 1.667) < 0.01

    def test_plus_150(self):
        """+150 underdog should convert correctly."""
        decimal = american_to_decimal(150)
        assert abs(decimal - 2.5) < 0.01

    def test_plus_200(self):
        """+200 should convert to 3.0 decimal."""
        decimal = american_to_decimal(200)
        assert abs(decimal - 3.0) < 0.01

    def test_minus_100(self):
        """-100 (even) should convert to 2.0 decimal."""
        decimal = american_to_decimal(-100)
        assert abs(decimal - 2.0) < 0.01


class TestDecimalToAmerican:
    """Tests for decimal to American odds conversion."""

    def test_decimal_2_gives_even(self):
        """2.0 decimal should give +100 or -100."""
        american = decimal_to_american(2.0)
        assert american == 100 or american == -100

    def test_decimal_3_gives_plus_200(self):
        """3.0 decimal should give +200."""
        american = decimal_to_american(3.0)
        assert american == 200

    def test_decimal_1_5_gives_minus_200(self):
        """1.5 decimal should give -200."""
        american = decimal_to_american(1.5)
        assert american == -200


class TestImpliedProbability:
    """Tests for implied probability conversions."""

    def test_minus_150_implies_60_percent(self):
        """-150 should imply 60% probability."""
        prob = american_to_implied_prob(-150)
        assert abs(prob - 0.6) < 0.001

    def test_plus_150_implies_40_percent(self):
        """+150 should imply 40% probability."""
        prob = american_to_implied_prob(150)
        assert abs(prob - 0.4) < 0.001

    def test_minus_200_implies_66_percent(self):
        """-200 should imply 66.67% probability."""
        prob = american_to_implied_prob(-200)
        assert abs(prob - 0.6667) < 0.01

    def test_plus_200_implies_33_percent(self):
        """+200 should imply 33.33% probability."""
        prob = american_to_implied_prob(200)
        assert abs(prob - 0.3333) < 0.01

    def test_even_odds_implies_50_percent(self):
        """-100/+100 should imply 50% probability."""
        prob_minus = american_to_implied_prob(-100)
        prob_plus = american_to_implied_prob(100)
        assert abs(prob_minus - 0.5) < 0.001
        assert abs(prob_plus - 0.5) < 0.001


class TestProbToOdds:
    """Tests for probability to odds conversion."""

    def test_60_percent_gives_minus_150(self):
        """60% should give approximately -150."""
        odds = implied_prob_to_american(0.6)
        assert odds == -150

    def test_40_percent_gives_plus_150(self):
        """40% should give approximately +150."""
        odds = implied_prob_to_american(0.4)
        assert odds == 150

    def test_roundtrip_conversion(self):
        """Converting odds to prob and back should return same odds."""
        original = -150
        prob = american_to_implied_prob(original)
        converted_back = implied_prob_to_american(prob)
        assert converted_back == original


class TestVigorish:
    """Tests for vig calculations."""

    def test_standard_vig_is_about_4_5_percent(self):
        """Standard -110/-110 line should have ~4.5% vig."""
        prob1 = american_to_implied_prob(-110)
        prob2 = american_to_implied_prob(-110)
        vig = calculate_vig(prob1, prob2)
        assert 4.0 < vig < 5.0

    def test_remove_vig_sums_to_one(self):
        """Vig-free probabilities should sum to 1."""
        true_prob1, true_prob2 = remove_vig(-150, 130)
        assert abs(true_prob1 + true_prob2 - 1.0) < 0.001


class TestEdgeCalculation:
    """Tests for edge (advantage) calculation."""

    def test_positive_edge_when_model_higher(self):
        """Edge should be positive when model prob > implied prob."""
        # Model says 60%, odds imply 54.5% (-120)
        edge = calculate_edge(0.60, -120)
        assert edge > 0

    def test_negative_edge_when_model_lower(self):
        """Edge should be negative when model prob < implied prob."""
        edge = calculate_edge(0.40, -120)
        assert edge < 0

    def test_edge_example(self):
        """Test specific edge calculation."""
        # Model: 60%, Odds: -120 (implies 54.5%)
        edge = calculate_edge(0.60, -120)
        implied = american_to_implied_prob(-120)
        expected_edge = (0.60 - implied) * 100
        assert abs(edge - expected_edge) < 0.1


class TestExpectedValue:
    """Tests for expected value calculation."""

    def test_positive_ev_with_edge(self):
        """Positive edge should give positive EV."""
        # 60% model prob at +150 (40% implied)
        ev = calculate_expected_value(0.60, 150)
        assert ev > 0

    def test_negative_ev_without_edge(self):
        """Below implied prob should give negative EV."""
        # 30% model prob at +150 (40% implied)
        ev = calculate_expected_value(0.30, 150)
        assert ev < 0


class TestKellyFraction:
    """Tests for Kelly Criterion calculation."""

    def test_positive_kelly_with_edge(self):
        """Positive edge should give positive Kelly."""
        kelly = calculate_kelly_fraction(0.60, 150)
        assert kelly > 0

    def test_negative_kelly_without_edge(self):
        """Negative edge should give negative Kelly."""
        kelly = calculate_kelly_fraction(0.30, 150)
        assert kelly < 0

    def test_kelly_reasonable_size(self):
        """Kelly fraction should be reasonable (not too large)."""
        kelly = calculate_kelly_fraction(0.60, 150)
        assert kelly < 0.5  # Shouldn't bet more than 50% of bankroll


class TestFormatting:
    """Tests for display formatting functions."""

    def test_format_positive_odds(self):
        """Positive odds should have + prefix."""
        assert format_american_odds(150) == "+150"

    def test_format_negative_odds(self):
        """Negative odds should show minus sign."""
        assert format_american_odds(-150) == "-150"

    def test_format_probability(self):
        """Probability should format as percentage."""
        assert format_probability(0.555) == "55.5%"

    def test_format_positive_spread(self):
        """Positive spread (underdog) should have + prefix."""
        assert format_spread(3.5) == "+3.5"

    def test_format_negative_spread(self):
        """Negative spread (favorite) should show minus."""
        assert format_spread(-3.5) == "-3.5"

    def test_format_pick_em(self):
        """Zero spread should show PK."""
        assert format_spread(0) == "PK"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
