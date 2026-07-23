"""Consistent dataframe rendering."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def table(df: pd.DataFrame, **kwargs) -> None:
    st.dataframe(df, use_container_width=True, hide_index=True, **kwargs)
