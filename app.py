"""Web front end: streamlit run app.py"""
from __future__ import annotations

import html
import io
from pathlib import Path

import matplotlib.pyplot as plt
import streamlit as st

from dcf.charts import margin_chart, scenario_chart, tornado_chart
from dcf.excel import build_workbook
from dcf.pipeline import analyze, revalue

st.set_page_config(page_title="DCF Engine", layout="wide", initial_sidebar_state="auto")
st.html(f"<style>{(Path(__file__).parent / 'app_style.css').read_text()}</style>")


@st.cache_data(ttl=3600, show_spinner="Pulling SEC filings and market data...")
def load(ticker: str):
    return analyze(ticker)


def pct(v: float) -> str:
    return f"{v:.1%}"


def usd(v: float) -> str:
    return f"${v:,.2f}"


def bn(v: float) -> str:
    return f"${v / 1e9:,.2f}B"


def md(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def table(header: list[str], rows: list[list[str]], cls: str = "", total_last: bool = False,
          highlight: tuple[int, int] | None = None) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
    body = []
    for i, r in enumerate(rows):
        cells = "".join(
            f'<td class="hl">{c}</td>' if highlight == (i, j) else f"<td>{c}</td>"
            for j, c in enumerate(r))
        tr = '<tr class="total">' if total_last and i == len(rows) - 1 else "<tr>"
        body.append(f"{tr}{cells}</tr>")
    return (f'<div class="ed-scroll"><table class="ed-table {cls}"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def figure(make, x) -> None:
    fig = make(x)
    # Smaller canvas than the README PNGs, so labels stay legible when scaled to a phone.
    w, h = fig.get_size_inches()
    fig.set_size_inches(w * 0.78, h * 0.78)
    fig.tight_layout()
    st.pyplot(fig, width="stretch")
    plt.close(fig)


def lede(x) -> str:
    """The reverse DCF result as one sentence."""
    price = f'<span class="num">{usd(x.base.price)}</span>'
    margin = x.implied["margin_target"].implied
    growth = x.implied["growth_start"]
    parts = []
    if margin is not None:
        parts.append(f'a long-run operating margin of <span class="num">{pct(margin)}</span>')
    if growth.implied is not None:
        cagr = growth.implied_10y_revenue_cagr
        verb = "shrinking" if cagr < 0 else "growing"
        parts.append(f'revenue {verb} <span class="num">{pct(abs(cagr))}</span> a year '
                     "for ten years")
    if not parts:
        return f"No growth rate or margin in a sensible range explains a price of {price}."
    return f"At {price}, the price implies {' or '.join(parts)}."


# ---- Ticker ----
left, _ = st.columns([1, 3])
ticker = left.text_input("Ticker", value="LULU", max_chars=10).strip().upper()
if not ticker:
    st.stop()
try:
    x = load(ticker)
except Exception as e:  # noqa: BLE001 - show any data problem to the user instead of a traceback
    md(f'<p class="ed-note">Couldn\'t value {html.escape(ticker)}: {html.escape(str(e))}. '
       "It may not file 10-Ks with the SEC (foreign filers and funds don't), or the data "
       "source may be busy. Try again later.</p>")
    st.stop()

# ---- Assumptions (sliders work in percent; the model takes decimals) ----
a = x.assumptions
defaults = {
    "g1": round(100 * (a.growth_year1 if a.growth_year1 is not None else a.growth_start), 2),
    "g": round(100 * a.growth_start, 2),
    "m0": round(100 * a.margin_start, 2),
    "m": round(100 * a.margin_target, 2),
    "tg": round(100 * a.terminal_growth, 2),
    "w": round(100 * x.result.wacc, 2),
}
with st.sidebar:
    md('<p class="ed-side-h">Assumptions</p>'
       '<p class="ed-caption">Starting values come from the saved assumptions file. '
       "Move a slider and the whole page re-values.</p>")
    s = {
        "g1": st.slider("Revenue growth, year 1", -30.0, 40.0, defaults["g1"], 0.5, format="%.1f%%"),
        "g": st.slider("Revenue growth, year 2 (fades to terminal)", -10.0, 40.0, defaults["g"],
                       0.5, format="%.1f%%"),
        "m0": st.slider("EBIT margin, next year", -10.0, 50.0, defaults["m0"], 0.5, format="%.1f%%"),
        "m": st.slider("EBIT margin, long run", -10.0, 50.0, defaults["m"], 0.5, format="%.1f%%"),
        "tg": st.slider("Terminal growth", 0.0, 4.0, defaults["tg"], 0.25, format="%.2f%%"),
        "w": st.slider("WACC", 5.0, 15.0, defaults["w"], 0.25, format="%.2f%%"),
    }

if s != defaults:
    if s["w"] <= s["tg"]:
        md('<p class="ed-note">WACC has to be above terminal growth.</p>')
        st.stop()
    # Only override what moved, so untouched inputs keep their exact (unrounded) values.
    fields = {"g1": "growth_year1", "g": "growth_start", "m0": "margin_start",
              "m": "margin_target", "tg": "terminal_growth", "w": "wacc_override"}
    x = revalue(x, a.with_(**{fields[k]: s[k] / 100 for k in s if s[k] != defaults[k]}))

r, b = x.result, x.base

# ---- Masthead and lede ----
md(f'<div class="ed-kicker"><b>{html.escape(x.ticker)}</b>'
   f"<span>{html.escape(x.company)}</span>"
   f"<span>Price <b>{usd(b.price)}</b></span>"
   f"<span>Data as of {html.escape(x.market.as_of)}</span>"
   f"<span>Base period {html.escape(b.label)}</span></div>"
   '<h1 class="ed-title">What\'s priced in?</h1>'
   f'<p class="ed-lede">{lede(x)}</p>')
if s != defaults:
    md('<p class="ed-caption">Using your slider values, not the saved assumptions.</p>')

# ---- Main chart and key figures ----
md('<hr class="ed-rule">')
main, side = st.columns([2, 1], gap="large")
with main:
    figure(margin_chart, x)
with side:
    upside = r.value_per_share / b.price - 1
    figs = [
        ("Value per share", usd(r.value_per_share), True),
        ("Share price", usd(b.price), False),
        ("Upside / downside", f"{upside:+.0%}", False),
        ("Enterprise value", bn(r.enterprise_value), False),
        ("Equity value", bn(r.equity_value), False),
        ("WACC", f"{r.wacc:.2%}", False),
        ("Terminal value / EV", pct(r.terminal_share_of_ev), False),
        ("Base revenue", bn(b.revenue), False),
    ]
    md('<dl class="ed-figs">' + "".join(
        f'<div class="{"key" if key else ""}"><dt>{label}</dt><dd>{value}</dd></div>'
        for label, value, key in figs) + "</dl>")

# ---- Reverse DCF ----
md('<hr class="ed-rule"><h2 class="ed-h2 first">What the price implies</h2>'
   '<p class="ed-prose">Each row changes one input, holding the rest at your assumptions, '
   "until value per share equals the share price.</p>")
labels = {"growth_start": "Revenue growth (start of fade)", "margin_target": "Long-run EBIT margin"}
rows = []
for iv in x.implied.values():
    implied = "no solution" if iv.implied is None else pct(iv.implied)
    cagr = "" if iv.implied_10y_revenue_cagr is None else pct(iv.implied_10y_revenue_cagr)
    rows.append([labels[iv.field], pct(iv.assumed), implied, cagr])
md(table(["Input", "Assumed", "Implied by price", "10Y revenue CAGR"], rows))

# ---- Scenarios ----
md('<h2 class="ed-h2">Scenarios</h2>'
   '<p class="ed-prose">Bear and bull shift starting growth by 4 points and the long-run '
   "margin by 3 points.</p>")
sc = x.scenarios
rows = [[name.capitalize(), pct(row["growth_start"]), pct(row["margin_target"]),
         usd(row["value_per_share"]), f'{row["upside"]:+.0%}', f'{row["weight"]:.0%}']
        for name, row in sc.iterrows()]
weighted = sc.attrs["weighted_value"]
rows.append(["Probability-weighted", "", "", usd(weighted), f"{weighted / b.price - 1:+.0%}", ""])
md(table(["Scenario", "Growth", "Margin", "Value / share", "vs. price", "Weight"], rows,
         total_last=True))
for make, note in (
    (scenario_chart, "Hatched bar: bear, base and bull weighted 25 / 50 / 25. "
                     "Dotted line: the current share price."),
    (tornado_chart, "Each input moves alone, both ways, with everything else held. "
                    "Inputs are sorted by how much they swing value per share."),
):
    main, side = st.columns([2, 1], gap="large")
    with main:
        figure(make, x)
    with side:
        md(f'<p class="ed-caption">{note}</p>')

# ---- Sensitivity grid ----
md('<h2 class="ed-h2">WACC against terminal growth</h2>'
   '<p class="ed-caption">Value per share. Rows are WACC, columns are terminal growth. '
   "The underlined cell is the current case.</p>")
grid = x.grid
mid = (len(grid) // 2, len(grid.columns) // 2 + 1)
rows = [[f"{w:.2%}"] + ["-" if v != v else f"${v:,.0f}" for v in vals]
        for w, vals in zip(grid.index, grid.values)]
md(table(["WACC"] + [pct(g) for g in grid.columns], rows, highlight=mid))

# ---- Forecast ----
md('<h2 class="ed-h2">Forecast</h2><p class="ed-caption">$M except rates.</p>')
proj = x.result.projection
names = {"revenue_growth": "Revenue growth", "revenue": "Revenue", "ebit_margin": "EBIT margin",
         "ebit": "EBIT", "taxes": "Taxes", "nopat": "NOPAT", "d_and_a": "D&A",
         "capex": "Capex", "nwc": "Working capital", "change_in_nwc": "Change in NWC",
         "fcff": "Free cash flow", "discount_factor": "Discount factor", "pv_fcff": "PV of FCF"}
rates = {"revenue_growth", "ebit_margin"}
rows = []
for item, label in names.items():
    vals = proj.loc[item]
    if item in rates:
        cells = [pct(v) for v in vals]
    elif item == "discount_factor":
        cells = [f"{v:.3f}" for v in vals]
    else:
        cells = [f"{v / 1e6:,.0f}" for v in vals]
    rows.append([label] + cells)
md(table([""] + list(proj.columns), rows, cls="wide"))

# ---- Download ----
md('<hr class="ed-rule">')
buf = io.BytesIO()
build_workbook(x).save(buf)
st.download_button("Download the Excel model", buf.getvalue(), f"{x.ticker}_dcf.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
md('<p class="ed-caption">Live formulas: change any blue input in Excel and the model '
   "re-values. Source: github.com/aasasingh/dcf-engine. Not investment advice.</p>")
