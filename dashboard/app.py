"""Dash entry point.

Uses Dash's built-in multi-page routing (register_page in each pages/*.py
module). A top navbar holds the portfolio selector that every page's
callback reads.
"""
from __future__ import annotations

import logging
import os

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from dashboard.api_client import ApiError, list_portfolios
from dashboard.components import error_banner, portfolio_selector

logging.basicConfig(
    level=os.environ.get("DASH_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s dash %(message)s",
)
log = logging.getLogger("dash")


app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    use_pages=True,
    pages_folder="pages",
    suppress_callback_exceptions=True,
    title="Portfolio Analytics",
)
server = app.server  # exposed for gunicorn/uvicorn if later deployed that way


def _initial_portfolios() -> list[dict]:
    # Called once at import time. If the API isn't up yet, we return an
    # empty list and let the selector pick it up on the first callback.
    try:
        return list_portfolios()
    except ApiError as e:
        log.warning("portfolio list unavailable at startup: %s", e)
        return []


PORTFOLIOS_AT_START = _initial_portfolios()


def _sidebar_layout():
    nav_links = [
        dbc.NavLink(page["name"], href=page["path"], active="exact")
        for page in sorted(dash.page_registry.values(), key=lambda p: p.get("order", 99))
    ]
    return dbc.Col(
        [
            html.H4("Portfolio Analytics", className="mt-3"),
            html.Div("Demo • FastAPI + Dash + AI", className="text-muted small mb-4"),
            html.Label("Portfolio", className="small text-muted"),
            html.Div(portfolio_selector(PORTFOLIOS_AT_START), id="portfolio-select-wrapper"),
            html.Hr(),
            dbc.Nav(nav_links, vertical=True, pills=True),
        ],
        md=2,
        className="bg-light vh-100 p-3 border-end",
    )


app.layout = dbc.Container(
    [
        dcc.Location(id="url"),
        dbc.Row(
            [
                _sidebar_layout(),
                dbc.Col(
                    [
                        html.Div(id="global-error"),
                        dash.page_container,
                    ],
                    md=10,
                    className="p-4",
                ),
            ],
            className="g-0",
        ),
    ],
    fluid=True,
)


@app.callback(
    Output("global-error", "children"),
    Input("url", "pathname"),
)
def _startup_check(_pathname):
    # If we started before the API was ready, PORTFOLIOS_AT_START is empty.
    # Tell the user visibly rather than rendering blank pages.
    if not PORTFOLIOS_AT_START:
        return error_banner("API not reachable — is the backend running?")
    return None


if __name__ == "__main__":
    app.run(
        host=os.environ.get("DASH_HOST", "0.0.0.0"),
        port=int(os.environ.get("DASH_PORT", "8050")),
        debug=os.environ.get("DASH_DEBUG", "false").lower() == "true",
    )
