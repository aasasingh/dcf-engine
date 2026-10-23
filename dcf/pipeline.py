"""Wire the stages together: fetch -> clean -> assumptions -> model -> analyses."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from . import assumptions as asm
from .clean import (annual_financials, fiscal_year_end, latest_shares_outstanding,
                    other_share_classes, trailing_twelve_months)
from .fetch import MarketData, company_facts, market_data
from .model import BaseYear, DCFResult, run_dcf
from .reverse import ImpliedValue, reverse_dcf
from .sensitivity import scenario_table, tornado, wacc_terminal_grid


@dataclass
class Analysis:
    ticker: str
    company: str
    hist: pd.DataFrame
    latest: pd.Series         # the base period: TTM if available, else last fiscal year
    market: MarketData
    base: BaseYear
    assumptions: asm.Assumptions
    assumptions_path: Path | None
    result: DCFResult
    implied: dict[str, ImpliedValue]
    grid: pd.DataFrame
    tornado: pd.DataFrame
    scenarios: pd.DataFrame


def latest_period(facts: dict, hist: pd.DataFrame) -> pd.Series:
    """Trailing twelve months if any 10-Q follows the last 10-K, else the last fiscal year."""
    ttm = trailing_twelve_months(facts, hist)
    if ttm is not None:
        return ttm
    fy = int(hist.columns[-1])
    last = hist[fy].copy()
    last.attrs["label"] = f"FY{fy}"
    last.attrs["period_end"] = fiscal_year_end(facts, fy)
    return last


def build_base_year(latest: pd.Series, facts: dict, md: MarketData) -> BaseYear:
    cover = latest_shares_outstanding(facts)
    shares = cover + other_share_classes(facts) if cover else float(latest["diluted_shares"])
    return BaseYear(
        label=latest.attrs["label"],
        period_end=latest.attrs["period_end"],
        revenue=float(latest["revenue"]),
        cash=float(latest["cash"] + latest["short_term_investments"]),
        debt=float(latest["total_debt"]),
        lease_liabilities=float(latest["operating_lease_liability"]),
        shares=shares,
        price=md.price,
    )


def analyze(ticker: str, refresh: bool = False) -> Analysis:
    ticker = ticker.upper()
    facts = company_facts(ticker, refresh)
    hist = annual_financials(facts)
    latest = latest_period(facts, hist)
    md = market_data(ticker, refresh)
    base = build_base_year(latest, facts, md)

    defaults = asm.default_assumptions(hist, latest, md.risk_free, md.beta_adjusted)
    a, path = asm.load(ticker, "base", defaults)
    x = Analysis(ticker=ticker, company=facts.get("entityName", ticker), hist=hist,
                 latest=latest, market=md, base=base, assumptions=a, assumptions_path=path,
                 result=None, implied={}, grid=None, tornado=None, scenarios=None)
    return revalue(x, a)


def revalue(x: Analysis, a: asm.Assumptions) -> Analysis:
    """Same company and data, new assumptions. Used by the web app's sliders."""
    return replace(
        x,
        assumptions=a,
        result=run_dcf(a, x.base),
        implied=reverse_dcf(a, x.base),
        grid=wacc_terminal_grid(a, x.base),
        tornado=tornado(a, x.base),
        scenarios=scenario_table(asm.scenarios(a), x.base),
    )
