"""Stress tests: WACC x terminal growth grid, one-at-a-time tornado, and scenarios."""
from __future__ import annotations

import pandas as pd

from .assumptions import Assumptions
from .model import BaseYear, run_dcf

# (field, low shift, high shift) applied one at a time to the base case.
TORNADO_SHOCKS = [
    ("growth_start", -0.02, 0.02),
    ("margin_target", -0.02, 0.02),
    ("wacc_override", -0.01, 0.01),
    ("terminal_growth", -0.005, 0.005),
    ("capex_pct_revenue", -0.01, 0.01),
    ("tax_rate", -0.03, 0.03),
    ("nwc_pct_revenue", -0.02, 0.02),
]


def wacc_terminal_grid(a: Assumptions, base: BaseYear, wacc_step: float = 0.01,
                       g_step: float = 0.005, n: int = 2) -> pd.DataFrame:
    """Value per share; rows = WACC, columns = terminal growth, centred on the base case."""
    centre_wacc = run_dcf(a, base).wacc
    waccs = [centre_wacc + wacc_step * i for i in range(-n, n + 1)]
    gs = [a.terminal_growth + g_step * i for i in range(-n, n + 1)]
    grid = {g: [run_dcf(a.with_(wacc_override=w, terminal_growth=g), base).value_per_share
                if w > g else float("nan") for w in waccs] for g in gs}
    return pd.DataFrame(grid, index=waccs)


def tornado(a: Assumptions, base: BaseYear) -> pd.DataFrame:
    """Value per share when each input is shocked down/up alone, sorted by total swing."""
    base_result = run_dcf(a, base)
    a = a.with_(wacc_override=base_result.wacc)  # so WACC can be shocked directly
    rows = []
    for field, down, up in TORNADO_SHOCKS:
        centre = getattr(a, field)
        low = run_dcf(a.with_(**{field: centre + down}), base).value_per_share
        high = run_dcf(a.with_(**{field: centre + up}), base).value_per_share
        rows.append({"input": field, "base_input": centre, "shock": up,
                     "value_low_shock": low, "value_high_shock": high,
                     "swing": abs(high - low)})
    out = pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)
    out.attrs["base_value"] = base_result.value_per_share
    return out


def scenario_table(cases: dict[str, Assumptions], base: BaseYear,
                   weights: dict[str, float] | None = None) -> pd.DataFrame:
    weights = weights or {"bear": 0.25, "base": 0.50, "bull": 0.25}
    rows = []
    for name, a in cases.items():
        r = run_dcf(a, base)
        rows.append({"scenario": name, "growth_start": a.growth_start,
                     "margin_target": a.margin_target, "value_per_share": r.value_per_share,
                     "upside": r.value_per_share / base.price - 1, "weight": weights[name]})
    df = pd.DataFrame(rows).set_index("scenario")
    df.attrs["weighted_value"] = float((df["value_per_share"] * df["weight"]).sum())
    return df
