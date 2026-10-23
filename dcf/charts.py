"""Static charts for the README, the memo and the web app (matplotlib, light theme).

Styled like a printed research note: ivory paper, black and grey ink, series told apart
by line style, serif titles and mono labels. Fonts are bundled in dcf/fonts (OFL).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator, PercentFormatter  # noqa: E402

from .model import margin_path  # noqa: E402
from .pipeline import Analysis  # noqa: E402

PAPER = "#FAF8F3"
INK = "#111111"
GREY = "#7a7770"
LIGHT = "#c9c5bb"
RULE = "#e4e1d8"

for _f in (Path(__file__).parent / "fonts").glob("*.ttf"):
    font_manager.fontManager.addfont(str(_f))
SERIF = ["Newsreader", "DejaVu Serif", "serif"]
MONO = ["IBM Plex Mono", "DejaVu Sans Mono", "monospace"]

plt.rcParams.update({
    "font.family": MONO,
    "font.size": 9,
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "axes.edgecolor": INK,
    "axes.linewidth": 0.6,
    "axes.labelcolor": INK,
    "axes.titlecolor": INK,
    "axes.titlesize": 15,
    "axes.titleweight": "normal",
    "axes.titlelocation": "left",
    "axes.titlepad": 14,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": INK,
    "ytick.color": INK,
    "xtick.labelcolor": GREY,
    "ytick.labelcolor": GREY,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "grid.color": RULE,
    "grid.linewidth": 0.6,
    "legend.frameon": False,
    "legend.labelcolor": INK,
    "legend.fontsize": 8.5,
    "hatch.color": INK,
    "hatch.linewidth": 0.6,
})

DOLLARS = FuncFormatter(lambda v, _: f"${v:,.0f}")
LABELS = {"wacc_override": "WACC", "margin_target": "Target EBIT margin",
          "capex_pct_revenue": "Capex % of revenue", "growth_start": "Revenue growth",
          "terminal_growth": "Terminal growth", "tax_rate": "Tax rate",
          "nwc_pct_revenue": "Working capital % of revenue"}


def _title(ax: plt.Axes, text: str) -> None:
    """Serif title flush with the left edge of the figure, not the plot area."""
    ax.figure.suptitle(text, x=0.012, ha="left", fontfamily=SERIF, fontsize=15, color=INK)


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
    top = max(values + margin_path(x.assumptions))
    ax.plot(range(n_hist), values, color=INK, lw=1.6, marker="o", ms=3.5, label="Reported")
    ax.plot(fx, [values[-1]] + margin_path(x.assumptions), color=INK, lw=1.6, ls=(0, (5, 3)),
            label="Base case")
    implied = x.implied.get("margin_target")
    if implied and implied.implied is not None:
        path = margin_path(x.assumptions.with_(margin_target=implied.implied))
        top = max(top, *path)
        ax.plot(fx, [values[-1]] + path, color=GREY, lw=1.8, ls=(0, (1, 2)), label="Priced in")
        ax.annotate(f"Priced in {implied.implied:.1%}", (fx[-1], path[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", color=GREY)
    ax.annotate(f"Base case {x.assumptions.margin_target:.1%}",
                (fx[-1], margin_path(x.assumptions)[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", color=INK)

    ticks = list(range(0, n_hist, 2)) + [n_hist - 1] + list(range(n_hist + 1, fx[-1] + 1, 3))
    all_labels = labels + forecast
    ax.set_xticks(ticks, [all_labels[i] for i in ticks])
    ax.axvline(n_hist - 1, color=LIGHT, lw=0.6)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_ylim(0, top * 1.15)
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    ax.set_xlim(-0.5, fx[-1] + 4)
    _title(ax, f"{x.ticker} EBIT margin: reported, base case, and what the price implies")
    ax.legend(loc="lower left", ncol=3, handlelength=3)
    fig.tight_layout()
    return fig


def tornado_chart(x: Analysis) -> plt.Figure:
    """Value per share when each input moves down or up alone, against the share price."""
    t = x.tornado.iloc[::-1]
    base_value = x.tornado.attrs["base_value"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = range(len(t))
    for col, style, label in (("value_low_shock", dict(color=INK), "Input lowered"),
                              ("value_high_shock", dict(color=PAPER, edgecolor=INK,
                                                        hatch="//////"), "Input raised")):
        widths = t[col] - base_value
        ax.barh(y, widths, left=base_value, height=0.55, label=label, linewidth=0.6, **style)
        for yi, v in zip(y, t[col]):
            ax.annotate(f"${v:,.0f}", (v, yi), xytext=(4 if v >= base_value else -4, 0),
                        textcoords="offset points", va="center", fontsize=8, color=INK,
                        ha="left" if v >= base_value else "right")
    names = []
    for _, r in t.iterrows():
        step = f"{r['shock']:.1%}".replace(".0%", "%")
        names.append(f"{LABELS.get(r['input'], r['input'])} +/- {step}")
    ax.set_yticks(list(y), names)
    ax.tick_params(axis="y", length=0, labelcolor=INK)
    ax.axvline(base_value, color=INK, lw=0.8)
    ax.axvline(x.base.price, color=GREY, lw=1.2, ls=(0, (1, 2)))
    ax.annotate(f"Price ${x.base.price:,.0f}", (x.base.price, len(t) - 0.4), xytext=(4, 0),
                textcoords="offset points", color=GREY, fontsize=8)
    ax.annotate(f"Base ${base_value:,.0f}", (base_value, len(t) - 0.4), xytext=(4, 0),
                textcoords="offset points", color=INK, fontsize=8)
    lo = min(x.base.price, t["value_low_shock"].min(), t["value_high_shock"].min())
    hi = max(t["value_low_shock"].max(), t["value_high_shock"].max())
    ax.set_xlim(lo * 0.85, hi * 1.08)
    ax.set_ylim(-0.6, len(t) + 0.2)
    ax.xaxis.set_major_formatter(DOLLARS)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x")
    ax.set_axisbelow(True)
    _title(ax, "Value per share when one input changes")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 1.01), ncol=2, handlelength=1.6,
              handleheight=1, borderaxespad=0)
    fig.tight_layout()
    return fig


def scenario_chart(x: Analysis) -> plt.Figure:
    """Bear, base, bull and probability-weighted value per share vs the share price."""
    s = x.scenarios
    names = [n.capitalize() for n in s.index] + ["Weighted"]
    values = list(s["value_per_share"]) + [s.attrs["weighted_value"]]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bars = ax.bar(names, values, width=0.5, color=INK, edgecolor=INK, linewidth=0.6)
    bars[-1].set_facecolor(PAPER)
    bars[-1].set_hatch("//////")
    for b, v in zip(bars, values):
        ax.annotate(f"${v:,.0f}  {v / x.base.price - 1:+.0%}",
                    (b.get_x() + b.get_width() / 2, v), xytext=(0, 4),
                    textcoords="offset points", ha="center", color=INK, fontsize=8.5)
    ax.axhline(x.base.price, color=GREY, lw=1.4, ls=(0, (1, 2)),
               label=f"Share price ${x.base.price:,.2f}")
    ax.legend(loc="upper left", handlelength=3)
    ax.yaxis.set_major_formatter(DOLLARS)
    ax.tick_params(axis="x", length=0, labelcolor=INK)
    ax.set_ylim(0, max(values) * 1.22)
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    _title(ax, "Value per share by scenario")
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
