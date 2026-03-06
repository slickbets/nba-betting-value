"""Donate page - support Slick Bets."""

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.shared import render_sidebar

st.set_page_config(page_title="Donate | Slick Bets", page_icon="💰", layout="wide")
render_sidebar()

st.title("💰 Support Slick Bets")

st.markdown("""
Slick Bets is a free tool built by a solo developer. If the picks have helped
you win or you just enjoy using the app, consider dropping a tip — it helps
keep the servers running and the model improving.

Every dollar goes directly toward keeping this project alive. No middleman, no
platform fees.
""")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 💵 Cash App")
    st.markdown(
        '<a href="https://cash.me/tipslickbets" target="_blank">'
        '<img src="https://img.shields.io/badge/Cash_App-$tipslickbets-00C244?style=for-the-badge&logo=cashapp&logoColor=white" />'
        '</a>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.code("$tipslickbets", language=None)
    st.caption("Tap the badge or search **$tipslickbets** in Cash App")

with col2:
    st.markdown("### 💙 Venmo")
    st.markdown(
        '<a href="https://venmo.com/slickbets" target="_blank">'
        '<img src="https://img.shields.io/badge/Venmo-@slickbets-008CFF?style=for-the-badge&logo=venmo&logoColor=white" />'
        '</a>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.code("@slickbets", language=None)
    st.caption("Tap the badge or search **@slickbets** on Venmo")

st.markdown("---")

st.markdown("""
### 🙏 Other Ways to Help

- **Share the app** with friends who bet on the NBA
- **Submit feedback** using the form in the sidebar — bug reports and feature ideas make the model better
- **Spread the word** on Twitter, Reddit, or your group chat
""")
