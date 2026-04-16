from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html


def kpi_card(title: str, value: str, subtitle: str = "", color: str = "primary") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="text-muted small text-uppercase"),
                html.H3(value, className=f"fw-bold text-{color} mb-0"),
                html.Div(subtitle, className="text-muted small") if subtitle else None,
            ]
        ),
        className="shadow-sm h-100",
    )


def error_banner(message: str):
    return dbc.Alert(message, color="danger", className="mt-2")


def portfolio_selector(portfolios: list[dict], value: int | None = None) -> dbc.Select:
    options = [{"label": f"{p['code']} — {p['name']}", "value": p["portfolio_id"]} for p in portfolios]
    return dbc.Select(
        id="portfolio-select",
        options=options,
        value=value if value is not None else (portfolios[0]["portfolio_id"] if portfolios else None),
    )


def fmt_pct(x: float | None, decimals: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x:+.{decimals}f}%"


def fmt_money(x: float | None) -> str:
    if x is None:
        return "—"
    if abs(x) >= 1_000_000:
        return f"${x / 1_000_000:,.2f}M"
    if abs(x) >= 1_000:
        return f"${x / 1_000:,.2f}K"
    return f"${x:,.2f}"
