"""Display formatters. Presentation only — they never change a value, only render it."""
from __future__ import annotations


def eur(value, decimals: int = 0) -> str:
    try:
        return f"€ {float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def pct(value, decimals: int = 1) -> str:
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def num(value) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"
