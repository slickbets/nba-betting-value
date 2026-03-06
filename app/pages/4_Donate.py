"""Donate page - support Slick Bets."""

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.shared import render_sidebar

st.set_page_config(page_title="Donate | Slick Bets", page_icon="💰", layout="wide")
render_sidebar()

st.markdown('<div class="hero-title" style="font-size:2rem;">Support Slick Bets</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-subtitle" style="font-size:0.95rem;">'
    'Slick Bets is a free tool built by a solo developer. If the picks have helped '
    'you win or you just enjoy using the app, consider dropping a tip &mdash; it helps '
    'keep the servers running and the model improving. Every dollar goes directly '
    'toward keeping this project alive. No middleman, no platform fees.'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown("")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        '<div class="game-card" style="text-align:center; padding:2rem;">'
        '<div style="font-size:2.5rem; margin-bottom:0.5rem;">💵</div>'
        '<div class="game-card-matchup" style="margin-bottom:1rem;">Cash App</div>'
        '<a href="https://cash.me/tipslickbets" target="_blank" style="text-decoration:none;">'
        '<div class="badge badge-high" style="font-size:1rem; padding:0.5rem 1.5rem; cursor:pointer;">'
        'Send Tip via Cash App'
        '</div>'
        '</a>'
        '<div style="margin-top:1rem;">'
        '<code style="font-size:1.1rem; background:#2D3340; padding:0.3rem 0.8rem; border-radius:6px; color:#FAFAFA;">$tipslickbets</code>'
        '</div>'
        '<div style="color:#888; font-size:0.8rem; margin-top:0.5rem;">Tap the button or search <b>$tipslickbets</b> in Cash App</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        '<div class="game-card" style="text-align:center; padding:2rem;">'
        '<div style="font-size:2.5rem; margin-bottom:0.5rem;">💙</div>'
        '<div class="game-card-matchup" style="margin-bottom:1rem;">Venmo</div>'
        '<a href="https://venmo.com/slickbets" target="_blank" style="text-decoration:none;">'
        '<div class="badge badge-high" style="font-size:1rem; padding:0.5rem 1.5rem; cursor:pointer; background:rgba(0,140,255,0.15); color:#008CFF; border:1px solid rgba(0,140,255,0.3);">'
        'Send Tip via Venmo'
        '</div>'
        '</a>'
        '<div style="margin-top:1rem;">'
        '<code style="font-size:1.1rem; background:#2D3340; padding:0.3rem 0.8rem; border-radius:6px; color:#FAFAFA;">@slickbets</code>'
        '</div>'
        '<div style="color:#888; font-size:0.8rem; margin-top:0.5rem;">Tap the button or search <b>@slickbets</b> on Venmo</div>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown("")
st.markdown("---")

st.markdown(
    '<div class="section-header">Other Ways to Help</div>'
    '<div style="color:#FAFAFA; line-height:2;">'
    '&bull; <b>Share the app</b> with friends who bet on the NBA<br>'
    '&bull; <b>Submit feedback</b> using the form in the sidebar<br>'
    '&bull; <b>Spread the word</b> on Twitter, Reddit, or your group chat'
    '</div>',
    unsafe_allow_html=True,
)
