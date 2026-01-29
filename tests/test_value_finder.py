"""Tests for value bet finder."""

import pytest
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.betting.value_finder import (
    ValueBet,
    categorize_edge,
    find_value_bets_for_game,
    filter_best_odds,
    get_value_summary,
    value_bets_to_dataframe,
)
from src.models.predictor import GamePrediction


@pytest.fixture
def sample_prediction():
    """Create a sample game prediction."""
    return GamePrediction(
        game_id="0022400123",
        home_team="BOS",
        away_team="LAL",
        home_elo=1600,
        away_elo=1520,
        home_win_prob=0.65,
        away_win_prob=0.35,
        predicted_spread=-5.2,
        home_implied_odds=-186,
        away_implied_odds=156,
    )


@pytest.fixture
def sample_odds_df():
    """Create sample odds DataFrame."""
    return pd.DataFrame([
        {
            "home_team": "BOS",
            "away_team": "LAL",
            "sportsbook": "draftkings",
            "home_ml": -150,
            "away_ml": 130,
        },
        {
            "home_team": "BOS",
            "away_team": "LAL",
            "sportsbook": "fanduel",
            "home_ml": -145,
            "away_ml": 125,
        },
    ])


class TestCategorizeEdge:
    """Tests for edge categorization."""

    def test_high_confidence(self):
        """Edge >= 10% should be High confidence."""
        assert categorize_edge(12.0) == "High"
        assert categorize_edge(10.0) == "High"

    def test_medium_confidence(self):
        """Edge 5-10% should be Medium confidence."""
        assert categorize_edge(7.0) == "Medium"
        assert categorize_edge(5.0) == "Medium"

    def test_low_confidence(self):
        """Edge < 5% should be Low confidence."""
        assert categorize_edge(3.0) == "Low"
        assert categorize_edge(4.9) == "Low"


class TestFindValueBets:
    """Tests for finding value bets."""

    def test_finds_value_when_present(self, sample_prediction, sample_odds_df):
        """Should find value bets when edge exists."""
        # Model says 65%, odds imply 60% (-150) = 5% edge
        value_bets = find_value_bets_for_game(
            sample_prediction, sample_odds_df, min_edge=3.0
        )

        # Should find value on the home team
        home_bets = [b for b in value_bets if b.selection == "home"]
        assert len(home_bets) > 0

    def test_respects_min_edge(self, sample_prediction, sample_odds_df):
        """Should only return bets above minimum edge."""
        # With high min_edge, should find fewer bets
        value_bets = find_value_bets_for_game(
            sample_prediction, sample_odds_df, min_edge=10.0
        )

        for bet in value_bets:
            assert bet.edge >= 10.0

    def test_filters_heavy_favorites(self, sample_prediction):
        """Should filter out very heavy favorites."""
        odds_df = pd.DataFrame([{
            "home_team": "BOS",
            "away_team": "LAL",
            "sportsbook": "draftkings",
            "home_ml": -400,  # Too heavy
            "away_ml": 300,
        }])

        value_bets = find_value_bets_for_game(
            sample_prediction, odds_df, min_edge=0.0, min_odds=-300
        )

        # Home team should be filtered out
        home_bets = [b for b in value_bets if b.selection == "home"]
        assert len(home_bets) == 0

    def test_filters_extreme_underdogs(self, sample_prediction):
        """Should filter out extreme underdogs."""
        odds_df = pd.DataFrame([{
            "home_team": "BOS",
            "away_team": "LAL",
            "sportsbook": "draftkings",
            "home_ml": -110,
            "away_ml": 600,  # Too extreme
        }])

        value_bets = find_value_bets_for_game(
            sample_prediction, odds_df, min_edge=0.0, max_odds=500
        )

        # Away team should be filtered out
        away_bets = [b for b in value_bets if b.selection == "away"]
        assert len(away_bets) == 0

    def test_empty_odds_returns_empty_list(self, sample_prediction):
        """Empty odds should return empty list."""
        value_bets = find_value_bets_for_game(
            sample_prediction, pd.DataFrame(), min_edge=0.0
        )
        assert len(value_bets) == 0


