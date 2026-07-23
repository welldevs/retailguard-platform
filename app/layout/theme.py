"""Professional, low-noise executive theme. Native Streamlit only — no plotly,
no gauges, no 3D, no animations. Restrained palette; light/dark aware.
"""
from __future__ import annotations

import streamlit as st

APP_TITLE = "Executive Decision Platform"
APP_ICON = "🛒"

_CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1440px;}
[data-testid="stMetric"] {
    background: rgba(128,128,128,0.06);
    border: 1px solid rgba(128,128,128,0.16);
    border-radius: 10px; padding: 14px 16px;
}
[data-testid="stMetricLabel"] {opacity: .72; font-size: .8rem;}
h1 {font-size: 1.7rem; font-weight: 700;}
h2, h3 {font-size: 1.12rem; font-weight: 600; margin-top: 1.1rem;}
hr {margin: .7rem 0;}
#MainMenu, footer {visibility: hidden;}
</style>
"""


def configure_page() -> None:
    st.set_page_config(
        page_title=APP_TITLE, page_icon=APP_ICON,
        layout="wide", initial_sidebar_state="expanded",
    )


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, description: str) -> None:
    st.title(title)
    st.caption(description)
    st.divider()
