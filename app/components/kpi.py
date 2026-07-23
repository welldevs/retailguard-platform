"""KPI tile row. Values are formatted upstream; this component only lays them out."""
from __future__ import annotations

import streamlit as st


def kpi_row(items: list[dict]) -> None:
    """Render a row of metric tiles. Each item: {label, value, delta?, help?}."""
    if not items:
        return
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        col.metric(
            it["label"],
            it.get("value", "—"),
            delta=it.get("delta"),
            help=it.get("help"),
        )
