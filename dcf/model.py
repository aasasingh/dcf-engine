"""Forward DCF: assumptions + base-year financials -> value per share.

Kept as one pure function (`run_dcf`) so the reverse DCF and sensitivity analysis can
call it thousands of times with tweaked inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .assumptions import Assumptions


@dataclass(frozen=True)
class BaseYear:
    """The starting point of the projection: the latest twelve months of results."""
    label: str                # e.g. "TTM Aug-26" or "FY2025"
    period_end: date
    revenue: float
    cash: float               # cash + short-term investments
    debt: float
    lease_liabilities: float
    shares: float             # latest shares outstanding
    price: float


@dataclass
class DCFResult:
    projection: pd.DataFrame  # rows = line items, columns = forecast years
    cost_of_equity: float
    wacc: float
    pv_fcff: float
    terminal_value: float
    pv_terminal_value: float
    enterprise_value: float
    equity_value: float
    value_per_share: float

    @property
    def terminal_share_of_ev(self) -> float:
        return self.pv_terminal_value / self.enterprise_value


def forecast_labels(base: BaseYear, n: int) -> list[str]:
    """Each forecast year is the twelve months ending on the base period's anniversary."""
    return [f"{base.period_end:%b}-{(base.period_end.year + t) % 100:02d}" for t in range(1, n + 1)]


def growth_path(a: Assumptions) -> list[float]:
    n = a.forecast_years
    path = [a.growth_start + (a.terminal_growth - a.growth_start) * (t - 1) / (n - 1)
            for t in range(1, n + 1)]
    if a.growth_year1 is not None:
        path[0] = a.growth_year1
    return path


def margin_path(a: Assumptions) -> list[float]:
    return [a.margin_start + (a.margin_target - a.margin_start) * min(t / a.margin_fade_years, 1)
            for t in range(1, a.forecast_years + 1)]


def net_debt(a: Assumptions, base: BaseYear) -> float:
    debt = base.debt + (base.lease_liabilities if a.leases_as_debt else 0.0)
    return debt - base.cash


def wacc(a: Assumptions, base: BaseYear) -> tuple[float, float]:
    """Return (cost of equity, WACC). Weights use market equity and book debt."""
    cost_of_equity = a.risk_free + a.beta * a.equity_risk_premium
    if a.wacc_override is not None:
        return cost_of_equity, a.wacc_override
    equity = base.price * base.shares
    debt = base.debt + (base.lease_liabilities if a.leases_as_debt else 0.0)
    after_tax_kd = a.pre_tax_cost_of_debt * (1 - a.tax_rate)
    w = (equity * cost_of_equity + debt * after_tax_kd) / (equity + debt)
    return cost_of_equity, w


def run_dcf(a: Assumptions, base: BaseYear) -> DCFResult:
    ke, r = wacc(a, base)
    if r <= a.terminal_growth:
        raise ValueError(f"WACC ({r:.2%}) must exceed terminal growth ({a.terminal_growth:.2%})")

    years = forecast_labels(base, a.forecast_years)
    rows: dict[str, list[float]] = {k: [] for k in (
        "revenue_growth", "revenue", "ebit_margin", "ebit", "taxes", "nopat", "d_and_a",
        "capex", "nwc", "change_in_nwc", "fcff", "discount_period", "discount_factor", "pv_fcff")}

    revenue = base.revenue
    # NWC starts at the assumed ratio rather than the actual balance, so year 1 isn't
    # distorted by one-off swings in last year's working capital.
    prev_nwc = base.revenue * a.nwc_pct_revenue
    for t, (g, m) in enumerate(zip(growth_path(a), margin_path(a)), start=1):
        revenue *= 1 + g
        ebit = revenue * m
        taxes = ebit * a.tax_rate
        nopat = ebit - taxes
        da = revenue * a.d_and_a_pct_revenue
        capex = revenue * a.capex_pct_revenue
        nwc = revenue * a.nwc_pct_revenue
        fcff = nopat + da - capex - (nwc - prev_nwc)
        period = t - 0.5 if a.mid_year_convention else t
        factor = 1 / (1 + r) ** period
        for k, v in (("revenue_growth", g), ("revenue", revenue), ("ebit_margin", m),
                     ("ebit", ebit), ("taxes", taxes), ("nopat", nopat), ("d_and_a", da),
                     ("capex", capex), ("nwc", nwc), ("change_in_nwc", nwc - prev_nwc),
                     ("fcff", fcff), ("discount_period", period), ("discount_factor", factor),
                     ("pv_fcff", fcff * factor)):
            rows[k].append(v)
        prev_nwc = nwc

    projection = pd.DataFrame(rows, index=years).T
    pv_fcff = float(projection.loc["pv_fcff"].sum())
    # Gordon growth on the year after the forecast, discounted from the end of the final year.
    terminal_value = projection.loc["fcff"].iloc[-1] * (1 + a.terminal_growth) / (r - a.terminal_growth)
    pv_tv = terminal_value / (1 + r) ** a.forecast_years
    ev = pv_fcff + pv_tv
    equity = ev - net_debt(a, base)
    return DCFResult(projection, ke, r, pv_fcff, terminal_value, pv_tv, ev, equity,
                     equity / base.shares)
