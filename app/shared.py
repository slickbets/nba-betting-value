"""Shared UI components across all pages."""

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON, now_ct
from src.utils.feedback import submit_feedback


def render_sidebar():
    """Render the shared sidebar with navigation and feedback form."""
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
