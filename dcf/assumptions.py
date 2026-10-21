"""Model assumptions: mechanical defaults derived from history, overridable via YAML.

Defaults are deliberately simple rules (averages, fades) so every number can be traced
back to the historicals. Edit assumptions/<TICKER>_<scenario>.yaml to override them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
ASSUMPTIONS_DIR = ROOT / "assumptions"


@dataclass(frozen=True)
class Assumptions:
    # Revenue: growth fades linearly from growth_start (year 1) to terminal_growth (final year).
    # growth_year1, if set, replaces year 1 only (e.g. a guided near-term decline) while
    # years 2+ stay on the fade line.
    growth_start: float
    terminal_growth: float
    forecast_years: int
    # Operating margin: moves linearly from margin_start to margin_target over margin_fade_years.
    margin_start: float
    margin_target: float
    margin_fade_years: int
    tax_rate: float
    d_and_a_pct_revenue: float
    capex_pct_revenue: float
    nwc_pct_revenue: float
    # Discount rate (CAPM). wacc_override, if set, replaces the computed WACC.
    risk_free: float
    beta: float
    equity_risk_premium: float
    pre_tax_cost_of_debt: float
    growth_year1: float | None = None
    wacc_override: float | None = None
    mid_year_convention: bool = True
    # Under US GAAP, operating lease cost already sits inside EBIT, so leases are
    # not treated as debt by default. Set True only alongside a lease-adjusted EBIT.
    leases_as_debt: bool = False

    def with_(self, **changes) -> "Assumptions":
        return replace(self, **changes)


def _clip(x: float, lo: float, hi: float) -> float:
    return float(min(max(x, lo), hi))


def default_assumptions(hist: pd.DataFrame, latest: pd.Series, risk_free: float,
                        beta: float) -> Assumptions:
    """`hist` = annual history; `latest` = the base period (TTM if available)."""
    rev = hist.loc["revenue"]
    cagr_3y = (rev.iloc[-1] / rev.iloc[-4]) ** (1 / 3) - 1

    def avg(item: str, n: int) -> float:
        return float(hist.loc[item].iloc[-n:].mean())

    return Assumptions(
        # Blend of the latest growth rate and the 3-year CAGR: recent momentum, tempered.
        growth_start=_clip((float(latest["revenue_growth"]) + cagr_3y) / 2, -0.05, 0.25),
        terminal_growth=0.025,
        forecast_years=10,
        # Status quo: today's margin persists. No recovery or decline is assumed.
        margin_start=float(latest["ebit_margin"]),
        margin_target=float(latest["ebit_margin"]),
        margin_fade_years=5,
        tax_rate=_clip(float(hist.loc["effective_tax_rate"].iloc[-5:].median()), 0.15, 0.35),
        d_and_a_pct_revenue=avg("d_and_a_pct_revenue", 3),
        capex_pct_revenue=avg("capex_pct_revenue", 3),
        nwc_pct_revenue=avg("nwc_pct_revenue", 5),
        risk_free=risk_free,
        beta=_clip(beta, 0.6, 2.0),
        equity_risk_premium=0.045,
        pre_tax_cost_of_debt=risk_free + 0.015,
    )


def scenarios(base: Assumptions) -> dict[str, Assumptions]:
    """Mechanical bear/bull cases: shift starting growth and target margin together."""
    return {
        "bear": base.with_(growth_start=base.growth_start - 0.04,
                           margin_target=base.margin_target - 0.03),
        "base": base,
        "bull": base.with_(growth_start=base.growth_start + 0.04,
                           margin_target=base.margin_target + 0.03),
    }


def load(ticker: str, scenario: str, defaults: Assumptions) -> tuple[Assumptions, Path]:
    """Apply any overrides from assumptions/<TICKER>_<scenario>.yaml on top of defaults.

    The file is created (populated with the defaults) if it does not exist, so there is
    always a readable record of the exact inputs behind a run.
    """
    path = ASSUMPTIONS_DIR / f"{ticker.upper()}_{scenario}.yaml"
    if not path.exists():
        ASSUMPTIONS_DIR.mkdir(parents=True, exist_ok=True)
        header = (f"# {ticker.upper()} {scenario} case. Auto-generated from historicals;\n"
                  f"# edit any value to override it. Rates are decimals (0.05 = 5%).\n")
        values = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(defaults).items()}
        path.write_text(header + yaml.safe_dump(values, sort_keys=False))

    # Always read back from the file so the run uses exactly what the file records.
    overrides = yaml.safe_load(path.read_text()) or {}
    valid = {f.name for f in fields(Assumptions)}
    unknown = set(overrides) - valid
    if unknown:
        raise ValueError(f"{path.name}: unknown assumption(s) {sorted(unknown)}")
    return defaults.with_(**overrides), path
