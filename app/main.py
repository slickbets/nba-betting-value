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
from src.utils.live_scores import refresh_live_scores
from app.shared import render_sidebar, confidence_badge, result_badge

# Page configuration
st.set_page_config(
    page_title="Slick Bets",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


def render_game_card(pred, info):
    """Render a single game as a styled card."""
    status = info.get('status', 'scheduled')
    game_time = info.get('time') or ''
    home_score = info.get('home_score')
    away_score = info.get('away_score')

    # Pick + confidence
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

    # Spread from winner's perspective
    spread_val = -(pred.predicted_spread if predicted_winner == pred.home_team else -pred.predicted_spread)
    spread_display = f"{predicted_winner} {spread_val:+.1f}"

    # Total
    predicted_total = getattr(pred, 'predicted_total', 0)
    total_display = f"{predicted_total:.1f}" if predicted_total else "-"

    # Score / time display
    if status == 'final' and home_score is not None and away_score is not None:
        score_html = f'<span class="score-final">{pred.away_team} {int(away_score)} - {int(home_score)} {pred.home_team}</span>'
        time_html = '<span class="badge badge-correct" style="font-size: 0.7rem;">FINAL</span>'
    elif status == 'in_progress' and home_score is not None and away_score is not None:
        score_html = f'<span class="score-live">{pred.away_team} {int(away_score)} - {int(home_score)} {pred.home_team}</span>'
        time_html = '<span class="badge badge-live" style="font-size: 0.7rem;">LIVE</span>'
    elif status == 'in_progress':
        score_html = ''
        time_html = '<span class="badge badge-live" style="font-size: 0.7rem;">LIVE</span>'
    else:
        score_html = ''
        time_html = f'<span class="game-card-time">{game_time}</span>' if game_time else ''

    # Result
    if status == 'final' and home_score is not None and away_score is not None:
        actual_winner = pred.home_team if int(home_score) > int(away_score) else pred.away_team
        result = "Correct" if actual_winner == predicted_winner else "Wrong"
    elif status == 'in_progress':
        result = "Live"
    else:
        result = "-"

    card_html = f"""
    <div class="game-card">
        <div class="game-card-header">
            <span class="game-card-matchup">{pred.away_team} @ {pred.home_team}</span>
            {time_html}
        </div>
        <div style="margin-bottom: 0.6rem;">
            {score_html}
        </div>
        <div class="game-card-body">
            <div class="game-card-stat">
                <div class="game-card-stat-label">SB Pick</div>
                <div class="game-card-stat-value">{predicted_winner}</div>
            </div>
            <div class="game-card-stat">
                <div class="game-card-stat-label">Win Prob</div>
                <div class="game-card-stat-value">{win_prob:.0%}</div>
            </div>
            <div class="game-card-stat">
                <div class="game-card-stat-label">Confidence</div>
                <div>{confidence_badge(confidence)}</div>
            </div>
            <div class="game-card-stat">
                <div class="game-card-stat-label">Spread</div>
                <div class="game-card-stat-value">{spread_display}</div>
            </div>
            <div class="game-card-stat">
                <div class="game-card-stat-label">Total</div>
                <div class="game-card-stat-value">{total_display}</div>
            </div>
            <div class="game-card-stat">
                <div class="game-card-stat-label">Result</div>
                <div>{result_badge(result)}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    # Inline expandable details
    with st.expander("Game Details", expanded=False):
        det_col1, det_col2, det_col3 = st.columns(3)

        with det_col1:
            st.markdown(f"**{pred.home_team} (Home)**")
            home_rest_applied = getattr(pred, 'rest_applied', False)
            home_rest_adj = getattr(pred, 'home_rest_adjustment', 0)
            home_rest_days = getattr(pred, 'home_rest_days', 1)
            has_home_adj = (pred.injuries_applied and pred.home_injury_adjustment != 0) or \
                          (home_rest_applied and home_rest_adj != 0)
            if has_home_adj:
                st.write(f"Base Elo: {pred.home_elo_base:.0f}")
                if pred.injuries_applied and pred.home_injury_adjustment != 0:
                    st.write(f"Injury Adj: {pred.home_injury_adjustment:+.0f}")
                if home_rest_applied and home_rest_adj != 0:
                    rest_label = "B2B" if home_rest_days == 0 else f"{home_rest_days}d rest"
                    st.write(f"Rest Adj ({rest_label}): {home_rest_adj:+.0f}")
                st.write(f"**Adj Elo: {pred.home_elo:.0f}**")
            else:
                st.write(f"Elo: {pred.home_elo:.0f}")
                if home_rest_applied:
                    st.caption(f"Rest: {home_rest_days} days")
            if getattr(pred, 'od_elo_applied', False):
                home_o = getattr(pred, 'home_offense_elo', 0)
                home_d = getattr(pred, 'home_defense_elo', 0)
                if home_o and home_d:
                    st.caption(f"O-Elo: {home_o:.0f} | D-Elo: {home_d:.0f}")
            st.write(f"Win Prob: {pred.home_win_prob:.1%}")

        with det_col2:
            st.markdown(f"**{pred.away_team} (Away)**")
            away_rest_applied = getattr(pred, 'rest_applied', False)
            away_rest_adj = getattr(pred, 'away_rest_adjustment', 0)
            away_rest_days = getattr(pred, 'away_rest_days', 1)
            has_away_adj = (pred.injuries_applied and pred.away_injury_adjustment != 0) or \
                          (away_rest_applied and away_rest_adj != 0)
            if has_away_adj:
                st.write(f"Base Elo: {pred.away_elo_base:.0f}")
                if pred.injuries_applied and pred.away_injury_adjustment != 0:
                    st.write(f"Injury Adj: {pred.away_injury_adjustment:+.0f}")
                if away_rest_applied and away_rest_adj != 0:
                    rest_label = "B2B" if away_rest_days == 0 else f"{away_rest_days}d rest"
                    st.write(f"Rest Adj ({rest_label}): {away_rest_adj:+.0f}")
                st.write(f"**Adj Elo: {pred.away_elo:.0f}**")
            else:
                st.write(f"Elo: {pred.away_elo:.0f}")
                if away_rest_applied:
                    st.caption(f"Rest: {away_rest_days} days")
            if getattr(pred, 'od_elo_applied', False):
                away_o = getattr(pred, 'away_offense_elo', 0)
                away_d = getattr(pred, 'away_defense_elo', 0)
                if away_o and away_d:
                    st.caption(f"O-Elo: {away_o:.0f} | D-Elo: {away_d:.0f}")
            st.write(f"Win Prob: {pred.away_win_prob:.1%}")

        with det_col3:
            st.markdown("**Prediction**")
            if pred.predicted_spread > 0:
                spread_str = f"{pred.home_team} by {pred.predicted_spread:.1f}"
            else:
                spread_str = f"{pred.away_team} by {abs(pred.predicted_spread):.1f}"
            st.write(f"Spread: {spread_str}")
            if getattr(pred, 'od_elo_applied', False) and getattr(pred, 'predicted_total', 0):
                st.write(f"Predicted Total: {pred.predicted_total:.1f}")

        # Injury details
        if pred.injuries_applied and (pred.home_injuries or pred.away_injuries):
            st.markdown("---")
            st.markdown("**Injury Report**")
            inj_c1, inj_c2 = st.columns(2)
            with inj_c1:
                if pred.home_injuries:
                    st.markdown(f"*{pred.home_team}:*")
                    for inj in pred.home_injuries:
                        if abs(inj.get('elo_impact', 0)) >= 5:
                            st.caption(f"* {inj['player_name']} ({inj.get('status', 'Out')}): {inj.get('elo_impact', 0):+.0f} Elo")
                else:
                    st.caption(f"{pred.home_team}: No significant injuries")
            with inj_c2:
                if pred.away_injuries:
                    st.markdown(f"*{pred.away_team}:*")
                    for inj in pred.away_injuries:
                        if abs(inj.get('elo_impact', 0)) >= 5:
                            st.caption(f"* {inj['player_name']} ({inj.get('status', 'Out')}): {inj.get('elo_impact', 0):+.0f} Elo")
                else:
                    st.caption(f"{pred.away_team}: No significant injuries")


def main():
    render_sidebar()

    # Hero section
    st.markdown('<div class="hero-title">Slick Bets</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">'
        'Data-driven NBA picks powered by Elo ratings, injury adjustments, and rest factors. '
        'Our model analyzes every game to find where the edge is &mdash; updated daily.'
        '</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="hero-tip">'
        'Enjoy the picks? <a href="/Donate">Leave a tip</a> to help keep Slick Bets running.'
        '</div>',
        unsafe_allow_html=True
    )

    # Initialize database
    try:
        init_database()
    except Exception as e:
        st.error(f"Database error: {e}")
        st.stop()

    # Accuracy hero cards
    season_total, season_correct, recent_total, recent_correct = get_accuracy_stats()

    if season_total > 0:
        season_pct = season_correct / season_total * 100

        cols = st.columns(3)
        with cols[0]:
            st.markdown(f"""
            <div class="accuracy-card">
                <div class="accuracy-big">{season_pct:.1f}%</div>
                <div class="accuracy-label">Season Accuracy</div>
                <div class="accuracy-detail">{season_correct} / {season_total} picks</div>
            </div>
            """, unsafe_allow_html=True)

        with cols[1]:
            if recent_total > 0:
                recent_pct = recent_correct / recent_total * 100
                st.markdown(f"""
                <div class="accuracy-card">
                    <div class="accuracy-big">{recent_pct:.1f}%</div>
                    <div class="accuracy-label">Last 7 Days</div>
                    <div class="accuracy-detail">{recent_correct} / {recent_total} picks</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="accuracy-card">
                    <div class="accuracy-big">-</div>
                    <div class="accuracy-label">Last 7 Days</div>
                    <div class="accuracy-detail">No recent games</div>
                </div>
                """, unsafe_allow_html=True)

        with cols[2]:
            # Daily update status
            last_run = get_last_run_info()
            if last_run['ran_today']:
                status_color = "#00C853"
                status_icon = "&#10003;"
                status_text = f"Updated {last_run['last_run_time']}" if last_run['last_run_time'] else "Updated today"
            elif last_run['last_run_date']:
                status_color = "#FFC107"
                status_icon = "&#9888;"
                status_text = f"Last: {last_run['last_run_date']}"
            else:
                status_color = "#F44336"
                status_icon = "&#10007;"
                status_text = "Never run"
            st.markdown(f"""
            <div class="accuracy-card">
                <div class="accuracy-big" style="color: {status_color};">{status_icon}</div>
                <div class="accuracy-label">Model Status</div>
                <div class="accuracy-detail">{status_text}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")

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
    game_info = {}

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

    st.markdown(
        f'<div class="section-header">{len(predictions)} Games &mdash; '
        f'{selected_date.strftime("%B %d, %Y")}</div>',
        unsafe_allow_html=True
    )

    # Render game cards in a 2-column grid
    for i in range(0, len(predictions), 2):
        cols = st.columns(2)
        with cols[0]:
            pred = predictions[i]
            info = game_info.get(pred.game_id, {})
            render_game_card(pred, info)
        if i + 1 < len(predictions):
            with cols[1]:
                pred = predictions[i + 1]
                info = game_info.get(pred.game_id, {})
                render_game_card(pred, info)


if __name__ == "__main__":
    main()
