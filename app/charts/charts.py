"""Chart helpers over native Streamlit. Every chart plots columns that already
exist in a mart — no metric is derived here.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


def line_chart(df: pd.DataFrame, x: str, ys, height: int = 300) -> None:
    ys = [c for c in (ys if isinstance(ys, (list, tuple)) else [ys]) if c in df.columns]
    if df.empty or x not in df.columns or not ys:
        st.caption("Sem dados para exibir.")
        return
    st.line_chart(df.set_index(x)[ys], height=height)


def bar_chart(df: pd.DataFrame, x: str, y: str, height: int = 320) -> None:
    if df.empty or x not in df.columns or y not in df.columns:
        st.caption("Sem dados para exibir.")
        return
    st.bar_chart(df.set_index(x)[y], height=height)
