from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class Portfolio(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    portfolio_id: int
    code: str
    name: str
    strategy: str
    benchmark: str
    inception: date
    base_ccy: str


class KpiSummary(BaseModel):
    portfolio_id: int
    as_of_date: date
    nav: float
    day_return_pct: float | None
    mtd_return_pct: float | None
    ytd_return_pct: float | None
    aum_usd: float


class NavPoint(BaseModel):
    as_of_date: date
    nav: float


class HoldingRow(BaseModel):
    ticker: str
    name: str
    sector: str
    weight_pct: float
    price: float
    market_value: float


class SectorSlice(BaseModel):
    sector: str
    weight_pct: float


class ReturnPoint(BaseModel):
    as_of_date: date
    portfolio_cum_return_pct: float
    benchmark_cum_return_pct: float


class RollingMetricPoint(BaseModel):
    as_of_date: date
    rolling_vol_pct: float | None = None
    rolling_sharpe: float | None = None


class RiskMetrics(BaseModel):
    portfolio_id: int
    window_days: int
    annualised_vol_pct: float
    annualised_return_pct: float
    sharpe: float
    max_drawdown_pct: float
    var_95_pct: float
    beta_vs_benchmark: float = Field(..., description="Beta vs. the portfolio's benchmark.")
