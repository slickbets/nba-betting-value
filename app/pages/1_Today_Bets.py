"""Today's Value Bets page."""

import streamlit as st
from datetime import datetime
import pandas as pd
import re
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def convert_et_to_ct(time_str: str) -> str:
    """Convert Eastern Time string to Central Time.

    Args:
        time_str: Time string like "7:00 pm ET"

    Returns:
        Time string like "6:00 PM CT"
    """
    if not time_str or 'ET' not in time_str:
        return time_str

    # Parse the time (e.g., "7:00 pm ET")
    match = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)\s*ET', time_str.strip(), re.IGNORECASE)
    if not match:
        return time_str

    hour = int(match.group(1))
    minute = match.group(2)
    period = match.group(3).upper()

    # Convert to 24-hour for easier math
    if period == 'PM' and hour != 12:
        hour += 12
    elif period == 'AM' and hour == 12:
        hour = 0

    # Subtract 1 hour for CT
    hour -= 1
    if hour < 0:
        hour += 24

    # Convert back to 12-hour format
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

from config import MIN_EDGE_PERCENT, ODDS_API_KEY, CURRENT_SEASON, now_ct
from src.data.database import get_games_by_date, init_database, upsert_game
from src.data.nba_fetcher import fetch_games_by_date, process_scoreboard_for_db, fetch_scoreboard_espn
from src.utils.update_status import get_last_run_info
from src.data.odds_fetcher import get_current_odds, get_odds_for_game
from src.models.predictor import predict_game, predictions_to_dataframe, clear_injuries_cache
from src.betting.value_finder import (
    find_value_bets_for_game,
    value_bets_to_dataframe,
    filter_best_odds,
    get_value_summary,
)
from src.betting.odds_converter import format_american_odds, format_probability

st.set_page_config(page_title="Today's Bets", page_icon="💰", layout="wide")

st.title("💰 Today's Value Bets")
st.markdown("Find betting opportunities where our model sees edge over the sportsbooks.")

# Daily update status indicator
last_run = get_last_run_info()
if last_run['ran_today']:
    if last_run['last_run_time']:
        st.success(f"✅ Model updated today at {last_run['last_run_time']}")
    else:
        st.success(f"✅ Model updated today")
elif last_run['last_run_date']:
    st.warning(f"⚠️ Model last updated: {last_run['last_run_date']} — Run `daily_update.py` for fresh predictions")
else:
    st.error("❌ Daily update has never run — Run `python scripts/daily_update.py` to initialize")

# Get minimum edge from session state or use default
min_edge = st.session_state.get('min_edge', MIN_EDGE_PERCENT)

# Date selector and injury toggle
col1, col2, col3 = st.columns([2, 2, 2])
with col1:
    selected_date = st.date_input(
        "Select Date",
        value=now_ct().date(),
        help="Choose a date to view games and predictions"
    )
    date_str = selected_date.strftime("%Y-%m-%d")

with col2:
    st.markdown(f"**Minimum Edge Threshold:** {min_edge}%")
    st.caption("Adjust in sidebar on main page")

with col3:
    apply_injuries = st.checkbox(
        "Apply Injury Adjustments",
        value=True,
        help="Adjust team Elo ratings based on injured players"
    )

col4, col5 = st.columns([2, 4])
with col4:
    hide_started_games = st.checkbox(
        "Hide Started Games",
        value=True,
        help="Hide games that are in progress or finished from Value Bets"
    )

st.markdown("---")

# Initialize database if needed
try:
    init_database()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

# Fetch games for the selected date
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_games_and_predictions(date_str: str, apply_injuries: bool = True):
    """Load games and generate predictions with optional injury adjustments."""
    games_df = get_games_by_date(date_str)

    if games_df.empty:
        return pd.DataFrame(), [], {}, {}

    predictions = []
    game_times = {}  # Map game_id to game_time in CT
    game_statuses = {}  # Map game_id to status

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
            # Store game status
            game_status = game.get('status', 'scheduled')
            game_statuses[game['game_id']] = game_status

            # Store game time display (prioritize status over start time)
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
    st.info("""
    **Possible reasons:**
    - No NBA games scheduled for this date
    - Database hasn't been initialized (run `python scripts/init_db.py`)
    - Historical data hasn't been loaded (run `python scripts/backfill_history.py`)
    """)
    st.stop()

