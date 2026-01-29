"""NBA Betting Value Finder - Streamlit Application."""

import streamlit as st
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON

# Page configuration
st.set_page_config(
    page_title="NBA Betting Value Finder",
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
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .value-positive {
        color: #28a745;
        font-weight: bold;
    }
    .value-negative {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # Sidebar
    with st.sidebar:
        st.title("🏀 NBA Value Finder")
        st.markdown("---")

        st.markdown(f"**Season:** {CURRENT_SEASON}")
        st.markdown(f"**Date:** {datetime.now().strftime('%B %d, %Y')}")

        st.markdown("---")
        st.markdown("### Navigation")
        st.markdown("""
        - **Today's Bets** - Find value bets for today's games
        - **Bet Log** - Track your bets and results
        - **Performance** - View historical performance
        - **Team Ratings** - Current Elo rankings
        """)

        st.markdown("---")
        st.markdown("### Settings")

        min_edge = st.slider(
            "Minimum Edge %",
            min_value=1.0,
            max_value=15.0,
            value=3.0,
            step=0.5,
            help="Only show bets with at least this much edge"
        )
        st.session_state['min_edge'] = min_edge

        st.markdown("---")
        st.markdown(
            "Built with [Streamlit](https://streamlit.io) | "
            "Data: [nba_api](https://github.com/swar/nba_api)"
        )

    # Main content
    st.markdown('<p class="main-header">NBA Betting Value Finder</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">'
        'Find value bets by comparing Elo-based predictions to sportsbook odds'
        '</p>',
        unsafe_allow_html=True
    )

    # Quick stats row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Today's Games",
            value="--",
            help="Number of games scheduled today"
        )

    with col2:
        st.metric(
            label="Value Bets Found",
            value="--",
            help="Bets with edge above threshold"
        )

    with col3:
        st.metric(
            label="Season Record",
            value="--",
            help="Win-Loss record on value bets"
        )

    with col4:
        st.metric(
            label="Season ROI",
            value="--",
            help="Return on investment this season"
        )

    st.markdown("---")

    # Getting started section
    st.markdown("### Getting Started")

    st.markdown("""
    Welcome to the NBA Betting Value Finder! This tool helps you identify potentially
    profitable betting opportunities by:

    1. **Calculating Elo ratings** for all NBA teams based on historical performance
    2. **Predicting win probabilities** for upcoming games
    3. **Comparing to sportsbook odds** to find edges
    4. **Tracking your bets** to measure performance over time

    Use the navigation in the sidebar to explore different features.
    """)

    # Setup instructions
    with st.expander("📋 First-time Setup"):
        st.markdown("""
        **1. Initialize the database:**
        ```bash
        python scripts/init_db.py
        ```

        **2. Backfill historical data and calculate Elo ratings:**
        ```bash
        python scripts/backfill_history.py
        ```

        **3. Configure your Odds API key:**
        - Sign up at [The Odds API](https://the-odds-api.com)
        - Add your key to the `.env` file:
        ```
        ODDS_API_KEY=your_key_here
        ```

        **4. You're ready!** Navigate to "Today's Bets" to find value.
        """)

    # Value betting explanation
    with st.expander("📚 What is Value Betting?"):
        st.markdown("""
        **Value betting** is a strategy where you bet when you believe the true
        probability of an outcome is higher than what the odds imply.

        **Example:**
        - Your model says Team A has a 60% chance to win
        - The sportsbook offers +120 odds (implied probability: 45.5%)
        - Your **edge** is 60% - 45.5% = **14.5%**
        - This is a value bet because you're getting better odds than the true probability

        **How this app calculates value:**
        1. We use Elo ratings to estimate each team's strength
        2. We convert Elo differences to win probabilities
        3. We compare our probabilities to sportsbook odds
        4. We flag bets where our model gives > 3% edge

        **Important:** No model is perfect. Use this as one input in your decision-making,
        not as a guaranteed winning strategy.
        """)

    # Elo explanation
    with st.expander("📊 How Elo Ratings Work"):
        st.markdown("""
        **Elo** is a rating system originally designed for chess that we've adapted for NBA.

        **Key concepts:**
        - Every team starts at **1500** Elo points
        - After each game, the winner gains points and loser loses points
        - The amount of points exchanged depends on the **expected outcome**
        - Beating a strong team = more points gained
        - Losing to a weak team = more points lost

        **Converting Elo to Win Probability:**
        ```
        Win Probability = 1 / (1 + 10^((Opponent_Elo - Your_Elo) / 400))
        ```

        **Home Court Advantage:**
        We add **67.5 Elo points** to the home team to account for home court advantage
        (roughly equivalent to a 2.7 point spread, reflecting modern NBA trends).

        **Converting to Spread:**
        We estimate point spread as: `Elo Difference / 25`

        So a team with +125 Elo advantage (after home court) would be favored by ~5 points.
        """)


if __name__ == "__main__":
    main()
