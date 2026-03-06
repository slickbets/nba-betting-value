"""Shared UI components across all pages."""

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON, now_ct
from src.utils.feedback import submit_feedback

GLOBAL_CSS = """
<style>
    /* Game cards */
    .game-card {
        background: #1A1F2B;
        border: 1px solid #2D3340;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 0.8rem;
        transition: border-color 0.2s;
    }
    .game-card:hover {
        border-color: #00C853;
    }
    .game-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.6rem;
    }
    .game-card-matchup {
        font-size: 1.15rem;
        font-weight: 600;
        color: #FAFAFA;
    }
    .game-card-time {
        font-size: 0.85rem;
        color: #888;
    }
    .game-card-body {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .game-card-stat {
        text-align: center;
    }
    .game-card-stat-label {
        font-size: 0.7rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .game-card-stat-value {
        font-size: 1rem;
        font-weight: 600;
        color: #FAFAFA;
    }

    /* Confidence badges */
    .badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .badge-high {
        background: rgba(0, 200, 83, 0.15);
        color: #00C853;
        border: 1px solid rgba(0, 200, 83, 0.3);
    }
    .badge-medium {
        background: rgba(255, 193, 7, 0.15);
        color: #FFC107;
        border: 1px solid rgba(255, 193, 7, 0.3);
    }
    .badge-low {
        background: rgba(158, 158, 158, 0.15);
        color: #9E9E9E;
        border: 1px solid rgba(158, 158, 158, 0.3);
    }

    /* Result badges */
    .badge-correct {
        background: rgba(0, 200, 83, 0.15);
        color: #00C853;
        border: 1px solid rgba(0, 200, 83, 0.3);
    }
    .badge-wrong {
        background: rgba(244, 67, 54, 0.15);
        color: #F44336;
        border: 1px solid rgba(244, 67, 54, 0.3);
    }
    .badge-live {
        background: rgba(255, 193, 7, 0.15);
        color: #FFC107;
        border: 1px solid rgba(255, 193, 7, 0.3);
    }

    /* Score display */
    .score-final {
        color: #FAFAFA;
        font-weight: 600;
    }
    .score-live {
        color: #FFC107;
        font-weight: 600;
    }

    /* Accuracy hero card */
    .accuracy-card {
        background: linear-gradient(135deg, #1A1F2B 0%, #0E1117 100%);
        border: 1px solid #2D3340;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
    }
    .accuracy-big {
        font-size: 2.8rem;
        font-weight: 700;
        color: #00C853;
        line-height: 1;
    }
    .accuracy-label {
        font-size: 0.85rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.3rem;
    }
    .accuracy-detail {
        font-size: 0.95rem;
        color: #FAFAFA;
        margin-top: 0.2rem;
    }

    /* Hero section */
    .hero-title {
        font-size: 2.8rem;
        font-weight: 700;
        color: #FAFAFA;
        margin-bottom: 0.3rem;
        line-height: 1.1;
    }
    .hero-subtitle {
        font-size: 1.1rem;
        color: #888;
        margin-bottom: 1.5rem;
        line-height: 1.5;
    }
    .hero-tip {
        font-size: 0.9rem;
        color: #888;
    }
    .hero-tip a {
        color: #00C853;
        text-decoration: none;
        font-weight: 600;
    }
    .hero-tip a:hover {
        text-decoration: underline;
    }

    /* Section headers */
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #FAFAFA;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }

    /* Hide default streamlit padding for cleaner look */
    .block-container {
        padding-top: 2rem;
    }

    /* Metric styling */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
    }
</style>
"""


def inject_css():
    """Inject global CSS styles."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def confidence_badge(level: str) -> str:
    """Return HTML for a confidence badge."""
    css_class = f"badge-{level.lower()}"
    return f'<span class="badge {css_class}">{level}</span>'


def result_badge(result: str) -> str:
    """Return HTML for a result badge."""
    if result == "Correct":
        return '<span class="badge badge-correct">W</span>'
    elif result == "Wrong":
        return '<span class="badge badge-wrong">L</span>'
    elif result == "Live":
        return '<span class="badge badge-live">LIVE</span>'
    return '<span style="color: #888;">-</span>'


def render_sidebar():
    """Render the shared sidebar with navigation and feedback form."""
    inject_css()
    with st.sidebar:
        st.title("🏀 Slick Bets")
        st.markdown("---")

        st.markdown(f"**Season:** {CURRENT_SEASON}")
        st.markdown(f"**Date:** {now_ct().strftime('%B %d, %Y')}")

        st.markdown("---")
        st.markdown("### Feedback")
        with st.form("feedback_form", clear_on_submit=True):
            fb_category = st.selectbox("Type", ["Bug", "Feature Request", "General Feedback"])
            fb_title = st.text_input("Title")
            fb_description = st.text_area("Details", height=100)
            fb_submitted = st.form_submit_button("Submit Feedback")
            if fb_submitted:
                if fb_title.strip():
                    if submit_feedback(fb_title.strip(), fb_description.strip(), fb_category):
                        st.success("Thanks! Feedback submitted.")
                    else:
                        st.error("Failed to submit. Try again later.")
                else:
                    st.warning("Please add a title.")

        st.markdown("---")
        st.markdown(
            "Built with [Streamlit](https://streamlit.io) | "
            "[slick-bets.com](https://slick-bets.com)"
        )
