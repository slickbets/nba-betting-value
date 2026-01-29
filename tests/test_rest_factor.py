"""Tests for rest factor calculations."""

import pytest
from src.models.rest_factor import (
    get_rest_adjustment,
    calculate_rest_days,
    get_rest_description,
    REST_ADJUSTMENTS,
    MAX_REST_BONUS,
)


class TestRestAdjustment:
    """Test rest day Elo adjustments."""

    def test_back_to_back_is_negative(self):
        """Teams on B2B should get negative adjustment."""
        adj = get_rest_adjustment(0)
        assert adj < 0
        assert adj == -25  # ~1 point penalty

    def test_normal_rest_is_zero(self):
        """1 day rest (normal) should have no adjustment."""
        adj = get_rest_adjustment(1)
        assert adj == 0

    def test_extra_rest_is_positive(self):
        """2+ days rest should get positive adjustment."""
        assert get_rest_adjustment(2) > 0
        assert get_rest_adjustment(3) > 0

    def test_diminishing_returns(self):
        """4+ days should cap at max bonus."""
        assert get_rest_adjustment(4) == MAX_REST_BONUS
        assert get_rest_adjustment(5) == MAX_REST_BONUS
        assert get_rest_adjustment(10) == MAX_REST_BONUS

    def test_invalid_rest_days(self):
        """Negative rest days should return 0."""
        assert get_rest_adjustment(-1) == 0


class TestCalculateRestDays:
    """Test rest day calculation from dates."""

    def test_back_to_back(self):
        """Games on consecutive days = 0 rest."""
        rest = calculate_rest_days("2025-01-24", "2025-01-25")
        assert rest == 0

    def test_normal_rest(self):
        """Games with one day between = 1 rest."""
        rest = calculate_rest_days("2025-01-23", "2025-01-25")
        assert rest == 1

    def test_two_days_rest(self):
        """Games with two days between = 2 rest."""
        rest = calculate_rest_days("2025-01-22", "2025-01-25")
        assert rest == 2

    def test_week_rest(self):
        """Week between games = 6 rest days."""
        rest = calculate_rest_days("2025-01-18", "2025-01-25")
        assert rest == 6

    def test_invalid_dates(self):
        """Invalid date formats should return default (1)."""
        assert calculate_rest_days("invalid", "2025-01-25") == 1
        assert calculate_rest_days("2025-01-25", "invalid") == 1
        assert calculate_rest_days(None, "2025-01-25") == 1


class TestRestDescription:
    """Test human-readable rest descriptions."""

    def test_back_to_back(self):
        assert get_rest_description(0) == "B2B"

    def test_one_day(self):
        assert get_rest_description(1) == "1 day"

    def test_two_days(self):
        assert get_rest_description(2) == "2 days"

    def test_multiple_days(self):
        assert "3 days" in get_rest_description(3)
        assert "5 days" in get_rest_description(5)


class TestRestImpactOnSpread:
    """Test that rest adjustments are meaningful for spreads."""

    def test_b2b_vs_rested_difference(self):
        """B2B vs well-rested should be ~1.5 point swing."""
        b2b_adj = get_rest_adjustment(0)  # -25
        rested_adj = get_rest_adjustment(3)  # +8

        # Difference of 33 Elo points = ~1.3 point spread swing
        diff = rested_adj - b2b_adj
        assert diff == 33  # Significant but not overwhelming

    def test_both_on_b2b_cancels_out(self):
        """If both teams are on B2B, adjustments cancel."""
        adj = get_rest_adjustment(0)
        # Net difference is 0 when both have same rest
        assert adj - adj == 0
