"""Team Ratings page - Elo rankings and history."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests

from src.data.bdl_fetcher import fetch_standings_bdl
from config import CURRENT_SEASON
from src.data.database import (
    init_database,
    get_all_teams,
    get_team_elo_history,
)
from config import ELO_INITIAL_RATING
from app.shared import render_sidebar

# Chart constants - warm palette
PLOTLY_TEMPLATE = "plotly_dark"
CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(224,220,213,0.06)"
ACCENT = "#C9A84C"
POSITIVE = "#8BA888"
NEGATIVE = "#B87366"
TEXT_MUTED = "#7A7770"

st.set_page_config(page_title="Team Ratings | Slick Bets", page_icon=str(Path(__file__).parent.parent.parent / "assets" / "favicon.png"), layout="wide")
render_sidebar()

st.markdown('<div class="page-header">Team Ratings</div>', unsafe_allow_html=True)
st.markdown('<div class="page-desc">Current Elo ratings and historical performance for all NBA teams.</div>', unsafe_allow_html=True)

init_database()

# Load teams
teams_df = get_all_teams()

if teams_df.empty:
    st.warning("No teams found. Run init_db.py to initialize the database.")
    st.stop()

# Fetch W/L records (BDL primary, ESPN fallback)
ESPN_ABBR_MAP = {'GS': 'GSW', 'SA': 'SAS', 'NY': 'NYK', 'NO': 'NOP', 'UTAH': 'UTA', 'WSH': 'WAS'}


@st.cache_data(ttl=3600)
def fetch_records():
    """Fetch current W/L records from BDL, falling back to ESPN."""
    records = fetch_standings_bdl(CURRENT_SEASON)
    if records:
        return records

    # ESPN fallback
    try:
        resp = requests.get(
            'https://site.api.espn.com/apis/v2/sports/basketball/nba/standings',
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        records = {}
        for conf in data.get('children', []):
            for team in conf.get('standings', {}).get('entries', []):
                abbr = team.get('team', {}).get('abbreviation', '')
                abbr = ESPN_ABBR_MAP.get(abbr, abbr)
                stats = {s['name']: s for s in team.get('stats', [])}
                w = int(stats.get('wins', {}).get('value', 0))
                l = int(stats.get('losses', {}).get('value', 0))
                records[abbr] = (w, l)
        return records
    except Exception:
        return {}


espn_records = fetch_records()
if espn_records:
    teams_df['wins'] = teams_df['abbreviation'].map(lambda a: espn_records.get(a, (0, 0))[0])
    teams_df['losses'] = teams_df['abbreviation'].map(lambda a: espn_records.get(a, (0, 0))[1])
    teams_df['record'] = teams_df.apply(lambda r: f"{r['wins']}\u2013{r['losses']}", axis=1)
else:
    teams_df['record'] = '\u2014'

# Add rank and tier
teams_df['rank'] = range(1, len(teams_df) + 1)
teams_df['elo_diff'] = teams_df['current_elo'] - ELO_INITIAL_RATING


def get_tier(elo):
    if elo >= 1600:
        return "Championship"
    elif elo >= 1550:
        return "Contender"
    elif elo >= 1500:
        return "Playoff"
    elif elo >= 1450:
        return "Bubble"
    else:
        return "Rebuilding"


teams_df['tier'] = teams_df['current_elo'].apply(get_tier)

TIER_COLORS = {
    "Championship": ACCENT,
    "Contender": "#B0ADA6",
    "Playoff": POSITIVE,
    "Bubble": TEXT_MUTED,
    "Rebuilding": "#4A4843",
}

TIER_CSS = {
    "Championship": "tier-championship",
    "Contender": "tier-contender",
    "Playoff": "tier-playoff",
    "Bubble": "tier-bubble",
    "Rebuilding": "tier-rebuilding",
}

# Rankings
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Current Elo Rankings</div>', unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])

with col1:
    display_df = teams_df[['rank', 'abbreviation', 'full_name', 'record', 'current_elo', 'elo_diff', 'tier']].copy()
    display_df['current_elo'] = display_df['current_elo'].round(0).astype(int)
    display_df['elo_diff'] = display_df['elo_diff'].apply(lambda x: f"{x:+.0f}")

    st.dataframe(
        display_df.rename(columns={
            'rank': '#',
            'abbreviation': 'Team',
            'full_name': 'Name',
            'record': 'W\u2013L',
            'current_elo': 'Elo',
            'elo_diff': 'vs Avg',
            'tier': 'Tier',
        }),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

with col2:
    st.markdown("**Tier Breakdown**")

    tier_counts = teams_df['tier'].value_counts()
    tier_order = ["Championship", "Contender", "Playoff", "Bubble", "Rebuilding"]

    fig = go.Figure(go.Bar(
        x=[tier_counts.get(t, 0) for t in tier_order],
        y=tier_order,
        orientation='h',
        marker_color=[TIER_COLORS[t] for t in tier_order],
    ))
    fig.update_layout(
        xaxis_title="Teams",
        template=PLOTLY_TEMPLATE,
        height=280,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        yaxis=dict(gridcolor=GRID_COLOR),
        xaxis=dict(gridcolor=GRID_COLOR),
        font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tier legend
    elo_ranges = {"Championship": "1600+", "Contender": "1550\u20131599", "Playoff": "1500\u20131549", "Bubble": "1450\u20131499", "Rebuilding": "<1450"}
    for tier_name in tier_order:
        count = tier_counts.get(tier_name, 0)
        css_class = TIER_CSS[tier_name]
        st.markdown(
            f'<div style="display:flex; justify-content:space-between; align-items:center; padding:0.25rem 0;">'
            f'<span class="tier-label {css_class}">{tier_name}</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace; font-size:0.75rem; color:#7A7770; font-variant-numeric:tabular-nums;">'
            f'{elo_ranges[tier_name]} &middot; {count}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

# Elo distribution
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Elo Distribution</div>', unsafe_allow_html=True)

fig = px.histogram(
    teams_df,
    x='current_elo',
    nbins=15,
    color_discrete_sequence=[ACCENT],
)
fig.add_vline(
    x=ELO_INITIAL_RATING,
    line_dash="dash",
    line_color=NEGATIVE,
    annotation_text="Avg (1500)",
    annotation_position="top right",
)
fig.update_layout(
    xaxis_title="Elo Rating",
    yaxis_title="Teams",
    template=PLOTLY_TEMPLATE,
    height=280,
    paper_bgcolor=CHART_BG,
    plot_bgcolor=CHART_BG,
    yaxis=dict(gridcolor=GRID_COLOR),
    xaxis=dict(gridcolor=GRID_COLOR),
    font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
)
st.plotly_chart(fig, use_container_width=True)

# Team analysis
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Team Analysis</div>', unsafe_allow_html=True)

selected_team = st.selectbox(
    "Select a Team",
    options=teams_df['abbreviation'].tolist(),
    format_func=lambda x: f"{x} \u2014 {teams_df[teams_df['abbreviation']==x]['full_name'].values[0]}",
)

if selected_team:
    team_data = teams_df[teams_df['abbreviation'] == selected_team].iloc[0]

    cols = st.columns(4)
    diff = team_data['current_elo'] - ELO_INITIAL_RATING
    stat_items = [
        (f"{team_data['current_elo']:.0f}", "Current Elo"),
        (f"{diff:+.0f}", "vs Average"),
        (f"#{team_data['rank']}", "Rank"),
        (team_data['tier'], "Tier"),
    ]
    for col, (value, label) in zip(cols, stat_items):
        with col:
            st.markdown(
                f'<div class="stat-card">'
                f'<div class="stat-card-value" style="font-size:1.3rem;">{value}</div>'
                f'<div class="stat-card-label">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("")

    # Elo history
    team_id = team_data['team_id']
    history_df = get_team_elo_history(team_id)

    if not history_df.empty:
        history_df['game_date'] = pd.to_datetime(history_df['game_date'])
        history_df = history_df.sort_values('game_date')

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=history_df['game_date'],
            y=history_df['elo_after'],
            mode='lines',
            name='Elo',
            line=dict(color=ACCENT, width=2),
        ))
        fig.add_hline(
            y=ELO_INITIAL_RATING,
            line_dash="dash",
            line_color=TEXT_MUTED,
            annotation_text="Avg",
        )

        peak_idx = history_df['elo_after'].idxmax()
        low_idx = history_df['elo_after'].idxmin()
        peak_row = history_df.loc[peak_idx]
        low_row = history_df.loc[low_idx]

        fig.add_trace(go.Scatter(
            x=[peak_row['game_date']],
            y=[peak_row['elo_after']],
            mode='markers',
            name='Peak',
            marker=dict(color=POSITIVE, size=8),
        ))
        fig.add_trace(go.Scatter(
            x=[low_row['game_date']],
            y=[low_row['elo_after']],
            mode='markers',
            name='Low',
            marker=dict(color=NEGATIVE, size=8),
        ))

        fig.update_layout(
            title=f"{team_data['full_name']} Elo Over Time",
            xaxis_title="Date",
            yaxis_title="Elo",
            template=PLOTLY_TEMPLATE,
            height=380,
            paper_bgcolor=CHART_BG,
            plot_bgcolor=CHART_BG,
            yaxis=dict(gridcolor=GRID_COLOR),
            xaxis=dict(gridcolor=GRID_COLOR),
            font=dict(family="Outfit, sans-serif", color="#E0DCD5"),
            title_font=dict(family="DM Serif Display, serif", size=14),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Peak / low / avg change
        stat_cols = st.columns(3)
        with stat_cols[0]:
            st.markdown(
                f'<div class="stat-card">'
                f'<div class="stat-card-value" style="font-size:1.3rem;">{peak_row["elo_after"]:.0f}</div>'
                f'<div class="stat-card-label">Peak Elo</div>'
                f'<div class="stat-card-detail">{peak_row["game_date"].strftime("%Y-%m-%d")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with stat_cols[1]:
            st.markdown(
                f'<div class="stat-card">'
                f'<div class="stat-card-value" style="font-size:1.3rem; color:var(--negative);">{low_row["elo_after"]:.0f}</div>'
                f'<div class="stat-card-label">Low Elo</div>'
                f'<div class="stat-card-detail">{low_row["game_date"].strftime("%Y-%m-%d")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with stat_cols[2]:
            avg_change = history_df['elo_change'].mean()
            avg_color = "var(--positive)" if avg_change > 0 else "var(--negative)"
            st.markdown(
                f'<div class="stat-card">'
                f'<div class="stat-card-value" style="font-size:1.3rem; color:{avg_color};">{avg_change:+.1f}</div>'
                f'<div class="stat-card-label">Avg Change/Game</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info(f"No Elo history available for {selected_team}. Run backfill to generate history.")

# Team comparison
st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Team Comparison</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    team1 = st.selectbox("Team 1", options=teams_df['abbreviation'].tolist(), key="team1")
with col2:
    team2 = st.selectbox("Team 2", options=teams_df['abbreviation'].tolist(), index=1, key="team2")

if team1 and team2 and team1 != team2:
    from src.models.elo import calculate_win_probabilities, elo_to_spread

    t1_data = teams_df[teams_df['abbreviation'] == team1].iloc[0]
    t2_data = teams_df[teams_df['abbreviation'] == team2].iloc[0]

    col1, col2, col3 = st.columns(3)

    with col1:
        home_prob, away_prob = calculate_win_probabilities(t1_data['current_elo'], t2_data['current_elo'])
        spread = elo_to_spread(t1_data['current_elo'], t2_data['current_elo'])
        st.markdown(
            f'<div class="stat-card">'
            f'<div style="font-family:\'DM Serif Display\',serif; font-size:1rem; color:var(--text); margin-bottom:0.6rem;">{team1} at Home</div>'
            f'<div class="detail-label">Win Prob</div>'
            f'<div class="detail-value">{team1} {home_prob:.1%} &middot; {team2} {away_prob:.1%}</div>'
            f'<div class="detail-label" style="margin-top:0.4rem;">Spread</div>'
            f'<div class="detail-value">{team1} {spread:.1f}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with col2:
        home_prob, away_prob = calculate_win_probabilities(t2_data['current_elo'], t1_data['current_elo'])
        spread = elo_to_spread(t2_data['current_elo'], t1_data['current_elo'])
        st.markdown(
            f'<div class="stat-card">'
            f'<div style="font-family:\'DM Serif Display\',serif; font-size:1rem; color:var(--text); margin-bottom:0.6rem;">{team2} at Home</div>'
            f'<div class="detail-label">Win Prob</div>'
            f'<div class="detail-value">{team2} {home_prob:.1%} &middot; {team1} {away_prob:.1%}</div>'
            f'<div class="detail-label" style="margin-top:0.4rem;">Spread</div>'
            f'<div class="detail-value">{team2} {spread:.1f}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with col3:
        elo_diff = t1_data['current_elo'] - t2_data['current_elo']
        st.markdown(
            f'<div class="stat-card">'
            f'<div style="font-family:\'DM Serif Display\',serif; font-size:1rem; color:var(--text); margin-bottom:0.6rem;">Elo Comparison</div>'
            f'<div class="detail-label">{team1}</div>'
            f'<div class="detail-value">{t1_data["current_elo"]:.0f}</div>'
            f'<div class="detail-label" style="margin-top:0.3rem;">{team2}</div>'
            f'<div class="detail-value">{t2_data["current_elo"]:.0f}</div>'
            f'<div class="detail-label" style="margin-top:0.3rem;">Difference</div>'
            f'<div class="detail-value" style="color:var(--accent);">{elo_diff:+.0f}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
