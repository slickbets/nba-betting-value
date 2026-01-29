"""Performance tracking page."""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.database import init_database, get_all_bets

st.set_page_config(page_title="Performance", page_icon="📈", layout="wide")

st.title("📈 Performance")
st.markdown("Track your betting performance over time.")

# Initialize database
init_database()

# Load bets
bets_df = get_all_bets()
settled = bets_df[bets_df['result'].notna()].copy()

if settled.empty:
    st.info("No settled bets yet. Start logging and settling bets to see your performance metrics.")
    st.stop()

# Convert dates
settled['game_date'] = pd.to_datetime(settled['game_date'])
settled['placed_at'] = pd.to_datetime(settled['placed_at'])

# Summary metrics
st.markdown("### Overall Performance")

col1, col2, col3, col4, col5 = st.columns(5)

total_bets = len(settled)
wins = len(settled[settled['result'] == 'win'])
losses = len(settled[settled['result'] == 'loss'])
pushes = len(settled[settled['result'] == 'push'])
win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

total_staked = settled['stake'].sum()
total_pnl = settled['profit_loss'].sum()
roi = (total_pnl / total_staked) * 100 if total_staked > 0 else 0

with col1:
    st.metric("Total Bets", total_bets)

with col2:
    st.metric("Record", f"{wins}-{losses}-{pushes}")

with col3:
    st.metric("Win Rate", f"{win_rate:.1f}%")

with col4:
    delta_color = "normal" if total_pnl >= 0 else "inverse"
    st.metric("Total P/L", f"${total_pnl:.2f}", delta_color=delta_color)

with col5:
    st.metric("ROI", f"{roi:+.1f}%")

st.markdown("---")

# Cumulative P/L chart
st.markdown("### Cumulative Profit/Loss")

settled_sorted = settled.sort_values('game_date')
settled_sorted['cumulative_pnl'] = settled_sorted['profit_loss'].cumsum()
settled_sorted['bet_number'] = range(1, len(settled_sorted) + 1)

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=settled_sorted['bet_number'],
    y=settled_sorted['cumulative_pnl'],
    mode='lines+markers',
    name='Cumulative P/L',
    line=dict(color='#1f77b4', width=2),
    marker=dict(size=6),
    hovertemplate='Bet #%{x}<br>P/L: $%{y:.2f}<extra></extra>'
))

# Add zero line
fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

# Color the area based on profit/loss
fig.add_trace(go.Scatter(
    x=settled_sorted['bet_number'],
    y=settled_sorted['cumulative_pnl'],
    fill='tozeroy',
    fillcolor='rgba(0, 255, 0, 0.1)' if total_pnl >= 0 else 'rgba(255, 0, 0, 0.1)',
    line=dict(width=0),
    showlegend=False,
    hoverinfo='skip'
))

fig.update_layout(
    title="Cumulative P/L by Bet",
    xaxis_title="Bet Number",
    yaxis_title="Cumulative P/L ($)",
    template="plotly_white",
    height=400,
)

st.plotly_chart(fig, use_container_width=True)

# Performance by edge bucket
st.markdown("### Performance by Edge")

col1, col2 = st.columns(2)

with col1:
    # Edge buckets
    bins = [0, 3, 5, 7, 10, 100]
    labels = ['0-3%', '3-5%', '5-7%', '7-10%', '10%+']
    settled['edge_bucket'] = pd.cut(
        settled['edge'].fillna(0),
        bins=bins,
        labels=labels,
        include_lowest=True
    )

    edge_stats = settled.groupby('edge_bucket', observed=True).agg({
        'profit_loss': ['sum', 'count'],
        'result': lambda x: (x == 'win').sum()
    }).round(2)

    edge_stats.columns = ['P/L', 'Bets', 'Wins']
    edge_stats['Win Rate'] = (edge_stats['Wins'] / edge_stats['Bets'] * 100).round(1)
    edge_stats['ROI'] = edge_stats.apply(
        lambda x: x['P/L'] / (settled[settled['edge_bucket'] == x.name]['stake'].sum()) * 100
        if settled[settled['edge_bucket'] == x.name]['stake'].sum() > 0 else 0,
        axis=1
    ).round(1)

    st.dataframe(
        edge_stats[['Bets', 'Wins', 'Win Rate', 'P/L', 'ROI']].rename(columns={
            'Win Rate': 'Win %',
            'ROI': 'ROI %',
        }),
        use_container_width=True
    )

with col2:
    # Edge vs Win Rate chart
    fig = px.bar(
        edge_stats.reset_index(),
        x='edge_bucket',
        y='Win Rate',
        title='Win Rate by Edge Bucket',
        color='Win Rate',
        color_continuous_scale=['red', 'yellow', 'green'],
    )
    fig.update_layout(template="plotly_white", height=300)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Performance by bet type
