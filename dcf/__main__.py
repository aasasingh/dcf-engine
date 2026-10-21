"""Command line: python -m dcf LULU [--refresh]"""
from __future__ import annotations

import argparse

from .excel import write_workbook
from .pipeline import analyze
from .fetch import ROOT


def main() -> None:
    p = argparse.ArgumentParser(description="Forward + reverse DCF from SEC filings")
    p.add_argument("ticker")
    p.add_argument("--refresh", action="store_true", help="re-download SEC and market data")
    args = p.parse_args()

    x = analyze(args.ticker, args.refresh)
    r, a, b = x.result, x.assumptions, x.base
    out = write_workbook(x, ROOT / "output" / f"{x.ticker}_dcf.xlsx")

    print(f"\n{x.company} ({x.ticker})  base {b.label}  price ${b.price:,.2f} ({x.market.as_of})")
    print(f"Assumptions: {x.assumptions_path.relative_to(ROOT)}")
    y1 = "" if a.growth_year1 is None else f"year 1 {a.growth_year1:.1%}, then "
    print(f"  growth {y1}{a.growth_start:.1%} -> {a.terminal_growth:.1%}   "
          f"EBIT margin {a.margin_start:.1%} -> {a.margin_target:.1%}   "
          f"WACC {r.wacc:.2%} (beta {a.beta:.2f})")
    print(f"\nEnterprise value   ${r.enterprise_value / 1e9:,.2f}B  (terminal value {r.terminal_share_of_ev:.0%})")
    print(f"Equity value       ${r.equity_value / 1e9:,.2f}B")
    print(f"Value per share    ${r.value_per_share:,.2f}  vs price ${b.price:,.2f}  "
          f"({r.value_per_share / b.price - 1:+.0%})")
    print("\nWhat the price implies (one input at a time):")
    for iv in x.implied.values():
        implied = "no solution in range" if iv.implied is None else f"{iv.implied:.1%}"
        print(f"  {iv.field:15s} assumed {iv.assumed:6.1%}   implied {implied}")
    s = x.scenarios
    print("\nScenarios: " + "   ".join(f"{k} ${v:,.0f}" for k, v in s["value_per_share"].items())
          + f"   weighted ${s.attrs['weighted_value']:,.0f}")
    print(f"\nWorkbook: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
