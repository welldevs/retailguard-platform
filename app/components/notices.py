"""Architectural-limitation notices + a resilient section runner.

`limitations()` surfaces KPIs that are NOT directly available in a mart. By
design they are never recomputed in Python — they are declared here and tracked
in app/TODO.md, feeding the mart_executive_mensal recommendation.
"""
from __future__ import annotations

from typing import Callable

import streamlit as st


def safe(section: Callable[[], None]) -> None:
    """Run a section; on failure show the error instead of crashing the page."""
    try:
        section()
    except Exception as exc:  # noqa: BLE001 — a serving page should degrade, not crash
        st.warning(f"⚠️ Seção indisponível: {type(exc).__name__}: {exc}")


def limitations(items: list[str]) -> None:
    if not items:
        return
    with st.expander(f"🔒 Limitações arquiteturais nesta visão ({len(items)})"):
        for it in items:
            st.markdown(f"- {it}")
        st.caption(
            "Estas métricas exigiriam recalcular ou juntar KPIs na camada de "
            "apresentação. Por decisão de arquitetura, a lógica permanece no dbt. "
            "Registrado em `app/TODO.md`."
        )
