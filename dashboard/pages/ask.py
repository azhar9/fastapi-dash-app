from __future__ import annotations

import json

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dash_table, dcc, html

from dashboard.api_client import ApiError
from dashboard.api_client import ask as api_ask
from dashboard.components import error_banner

dash.register_page(__name__, path="/ask", name="Ask (AI)", order=5)

EXAMPLES = [
    "Top 5 holdings in the Tech portfolio by weight",
    "Show the NAV of GAM_CORE over the last year",
    "Which sector has the highest average weight across all portfolios?",
    "Compare cumulative returns of GAM_TECH vs GAM_DIVIDEND since inception",
    "List the 10 most volatile stocks over the last 90 days",
]


def layout(**_kwargs):
    return html.Div(
        [
            html.H2("Ask in plain English", className="mb-2"),
            html.P(
                "Your question is sent to an LLM, converted to SQL, "
                "validated, and run against a read-only Postgres role. "
                "The generated SQL is always shown so you can audit it.",
                className="text-muted",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Input(
                            id="ask-input",
                            placeholder="e.g. Top 5 holdings in GAM_TECH by weight",
                            type="text",
                            debounce=False,
                        ),
                        md=9,
                    ),
                    dbc.Col(
                        dbc.Button("Ask", id="ask-submit", color="primary", className="w-100"),
                        md=3,
                    ),
                ],
                className="g-2 mb-2",
            ),
            html.Div(
                [
                    html.Small("Try: ", className="text-muted me-2"),
                    *[
                        dbc.Badge(
                            ex,
                            id={"type": "ask-example", "index": i},
                            color="light",
                            text_color="primary",
                            className="me-2 mb-2",
                            style={"cursor": "pointer"},
                        )
                        for i, ex in enumerate(EXAMPLES)
                    ],
                ],
                className="mb-3",
            ),
            dcc.Loading(
                html.Div(id="ask-output"),
                type="default",
            ),
        ]
    )


@dash.callback(
    Output("ask-input", "value"),
    Input({"type": "ask-example", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _use_example(_clicks):
    ctx = dash.callback_context
    if not ctx.triggered or all(c is None for c in _clicks):
        return dash.no_update
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    try:
        # Dash pattern-matching IDs come through as JSON strings.
        idx = int(json.loads(triggered_id)["index"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return dash.no_update
    return EXAMPLES[idx]


@dash.callback(
    Output("ask-output", "children"),
    Input("ask-submit", "n_clicks"),
    Input("ask-input", "n_submit"),
    State("ask-input", "value"),
    prevent_initial_call=True,
)
def _run(_n_clicks, _n_submit, question):
    if not question or not question.strip():
        return None
    try:
        result = api_ask(question.strip())
    except ApiError as e:
        return error_banner(f"{e.status or ''} {e.detail}")

    sql_block = dbc.Card(
        dbc.CardBody([
            html.H6("Generated SQL", className="text-muted small text-uppercase"),
            html.Pre(
                result["sql"],
                style={
                    "backgroundColor": "#f8f9fa",
                    "padding": "12px",
                    "borderRadius": "4px",
                    "fontSize": "13px",
                    "whiteSpace": "pre-wrap",
                    "wordBreak": "break-word",
                },
            ),
            html.Div(result.get("explanation", ""), className="text-muted small mt-2"),
        ]),
        className="shadow-sm mb-3",
    )

    rows = result.get("rows", [])
    columns = result.get("columns", [])
    if not rows:
        return [sql_block, dbc.Alert("Query returned no rows.", color="warning")]

    table = dash_table.DataTable(
        data=rows,
        columns=[{"name": c, "id": c} for c in columns],
        sort_action="native",
        page_size=15,
        style_cell={"padding": "6px", "fontSize": "13px"},
        style_header={"fontWeight": "600", "backgroundColor": "#f8f9fa"},
    )

    chart = _maybe_chart(result, rows)

    results_card = dbc.Card(
        dbc.CardBody([
            html.H6(f"Results ({result['row_count']} rows)", className="text-muted small text-uppercase"),
            table,
        ]),
        className="shadow-sm mb-3",
    )

    out = [sql_block, results_card]
    if chart is not None:
        out.append(chart)
    return out


def _maybe_chart(result: dict, rows: list[dict]):
    chart_type = (result.get("chart_type") or "none").lower()
    x_col = result.get("x_col")
    y_col = result.get("y_col")
    title = result.get("title") or ""
    if chart_type == "none" or not x_col or not y_col:
        return None
    if x_col not in rows[0] or y_col not in rows[0]:
        return None

    df = pd.DataFrame(rows)
    fig = go.Figure()
    if chart_type == "line":
        if x_col == "as_of_date":
            df[x_col] = pd.to_datetime(df[x_col])
        fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode="lines", name=y_col))
    elif chart_type == "bar":
        fig.add_trace(go.Bar(x=df[x_col], y=df[y_col]))
    elif chart_type == "pie":
        fig.add_trace(go.Pie(labels=df[x_col], values=df[y_col], hole=0.4, textinfo="label+percent"))
    else:
        return None

    fig.update_layout(
        margin=dict(l=10, r=10, t=40, b=10),
        height=380,
        title=title,
        template="plotly_white",
    )

    return dbc.Card(
        dbc.CardBody(dcc.Graph(figure=fig, config={"displayModeBar": False})),
        className="shadow-sm",
    )
