"""Model Accuracy tracking page."""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import now_ct
from src.data.database import init_database, get_connection
from app.shared import render_sidebar, confidence_badge, result_badge

# Chart constants - warm palette
PLOTLY_TEMPLATE = "plotly_dark"
CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(224,220,213,0.06)"
ACCENT = "#C9A84C"
POSITIVE = "#8BA888"
NEGATIVE = "#B87366"
TEXT_MUTED = "#7A7770"

st.set_page_config(page_title="Model Accuracy | Slick Bets", page_icon=str(Path(__file__).parent.parent.parent / "assets" / "favicon.png"), layout="wide")
render_sidebar()

st.markdown('<div class="page-header">Model Accuracy</div>', unsafe_allow_html=True)
st.markdown('<div class="page-desc">Track how well the model predicts game outcomes over time.</div>', unsafe_allow_html=True)

init_database()


def get_completed_games_with_predictions(start_date: str, end_date: str) -> pd.DataFrame:
    """Get all completed games that have predictions."""
    query = """
        SELECT
            g.game_id,
            g.game_date,
            g.home_team_id,
            g.away_team_id,
            g.home_score,
            g.away_score,
            g.predicted_home_win_prob,
            g.predicted_spread,
            g.predicted_total,
            g.home_elo_pre,
            g.away_elo_pre,
            ht.abbreviation as home_team,
            at.abbreviation as away_team
        FROM games g
        JOIN teams ht ON g.home_team_id = ht.team_id
        JOIN teams at ON g.away_team_id = at.team_id
        WHERE g.status = 'final'
        AND g.home_score IS NOT NULL
        AND g.away_score IS NOT NULL
        AND g.predicted_home_win_prob IS NOT NULL
        AND g.game_date BETWEEN ? AND ?
        ORDER BY g.game_date DESC
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    return df


def calculate_accuracy_metrics(df: pd.DataFrame) -> dict:
    """Calculate model accuracy metrics."""
    if df.empty:
        return {}

    df = df.copy()
    df['home_won'] = df['home_score'] > df['away_score']
    df['predicted_home_win'] = df['predicted_home_win_prob'] > 0.5
    df['correct_pick'] = df['home_won'] == df['predicted_home_win']
    df['actual_margin'] = df['home_score'] - df['away_score']
    df['spread_error'] = abs(df['predicted_spread'] - df['actual_margin'])
    df['confidence'] = df['predicted_home_win_prob'].apply(lambda x: max(x, 1 - x))
    df['actual_total'] = df['home_score'] + df['away_score']
    df['has_predicted_total'] = df['predicted_total'].notna() & (df['predicted_total'] > 0)
    df['total_error'] = abs(df['predicted_total'] - df['actual_total']).where(df['has_predicted_total'])

    total_games = len(df)
    correct_picks = df['correct_pick'].sum()
    pick_accuracy = correct_picks / total_games * 100 if total_games > 0 else 0
    avg_spread_error = df['spread_error'].mean()
    median_spread_error = df['spread_error'].median()

    total_df = df[df['has_predicted_total']]
    total_games_with_total = len(total_df)
    avg_total_error = total_df['total_error'].mean() if total_games_with_total > 0 else None
    median_total_error = total_df['total_error'].median() if total_games_with_total > 0 else None

    high_conf = df[df['confidence'] >= 0.65]
    med_conf = df[(df['confidence'] >= 0.55) & (df['confidence'] < 0.65)]
    low_conf = df[df['confidence'] < 0.55]

    return {
        'total_games': total_games,
        'correct_picks': correct_picks,
        'pick_accuracy': pick_accuracy,
        'avg_spread_error': avg_spread_error,
        'median_spread_error': median_spread_error,
        'high_conf_games': len(high_conf),
        'high_conf_accuracy': high_conf['correct_pick'].mean() * 100 if len(high_conf) > 0 else 0,
        'med_conf_games': len(med_conf),
        'med_conf_accuracy': med_conf['correct_pick'].mean() * 100 if len(med_conf) > 0 else 0,
        'low_conf_games': len(low_conf),
        'low_conf_accuracy': low_conf['correct_pick'].mean() * 100 if len(low_conf) > 0 else 0,
        'total_games_with_total': total_games_with_total,
        'avg_total_error': avg_total_error,
        'median_total_error': median_total_error,
        'df': df,
    }


# Date range selector
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    preset = st.selectbox(
        "Quick Select",
        ["Last 7 Days", "Last 14 Days", "Last 30 Days", "Last 60 Days", "This Season", "Custom"],
    )

with col2:
    if preset == "Last 7 Days":
        end_date = now_ct().date()
        start_date = end_date - timedelta(days=7)
    elif preset == "Last 14 Days":
        end_date = now_ct().date()
        start_date = end_date - timedelta(days=14)
    elif preset == "Last 30 Days":
        end_date = now_ct().date()
        start_date = end_date - timedelta(days=30)
    elif preset == "Last 60 Days":
        end_date = now_ct().date()
        start_date = end_date - timedelta(days=60)
    elif preset == "This Season":
        end_date = now_ct().date()
        start_date = datetime(2025, 10, 1).date()
    else:
        start_date = st.date_input("Start Date", value=now_ct().date() - timedelta(days=30))
        end_date = st.date_input("End Date", value=now_ct().date())

with col3:
    st.markdown(
        f'<div style="margin-top:1.6rem;">'
        f'<span class="detail-label">Analyzing</span><br>'
        f'<span class="detail-value">{start_date.strftime("%b %d, %Y")} \u2014 {end_date.strftime("%b %d, %Y")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# Load data
games_df = get_completed_games_with_predictions(
    start_date.strftime("%Y-%m-%d"),
    end_date.strftime("%Y-%m-%d"),
)

if games_df.empty:
    st.warning("No completed games with predictions found for this period.")
    st.info("Predictions are stored when you run daily_update.py before games start.")
    st.stop()

metrics = calculate_accuracy_metrics(games_df)
df = metrics['df']

# Summary stat cards
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Overall Accuracy</div>', unsafe_allow_html=True)

accuracy_color = POSITIVE if metrics['pick_accuracy'] >= 60 else ACCENT if metrics['pick_accuracy'] >= 55 else NEGATIVE

cols = st.columns(5)
stat_data = [
    (str(metrics['total_games']), 'Games Analyzed', None),
    (f"{metrics['correct_picks']}/{metrics['total_games']}", 'Correct Picks', None),
    (f"{metrics['pick_accuracy']:.1f}%", 'Pick Accuracy', accuracy_color),
    (f"{metrics['avg_spread_error']:.1f}", 'Avg Spread Error', None),
    (f"{metrics['median_spread_error']:.1f}", 'Median Spread Error', None),
]

for col, (value, label, color) in zip(cols, stat_data):
    with col:
        color_style = f' style="color:{color};"' if color else ''
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-card-value"{color_style}>{value}</div>'
            f'<div class="stat-card-label">{label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# Accuracy by confidence
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Accuracy by Confidence</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    conf_rows = [
        ("High (65%+)", metrics['high_conf_games'], metrics['high_conf_accuracy'], "High"),
        ("Medium (55\u201365%)", metrics['med_conf_games'], metrics['med_conf_accuracy'], "Medium"),
        ("Low (<55%)", metrics['low_conf_games'], metrics['low_conf_accuracy'], "Low"),
    ]
    for label, games, acc, level in conf_rows:
        st.markdown(
            f'<div class="conf-row">'
            f'<div>'
            f'<span class="conf-row-label">{label}</span>'
            f'<span class="conf-row-count">{games} games</span>'
            f'</div>'
            f'<div style="display:flex; align-items:center; gap:0.6rem;">'
            f'<span class="conf-row-value">{acc:.1f}%</span>'
            f'{confidence_badge(level)}'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.caption("High confidence picks should have higher accuracy if the model is well-calibrated.")

with col2:
    conf_data = pd.DataFrame({
        'Confidence': ['High (65%+)', 'Medium (55\u201365%)', 'Low (<55%)'],
        'Games': [metrics['high_conf_games'], metrics['med_conf_games'], metrics['low_conf_games']],
        'Accuracy': [metrics['high_conf_accuracy'], metrics['med_conf_accuracy'], metrics['low_conf_accuracy']],
    })

    fig = px.bar(
        conf_data,
        x='Confidence',
        y='Accuracy',
        color='Confidence',
        color_discrete_map={
            'High (65%+)': ACCENT,
            'Medium (55\u201365%)': TEXT_MUTED,
            'Low (<55%)': '#4A4843',
        },
        title='Accuracy by Confidence',
    )
    fig.add_hline(y=50, line_dash="dash", line_color=TEXT_MUTED, annotation_text="50% (coin flip)")
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=300,
        showlegend=False,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        yaxis=dict(gridcolor=GRID_COLOR),
        font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
        title_font=dict(family="DM Serif Display, serif", size=14),
    )
    st.plotly_chart(fig, use_container_width=True)

# Accuracy over time
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Accuracy Over Time</div>', unsafe_allow_html=True)

df['game_date'] = pd.to_datetime(df['game_date'])
df['week'] = df['game_date'].dt.to_period('W').astype(str)

weekly = df.groupby('week').agg({
    'correct_pick': ['sum', 'count'],
    'spread_error': 'mean',
}).reset_index()
weekly.columns = ['Week', 'Correct', 'Total', 'Avg Spread Error']
weekly['Accuracy'] = weekly['Correct'] / weekly['Total'] * 100

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=weekly['Week'],
    y=weekly['Accuracy'],
    mode='lines+markers',
    name='Weekly Accuracy',
    line=dict(color=ACCENT, width=2),
    marker=dict(size=6, color=ACCENT),
))
fig.add_hline(y=50, line_dash="dash", line_color=TEXT_MUTED, opacity=0.5)
fig.add_hline(y=metrics['pick_accuracy'], line_dash="dot", line_color=ACCENT,
              annotation_text=f"Avg: {metrics['pick_accuracy']:.1f}%")
fig.update_layout(
    xaxis_title="Week",
    yaxis_title="Accuracy %",
    template=PLOTLY_TEMPLATE,
    height=400,
    yaxis=dict(range=[0, 100], gridcolor=GRID_COLOR),
    xaxis=dict(gridcolor=GRID_COLOR),
    paper_bgcolor=CHART_BG,
    plot_bgcolor=CHART_BG,
    font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
)
st.plotly_chart(fig, use_container_width=True)

# Accuracy by team
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Accuracy by Team</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown("**When Picking Team to Win**")
    home_picks = df[df['predicted_home_win'] == True].copy()
    home_picks['team_picked'] = home_picks['home_team']
    home_picks['picked_correctly'] = home_picks['correct_pick']

    away_picks = df[df['predicted_home_win'] == False].copy()
    away_picks['team_picked'] = away_picks['away_team']
    away_picks['picked_correctly'] = away_picks['correct_pick']

    all_picks = pd.concat([home_picks, away_picks])
    team_accuracy = all_picks.groupby('team_picked').agg({
        'picked_correctly': ['sum', 'count'],
    }).reset_index()
    team_accuracy.columns = ['Team', 'Correct', 'Total']
    team_accuracy['Accuracy'] = (team_accuracy['Correct'] / team_accuracy['Total'] * 100).round(1)
    team_accuracy = team_accuracy.sort_values('Accuracy', ascending=False)

    min_games = 3 if len(team_accuracy) > 10 else 1
    filtered = team_accuracy[team_accuracy['Total'] >= min_games].head(10)
    if filtered.empty:
        st.caption("Not enough data yet")
    else:
        st.dataframe(filtered, use_container_width=True, hide_index=True)

with col2:
    st.markdown("**When Picking Team to Lose**")
    against_home = df[df['predicted_home_win'] == False].copy()
    against_home['team_faded'] = against_home['home_team']
    against_home['fade_correct'] = against_home['correct_pick']

    against_away = df[df['predicted_home_win'] == True].copy()
    against_away['team_faded'] = against_away['away_team']
    against_away['fade_correct'] = against_away['correct_pick']

    all_fades = pd.concat([against_home, against_away])
    fade_accuracy = all_fades.groupby('team_faded').agg({
        'fade_correct': ['sum', 'count'],
    }).reset_index()
    fade_accuracy.columns = ['Team', 'Correct', 'Total']
    fade_accuracy['Accuracy'] = (fade_accuracy['Correct'] / fade_accuracy['Total'] * 100).round(1)
    fade_accuracy = fade_accuracy.sort_values('Accuracy', ascending=False)

    min_games = 3 if len(fade_accuracy) > 10 else 1
    filtered = fade_accuracy[fade_accuracy['Total'] >= min_games].head(10)
    if filtered.empty:
        st.caption("Not enough data yet")
    else:
        st.dataframe(filtered, use_container_width=True, hide_index=True)

# Spread error distribution
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Spread Error Distribution</div>', unsafe_allow_html=True)

fig = px.histogram(
    df,
    x='spread_error',
    nbins=20,
    labels={'spread_error': 'Spread Error (points)', 'count': 'Games'},
    color_discrete_sequence=[ACCENT],
)
fig.add_vline(x=metrics['avg_spread_error'], line_dash="dash", line_color=NEGATIVE,
              annotation_text=f"Avg: {metrics['avg_spread_error']:.1f}")
fig.add_vline(x=metrics['median_spread_error'], line_dash="dash", line_color=POSITIVE,
              annotation_text=f"Median: {metrics['median_spread_error']:.1f}")
fig.update_layout(
    template=PLOTLY_TEMPLATE,
    height=350,
    paper_bgcolor=CHART_BG,
    plot_bgcolor=CHART_BG,
    yaxis=dict(gridcolor=GRID_COLOR),
    xaxis=dict(gridcolor=GRID_COLOR),
    font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
)
st.plotly_chart(fig, use_container_width=True)

# Total error distribution
if metrics['total_games_with_total'] and metrics['total_games_with_total'] > 0:
    st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Total (O/U) Error Distribution</div>', unsafe_allow_html=True)

    total_col1, total_col2 = st.columns([1, 2])
    with total_col1:
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-card-value">{metrics["avg_total_error"]:.1f}</div>'
            f'<div class="stat-card-label">Avg Total Error</div>'
            f'<div class="stat-card-detail">{metrics["total_games_with_total"]} games</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-card-value">{metrics["median_total_error"]:.1f}</div>'
            f'<div class="stat-card-label">Median Total Error</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with total_col2:
        total_df = df[df['has_predicted_total']].copy()
        fig_total = px.histogram(
            total_df,
            x='total_error',
            nbins=20,
            labels={'total_error': 'Total Error (points)', 'count': 'Games'},
            color_discrete_sequence=[ACCENT],
        )
        fig_total.add_vline(x=metrics['avg_total_error'], line_dash="dash", line_color=NEGATIVE,
                            annotation_text=f"Avg: {metrics['avg_total_error']:.1f}")
        fig_total.add_vline(x=metrics['median_total_error'], line_dash="dash", line_color=POSITIVE,
                            annotation_text=f"Median: {metrics['median_total_error']:.1f}")
        fig_total.update_layout(
            template=PLOTLY_TEMPLATE,
            height=300,
            paper_bgcolor=CHART_BG,
            plot_bgcolor=CHART_BG,
            yaxis=dict(gridcolor=GRID_COLOR),
            xaxis=dict(gridcolor=GRID_COLOR),
            font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
        )
        st.plotly_chart(fig_total, use_container_width=True)
else:
    st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Total (O/U) Accuracy</div>', unsafe_allow_html=True)
    st.caption("No predicted totals stored yet. Totals will start tracking with the next daily update.")

# Home vs Away
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Home vs Away Picks</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    home_picks_df = df[df['predicted_home_win'] == True]
    away_picks_df = df[df['predicted_home_win'] == False]

    home_away_data = pd.DataFrame({
        'Pick Type': ['Picked Home', 'Picked Away'],
        'Games': [len(home_picks_df), len(away_picks_df)],
        'Correct': [home_picks_df['correct_pick'].sum(), away_picks_df['correct_pick'].sum()],
    })
    home_away_data['Accuracy'] = (home_away_data['Correct'] / home_away_data['Games'] * 100).round(1)
    st.dataframe(home_away_data, use_container_width=True, hide_index=True)

with col2:
    fig = px.pie(
        home_away_data,
        values='Games',
        names='Pick Type',
        color_discrete_sequence=[ACCENT, TEXT_MUTED],
    )
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=280,
        paper_bgcolor=CHART_BG,
        font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
    )
    st.plotly_chart(fig, use_container_width=True)

# Recent predictions
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Recent Predictions vs Results</div>', unsafe_allow_html=True)

recent = df.sort_values('game_date', ascending=False).head(15).copy()
recent['matchup'] = recent['away_team'] + ' @ ' + recent['home_team']
recent['predicted_winner'] = recent.apply(
    lambda x: x['home_team'] if x['predicted_home_win'] else x['away_team'],
    axis=1,
)
recent['actual_winner'] = recent.apply(
    lambda x: x['home_team'] if x['home_won'] else x['away_team'],
    axis=1,
)
recent['outcome'] = recent['correct_pick'].apply(lambda x: 'W' if x else 'L')
recent['pred_spread'] = recent['predicted_spread'].apply(lambda x: f"{x:+.1f}")
recent['actual_margin'] = recent['actual_margin'].apply(lambda x: f"{x:+.0f}")
recent['final_score'] = recent.apply(
    lambda x: f"{int(x['away_score'])}\u2013{int(x['home_score'])}",
    axis=1,
)

display_cols = ['game_date', 'matchup', 'final_score', 'predicted_winner', 'actual_winner', 'outcome', 'pred_spread', 'actual_margin']
display_df = recent[display_cols].copy()
display_df['game_date'] = pd.to_datetime(display_df['game_date']).dt.strftime('%Y-%m-%d')

st.dataframe(
    display_df.rename(columns={
        'game_date': 'Date',
        'matchup': 'Matchup',
        'final_score': 'Score',
        'predicted_winner': 'Predicted',
        'actual_winner': 'Actual',
        'outcome': '',
        'pred_spread': 'Pred Spread',
        'actual_margin': 'Actual Margin',
    }),
    use_container_width=True,
    hide_index=True,
)