st.markdown("### Performance by Bet Type")

col1, col2 = st.columns(2)

with col1:
    type_stats = settled.groupby('bet_type').agg({
        'profit_loss': 'sum',
        'stake': 'sum',
        'result': lambda x: (x == 'win').sum(),
        'bet_id': 'count'
    }).round(2)

    type_stats.columns = ['P/L', 'Staked', 'Wins', 'Bets']
    type_stats['Win Rate'] = (type_stats['Wins'] / type_stats['Bets'] * 100).round(1)
    type_stats['ROI'] = (type_stats['P/L'] / type_stats['Staked'] * 100).round(1)

    st.dataframe(
        type_stats[['Bets', 'Wins', 'Win Rate', 'P/L', 'ROI']].rename(columns={
            'Win Rate': 'Win %',
            'ROI': 'ROI %',
        }),
        use_container_width=True
    )

with col2:
    # Pie chart of P/L by type
    if len(type_stats) > 0:
        fig = px.pie(
            type_stats.reset_index(),
            values='Bets',
            names='bet_type',
            title='Bets by Type',
        )
        fig.update_layout(template="plotly_white", height=300)
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Performance by sportsbook
if 'sportsbook' in settled.columns and settled['sportsbook'].notna().any():
    st.markdown("### Performance by Sportsbook")

    book_stats = settled.groupby('sportsbook').agg({
        'profit_loss': 'sum',
        'stake': 'sum',
        'result': lambda x: (x == 'win').sum(),
        'bet_id': 'count'
    }).round(2)

    book_stats.columns = ['P/L', 'Staked', 'Wins', 'Bets']
    book_stats['Win Rate'] = (book_stats['Wins'] / book_stats['Bets'] * 100).round(1)
    book_stats['ROI'] = (book_stats['P/L'] / book_stats['Staked'] * 100).round(1)

    st.dataframe(
        book_stats[['Bets', 'Wins', 'Win Rate', 'P/L', 'ROI']].rename(columns={
            'Win Rate': 'Win %',
            'ROI': 'ROI %',
        }),
        use_container_width=True
    )

    st.markdown("---")

# Monthly performance
st.markdown("### Monthly Performance")

settled['month'] = settled['game_date'].dt.to_period('M')
monthly = settled.groupby('month').agg({
    'profit_loss': 'sum',
    'stake': 'sum',
    'bet_id': 'count',
    'result': lambda x: (x == 'win').sum()
}).round(2)

monthly.columns = ['P/L', 'Staked', 'Bets', 'Wins']
monthly['ROI'] = (monthly['P/L'] / monthly['Staked'] * 100).round(1)
monthly['Win Rate'] = (monthly['Wins'] / monthly['Bets'] * 100).round(1)
monthly.index = monthly.index.astype(str)

col1, col2 = st.columns(2)

with col1:
    st.dataframe(
        monthly[['Bets', 'Wins', 'Win Rate', 'P/L', 'ROI']].rename(columns={
            'Win Rate': 'Win %',
            'ROI': 'ROI %',
        }),
        use_container_width=True
    )

with col2:
    fig = go.Figure()

    colors = ['green' if x >= 0 else 'red' for x in monthly['P/L']]

    fig.add_trace(go.Bar(
        x=monthly.index,
        y=monthly['P/L'],
        marker_color=colors,
        name='P/L',
    ))

    fig.update_layout(
        title="Monthly P/L",
        xaxis_title="Month",
        yaxis_title="P/L ($)",
        template="plotly_white",
        height=300,
    )

    st.plotly_chart(fig, use_container_width=True)

# Recent bets
st.markdown("---")
st.markdown("### Recent Settled Bets")

recent = settled.sort_values('game_date', ascending=False).head(10)
recent['matchup'] = recent.apply(lambda x: f"{x['away_abbr']} @ {x['home_abbr']}", axis=1)

display_df = recent[['game_date', 'matchup', 'bet_type', 'selection', 'odds', 'stake', 'result', 'profit_loss']].copy()
display_df['game_date'] = display_df['game_date'].dt.strftime('%Y-%m-%d')
display_df['odds'] = display_df['odds'].apply(lambda x: f"{int(x):+d}")
display_df['stake'] = display_df['stake'].apply(lambda x: f"${x:.2f}")
display_df['profit_loss'] = display_df['profit_loss'].apply(lambda x: f"${x:+.2f}")

st.dataframe(
    display_df.rename(columns={
        'game_date': 'Date',
        'matchup': 'Game',
        'bet_type': 'Type',
        'selection': 'Pick',
        'odds': 'Odds',
        'stake': 'Stake',
        'result': 'Result',
        'profit_loss': 'P/L',
    }),
    use_container_width=True,
    hide_index=True,
)
