"""Game Details page - Elo breakdowns, injuries, rest factors, and live odds."""

import streamlit as st
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import ODDS_API_KEY, CURRENT_SEASON, now_ct
from src.utils.time_utils import convert_et_to_ct
from src.data.database import get_games_by_date, init_database
from src.utils.update_status import get_last_run_info
from src.utils.live_scores import refresh_live_scores
from src.data.odds_fetcher import get_current_odds
from src.models.predictor import predict_game, predictions_to_dataframe
from app.shared import render_sidebar, confidence_badge

st.set_page_config(page_title="Game Details | Slick Bets", page_icon="SB", layout="wide")
render_sidebar()

st.markdown('<div class="page-header">Game Details</div>', unsafe_allow_html=True)
st.markdown('<div class="page-desc">Elo breakdowns, injury impacts, rest factors, and sportsbook odds.</div>', unsafe_allow_html=True)

# Daily update status
last_run = get_last_run_info()
if last_run['ran_today']:
    status_text = f"Model updated today at {last_run['last_run_time']}" if last_run['last_run_time'] else "Model updated today"
    st.success(status_text)
elif last_run['last_run_date']:
    st.warning(f"Model last updated: {last_run['last_run_date']}")
else:
    st.error("Daily update has never run")

# Date selector and controls
col1, col2 = st.columns([2, 2])
with col1:
    selected_date = st.date_input(
        "Select Date",
        value=now_ct().date(),
        help="Choose a date to view games and predictions",
    )
    date_str = selected_date.strftime("%Y-%m-%d")

with col2:
    apply_injuries = st.checkbox(
        "Apply Injury Adjustments",
        value=True,
        help="Adjust team Elo ratings based on injured players",
    )

st.markdown("---")

# Initialize database
try:
    init_database()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Auto-refresh live scores
if date_str == now_ct().strftime("%Y-%m-%d"):
    refresh_live_scores(date_str)


@st.cache_data(ttl=60)
def load_games_and_predictions(date_str: str, apply_injuries: bool = True):
    """Load games and generate predictions."""
    games_df = get_games_by_date(date_str)

    if games_df.empty:
        return pd.DataFrame(), [], {}, {}

    predictions = []
    game_times = {}
    game_statuses = {}

    for _, game in games_df.iterrows():
        pred = predict_game(
            home_team_id=game['home_team_id'],
            away_team_id=game['away_team_id'],
            home_elo=game.get('home_elo'),
            away_elo=game.get('away_elo'),
            game_id=game['game_id'],
            game_date=date_str,
            apply_injuries=apply_injuries,
            home_offense_elo=game.get('home_offense_elo'),
            home_defense_elo=game.get('home_defense_elo'),
            away_offense_elo=game.get('away_offense_elo'),
            away_defense_elo=game.get('away_defense_elo'),
        )
        if pred:
            predictions.append(pred)
            game_status = game.get('status', 'scheduled')
            game_statuses[game['game_id']] = game_status

            game_time_et = game.get('game_time')
            if game_status == 'in_progress':
                game_times[game['game_id']] = 'In Progress'
            elif game_status == 'final':
                game_times[game['game_id']] = 'Final'
            elif game_time_et:
                game_times[game['game_id']] = convert_et_to_ct(game_time_et)
            else:
                game_times[game['game_id']] = None

    return games_df, predictions, game_times, game_statuses


games_df, predictions, game_times, game_statuses = load_games_and_predictions(date_str, apply_injuries)

if games_df.empty:
    st.warning(f"No games found for {selected_date.strftime('%B %d, %Y')}.")
    st.info("No NBA games scheduled, or database hasn't been initialized.")
    st.stop()

# Game count
st.markdown(
    f'<div class="section-title">{len(predictions)} Games Found</div>',
    unsafe_allow_html=True,
)

