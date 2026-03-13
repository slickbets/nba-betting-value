"""Shared UI components across all pages."""

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON, now_ct
from src.utils.feedback import submit_feedback

FONT_PRECONNECT = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
)

GLOBAL_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Outfit:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --bg: #141414;
    --surface: #1C1C1C;
    --border: #2A2A2A;
    --text: #E0DCD5;
    --text-muted: #7A7770;
    --accent: #C9A84C;
    --positive: #8BA888;
    --negative: #B87366;
    --neutral: #6B6760;
    color-scheme: dark;
}

/* Streamlit overrides */
.stApp, [data-testid="stAppViewContainer"] {
    background-color: var(--bg) !important;
}
[data-testid="stSidebar"] {
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
.block-container {
    padding-top: 2rem;
    max-width: 1100px;
}
[data-testid="stHeader"] {
    background-color: var(--bg) !important;
}

/* Base typography — exclude icon fonts */
html, body, [class*="css"], .stMarkdown, p, li, td, th, label,
[data-testid="stMarkdownContainer"] span {
    font-family: 'Outfit', sans-serif !important;
    color: var(--text);
}
/* Preserve Streamlit icon fonts */
[data-testid="stSidebarCollapseButton"] *,
.material-symbols-rounded,
[data-testid="stExpanderToggleIcon"] *,
button[kind="icon"] * {
    font-family: 'Material Symbols Rounded', sans-serif !important;
}
h1, h2, h3, h4, h5, h6,
[data-testid="stHeadingWithActionElements"] {
    font-family: 'DM Serif Display', serif !important;
    color: var(--text) !important;
    text-wrap: balance;
    font-weight: 400 !important;
}

/* Masthead */
.masthead {
    padding-bottom: 1.2rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.5rem;
}
.masthead-title {
    font-family: 'DM Serif Display', serif;
    font-size: 2.4rem;
    font-weight: 400;
    color: var(--text);
    letter-spacing: 0.02em;
    line-height: 1;
    margin: 0;
    text-wrap: balance;
    display: flex;
    align-items: center;
}
.masthead-dateline {
    font-family: 'Outfit', sans-serif;
    font-size: 0.78rem;
    color: var(--text-muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: 0.5rem;
}
.masthead-desc {
    font-family: 'Outfit', sans-serif;
    font-size: 0.88rem;
    color: var(--text-muted);
    font-weight: 300;
    margin-top: 0.3rem;
    line-height: 1.6;
}
.masthead-desc a {
    color: var(--accent);
    text-decoration: none;
    font-weight: 400;
}
.masthead-desc a:hover {
    text-decoration: underline;
}

/* Page headers (non-home pages) */
.page-header {
    font-family: 'DM Serif Display', serif;
    font-size: 1.8rem;
    font-weight: 400;
    color: var(--text);
    margin: 0 0 0.3rem 0;
    text-wrap: balance;
}
.page-desc {
    font-family: 'Outfit', sans-serif;
    font-size: 0.85rem;
    color: var(--text-muted);
    font-weight: 300;
    margin-bottom: 1.2rem;
    line-height: 1.5;
}

/* Section headers with rule */
.section-rule {
    border: 0;
    border-top: 1px solid var(--border);
    margin: 2rem 0 0.5rem 0;
}
.section-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1.1rem;
    font-weight: 400;
    color: var(--text);
    margin: 0 0 1rem 0;
    text-wrap: balance;
}

/* Accuracy strip */
.accuracy-strip {
    display: flex;
    gap: 2.5rem;
    padding: 1rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
}
.accuracy-stat {
    display: flex;
    flex-direction: column;
}
.accuracy-stat-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.3rem;
    font-weight: 500;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
}
.accuracy-stat-label {
    font-family: 'Outfit', sans-serif;
    font-size: 0.7rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 0.15rem;
}
.accuracy-stat-detail {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}

