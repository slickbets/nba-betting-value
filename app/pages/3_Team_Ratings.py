"""Team Ratings page - Elo rankings and history."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests

from src.data.database import (
    init_database,
    get_all_teams,
    get_team_elo_history,
)
from config import ELO_INITIAL_RATING
from app.shared import render_sidebar

PLOTLY_TEMPLATE = "plotly_dark"
CHART_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.08)"
GREEN = "#00C853"

st.set_page_config(page_title="Team Ratings | Slick Bets", page_icon="🏆", layout="wide")
render_sidebar()

st.markdown('<div class="hero-title" style="font-size:2rem;">Team Ratings</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-subtitle" style="font-size:0.95rem;">Current Elo ratings and historical performance for all NBA teams.</div>', unsafe_allow_html=True)

# Initialize database
init_database()

# Load teams
teams_df = get_all_teams()

if teams_df.empty:
    st.warning("No teams found. Please run `python scripts/init_db.py` to initialize the database.")
    st.stop()

# Fetch W/L records from ESPN standings API
ESPN_ABBR_MAP = {'GS': 'GSW', 'SA': 'SAS', 'NY': 'NYK', 'NO': 'NOP', 'UTAH': 'UTA', 'WSH': 'WAS'}

@st.cache_data(ttl=3600)
def fetch_espn_records():
    """Fetch current W/L records from ESPN standings API."""
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

espn_records = fetch_espn_records()
if espn_records:
    teams_df['wins'] = teams_df['abbreviation'].map(lambda a: espn_records.get(a, (0, 0))[0])
    teams_df['losses'] = teams_df['abbreviation'].map(lambda a: espn_records.get(a, (0, 0))[1])
    teams_df['record'] = teams_df.apply(lambda r: f"{r['wins']}-{r['losses']}", axis=1)
else:
    teams_df['record'] = '-'

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

tier_colors = {
    "Championship": "#FFD700",
    "Contender": "#C0C0C0",
    "Playoff": "#CD7F32",
    "Bubble": "#808080",
    "Rebuilding": "#555555",
}

tier_badge_css = {
    "Championship": "background:rgba(255,215,0,0.15); color:#FFD700; border:1px solid rgba(255,215,0,0.3);",
    "Contender": "background:rgba(192,192,192,0.15); color:#C0C0C0; border:1px solid rgba(192,192,192,0.3);",
    "Playoff": "background:rgba(205,127,50,0.15); color:#CD7F32; border:1px solid rgba(205,127,50,0.3);",
    "Bubble": "background:rgba(128,128,128,0.15); color:#888; border:1px solid rgba(128,128,128,0.3);",
    "Rebuilding": "background:rgba(85,85,85,0.15); color:#777; border:1px solid rgba(85,85,85,0.3);",
}

# Rankings
st.markdown('<div class="section-header">Current Elo Rankings</div>', unsafe_allow_html=True)

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
            'record': 'W-L',
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
        marker_color=[tier_colors[t] for t in tier_order],
    ))

    fig.update_layout(
        title="Teams by Tier",
        xaxis_title="Number of Teams",
        template=PLOTLY_TEMPLATE,
        height=300,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        yaxis=dict(gridcolor=GRID_COLOR),
        xaxis=dict(gridcolor=GRID_COLOR),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Tier descriptions as styled cards
    for tier_name in tier_order:
        elo_range = {"Championship": "1600+", "Contender": "1550-1599", "Playoff": "1500-1549", "Bubble": "1450-1499", "Rebuilding": "<1450"}
        desc = {"Championship": "Title favorites", "Contender": "Strong playoff teams", "Playoff": "Playoff caliber", "Bubble": "Play-in range", "Rebuilding": "Lottery teams"}
        badge_style = tier_badge_css[tier_name]
        count = tier_counts.get(tier_name, 0)
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center; padding:0.3rem 0;">
            <span class="badge" style="{badge_style}">{tier_name}</span>
            <span style="color:#888; font-size:0.8rem;">{elo_range[tier_name]} &middot; {count} teams</span>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# Elo distribution chart
st.markdown('<div class="section-header">Elo Distribution</div>', unsafe_allow_html=True)

fig = px.histogram(
    teams_df,
    x='current_elo',
    nbins=15,
    title='Distribution of Team Elo Ratings',
    color_discrete_sequence=[GREEN],
)

fig.add_vline(
    x=ELO_INITIAL_RATING,
    line_dash="dash",
    line_color="red",
    annotation_text="Average (1500)",
    annotation_position="top right",
)

fig.update_layout(
    xaxis_title="Elo Rating",
    yaxis_title="Number of Teams",
    template=PLOTLY_TEMPLATE,
    height=300,
    paper_bgcolor=CHART_BG,
    plot_bgcolor=CHART_BG,
    yaxis=dict(gridcolor=GRID_COLOR),
    xaxis=dict(gridcolor=GRID_COLOR),
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Team-specific analysis
st.markdown('<div class="section-header">Team Analysis</div>', unsafe_allow_html=True)

selected_team = st.selectbox(
    "Select a team",
    options=teams_df['abbreviation'].tolist(),
    format_func=lambda x: f"{x} - {teams_df[teams_df['abbreviation']==x]['full_name'].values[0]}"
)

if selected_team:
    team_data = teams_df[teams_df['abbreviation'] == selected_team].iloc[0]

    cols = st.columns(4)
    labels = ["Current Elo", "vs Average", "Rank", "Tier"]
    diff = team_data['current_elo'] - ELO_INITIAL_RATING
    values = [
        f"{team_data['current_elo']:.0f}",
        f"{diff:+.0f}",
        f"#{team_data['rank']}",
        team_data['tier'],
    ]
    for col, label, value in zip(cols, labels, values):
        with col:
            st.markdown(f"""
            <div class="accuracy-card">
                <div class="accuracy-big" style="font-size:1.8rem;">{value}</div>
                <div class="accuracy-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

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
            name='Elo Rating',
            line=dict(color=GREEN, width=2),
        ))

        fig.add_hline(
            y=ELO_INITIAL_RATING,
            line_dash="dash",
            line_color="gray",
            annotation_text="Average",
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
            marker=dict(color=GREEN, size=10),
        ))

        fig.add_trace(go.Scatter(
            x=[low_row['game_date']],
            y=[low_row['elo_after']],
            mode='markers',
            name='Low',
            marker=dict(color='#F44336', size=10),
        ))

        fig.update_layout(
            title=f"{team_data['full_name']} Elo Rating Over Time",
            xaxis_title="Date",
            yaxis_title="Elo Rating",
            template=PLOTLY_TEMPLATE,
            height=400,
            paper_bgcolor=CHART_BG,
            plot_bgcolor=CHART_BG,
            yaxis=dict(gridcolor=GRID_COLOR),
            xaxis=dict(gridcolor=GRID_COLOR),
        )

        st.plotly_chart(fig, use_container_width=True)

        # Stats
        stat_cols = st.columns(3)
        with stat_cols[0]:
            st.markdown(f"""
            <div class="accuracy-card">
                <div class="accuracy-big" style="font-size:1.8rem;">{peak_row['elo_after']:.0f}</div>
                <div class="accuracy-label">Peak Elo</div>
                <div class="accuracy-detail">{peak_row['game_date'].strftime('%Y-%m-%d')}</div>
            </div>
            """, unsafe_allow_html=True)
        with stat_cols[1]:
            st.markdown(f"""
            <div class="accuracy-card">
                <div class="accuracy-big" style="font-size:1.8rem; color:#F44336;">{low_row['elo_after']:.0f}</div>
                <div class="accuracy-label">Low Elo</div>
                <div class="accuracy-detail">{low_row['game_date'].strftime('%Y-%m-%d')}</div>
            </div>
            """, unsafe_allow_html=True)
        with stat_cols[2]:
            avg_change = history_df['elo_change'].mean()
            avg_color = GREEN if avg_change > 0 else "#F44336"
            st.markdown(f"""
            <div class="accuracy-card">
                <div class="accuracy-big" style="font-size:1.8rem; color:{avg_color};">{avg_change:+.1f}</div>
                <div class="accuracy-label">Avg Change/Game</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info(f"No Elo history available for {selected_team}. Run backfill to generate history.")

st.markdown("---")

# Comparison tool
st.markdown('<div class="section-header">Team Comparison</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    team1 = st.selectbox(
        "Team 1",
        options=teams_df['abbreviation'].tolist(),
        key="team1"
    )

with col2:
    team2 = st.selectbox(
        "Team 2",
        options=teams_df['abbreviation'].tolist(),
        index=1,
        key="team2"
    )

if team1 and team2 and team1 != team2:
    from src.models.elo import calculate_win_probabilities, elo_to_spread

    t1_data = teams_df[teams_df['abbreviation'] == team1].iloc[0]
    t2_data = teams_df[teams_df['abbreviation'] == team2].iloc[0]

    col1, col2, col3 = st.columns(3)

    with col1:
        home_prob, away_prob = calculate_win_probabilities(t1_data['current_elo'], t2_data['current_elo'])
        spread = elo_to_spread(t1_data['current_elo'], t2_data['current_elo'])
        st.markdown(f"""
        <div class="game-card">
            <div class="game-card-matchup" style="margin-bottom:0.5rem;">{team1} at Home</div>
            <div class="game-card-stat-label">Win Prob</div>
            <div class="game-card-stat-value">{team1} {home_prob:.1%} &middot; {team2} {away_prob:.1%}</div>
            <div class="game-card-stat-label" style="margin-top:0.4rem;">Spread</div>
            <div class="game-card-stat-value">{team1} {spread:.1f}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        home_prob, away_prob = calculate_win_probabilities(t2_data['current_elo'], t1_data['current_elo'])
        spread = elo_to_spread(t2_data['current_elo'], t1_data['current_elo'])
        st.markdown(f"""
        <div class="game-card">
            <div class="game-card-matchup" style="margin-bottom:0.5rem;">{team2} at Home</div>
            <div class="game-card-stat-label">Win Prob</div>
            <div class="game-card-stat-value">{team2} {home_prob:.1%} &middot; {team1} {away_prob:.1%}</div>
            <div class="game-card-stat-label" style="margin-top:0.4rem;">Spread</div>
            <div class="game-card-stat-value">{team2} {spread:.1f}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        elo_diff = t1_data['current_elo'] - t2_data['current_elo']
        st.markdown(f"""
        <div class="game-card">
            <div class="game-card-matchup" style="margin-bottom:0.5rem;">Elo Comparison</div>
            <div class="game-card-stat-label">{team1}</div>
            <div class="game-card-stat-value">{t1_data['current_elo']:.0f}</div>
            <div class="game-card-stat-label" style="margin-top:0.4rem;">{team2}</div>
            <div class="game-card-stat-value">{t2_data['current_elo']:.0f}</div>
            <div class="game-card-stat-label" style="margin-top:0.4rem;">Difference</div>
            <div class="game-card-stat-value">{elo_diff:+.0f}</div>
        </div>
        """, unsafe_allow_html=True)
