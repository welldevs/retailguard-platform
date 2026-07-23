"""Global period (year_month) selection, shared across pages via session_state.

`filter_period` is a ROW FILTER only — it never aggregates or recomputes. Marts
without a `year_month` column (per-entity marts) are returned untouched.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

PERIOD_KEY = "period_range"


def set_period(months) -> None:
    st.session_state[PERIOD_KEY] = months


def get_period():
    return st.session_state.get(PERIOD_KEY)


def filter_period(df: pd.DataFrame, col: str = "year_month") -> pd.DataFrame:
    rng = get_period()
    if df.empty or col not in df.columns or not rng:
        return df
    lo, hi = rng
    return df[(df[col] >= lo) & (df[col] <= hi)]
