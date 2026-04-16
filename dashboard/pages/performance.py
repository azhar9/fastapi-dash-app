from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from dashboard.api_client import ApiError, get_rolling, get_vs_benchmark
from dashboard.components import error_banner

dash.register_page(__name__, path="/performance", name="Performance", order=3)


def layout(**_kwargs):
    return html.Div(
        [
            html.H2("Performance", className="mb-4"),
            dbc.Row(
                [
                    dbc.Col(html.Label("Rolling window (days)"), md="auto", align="center"),
                    dbc.Col(dcc.Slider(
                        id="pf-window",
                        min=20, max=120, step=10, value=60,
                        marks={20: "20", 60: "60", 90: "90", 120: "120"},
                    ), md=6),
                ],
                className="mb-3",
            ),
            dbc.Card(dbc.CardBody([
                html.H5("Cumulative Return vs. Benchmark", className="card-title"),
                dcc.Graph(id="pf-cum-chart", config={"displayModeBar": False}),
            ]), className="shadow-sm mb-3"),
            dbc.Card(dbc.CardBody([
                html.H5("Rolling Volatility & Sharpe", className="card-title"),
                dcc.Graph(id="pf-rolling-chart", config={"displayModeBar": False}),
            ]), className="shadow-sm"),
            html.Div(id="pf-error"),
        ]
    )


@dash.callback(
    Output("pf-cum-chart", "figure"),
    Output("pf-rolling-chart", "figure"),
    Output("pf-error", "children"),
    Input("portfolio-select", "value"),
    Input("pf-window", "value"),
)
def _render(portfolio_id, window_days):
    if portfolio_id is None:
        return go.Figure(), go.Figure(), None
    try:
        cum     = get_vs_benchmark(int(portfolio_id))
        rolling = get_rolling(int(portfolio_id), window_days=int(window_days))
    except ApiError as e:
        return go.Figure(), go.Figure(), error_banner(f"Failed to load performance: {e.detail}")

    cum_df = pd.DataFrame(cum)
    cum_fig = go.Figure()
    if not cum_df.empty:
        cum_df["as_of_date"] = pd.to_datetime(cum_df["as_of_date"])
        cum_fig.add_trace(go.Scatter(
            x=cum_df["as_of_date"], y=cum_df["portfolio_cum_return_pct"],
            mode="lines", name="Portfolio",
        ))
        cum_fig.add_trace(go.Scatter(
            x=cum_df["as_of_date"], y=cum_df["benchmark_cum_return_pct"],
            mode="lines", name="Benchmark", line=dict(dash="dot"),
        ))
    cum_fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=360, yaxis_title="Cumulative Return (%)",
        template="plotly_white",
        legend=dict(orientation="h", y=-0.15),
    )

    rl_df = pd.DataFrame(rolling)
    rl_fig = go.Figure()
    if not rl_df.empty:
        rl_df["as_of_date"] = pd.to_datetime(rl_df["as_of_date"])
        rl_fig.add_trace(go.Scatter(
            x=rl_df["as_of_date"], y=rl_df["rolling_vol_pct"],
            mode="lines", name="Rolling Vol (%)", yaxis="y1",
        ))
        rl_fig.add_trace(go.Scatter(
            x=rl_df["as_of_date"], y=rl_df["rolling_sharpe"],
            mode="lines", name="Rolling Sharpe", yaxis="y2",
        ))
    rl_fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=360,
        yaxis=dict(title="Vol (%)"),
        yaxis2=dict(title="Sharpe", overlaying="y", side="right"),
        template="plotly_white",
        legend=dict(orientation="h", y=-0.15),
    )

    return cum_fig, rl_fig, None
