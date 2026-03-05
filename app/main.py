"""NBA Game Predictions - Streamlit Application."""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import re

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON, now_ct
from src.data.database import init_database, get_connection, get_games_by_date
from src.models.predictor import predict_game
from src.utils.update_status import get_last_run_info

# Page configuration
st.set_page_config(
    page_title="NBA Game Predictions",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)


def convert_et_to_ct(time_str: str) -> str:
    """Convert Eastern Time string to Central Time."""
    if not time_str or 'ET' not in time_str:
        return time_str

    match = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)\s*ET', time_str.strip(), re.IGNORECASE)
    if not match:
        return time_str

    hour = int(match.group(1))
    minute = match.group(2)
    period = match.group(3).upper()

    if period == 'PM' and hour != 12:
        hour += 12
    elif period == 'AM' and hour == 12:
        hour = 0

    hour -= 1
    if hour < 0:
        hour += 24

    if hour == 0:
        display_hour = 12
        display_period = 'AM'
    elif hour < 12:
        display_hour = hour
        display_period = 'AM'
    elif hour == 12:
        display_hour = 12
        display_period = 'PM'
    else:
        display_hour = hour - 12
        display_period = 'PM'

    return f"{display_hour}:{minute} {display_period} CT"


def get_accuracy_stats():
    """Get season and recent accuracy stats."""
    try:
        with get_connection() as conn:
            # Season accuracy
            season_df = pd.read_sql_query("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE
                        WHEN (predicted_home_win_prob > 0.5 AND home_score > away_score)
                          OR (predicted_home_win_prob < 0.5 AND away_score > home_score)
                        THEN 1 ELSE 0
                    END) as correct
                FROM games
                WHERE status = 'final'
                AND home_score IS NOT NULL
                AND away_score IS NOT NULL
                AND predicted_home_win_prob IS NOT NULL
            """, conn)

            # Last 7 days accuracy
            seven_days_ago = (now_ct() - timedelta(days=7)).strftime("%Y-%m-%d")
            recent_df = pd.read_sql_query("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE
                        WHEN (predicted_home_win_prob > 0.5 AND home_score > away_score)
                          OR (predicted_home_win_prob < 0.5 AND away_score > home_score)
                        THEN 1 ELSE 0
                    END) as correct
                FROM games
                WHERE status = 'final'
                AND home_score IS NOT NULL
                AND away_score IS NOT NULL
                AND predicted_home_win_prob IS NOT NULL
                AND game_date >= ?
            """, conn, params=[seven_days_ago])

        season_total = int(season_df['total'].iloc[0])
        season_correct = int(season_df['correct'].iloc[0])
        recent_total = int(recent_df['total'].iloc[0])
        recent_correct = int(recent_df['correct'].iloc[0])

        return season_total, season_correct, recent_total, recent_correct
    except Exception:
        return 0, 0, 0, 0


def main():
    # Sidebar
    with st.sidebar:
        st.title("🏀 NBA Predictions")
        st.markdown("---")

        st.markdown(f"**Season:** {CURRENT_SEASON}")
        st.markdown(f"**Date:** {now_ct().strftime('%B %d, %Y')}")

        st.markdown("---")
        st.markdown("### Navigation")
        st.markdown("""
        - **Home** - Today's predictions
        - **Game Details** - Elo breakdowns & odds
        - **Model Accuracy** - Prediction tracking
        - **Team Ratings** - Elo rankings
        """)

        st.markdown("---")
        st.markdown(
            "Built with [Streamlit](https://streamlit.io) | "
            "Data: [nba_api](https://github.com/swar/nba_api)"
        )

    # Main content
    st.markdown('<p class="main-header">NBA Game Predictions</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">'
        'Elo-based win probability predictions for today\'s NBA games'
        '</p>',
        unsafe_allow_html=True
    )

    # Daily update status
    last_run = get_last_run_info()
    if last_run['ran_today']:
        if last_run['last_run_time']:
            st.success(f"Model updated today at {last_run['last_run_time']}")
        else:
            st.success("Model updated today")
    elif last_run['last_run_date']:
        st.warning(f"Model last updated: {last_run['last_run_date']} — Run `daily_update.py` for fresh predictions")
    else:
        st.error("Daily update has never run — Run `python scripts/daily_update.py` to initialize")

    # Initialize database
    try:
        init_database()
    except Exception as e:
        st.error(f"Database error: {e}")
        st.stop()

    # Accuracy summary
    season_total, season_correct, recent_total, recent_correct = get_accuracy_stats()

    if season_total > 0:
        season_pct = season_correct / season_total * 100
        accuracy_parts = [f"**Season:** {season_pct:.1f}% accurate ({season_correct}/{season_total})"]
        if recent_total > 0:
            recent_pct = recent_correct / recent_total * 100
            accuracy_parts.append(f"**Last 7 days:** {recent_pct:.1f}% ({recent_correct}/{recent_total})")
        st.markdown(" | ".join(accuracy_parts))

    # Date selector
    selected_date = st.date_input(
        "Select Date",
        value=now_ct().date(),
        help="Choose a date to view predictions"
    )
    date_str = selected_date.strftime("%Y-%m-%d")

    st.markdown("---")

    # Load games and predictions
    games_df = get_games_by_date(date_str)

    if games_df.empty:
        st.warning(f"No games found for {selected_date.strftime('%B %d, %Y')}.")
        st.stop()

    predictions = []
    game_times = {}

    for _, game in games_df.iterrows():
        pred = predict_game(
            home_team_id=game['home_team_id'],
            away_team_id=game['away_team_id'],
            home_elo=game.get('home_elo'),
            away_elo=game.get('away_elo'),
            game_id=game['game_id'],
            game_date=date_str,
            apply_injuries=True,
            home_offense_elo=game.get('home_offense_elo'),
            home_defense_elo=game.get('home_defense_elo'),
            away_offense_elo=game.get('away_offense_elo'),
            away_defense_elo=game.get('away_defense_elo'),
        )
        if pred:
            predictions.append(pred)
            game_status = game.get('status', 'scheduled')
            game_time_et = game.get('game_time')

            if game_status == 'in_progress':
                game_times[game['game_id']] = 'In Progress'
            elif game_status == 'final':
                game_times[game['game_id']] = 'Final'
            elif game_time_et:
                game_times[game['game_id']] = convert_et_to_ct(game_time_et)
            else:
                game_times[game['game_id']] = None

    if not predictions:
        st.info("No predictions available for this date.")
        st.stop()

    st.markdown(f"### {len(predictions)} Games")

    # Model Picks table
    picks_data = []
    for pred in predictions:
        game_time = game_times.get(pred.game_id, '-')

        if pred.home_win_prob > 0.5:
            predicted_winner = pred.home_team
            win_prob = pred.home_win_prob
        else:
            predicted_winner = pred.away_team
            win_prob = pred.away_win_prob

        if win_prob >= 0.65:
            confidence = "High"
        elif win_prob >= 0.55:
            confidence = "Medium"
        else:
            confidence = "Low"

        picks_data.append({
            'Time': game_time if game_time else '-',
            'Matchup': f"{pred.away_team} @ {pred.home_team}",
            'Pick': f"{predicted_winner}",
            'Win Prob': f"{win_prob:.1%}",
            'Confidence': confidence,
            'Spread': f"{pred.home_team} {pred.predicted_spread:+.1f}" if pred.predicted_spread < 0 else f"{pred.away_team} {-pred.predicted_spread:+.1f}",
        })

    picks_df = pd.DataFrame(picks_data)
    st.dataframe(picks_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
