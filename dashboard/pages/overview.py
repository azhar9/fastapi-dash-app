from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from dashboard.api_client import ApiError, get_kpis, get_nav
from dashboard.components import error_banner, fmt_money, fmt_pct, kpi_card

dash.register_page(__name__, path="/", name="Overview", order=1)


def layout(**_kwargs):
    return html.Div(
        [
            html.H2("Portfolio Overview", className="mb-4"),
            dbc.Row(id="ov-kpi-row", className="g-3 mb-4"),
            dbc.Card(
                dbc.CardBody([
                    html.H5("Net Asset Value (rebased)", className="card-title"),
                    dcc.Graph(id="ov-nav-chart", config={"displayModeBar": False}),
                ]),
                className="shadow-sm",
            ),
            html.Div(id="ov-error"),
        ]
    )


@dash.callback(
    Output("ov-kpi-row", "children"),
    Output("ov-nav-chart", "figure"),
    Output("ov-error", "children"),
    Input("portfolio-select", "value"),
)
def _render(portfolio_id):
    if portfolio_id is None:
        return [], go.Figure(), None
    try:
        kpis = get_kpis(int(portfolio_id))
        nav = get_nav(int(portfolio_id))
    except ApiError as e:
        return [], go.Figure(), error_banner(f"Failed to load data: {e.detail}")

    cards = dbc.Row(
        [
            dbc.Col(kpi_card("NAV", f"{kpis['nav']:.4f}", f"as of {kpis['as_of_date']}"),  md=3),
            dbc.Col(kpi_card("Day Return",  fmt_pct(kpis.get("day_return_pct")), color="success" if (kpis.get("day_return_pct") or 0) >= 0 else "danger"), md=3),
            dbc.Col(kpi_card("MTD Return",  fmt_pct(kpis.get("mtd_return_pct")), color="success" if (kpis.get("mtd_return_pct") or 0) >= 0 else "danger"), md=3),
            dbc.Col(kpi_card("YTD Return",  fmt_pct(kpis.get("ytd_return_pct")), color="success" if (kpis.get("ytd_return_pct") or 0) >= 0 else "danger"), md=3),
        ],
        className="g-3 mb-2",
    )
    aum_row = dbc.Row(
        dbc.Col(kpi_card("Notional AUM", fmt_money(kpis.get("aum_usd")), "USD, demo = NAV × 1M"), md=3)
    )

    df = pd.DataFrame(nav)
    fig = go.Figure()
    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        fig.add_trace(go.Scatter(x=df["as_of_date"], y=df["nav"], mode="lines", name="NAV"))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
        xaxis_title=None,
        yaxis_title="NAV",
        template="plotly_white",
    )

    return [cards, aum_row], fig, None
