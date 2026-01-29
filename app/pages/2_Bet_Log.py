"""Bet Log page - Track and settle bets."""

import streamlit as st
from datetime import datetime
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.database import (
    init_database,
    get_all_bets,
    get_unsettled_bets,
    insert_bet,
    settle_bet,
    get_games_by_date,
)
from src.betting.odds_converter import (
    american_to_decimal,
    format_american_odds,
    format_probability,
)

st.set_page_config(page_title="Bet Log", page_icon="📝", layout="wide")

st.title("📝 Bet Log")
st.markdown("Track your bets and monitor results.")

# Initialize database
init_database()

# Tabs for different views
tab1, tab2, tab3 = st.tabs(["📋 All Bets", "⏳ Pending", "➕ Add Bet"])

# Tab 1: All Bets
with tab1:
    st.markdown("### All Bets")

    bets_df = get_all_bets()

    if bets_df.empty:
        st.info("No bets logged yet. Use the 'Add Bet' tab to start tracking your bets.")
    else:
        # Summary stats
        col1, col2, col3, col4 = st.columns(4)

        total_stake = bets_df['stake'].sum()
        settled = bets_df[bets_df['result'].notna()]
        total_pnl = settled['profit_loss'].sum() if not settled.empty else 0
        wins = len(settled[settled['result'] == 'win'])
        losses = len(settled[settled['result'] == 'loss'])

        with col1:
            st.metric("Total Bets", len(bets_df))
        with col2:
            st.metric("Total Staked", f"${total_stake:.2f}")
        with col3:
            st.metric("Win/Loss", f"{wins}-{losses}")
        with col4:
            pnl_color = "normal" if total_pnl >= 0 else "inverse"
            st.metric("Total P/L", f"${total_pnl:.2f}", delta_color=pnl_color)

        st.markdown("---")

        # Display bets table
        display_cols = [
            'game_date', 'home_abbr', 'away_abbr', 'bet_type', 'selection',
            'odds', 'stake', 'edge', 'result', 'profit_loss'
        ]

        # Format for display
        display_df = bets_df.copy()
        display_df['matchup'] = display_df.apply(
            lambda x: f"{x['away_abbr']} @ {x['home_abbr']}", axis=1
        )
        display_df['odds_display'] = display_df['odds'].apply(
            lambda x: format_american_odds(int(x)) if pd.notna(x) else ""
        )
        display_df['stake_display'] = display_df['stake'].apply(lambda x: f"${x:.2f}")
        display_df['edge_display'] = display_df['edge'].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else ""
        )
        display_df['pnl_display'] = display_df['profit_loss'].apply(
            lambda x: f"${x:+.2f}" if pd.notna(x) else "Pending"
        )

        st.dataframe(
            display_df[['game_date', 'matchup', 'bet_type', 'selection',
                       'odds_display', 'stake_display', 'edge_display',
                       'result', 'pnl_display']].rename(columns={
                'game_date': 'Date',
                'matchup': 'Game',
                'bet_type': 'Type',
                'selection': 'Pick',
                'odds_display': 'Odds',
                'stake_display': 'Stake',
                'edge_display': 'Edge',
                'result': 'Result',
                'pnl_display': 'P/L',
            }),
            use_container_width=True,
            hide_index=True,
        )

