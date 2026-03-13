"""Donate page - support Slick Bets."""

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.shared import render_sidebar

st.set_page_config(page_title="Support | Slick Bets", page_icon=str(Path(__file__).parent.parent.parent / "assets" / "favicon.png"), layout="wide")
render_sidebar()

st.markdown('<div class="page-header">Support Slick Bets</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="page-desc">'
    'Slick Bets is a free tool built by a solo developer. If the picks have helped '
    'you win or you just enjoy using the app, consider dropping a tip. Every dollar goes '
    'directly toward keeping this project alive \u2014 servers, data, and model improvements. '
    'No middleman, no platform fees.'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown("")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        '<div class="donate-card">'
        '<div class="donate-card-title">Cash App</div>'
        '<a href="https://cash.me/tipslickbets" target="_blank" class="donate-btn">Send Tip via Cash App</a>'
        '<div class="donate-card-handle">$tipslickbets</div>'
        '<div style="color:#7A7770; font-size:0.78rem; margin-top:0.6rem;">Tap the button or search $tipslickbets in Cash App</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        '<div class="donate-card">'
        '<div class="donate-card-title">Venmo</div>'
        '<a href="https://venmo.com/slickbets" target="_blank" class="donate-btn donate-btn-venmo">Send Tip via Venmo</a>'
        '<div class="donate-card-handle">@slickbets</div>'
        '<div style="color:#7A7770; font-size:0.78rem; margin-top:0.6rem;">Tap the button or search @slickbets on Venmo</div>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown("")
st.markdown("---")

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Other Ways to Help</div>', unsafe_allow_html=True)
st.markdown(
    '<div style="color:var(--text); line-height:2; font-family:\'Outfit\',sans-serif; font-size:0.9rem;">'
    '&bull; <b>Share the app</b> with friends who bet on the NBA<br>'
    '&bull; <b>Submit feedback</b> using the form in the sidebar<br>'
    '&bull; <b>Spread the word</b> on Twitter, Reddit, or your group chat'
    '</div>',
    unsafe_allow_html=True,
)
