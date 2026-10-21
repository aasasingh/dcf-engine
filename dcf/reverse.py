"""Reverse DCF: which assumption values make the model's output equal today's price?

Value rises monotonically with growth and with margin, so a bracketing root-finder
(Brent's method) solves value(x) - price = 0 reliably.
"""
from __future__ import annotations

from dataclasses import dataclass

from scipy.optimize import brentq

from .assumptions import Assumptions
from .model import BaseYear, growth_path, run_dcf

# Search ranges: wide enough to cover any plausible business, narrow enough that WACC
# stays above terminal growth throughout.
SOLVE_RANGES = {
    "growth_start": (-0.30, 0.80),
    "margin_target": (-0.20, 0.80),
}


@dataclass
class ImpliedValue:
    field: str
    implied: float | None     # None if no value in the search range matches the price
    assumed: float
    implied_10y_revenue_cagr: float | None = None


def solve_for(field: str, a: Assumptions, base: BaseYear) -> ImpliedValue:
    lo, hi = SOLVE_RANGES[field]

    def gap(x: float) -> float:
        return run_dcf(a.with_(**{field: x}), base).value_per_share - base.price

    if gap(lo) * gap(hi) > 0:
        return ImpliedValue(field, None, getattr(a, field))
    x = brentq(gap, lo, hi, xtol=1e-7)

    implied_a = a.with_(**{field: x})
    cagr = 1.0
    for g in growth_path(implied_a):
        cagr *= 1 + g
    cagr = cagr ** (1 / implied_a.forecast_years) - 1
    return ImpliedValue(field, x, getattr(a, field), cagr)


def reverse_dcf(a: Assumptions, base: BaseYear) -> dict[str, ImpliedValue]:
    return {f: solve_for(f, a, base) for f in SOLVE_RANGES}