# Display game count
st.markdown(f"### {len(predictions)} Games Found")

# Injury impact summary
if apply_injuries and predictions:
    games_with_injury_impact = [
        p for p in predictions
        if p.injuries_applied and (abs(p.home_injury_adjustment) >= 20 or abs(p.away_injury_adjustment) >= 20)
    ]

    if games_with_injury_impact:
        st.markdown("#### 🏥 Significant Injury Impact")
        for pred in games_with_injury_impact:
            impact_parts = []
            if abs(pred.home_injury_adjustment) >= 20:
                impact_parts.append(f"{pred.home_team}: {pred.home_injury_adjustment:+.0f} Elo")
            if abs(pred.away_injury_adjustment) >= 20:
                impact_parts.append(f"{pred.away_team}: {pred.away_injury_adjustment:+.0f} Elo")
            st.warning(f"**{pred.away_team} @ {pred.home_team}** - {', '.join(impact_parts)}")

# B2B / rest impact summary
if predictions:
    games_with_b2b = [
        p for p in predictions
        if getattr(p, 'rest_applied', False) and (getattr(p, 'home_rest_days', 1) == 0 or getattr(p, 'away_rest_days', 1) == 0)
    ]

    if games_with_b2b:
        st.markdown("#### ⚠️ Back-to-Back Alert")
        for pred in games_with_b2b:
            b2b_parts = []
            if getattr(pred, 'home_rest_days', 1) == 0:
                b2b_parts.append(f"{pred.home_team} on B2B ({getattr(pred, 'home_rest_adjustment', 0):+.0f} Elo)")
            if getattr(pred, 'away_rest_days', 1) == 0:
                b2b_parts.append(f"{pred.away_team} on B2B ({getattr(pred, 'away_rest_adjustment', 0):+.0f} Elo)")
            st.info(f"**{pred.away_team} @ {pred.home_team}** - {', '.join(b2b_parts)}")

# Fetch odds
odds_df = pd.DataFrame()
if ODDS_API_KEY and ODDS_API_KEY != "your_key_here":
    with st.spinner("Fetching current odds..."):
        try:
            odds_df = get_current_odds()
            if not odds_df.empty:
                st.success(f"Loaded odds from {odds_df['sportsbook'].nunique()} sportsbooks")
        except Exception as e:
            st.warning(f"Could not fetch odds: {e}")
else:
    st.info("💡 Configure ODDS_API_KEY in .env to see live odds and value bets")

# Find value bets
all_value_bets = []
for pred in predictions:
    if not odds_df.empty:
        game_odds = odds_df[
            (odds_df["home_team"] == pred.home_team) &
            (odds_df["away_team"] == pred.away_team)
        ]
        bets = find_value_bets_for_game(pred, game_odds, min_edge)
        all_value_bets.extend(bets)

