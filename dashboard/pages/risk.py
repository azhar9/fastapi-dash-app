from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from dashboard.api_client import ApiError, get_risk
from dashboard.components import error_banner, fmt_pct, kpi_card

dash.register_page(__name__, path="/risk", name="Risk", order=4)


def layout(**_kwargs):
    return html.Div(
        [
            html.H2("Risk Metrics", className="mb-4"),
            dbc.Row(
                [
                    dbc.Col(html.Label("Lookback window (days)"), md="auto", align="center"),
                    dbc.Col(dcc.Dropdown(
                        id="rk-window",
                        options=[
                            {"label": "90",   "value": 90},
                            {"label": "180",  "value": 180},
                            {"label": "365",  "value": 365},
                            {"label": "730",  "value": 730},
                        ],
                        value=365,
                        clearable=False,
                    ), md=3),
                ],
                className="mb-3",
            ),
            dbc.Row(id="rk-cards", className="g-3"),
            html.Div(id="rk-error"),
            html.Div(
                html.Small(
                    "Notes: Volatility and return are annualised assuming 252 trading days. "
                    "VaR is historical (5th percentile of daily returns). "
                    "Beta is vs. the portfolio's benchmark. Risk-free rate is assumed zero.",
                    className="text-muted",
                ),
                className="mt-3",
            ),
        ]
    )


@dash.callback(
    Output("rk-cards", "children"),
    Output("rk-error", "children"),
    Input("portfolio-select", "value"),
    Input("rk-window", "value"),
)
def _render(portfolio_id, window_days):
    if portfolio_id is None:
        return [], None
    try:
        r = get_risk(int(portfolio_id), window_days=int(window_days))
    except ApiError as e:
        return [], error_banner(f"Failed to load risk data: {e.detail}")

    cards = [
        dbc.Col(kpi_card("Ann. Return",    fmt_pct(r.get("annualised_return_pct")),
                         color="success" if (r.get("annualised_return_pct") or 0) >= 0 else "danger"), md=4),
        dbc.Col(kpi_card("Ann. Volatility", fmt_pct(r.get("annualised_vol_pct")), color="warning"),  md=4),
        dbc.Col(kpi_card("Sharpe Ratio",   f"{r.get('sharpe', 0):.2f}"),                              md=4),
        dbc.Col(kpi_card("Max Drawdown",   fmt_pct(r.get("max_drawdown_pct")),     color="danger"),  md=4),
        dbc.Col(kpi_card("VaR 95 (daily)", fmt_pct(r.get("var_95_pct")),           color="danger"),  md=4),
        dbc.Col(kpi_card("Beta vs Bench",  f"{r.get('beta_vs_benchmark', 0):.2f}"),                  md=4),
    ]
    return cards, None