# Injury impact alerts
if apply_injuries and predictions:
    games_with_injury_impact = [
        p for p in predictions
        if p.injuries_applied and (abs(p.home_injury_adjustment) >= 20 or abs(p.away_injury_adjustment) >= 20)
    ]
    if games_with_injury_impact:
        st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Significant Injury Impact</div>', unsafe_allow_html=True)
        for pred in games_with_injury_impact:
            impact_parts = []
            if abs(pred.home_injury_adjustment) >= 20:
                impact_parts.append(f"{pred.home_team}: {pred.home_injury_adjustment:+.0f} Elo")
            if abs(pred.away_injury_adjustment) >= 20:
                impact_parts.append(f"{pred.away_team}: {pred.away_injury_adjustment:+.0f} Elo")
            st.warning(f"**{pred.away_team} @ {pred.home_team}** \u2014 {', '.join(impact_parts)}")

# B2B alerts
if predictions:
    games_with_b2b = [
        p for p in predictions
        if getattr(p, 'rest_applied', False) and (getattr(p, 'home_rest_days', 1) == 0 or getattr(p, 'away_rest_days', 1) == 0)
    ]
    if games_with_b2b:
        st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Back-to-Back Alert</div>', unsafe_allow_html=True)
        for pred in games_with_b2b:
            b2b_parts = []
            if getattr(pred, 'home_rest_days', 1) == 0:
                b2b_parts.append(f"{pred.home_team} on B2B ({getattr(pred, 'home_rest_adjustment', 0):+.0f} Elo)")
            if getattr(pred, 'away_rest_days', 1) == 0:
                b2b_parts.append(f"{pred.away_team} on B2B ({getattr(pred, 'away_rest_adjustment', 0):+.0f} Elo)")
            st.info(f"**{pred.away_team} @ {pred.home_team}** \u2014 {', '.join(b2b_parts)}")

# Fetch odds
odds_df = pd.DataFrame()
if ODDS_API_KEY and ODDS_API_KEY != "your_key_here":
    with st.spinner("Fetching odds\u2026"):
        try:
            odds_df = get_current_odds()
            if not odds_df.empty:
                st.success(f"Loaded odds from {odds_df['sportsbook'].nunique()} sportsbooks")
        except Exception as e:
            st.warning(f"Could not fetch odds: {e}")

# Predictions table
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">All Predictions</div>', unsafe_allow_html=True)

pred_df = predictions_to_dataframe(predictions)
if not pred_df.empty:
    pred_df['game_time'] = pred_df['game_id'].map(game_times)

    base_cols = ['game_time', 'matchup', 'favorite', 'home_win_prob', 'away_win_prob',
                 'spread_display', 'home_fair_odds', 'away_fair_odds']

    display_df = pred_df[base_cols].copy()
    display_df['game_time'] = display_df['game_time'].fillna('\u2014')

    if 'home_rest_days' in pred_df.columns and 'away_rest_days' in pred_df.columns:
        display_df['home_rest'] = pred_df.apply(
            lambda r: f"{r['home_rest_days']}d" + (" B2B" if r['home_rest_days'] == 0 else "") if pd.notna(r.get('home_rest_days')) else "\u2014",
            axis=1,
        )
        display_df['away_rest'] = pred_df.apply(
            lambda r: f"{r['away_rest_days']}d" + (" B2B" if r['away_rest_days'] == 0 else "") if pd.notna(r.get('away_rest_days')) else "\u2014",
            axis=1,
        )

    if 'predicted_total' in pred_df.columns:
        display_df['predicted_total'] = pred_df['predicted_total'].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) and x > 0 else "\u2014"
        )

    display_df['home_win_prob'] = display_df['home_win_prob'].apply(lambda x: f"{x:.1%}")
    display_df['away_win_prob'] = display_df['away_win_prob'].apply(lambda x: f"{x:.1%}")
    display_df['home_fair_odds'] = display_df['home_fair_odds'].apply(lambda x: f"{int(x):+d}")
    display_df['away_fair_odds'] = display_df['away_fair_odds'].apply(lambda x: f"{int(x):+d}")

    column_rename = {
        'game_time': 'Time (CT)',
        'matchup': 'Game',
        'favorite': 'Pick',
        'home_win_prob': 'Home Win%',
        'away_win_prob': 'Away Win%',
        'spread_display': 'Predicted Spread',
        'predicted_total': 'Predicted Total',
        'home_fair_odds': 'Home Fair Odds',
        'away_fair_odds': 'Away Fair Odds',
        'home_rest': 'Home Rest',
        'away_rest': 'Away Rest',
    }

    st.dataframe(
        display_df.rename(columns=column_rename),
        use_container_width=True,
        hide_index=True,
    )