class TestFilterBestOdds:
    """Tests for filtering to best odds per bet."""

    def test_keeps_best_odds_per_selection(self):
        """Should keep only the best odds for each team."""
        value_bets = [
            ValueBet(
                game_id="123", matchup="LAL @ BOS", selection="home", team="BOS",
                bet_type="moneyline", line=None, odds=-145, sportsbook="fanduel",
                model_prob=0.65, implied_prob=0.59, edge=6.0,
                expected_value=5.0, kelly_fraction=0.1, confidence="Medium"
            ),
            ValueBet(
                game_id="123", matchup="LAL @ BOS", selection="home", team="BOS",
                bet_type="moneyline", line=None, odds=-150, sportsbook="draftkings",
                model_prob=0.65, implied_prob=0.60, edge=5.0,
                expected_value=4.0, kelly_fraction=0.08, confidence="Medium"
            ),
        ]

        filtered = filter_best_odds(value_bets)

        assert len(filtered) == 1
        assert filtered[0].odds == -145  # Better odds


class TestValueSummary:
    """Tests for value bet summary."""

    def test_summary_with_bets(self):
        """Should return correct summary stats."""
        value_bets = [
            ValueBet(
                game_id="123", matchup="LAL @ BOS", selection="home", team="BOS",
                bet_type="moneyline", line=None, odds=-145, sportsbook="fanduel",
                model_prob=0.65, implied_prob=0.59, edge=10.0,
                expected_value=5.0, kelly_fraction=0.1, confidence="High"
            ),
            ValueBet(
                game_id="123", matchup="LAL @ BOS", selection="away", team="LAL",
                bet_type="moneyline", line=None, odds=125, sportsbook="fanduel",
                model_prob=0.40, implied_prob=0.35, edge=5.0,
                expected_value=3.0, kelly_fraction=0.05, confidence="Medium"
            ),
        ]

        summary = get_value_summary(value_bets)

        assert summary["total_bets"] == 2
        assert summary["avg_edge"] == 7.5
        assert summary["high_confidence"] == 1
        assert summary["medium_confidence"] == 1

    def test_summary_empty_list(self):
        """Empty list should return zero stats."""
        summary = get_value_summary([])

        assert summary["total_bets"] == 0
        assert summary["avg_edge"] == 0


class TestValueBetsToDataFrame:
    """Tests for DataFrame conversion."""

    def test_converts_to_dataframe(self):
        """Should convert value bets to DataFrame."""
        value_bets = [
            ValueBet(
                game_id="123", matchup="LAL @ BOS", selection="home", team="BOS",
                bet_type="moneyline", line=None, odds=-145, sportsbook="fanduel",
                model_prob=0.65, implied_prob=0.59, edge=6.0,
                expected_value=5.0, kelly_fraction=0.1, confidence="Medium"
            ),
        ]

        df = value_bets_to_dataframe(value_bets)

        assert len(df) == 1
        assert df.iloc[0]["team"] == "BOS"
        assert df.iloc[0]["odds"] == "+145" or df.iloc[0]["odds"] == "-145"

    def test_empty_list_gives_empty_dataframe(self):
        """Empty list should give empty DataFrame."""
        df = value_bets_to_dataframe([])
        assert df.empty


class TestValueBetDataclass:
    """Tests for ValueBet dataclass."""

    def test_str_format(self):
        """Should have readable string representation."""
        bet = ValueBet(
            game_id="123", matchup="LAL @ BOS", selection="home", team="BOS",
            bet_type="moneyline", line=None, odds=-145, sportsbook="fanduel",
            model_prob=0.65, implied_prob=0.59, edge=6.0,
            expected_value=5.0, kelly_fraction=0.1, confidence="Medium"
        )

        s = str(bet)

        assert "LAL @ BOS" in s
        assert "BOS" in s
        assert "fanduel" in s
        assert "6.0%" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
