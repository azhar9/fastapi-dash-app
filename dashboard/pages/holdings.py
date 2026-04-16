from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, dash_table, dcc, html

from dashboard.api_client import ApiError, get_holdings, get_sectors
from dashboard.components import error_banner

dash.register_page(__name__, path="/holdings", name="Holdings", order=2)


def layout(**_kwargs):
    return html.Div(
        [
            html.H2("Holdings", className="mb-4"),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H5("Sector Allocation", className="card-title"),
                                dcc.Graph(id="hl-sector-chart", config={"displayModeBar": False}),
                            ]),
                            className="shadow-sm",
                        ),
                        md=5,
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H5("Positions", className="card-title"),
                                html.Div(id="hl-table"),
                            ]),
                            className="shadow-sm",
                        ),
                        md=7,
                    ),
                ],
                className="g-3",
            ),
            html.Div(id="hl-error"),
        ]
    )


@dash.callback(
    Output("hl-sector-chart", "figure"),
    Output("hl-table", "children"),
    Output("hl-error", "children"),
    Input("portfolio-select", "value"),
)
def _render(portfolio_id):
    if portfolio_id is None:
        return go.Figure(), html.Div(), None
    try:
        sectors = get_sectors(int(portfolio_id))
        rows    = get_holdings(int(portfolio_id))
    except ApiError as e:
        return go.Figure(), html.Div(), error_banner(f"Failed to load holdings: {e.detail}")

    fig = go.Figure(
        go.Pie(
            labels=[s["sector"] for s in sectors],
            values=[s["weight_pct"] for s in sectors],
            hole=0.55,
            textinfo="label+percent",
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=400,
        showlegend=False,
        template="plotly_white",
    )

    table = dash_table.DataTable(
        data=rows,
        columns=[
            {"name": "Ticker",      "id": "ticker"},
            {"name": "Name",        "id": "name"},
            {"name": "Sector",      "id": "sector"},
            {"name": "Weight (%)",  "id": "weight_pct",    "type": "numeric", "format": {"specifier": ".2f"}},
            {"name": "Price",       "id": "price",         "type": "numeric", "format": {"specifier": ",.2f"}},
            {"name": "Mkt Value",   "id": "market_value",  "type": "numeric", "format": {"specifier": ",.0f"}},
        ],
        sort_action="native",
        filter_action="native",
        page_size=15,
        style_cell={"padding": "6px", "fontSize": "13px"},
        style_header={"fontWeight": "600", "backgroundColor": "#f8f9fa"},
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#fafbfc"}
        ],
    )
    return fig, table, None
