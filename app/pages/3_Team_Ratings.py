"""Team Ratings page - Elo rankings and history."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.database import (
    init_database,
    get_all_teams,
    get_team_elo_history,
)
from config import ELO_INITIAL_RATING

st.set_page_config(page_title="Team Ratings", page_icon="🏆", layout="wide")

st.title("🏆 Team Ratings")
st.markdown("Current Elo ratings and historical performance for all NBA teams.")

# Initialize database
init_database()

# Load teams
teams_df = get_all_teams()

if teams_df.empty:
    st.warning("No teams found. Please run `python scripts/init_db.py` to initialize the database.")
    st.stop()

# Rankings table
st.markdown("### Current Elo Rankings")

# Add rank and tier
teams_df['rank'] = range(1, len(teams_df) + 1)
teams_df['elo_diff'] = teams_df['current_elo'] - ELO_INITIAL_RATING

# Create tier labels
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

# Color by tier
tier_colors = {
    "Championship": "#FFD700",
    "Contender": "#C0C0C0",
    "Playoff": "#CD7F32",
    "Bubble": "#808080",
    "Rebuilding": "#A9A9A9",
}

# Display columns
col1, col2 = st.columns([2, 1])

with col1:
    # Rankings table
    display_df = teams_df[['rank', 'abbreviation', 'full_name', 'current_elo', 'elo_diff', 'tier']].copy()
    display_df['current_elo'] = display_df['current_elo'].round(0).astype(int)
    display_df['elo_diff'] = display_df['elo_diff'].apply(lambda x: f"{x:+.0f}")

    st.dataframe(
        display_df.rename(columns={
            'rank': '#',
            'abbreviation': 'Team',
            'full_name': 'Name',
            'current_elo': 'Elo',
            'elo_diff': 'vs Avg',
            'tier': 'Tier',
        }),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

with col2:
    # Tier breakdown
    st.markdown("### Tier Breakdown")

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
        template="plotly_white",
        height=300,
    )

    st.plotly_chart(fig, use_container_width=True)

    # Tier descriptions
    st.markdown("**Tier Definitions:**")
    st.markdown("""
    - **Championship** (1600+): Title favorites
    - **Contender** (1550-1599): Strong playoff teams
    - **Playoff** (1500-1549): Playoff caliber
    - **Bubble** (1450-1499): Play-in range
    - **Rebuilding** (<1450): Lottery teams
    """)

st.markdown("---")

# Elo distribution chart
st.markdown("### Elo Distribution")

fig = px.histogram(
    teams_df,
    x='current_elo',
    nbins=15,
    title='Distribution of Team Elo Ratings',
    color_discrete_sequence=['#1f77b4'],
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
    template="plotly_white",
    height=300,
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Team-specific analysis
st.markdown("### Team Analysis")

selected_team = st.selectbox(
    "Select a team",
    options=teams_df['abbreviation'].tolist(),
    format_func=lambda x: f"{x} - {teams_df[teams_df['abbreviation']==x]['full_name'].values[0]}"
)

if selected_team:
    team_data = teams_df[teams_df['abbreviation'] == selected_team].iloc[0]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Current Elo", f"{team_data['current_elo']:.0f}")

    with col2:
        diff = team_data['current_elo'] - ELO_INITIAL_RATING
        st.metric("vs Average", f"{diff:+.0f}")

    with col3:
        st.metric("Rank", f"#{team_data['rank']}")

    with col4:
        st.metric("Tier", team_data['tier'])

    # Elo history
    team_id = team_data['team_id']
    history_df = get_team_elo_history(team_id)

    if not history_df.empty:
        st.markdown(f"#### {selected_team} Elo History")

        history_df['game_date'] = pd.to_datetime(history_df['game_date'])
        history_df = history_df.sort_values('game_date')

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=history_df['game_date'],
            y=history_df['elo_after'],
            mode='lines',
            name='Elo Rating',
            line=dict(color='#1f77b4', width=2),
        ))

        fig.add_hline(
            y=ELO_INITIAL_RATING,
            line_dash="dash",
            line_color="gray",
            annotation_text="Average",
        )

        # Add peak and low annotations
        peak_idx = history_df['elo_after'].idxmax()
        low_idx = history_df['elo_after'].idxmin()

        peak_row = history_df.loc[peak_idx]
        low_row = history_df.loc[low_idx]

        fig.add_trace(go.Scatter(
            x=[peak_row['game_date']],
            y=[peak_row['elo_after']],
            mode='markers',
            name='Peak',
            marker=dict(color='green', size=10),
        ))

        fig.add_trace(go.Scatter(
            x=[low_row['game_date']],
            y=[low_row['elo_after']],
            mode='markers',
            name='Low',
            marker=dict(color='red', size=10),
        ))

        fig.update_layout(
            title=f"{team_data['full_name']} Elo Rating Over Time",
            xaxis_title="Date",
            yaxis_title="Elo Rating",
            template="plotly_white",
            height=400,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Stats
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Peak Elo", f"{peak_row['elo_after']:.0f}")
            st.caption(f"on {peak_row['game_date'].strftime('%Y-%m-%d')}")

        with col2:
            st.metric("Low Elo", f"{low_row['elo_after']:.0f}")
            st.caption(f"on {low_row['game_date'].strftime('%Y-%m-%d')}")

        with col3:
            avg_change = history_df['elo_change'].mean()
            st.metric("Avg Change/Game", f"{avg_change:+.1f}")
    else:
        st.info(f"No Elo history available for {selected_team}. Run backfill to generate history.")

st.markdown("---")

# Comparison tool
st.markdown("### Team Comparison")

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

    st.markdown(f"#### {team1} vs {team2}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"**{team1} at Home:**")
        home_prob, away_prob = calculate_win_probabilities(t1_data['current_elo'], t2_data['current_elo'])
        spread = elo_to_spread(t1_data['current_elo'], t2_data['current_elo'])

        st.write(f"{team1} win: {home_prob:.1%}")
        st.write(f"{team2} win: {away_prob:.1%}")
        st.write(f"Spread: {team1} {spread:.1f}")

    with col2:
        st.markdown(f"**{team2} at Home:**")
        home_prob, away_prob = calculate_win_probabilities(t2_data['current_elo'], t1_data['current_elo'])
        spread = elo_to_spread(t2_data['current_elo'], t1_data['current_elo'])

        st.write(f"{team2} win: {home_prob:.1%}")
        st.write(f"{team1} win: {away_prob:.1%}")
        st.write(f"Spread: {team2} {spread:.1f}")

    with col3:
        st.markdown("**Elo Comparison:**")
        elo_diff = t1_data['current_elo'] - t2_data['current_elo']
        st.write(f"{team1}: {t1_data['current_elo']:.0f}")
        st.write(f"{team2}: {t2_data['current_elo']:.0f}")
        st.write(f"Difference: {elo_diff:+.0f}")