# Value bets summary
if all_value_bets:
    best_bets = filter_best_odds(all_value_bets)

    # Filter out started games if checkbox is checked
    if hide_started_games:
        best_bets = [
            bet for bet in best_bets
            if game_statuses.get(bet.game_id) == 'scheduled'
        ]

    summary = get_value_summary(best_bets)

    st.markdown("### 🎯 Value Bets Found")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Value Bets", summary['total_bets'])
    with col2:
        st.metric("Avg Edge", f"{summary['avg_edge']:.1f}%")
    with col3:
        st.metric("Avg EV/100", f"${summary['avg_ev']:.2f}")
    with col4:
        st.metric("High Confidence", summary['high_confidence'])

    st.markdown("---")

    # Display value bets table
    bets_df = value_bets_to_dataframe(best_bets)

    if not bets_df.empty:
        # Add game time to value bets
        bets_df['game_time'] = bets_df['game_id'].map(game_times).fillna('-')

        display_cols = [
            'game_time', 'matchup', 'team', 'odds', 'sportsbook',
            'model_prob_display', 'implied_prob_display',
            'edge_display', 'ev_display', 'confidence'
        ]

        st.dataframe(
            bets_df[display_cols].rename(columns={
                'game_time': 'Time (CT)',
                'matchup': 'Game',
                'team': 'Pick',
                'odds': 'Odds',
                'sportsbook': 'Book',
                'model_prob_display': 'Model Prob',
                'implied_prob_display': 'Implied Prob',
                'edge_display': 'Edge',
                'ev_display': 'EV/$100',
                'confidence': 'Confidence',
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Detailed view for each value bet
        st.markdown("### 📋 Bet Details")

        for bet in best_bets:
            with st.expander(f"{bet.matchup} - {bet.team} ({bet.confidence} Confidence)"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown("**Bet Details**")
                    st.write(f"Team: **{bet.team}**")
                    st.write(f"Type: {bet.bet_type}")
                    st.write(f"Odds: {format_american_odds(bet.odds)}")
                    st.write(f"Book: {bet.sportsbook}")

                with col2:
                    st.markdown("**Probabilities**")
                    st.write(f"Model: {format_probability(bet.model_prob)}")
                    st.write(f"Implied: {format_probability(bet.implied_prob)}")
                    st.write(f"Edge: **{bet.edge:.1f}%**")

                with col3:
                    st.markdown("**Expected Value**")
                    st.write(f"EV per $100: **${bet.expected_value:.2f}**")
                    st.write(f"Kelly: {bet.kelly_fraction:.1%}")

                    if bet.kelly_fraction > 0:
                        kelly_bet = bet.kelly_fraction * 100  # As % of bankroll
                        half_kelly = kelly_bet / 2
                        st.caption(f"Suggested bet: {half_kelly:.1f}% of bankroll (half Kelly)")

else:
    if odds_df.empty:
        st.info("Configure odds API to find value bets")
    else:
        st.info(f"No value bets found with edge > {min_edge}% for today's games")

st.markdown("---")

# Model Win/Loss Predictions
st.markdown("### 🏆 Model Picks (Win/Loss)")
st.caption("Which team the model predicts to win each game, regardless of betting value.")

if predictions:
    picks_data = []
    for pred in predictions:
        game_time = game_times.get(pred.game_id, '-')

        # Determine predicted winner
        if pred.home_win_prob > 0.5:
            predicted_winner = pred.home_team
            win_prob = pred.home_win_prob
            loser = pred.away_team
            lose_prob = pred.away_win_prob
        else:
            predicted_winner = pred.away_team
            win_prob = pred.away_win_prob
            loser = pred.home_team
            lose_prob = pred.home_win_prob

        # Confidence indicator
        if win_prob >= 0.65:
            confidence = "High"
        elif win_prob >= 0.55:
            confidence = "Medium"
        else:
            confidence = "Low"

        picks_data.append({
            'Time': game_time if game_time else '-',
            'Matchup': f"{pred.away_team} @ {pred.home_team}",
            'Pick': f"✅ {predicted_winner}",
            'Win Prob': f"{win_prob:.1%}",
            'Confidence': confidence,
            'Spread': f"{pred.home_team} {pred.predicted_spread:+.1f}" if pred.predicted_spread < 0 else f"{pred.away_team} {-pred.predicted_spread:+.1f}",
        })

    picks_df = pd.DataFrame(picks_data)
    st.dataframe(picks_df, use_container_width=True, hide_index=True)
else:
    st.info("No games to display")

st.markdown("---")

# All games predictions table
st.markdown("### 📊 All Game Predictions")

pred_df = predictions_to_dataframe(predictions)
if not pred_df.empty:
    # Add game times to the predictions dataframe
    pred_df['game_time'] = pred_df['game_id'].map(game_times)

    # Build display columns based on injury data availability
    base_cols = ['game_time', 'matchup', 'home_elo', 'away_elo', 'home_win_prob', 'away_win_prob',
                 'spread_display', 'home_fair_odds', 'away_fair_odds']

    display_df = pred_df[base_cols].copy()
    display_df['game_time'] = display_df['game_time'].fillna('-')

    # Add injury adjustment columns if applicable
    if apply_injuries and 'home_injury_adj' in pred_df.columns:
        display_df['home_inj'] = pred_df['home_injury_adj'].apply(
            lambda x: f"{x:+.0f}" if x != 0 else "-"
        )
        display_df['away_inj'] = pred_df['away_injury_adj'].apply(
            lambda x: f"{x:+.0f}" if x != 0 else "-"
        )

    # Add rest days columns if available
    if 'home_rest_days' in pred_df.columns and 'away_rest_days' in pred_df.columns:
        display_df['home_rest'] = pred_df.apply(
            lambda r: f"{r['home_rest_days']}d" + (" ⚠️" if r['home_rest_days'] == 0 else "") if pd.notna(r.get('home_rest_days')) else "-",
            axis=1
        )
        display_df['away_rest'] = pred_df.apply(
            lambda r: f"{r['away_rest_days']}d" + (" ⚠️" if r['away_rest_days'] == 0 else "") if pd.notna(r.get('away_rest_days')) else "-",
            axis=1
        )

    # Add predicted total if O/D Elo is available
    if 'predicted_total' in pred_df.columns:
        display_df['predicted_total'] = pred_df['predicted_total'].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) and x > 0 else "-"
        )

    display_df['home_win_prob'] = display_df['home_win_prob'].apply(lambda x: f"{x:.1%}")
    display_df['away_win_prob'] = display_df['away_win_prob'].apply(lambda x: f"{x:.1%}")

    column_rename = {
        'game_time': 'Time (CT)',
        'matchup': 'Game',
        'home_elo': 'Home Elo',
        'away_elo': 'Away Elo',
        'home_win_prob': 'Home Win%',
        'away_win_prob': 'Away Win%',
        'spread_display': 'Spread',
        'predicted_total': 'Total',
        'home_fair_odds': 'Home Fair Odds',
        'away_fair_odds': 'Away Fair Odds',
        'home_inj': 'Home Inj',
        'away_inj': 'Away Inj',
        'home_rest': 'Home Rest',
        'away_rest': 'Away Rest',
    }

    st.dataframe(
        display_df.rename(columns=column_rename),
        use_container_width=True,
        hide_index=True,
    )

# Game details expanders
st.markdown("### 🏀 Game Details")

for pred in predictions:
    # Add injury indicator to expander title
    injury_flag = ""
    if pred.injuries_applied:
        total_impact = abs(pred.home_injury_adjustment) + abs(pred.away_injury_adjustment)
        if total_impact >= 40:
            injury_flag = " 🏥"
        elif total_impact >= 20:
            injury_flag = " 🩹"

    # Add B2B indicator to expander title
    rest_flag = ""
    if getattr(pred, 'rest_applied', False):
        if getattr(pred, 'home_rest_days', 1) == 0 or getattr(pred, 'away_rest_days', 1) == 0:
            rest_flag = " ⚠️B2B"

    # Get game time for this game
    game_time_ct = game_times.get(pred.game_id)
    time_display = f" - {game_time_ct}" if game_time_ct else ""

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
            # Show O/D Elo if available
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
            # Show O/D Elo if available
            if getattr(pred, 'od_elo_applied', False):
                away_o = getattr(pred, 'away_offense_elo', 0)
                away_d = getattr(pred, 'away_defense_elo', 0)
                if away_o and away_d:
                    st.caption(f"O-Elo: {away_o:.0f} | D-Elo: {away_d:.0f}")
            st.write(f"Win Prob: {pred.away_win_prob:.1%}")
            st.write(f"Fair Odds: {pred.away_implied_odds:+d}")

        with col3:
            st.markdown("**Prediction**")
            if pred.predicted_spread < 0:
                spread_str = f"{pred.home_team} by {abs(pred.predicted_spread):.1f}"
            else:
                spread_str = f"{pred.away_team} by {pred.predicted_spread:.1f}"
            st.write(f"Spread: {spread_str}")

            # Show predicted total if O/D Elo is applied
            if getattr(pred, 'od_elo_applied', False) and getattr(pred, 'predicted_total', 0):
                st.write(f"Predicted Total: {pred.predicted_total:.1f}")

            # Show odds for this game if available
            if not odds_df.empty:
                game_odds = odds_df[
                    (odds_df["home_team"] == pred.home_team) &
                    (odds_df["away_team"] == pred.away_team)
                ]
                if not game_odds.empty:
                    st.markdown("**Available Odds:**")
                    for _, odds_row in game_odds.iterrows():
                        book = odds_row.get("sportsbook", "")
                        home_ml = odds_row.get("home_ml")
                        away_ml = odds_row.get("away_ml")
                        if pd.notna(home_ml) and pd.notna(away_ml):
                            st.caption(f"{book}: {pred.home_team} {int(home_ml):+d} / {pred.away_team} {int(away_ml):+d}")

        # Show injury details
        if pred.injuries_applied and (pred.home_injuries or pred.away_injuries):
            st.markdown("---")
            st.markdown("**🏥 Injury Report**")

            inj_col1, inj_col2 = st.columns(2)

            with inj_col1:
                if pred.home_injuries:
                    st.markdown(f"*{pred.home_team}:*")
                    for inj in pred.home_injuries:
                        if abs(inj.get('elo_impact', 0)) >= 5:  # Only show significant impacts
                            status = inj.get('status', 'Out')
                            impact = inj.get('elo_impact', 0)
                            reason = inj.get('reason', '')
                            reason_str = f" - {reason}" if reason else ""
                            st.caption(f"• {inj['player_name']} ({status}): {impact:+.0f} Elo{reason_str}")
                else:
                    st.caption(f"{pred.home_team}: No significant injuries")

            with inj_col2:
                if pred.away_injuries:
                    st.markdown(f"*{pred.away_team}:*")
                    for inj in pred.away_injuries:
                        if abs(inj.get('elo_impact', 0)) >= 5:  # Only show significant impacts
                            status = inj.get('status', 'Out')
                            impact = inj.get('elo_impact', 0)
                            reason = inj.get('reason', '')
                            reason_str = f" - {reason}" if reason else ""
                            st.caption(f"• {inj['player_name']} ({status}): {impact:+.0f} Elo{reason_str}")
                else:
                    st.caption(f"{pred.away_team}: No significant injuries")

# Refresh button
st.markdown("---")
if st.button("🔄 Refresh Data"):
    with st.spinner("Fetching latest game data..."):
        updated_count = 0
        source = None

        try:
            # Try NBA API first (works locally, may be blocked on cloud servers)
            fresh_games = fetch_games_by_date(date_str)
            if not fresh_games.empty:
                processed = process_scoreboard_for_db(fresh_games, CURRENT_SEASON)
                for game in processed:
                    upsert_game(**game)
                    updated_count += 1
                source = "NBA API"
        except Exception:
            pass  # Fall through to ESPN fallback

        # Fallback to ESPN if NBA API returned nothing
        if updated_count == 0:
            try:
                espn_games = fetch_scoreboard_espn(date_str)
                if espn_games:
                    # Get existing games from DB to match by team abbreviation
                    existing_games = get_games_by_date(date_str)
                    if not existing_games.empty:
                        for espn_game in espn_games:
                            # Find matching DB game by team abbreviations
                            match = existing_games[
                                (existing_games['home_abbr'] == espn_game['home_abbr']) &
                                (existing_games['away_abbr'] == espn_game['away_abbr'])
                            ]
                            if not match.empty:
                                game_row = match.iloc[0]
                                upsert_game(
                                    game_id=game_row['game_id'],
                                    season=game_row['season'],
                                    game_date=date_str,
                                    game_time=espn_game.get('game_time'),
                                    home_team_id=int(game_row['home_team_id']),
                                    away_team_id=int(game_row['away_team_id']),
                                    home_score=espn_game['home_score'],
                                    away_score=espn_game['away_score'],
                                    status=espn_game['status'],
                                )
                                updated_count += 1
                    source = "ESPN"
                else:
                    st.warning("⚠️ Could not fetch game data from either NBA API or ESPN.")
            except Exception as e:
                st.error(f"❌ Error fetching data: {e}")

        if updated_count > 0:
            st.success(f"✅ Updated {updated_count} games from {source}")
            st.cache_data.clear()
            clear_injuries_cache()
            time.sleep(1)  # Let user see the message
            st.rerun()