/* Game rows */
.game-row-header {
    display: grid;
    grid-template-columns: 1.5fr 1fr 0.6fr 0.6fr 1fr 0.5fr 0.7fr;
    padding: 0.5rem 0.4rem;
    border-bottom: 1px solid var(--border);
}
.game-row-header span {
    font-family: 'Outfit', sans-serif;
    font-size: 0.65rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.game-row {
    display: grid;
    grid-template-columns: 1.5fr 1fr 0.6fr 0.6fr 1fr 0.5fr 0.7fr;
    align-items: center;
    padding: 0.65rem 0.4rem;
    border-bottom: 1px solid var(--border);
    touch-action: manipulation;
    transition: background-color 0.12s ease;
}
.game-row:hover {
    background: var(--surface);
}
.game-matchup {
    font-family: 'Outfit', sans-serif;
    font-size: 0.92rem;
    font-weight: 500;
    color: var(--text);
}
.game-time {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}
.game-score {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}
.game-score-live {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
}
.game-pick {
    font-family: 'Outfit', sans-serif;
    font-size: 0.88rem;
    font-weight: 500;
    color: var(--text);
}
.game-num {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    font-weight: 400;
    color: var(--text);
    font-variant-numeric: tabular-nums;
}
.game-num-accent {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
}

/* Confidence dots */
.conf-dots {
    display: inline-flex;
    gap: 3px;
    align-items: center;
}
.conf-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
}
.conf-dot-filled { background: var(--accent); }
.conf-dot-empty { background: var(--border); }

/* Result indicators */
.result-w {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--positive);
}
.result-l {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--negative);
}
.result-live {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--accent);
    letter-spacing: 0.04em;
}
.result-pending {
    color: var(--neutral);
}

/* Stat cards */
.stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 1rem 1.2rem;
}
.stat-card-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.5rem;
    font-weight: 500;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.stat-card-label {
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 0.4rem;
}
.stat-card-detail {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    margin-top: 0.15rem;
}

/* Detail labels */
.detail-label {
    font-family: 'Outfit', sans-serif;
    font-size: 0.7rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.detail-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.88rem;
    color: var(--text);
    font-variant-numeric: tabular-nums;
}

/* Tier labels */
.tier-label {
    font-family: 'Outfit', sans-serif;
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 0.15rem 0.5rem;
    border-radius: 2px;
    display: inline-block;
}
.tier-championship { background: rgba(201,168,76,0.12); color: var(--accent); }
.tier-contender { background: rgba(192,192,192,0.08); color: #B0ADA6; }
.tier-playoff { background: rgba(139,168,136,0.08); color: var(--positive); }
.tier-bubble { background: rgba(122,119,112,0.08); color: var(--text-muted); }
.tier-rebuilding { background: rgba(107,103,96,0.06); color: var(--neutral); }

/* Donate */
.donate-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 2rem;
    text-align: center;
    transition: border-color 0.15s ease;
}
.donate-card:hover {
    border-color: var(--accent);
}
.donate-card-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1.15rem;
    color: var(--text);
    margin-bottom: 1rem;
}
.donate-card-handle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.95rem;
    color: var(--text);
    background: var(--bg);
    padding: 0.3rem 0.8rem;
    border-radius: 2px;
    display: inline-block;
    margin-top: 0.8rem;
}
.donate-btn {
    display: inline-block;
    font-family: 'Outfit', sans-serif;
    font-size: 0.82rem;
    font-weight: 500;
    letter-spacing: 0.03em;
    padding: 0.5rem 1.5rem;
    border: 1px solid var(--accent);
    color: var(--accent);
    border-radius: 2px;
    text-decoration: none;
    transition: background-color 0.15s ease, color 0.15s ease;
}
.donate-btn:hover {
    background: var(--accent);
    color: var(--bg);
    text-decoration: none;
    opacity: 1;
}
.donate-btn-venmo {
    border-color: #6B8CC7;
    color: #6B8CC7;
}
.donate-btn-venmo:hover {
    background: #6B8CC7;
    color: var(--bg);
}

/* Injury items */
.injury-item {
    font-family: 'Outfit', sans-serif;
    font-size: 0.82rem;
    color: var(--text-muted);
    padding: 0.1rem 0;
}
.injury-impact {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: var(--negative);
    font-variant-numeric: tabular-nums;
}

/* Confidence row (accuracy page) */
.conf-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.7rem 0;
    border-bottom: 1px solid var(--border);
}
.conf-row-label {
    font-family: 'Outfit', sans-serif;
    font-size: 0.9rem;
    font-weight: 400;
    color: var(--text);
}
.conf-row-count {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    margin-left: 0.5rem;
}
.conf-row-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1rem;
    font-weight: 500;
    color: var(--text);
    font-variant-numeric: tabular-nums;
}