# Game detail expanders
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Game Breakdowns</div>', unsafe_allow_html=True)

for pred in predictions:
    injury_flag = ""
    if pred.injuries_applied:
        total_impact = abs(pred.home_injury_adjustment) + abs(pred.away_injury_adjustment)
        if total_impact >= 40:
            injury_flag = " \u2014 Major Injuries"
        elif total_impact >= 20:
            injury_flag = " \u2014 Injuries"

    rest_flag = ""
    if getattr(pred, 'rest_applied', False):
        if getattr(pred, 'home_rest_days', 1) == 0 or getattr(pred, 'away_rest_days', 1) == 0:
            rest_flag = " (B2B)"

    game_time_ct = game_times.get(pred.game_id)
    time_display = f" \u2014 {game_time_ct}" if game_time_ct else ""

    with st.expander(f"{pred.away_team} @ {pred.home_team}{time_display}{injury_flag}{rest_flag}"):
        st.caption(f"Game ID: `{pred.game_id}`")
        col1, col2, col3 = st.columns(3)

        with col1:
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
            st.write(f"Fair Odds: {pred.home_implied_odds:+d}")

        with col2:
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
            st.write(f"Fair Odds: {pred.away_implied_odds:+d}")

        with col3:
            st.markdown("**Prediction**")
            if pred.predicted_spread > 0:
                spread_str = f"{pred.home_team} by {pred.predicted_spread:.1f}"
            else:
                spread_str = f"{pred.away_team} by {abs(pred.predicted_spread):.1f}"
            st.write(f"Spread: {spread_str}")

            if getattr(pred, 'od_elo_applied', False) and getattr(pred, 'predicted_total', 0):
                st.write(f"Predicted Total: {pred.predicted_total:.1f}")

            if not odds_df.empty:
                game_odds = odds_df[
                    (odds_df["home_team"] == pred.home_team) &
                    (odds_df["away_team"] == pred.away_team)
                ]
                if not game_odds.empty:
                    st.markdown("**Sportsbook Odds:**")
                    for _, odds_row in game_odds.iterrows():
                        book = odds_row.get("sportsbook", "")
                        home_ml = odds_row.get("home_ml")
                        away_ml = odds_row.get("away_ml")
                        if pd.notna(home_ml) and pd.notna(away_ml):
                            st.caption(f"{book}: {pred.home_team} {int(home_ml):+d} / {pred.away_team} {int(away_ml):+d}")

        if pred.injuries_applied and (pred.home_injuries or pred.away_injuries):
            st.markdown("---")
            st.markdown("**Injury Report**")
            inj_col1, inj_col2 = st.columns(2)

            with inj_col1:
                if pred.home_injuries:
                    st.markdown(f"*{pred.home_team}:*")
                    for inj in pred.home_injuries:
                        if abs(inj.get('elo_impact', 0)) >= 5:
                            status = inj.get('status', 'Out')
                            impact = inj.get('elo_impact', 0)
                            reason = inj.get('reason', '')
                            reason_str = f" \u2014 {reason}" if reason else ""
                            st.caption(f"* {inj['player_name']} ({status}): {impact:+.0f} Elo{reason_str}")
                else:
                    st.caption(f"{pred.home_team}: No significant injuries")

            with inj_col2:
                if pred.away_injuries:
                    st.markdown(f"*{pred.away_team}:*")
                    for inj in pred.away_injuries:
                        if abs(inj.get('elo_impact', 0)) >= 5:
                            status = inj.get('status', 'Out')
                            impact = inj.get('elo_impact', 0)
                            reason = inj.get('reason', '')
                            reason_str = f" \u2014 {reason}" if reason else ""
                            st.caption(f"* {inj['player_name']} ({status}): {impact:+.0f} Elo{reason_str}")
                else:
                    st.caption(f"{pred.away_team}: No significant injuries")

st.markdown("---")
st.caption("Live scores update automatically every 60 seconds via ESPN.")