# Tab 2: Pending Bets
with tab2:
    st.markdown("### Pending Bets")
    st.markdown("Settle completed bets here.")

    unsettled = get_unsettled_bets()

    if unsettled.empty:
        st.success("No pending bets to settle!")
    else:
        for _, bet in unsettled.iterrows():
            matchup = f"{bet['away_abbr']} @ {bet['home_abbr']}"
            game_status = bet.get('status', 'scheduled')

            with st.expander(f"🎫 {matchup} - {bet['selection']} ({bet['bet_type']})"):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.write(f"**Date:** {bet['game_date']}")
                    st.write(f"**Pick:** {bet['selection']}")
                    st.write(f"**Type:** {bet['bet_type']}")
                    st.write(f"**Odds:** {format_american_odds(int(bet['odds']))}")
                    st.write(f"**Stake:** ${bet['stake']:.2f}")

                    if pd.notna(bet.get('edge')):
                        st.write(f"**Edge:** {bet['edge']:.1f}%")

                with col2:
                    st.write(f"**Game Status:** {game_status}")

                    if game_status == 'final':
                        st.write(f"**Score:** {bet['away_abbr']} {bet['away_score']} - {bet['home_abbr']} {bet['home_score']}")

                        # Settle buttons
                        st.markdown("**Settle Bet:**")

                        decimal_odds = american_to_decimal(int(bet['odds']))
                        stake = bet['stake']

                        col_win, col_loss, col_push = st.columns(3)

                        with col_win:
                            if st.button("✅ Win", key=f"win_{bet['bet_id']}"):
                                payout = stake * decimal_odds
                                profit = payout - stake
                                settle_bet(bet['bet_id'], 'win', payout, profit)
                                st.success(f"Settled as WIN: +${profit:.2f}")
                                st.rerun()

                        with col_loss:
                            if st.button("❌ Loss", key=f"loss_{bet['bet_id']}"):
                                settle_bet(bet['bet_id'], 'loss', 0, -stake)
                                st.error(f"Settled as LOSS: -${stake:.2f}")
                                st.rerun()

                        with col_push:
                            if st.button("↔️ Push", key=f"push_{bet['bet_id']}"):
                                settle_bet(bet['bet_id'], 'push', stake, 0)
                                st.info("Settled as PUSH: $0.00")
                                st.rerun()
                    else:
                        st.info("Game not yet completed")

# Tab 3: Add Bet
with tab3:
    st.markdown("### Log a New Bet")

    with st.form("add_bet_form"):
        col1, col2 = st.columns(2)

        with col1:
            game_id = st.text_input(
                "Game ID",
                help="Internal game ID (or enter manually)"
            )

            bet_type = st.selectbox(
                "Bet Type",
                options=["moneyline", "spread", "total", "other"]
            )

            selection = st.text_input(
                "Selection",
                help="Team abbreviation or 'over'/'under'"
            )

            line = st.number_input(
                "Line (if applicable)",
                value=0.0,
                step=0.5,
                help="Spread or total line"
            )

        with col2:
            odds = st.number_input(
                "Odds (American)",
                value=-110,
                step=5,
                help="e.g., -110, +150"
            )

            stake = st.number_input(
                "Stake ($)",
                min_value=0.0,
                value=10.0,
                step=5.0
            )

            sportsbook = st.selectbox(
                "Sportsbook",
                options=["draftkings", "fanduel", "betmgm", "caesars", "other"]
            )

            model_prob = st.number_input(
                "Model Probability (%)",
                min_value=0.0,
                max_value=100.0,
                value=50.0,
                help="Your estimated win probability"
            )

        notes = st.text_area("Notes (optional)")

        submitted = st.form_submit_button("Log Bet")

        if submitted:
            if not selection:
                st.error("Please enter a selection")
            elif stake <= 0:
                st.error("Stake must be greater than 0")
            else:
                from src.betting.odds_converter import american_to_implied_prob, calculate_edge

                implied_prob = american_to_implied_prob(int(odds))
                edge = (model_prob / 100) - implied_prob

                bet_id = insert_bet(
                    game_id=game_id or f"manual_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    bet_type=bet_type,
                    selection=selection,
                    line=line if line != 0 else None,
                    odds=int(odds),
                    stake=stake,
                    model_probability=model_prob / 100,
                    implied_probability=implied_prob,
                    edge=edge * 100,
                    sportsbook=sportsbook,
                    notes=notes or None,
                )

                st.success(f"Bet logged successfully! (ID: {bet_id})")
                st.balloons()

# Quick add section
st.markdown("---")
st.markdown("### Quick Stats")

bets_df = get_all_bets()
if not bets_df.empty:
    settled = bets_df[bets_df['result'].notna()]

    if not settled.empty:
        col1, col2, col3 = st.columns(3)

        with col1:
            wins = len(settled[settled['result'] == 'win'])
            total = len(settled[settled['result'].isin(['win', 'loss'])])
            win_rate = wins / total * 100 if total > 0 else 0
            st.metric("Win Rate", f"{win_rate:.1f}%")

        with col2:
            total_staked = settled['stake'].sum()
            total_returned = settled['payout'].sum()
            roi = ((total_returned - total_staked) / total_staked) * 100 if total_staked > 0 else 0
            st.metric("ROI", f"{roi:+.1f}%")

        with col3:
            avg_edge = settled['edge'].mean()
            st.metric("Avg Edge", f"{avg_edge:.1f}%" if pd.notna(avg_edge) else "N/A")