/* Override Streamlit components */
[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 1.4rem !important;
    font-weight: 500 !important;
    font-variant-numeric: tabular-nums !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'Outfit', sans-serif !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-size: 0.7rem !important;
}
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 3px !important;
    background: transparent !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.85rem !important;
}
[data-testid="stDataFrame"] {
    font-variant-numeric: tabular-nums;
}
hr {
    border: 0;
    border-top: 1px solid var(--border);
    margin: 1rem 0;
}
a {
    color: var(--accent);
    text-decoration: none;
    transition: opacity 0.12s ease;
}
a:hover {
    opacity: 0.8;
}
[data-testid="stAlert"] {
    border-radius: 3px !important;
    font-family: 'Outfit', sans-serif !important;
}

/* Responsive */
@media (max-width: 768px) {
    .game-row, .game-row-header {
        grid-template-columns: 1.5fr 0.8fr 0.6fr 0.6fr 0.6fr;
    }
    .game-row > :nth-child(6),
    .game-row > :nth-child(7),
    .game-row-header > :nth-child(6),
    .game-row-header > :nth-child(7) {
        display: none;
    }
    .accuracy-strip { gap: 1.5rem; }
    .masthead-title { font-size: 1.8rem; }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.01ms !important;
    }
}
</style>"""


def inject_css():
    """Inject global CSS and font preconnect."""
    st.markdown(FONT_PRECONNECT, unsafe_allow_html=True)
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def confidence_badge(level: str) -> str:
    """Return HTML for confidence dots."""
    if level == "High":
        dots = ('<span class="conf-dot conf-dot-filled"></span>'
                '<span class="conf-dot conf-dot-filled"></span>'
                '<span class="conf-dot conf-dot-filled"></span>')
    elif level == "Medium":
        dots = ('<span class="conf-dot conf-dot-filled"></span>'
                '<span class="conf-dot conf-dot-filled"></span>'
                '<span class="conf-dot conf-dot-empty"></span>')
    else:
        dots = ('<span class="conf-dot conf-dot-filled"></span>'
                '<span class="conf-dot conf-dot-empty"></span>'
                '<span class="conf-dot conf-dot-empty"></span>')
    return f'<span class="conf-dots">{dots}</span>'


def result_badge(result: str) -> str:
    """Return HTML for a result indicator."""
    if result == "Correct":
        return '<span class="result-w">W</span>'
    elif result == "Wrong":
        return '<span class="result-l">L</span>'
    elif result == "Live":
        return '<span class="result-live">LIVE</span>'
    return '<span class="result-pending">&mdash;</span>'


def render_sidebar():
    """Render the shared sidebar."""
    inject_css()
    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'DM Serif Display\',serif; font-size:1.4rem; color:#E0DCD5; margin-bottom:0.2rem;">Slick Bets</div>'
            '<div style="font-family:\'Outfit\',sans-serif; font-size:0.72rem; color:#7A7770; text-transform:uppercase; letter-spacing:0.06em;">'
            f'{CURRENT_SEASON} Season</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown(
            f'<div style="font-family:\'Outfit\',sans-serif; font-size:0.82rem; color:#7A7770;">'
            f'{now_ct().strftime("%B %d, %Y")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown(
            '<div style="font-family:\'DM Serif Display\',serif; font-size:1rem; color:#E0DCD5; margin-bottom:0.5rem;">Feedback</div>',
            unsafe_allow_html=True,
        )
        with st.form("feedback_form", clear_on_submit=True):
            fb_category = st.selectbox("Type", ["Bug", "Feature Request", "General Feedback"])
            fb_title = st.text_input("Title")
            fb_description = st.text_area("Details", height=100)
            fb_submitted = st.form_submit_button("Submit")
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
            '<div style="font-family:\'Outfit\',sans-serif; font-size:0.72rem; color:#6B6760;">'
            '<a href="https://slick-bets.com" style="color:#C9A84C; text-decoration:none;">slick-bets.com</a>'
            '</div>',
            unsafe_allow_html=True,
        )
