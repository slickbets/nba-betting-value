"""NBA Game Predictions - Streamlit Application."""

import streamlit as st
from datetime import timedelta
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON, now_ct
from src.data.database import init_database, get_connection, get_games_by_date
from src.models.predictor import predict_game
from src.utils.update_status import get_last_run_info
from src.utils.time_utils import convert_et_to_ct
from src.utils.feedback import submit_feedback
from src.utils.live_scores import refresh_live_scores

# Page configuration
st.set_page_config(
    page_title="Slick Bets",
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
        st.title("🏀 Slick Bets")
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
        st.markdown("### Feedback")
        with st.form("feedback_form", clear_on_submit=True):
            fb_category = st.selectbox("Type", ["Bug", "Feature Request", "General Feedback"])
            fb_title = st.text_input("Title")
            fb_description = st.text_area("Details", height=100)
            fb_submitted = st.form_submit_button("Submit Feedback")
            if fb_submitted:
                if fb_title.strip():
                    if submit_feedback(fb_title.strip(), fb_description.strip(), fb_category):
                        st.success("Thanks! Feedback submitted.")
                    else:
                        st.error("Failed to submit. Try again later.")
                else:
                    st.warning("Please add a title.")

        st.markdown("---")
        st.markdown(
            "Built with [Streamlit](https://streamlit.io) | "
            "Data: [nba_api](https://github.com/swar/nba_api)"
        )

    # Main content
    st.markdown('<p class="main-header">Slick Bets</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">'
        'Data-driven NBA picks powered by Elo ratings, injury adjustments, and rest factors. '
        'Our model analyzes every game to find where the edge is — updated daily.'
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

    # Auto-refresh live scores from ESPN (cached 60s)
    if date_str == now_ct().strftime("%Y-%m-%d"):
        refresh_live_scores(date_str)

    st.markdown("---")

    # Load games and predictions
    games_df = get_games_by_date(date_str)

    if games_df.empty:
        st.warning(f"No games found for {selected_date.strftime('%B %d, %Y')}.")
        st.stop()

    predictions = []
    game_info = {}  # game_id -> {time, status, home_score, away_score}

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
                time_display = 'In Progress'
            elif game_status == 'final':
                time_display = 'Final'
            elif game_time_et:
                time_display = convert_et_to_ct(game_time_et)
            else:
                time_display = None

            game_info[game['game_id']] = {
                'time': time_display,
                'status': game_status,
                'home_score': game.get('home_score'),
                'away_score': game.get('away_score'),
            }

    if not predictions:
        st.info("No predictions available for this date.")
        st.stop()

    st.markdown(f"### {len(predictions)} Games")

    # Model Picks table
    picks_data = []
    for pred in predictions:
        info = game_info.get(pred.game_id, {})
        game_time = info.get('time') or '-'
        status = info.get('status', 'scheduled')

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

        # Score column: time, live score, or final score
        home_score = info.get('home_score')
        away_score = info.get('away_score')
        if status == 'final' and home_score is not None and away_score is not None:
            score = f"{pred.away_team} {int(away_score)} - {int(home_score)} {pred.home_team} (Final)"
        elif status == 'in_progress' and home_score is not None and away_score is not None:
            score = f"{pred.away_team} {int(away_score)} - {int(home_score)} {pred.home_team} (Live)"
        elif status == 'in_progress':
            score = "In Progress"
        else:
            score = game_time

        # Result column
        if status == 'final' and home_score is not None and away_score is not None:
            if int(home_score) > int(away_score):
                actual_winner = pred.home_team
            else:
                actual_winner = pred.away_team
            result = "Correct" if actual_winner == predicted_winner else "Wrong"
        elif status == 'in_progress':
            result = "Live"
        else:
            result = "-"

        picks_data.append({
            'Matchup': f"{pred.away_team} @ {pred.home_team}",
            'Slick Bets Model Pick': f"{predicted_winner}",
            'Win Prob': f"{win_prob:.1%}",
            'Confidence': confidence,
            'Spread': f"{predicted_winner} {-(pred.predicted_spread if predicted_winner == pred.home_team else -pred.predicted_spread):+.1f}",
            'Score': score,
            'Result': result,
        })

    picks_df = pd.DataFrame(picks_data)
    st.dataframe(picks_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
