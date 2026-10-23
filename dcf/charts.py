"""Static charts for the README, the memo and the web app (matplotlib, light theme)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

from .model import margin_path  # noqa: E402
from .pipeline import Analysis  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 10,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "legend.frameon": False,
    "legend.labelcolor": INK_2,
})

DOLLARS = FuncFormatter(lambda v, _: f"${v:,.0f}")
LABELS = {"wacc_override": "WACC", "margin_target": "Target EBIT margin",
          "capex_pct_revenue": "Capex % of revenue", "growth_start": "Revenue growth",
          "terminal_growth": "Terminal growth", "tax_rate": "Tax rate",
          "nwc_pct_revenue": "Working capital % of revenue"}


def margin_chart(x: Analysis) -> plt.Figure:
    """Historical EBIT margin, the base-case path, and the path the price implies."""
    hist = x.hist.loc["ebit_margin"]
    labels = [f"FY{int(fy) % 100:02d}" for fy in hist.index]
    values = list(hist.values)
    if x.base.label.startswith("TTM"):
        labels.append("TTM")
        values.append(float(x.latest["ebit_margin"]))
    forecast = list(x.result.projection.columns)
    n_hist = len(values)
    fx = list(range(n_hist - 1, n_hist + len(forecast)))

    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(range(n_hist), values, color=BLUE, lw=2, marker="o", ms=4, label="Reported")
    ax.plot(fx, [values[-1]] + margin_path(x.assumptions), color=BLUE, lw=2, ls="--",
            label="Base case")
    implied = x.implied.get("margin_target")
    if implied and implied.implied is not None:
        path = margin_path(x.assumptions.with_(margin_target=implied.implied))
        ax.plot(fx, [values[-1]] + path, color=ORANGE, lw=2, ls="--", label="Priced in")
        ax.annotate(f"Priced in {implied.implied:.1%}", (fx[-1], path[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", color=INK_2)
    ax.annotate(f"Base case {x.assumptions.margin_target:.1%}",
                (fx[-1], margin_path(x.assumptions)[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", color=INK_2)

    ticks = list(range(0, n_hist, 2)) + [n_hist - 1] + list(range(n_hist + 1, fx[-1] + 1, 3))
    all_labels = labels + forecast
    ax.set_xticks(ticks, [all_labels[i] for i in ticks])
    ax.axvline(n_hist - 1, color=AXIS, lw=0.8)
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_ylim(0, max(values) * 1.15)
    ax.grid(axis="y")
    ax.set_xlim(-0.5, fx[-1] + 3.5)
    ax.set_title(f"{x.ticker} EBIT margin: reported, base case, and what the price implies")
    ax.legend(loc="lower left", ncol=3)
    fig.tight_layout()
    return fig


def tornado_chart(x: Analysis) -> plt.Figure:
    """Value per share when each input moves down or up alone, against the share price."""
    t = x.tornado.iloc[::-1]
    base_value = x.tornado.attrs["base_value"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = range(len(t))
    for col, color, label in (("value_low_shock", BLUE, "Input lowered"),
                              ("value_high_shock", ORANGE, "Input raised")):
        widths = t[col] - base_value
        ax.barh(y, widths, left=base_value, height=0.6, color=color, label=label,
                edgecolor=SURFACE, linewidth=1)
        for yi, v in zip(y, t[col]):
            ax.annotate(f"${v:,.0f}", (v, yi), xytext=(4 if v >= base_value else -4, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=INK_2,
                        ha="left" if v >= base_value else "right")
    names = []
    for _, r in t.iterrows():
        step = f"{r['shock']:.1%}".replace(".0%", "%")
        names.append(f"{LABELS.get(r['input'], r['input'])} (+/- {step})")
    ax.set_yticks(list(y), names)
    ax.axvline(base_value, color=INK_2, lw=1)
    ax.axvline(x.base.price, color=MUTED, lw=1, ls=":")
    ax.annotate(f"Price ${x.base.price:,.0f}", (x.base.price, len(t) - 0.4), xytext=(4, 0),
                textcoords="offset points", color=INK_2, fontsize=9)
    ax.annotate(f"Base ${base_value:,.0f}", (base_value, len(t) - 0.4), xytext=(4, 0),
                textcoords="offset points", color=INK_2, fontsize=9)
    lo = min(x.base.price, t["value_low_shock"].min(), t["value_high_shock"].min())
    hi = max(t["value_low_shock"].max(), t["value_high_shock"].max())
    ax.set_xlim(lo * 0.85, hi * 1.08)
    ax.set_ylim(-0.6, len(t) + 0.2)
    ax.xaxis.set_major_formatter(DOLLARS)
    ax.grid(axis="x")
    ax.set_axisbelow(True)
    ax.set_title("Value per share when one input changes")
    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


def scenario_chart(x: Analysis) -> plt.Figure:
    """Bear, base, bull and probability-weighted value per share vs the share price."""
    s = x.scenarios
    names = [n.capitalize() for n in s.index] + ["Weighted"]
    values = list(s["value_per_share"]) + [s.attrs["weighted_value"]]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bars = ax.bar(names, values, width=0.55, color=BLUE, edgecolor=SURFACE, linewidth=2)
    bars[-1].set_color(INK_2)
    for b, v in zip(bars, values):
        ax.annotate(f"${v:,.0f}\n{v / x.base.price - 1:+.0%}", (b.get_x() + b.get_width() / 2, v),
                    xytext=(0, 4), textcoords="offset points", ha="center", color=INK_2,
                    fontsize=9)
    ax.axhline(x.base.price, color=ORANGE, lw=2, ls="--",
               label=f"Share price ${x.base.price:,.2f}")
    ax.legend(loc="upper left")
    ax.yaxis.set_major_formatter(DOLLARS)
    ax.set_ylim(0, max(values) * 1.22)
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    ax.set_title("Value per share by scenario")
    fig.tight_layout()
    return fig


CHARTS = {"margin": margin_chart, "tornado": tornado_chart, "scenarios": scenario_chart}


def save_charts(x: Analysis, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, make in CHARTS.items():
        fig = make(x)
        path = folder / f"{x.ticker}_{name}.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
    return paths
