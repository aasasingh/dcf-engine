"""Web front end: streamlit run app.py"""
from __future__ import annotations

import io

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from dcf.charts import margin_chart, scenario_chart, tornado_chart
from dcf.excel import build_workbook
from dcf.pipeline import analyze, revalue

st.set_page_config(page_title="DCF Engine", layout="wide")


@st.cache_data(ttl=3600, show_spinner="Pulling SEC filings and market data...")
def load(ticker: str):
    return analyze(ticker)


def pct(v: float) -> str:
    return f"{v:.1%}"


st.title("DCF Engine: what's priced in?")
st.caption("Values a company from its SEC filings, then solves for the growth and margins "
           "the current share price assumes. US companies that file 10-Ks only. "
           "Not investment advice.")

ticker = st.text_input("Ticker", value="LULU", max_chars=10).strip().upper()
if not ticker:
    st.stop()
try:
    x = load(ticker)
except Exception as e:  # noqa: BLE001 - show any data problem to the user instead of a traceback
    st.error(f"Couldn't value {ticker}: {e}. It may not file 10-Ks with the SEC "
             "(foreign filers and funds don't), or the data source may be busy. Try again later.")
    st.stop()

a = x.assumptions
with st.sidebar:
    st.header("Assumptions")
    st.caption("Starting values come from the saved assumptions file. Move a slider and "
               "everything re-values.")
    g1 = st.slider("Revenue growth, year 1", -0.30, 0.40,
                   float(a.growth_year1 if a.growth_year1 is not None else a.growth_start), 0.005,
                   format="%.3f")
    g = st.slider("Revenue growth, year 2 (fades to terminal)", -0.10, 0.40,
                  float(a.growth_start), 0.005, format="%.3f")
    m0 = st.slider("EBIT margin, next year", -0.10, 0.50, float(a.margin_start), 0.005,
                   format="%.3f")
    m = st.slider("EBIT margin, long run", -0.10, 0.50, float(a.margin_target), 0.005,
                  format="%.3f")
    tg = st.slider("Terminal growth", 0.0, 0.04, float(a.terminal_growth), 0.0025,
                   format="%.4f")
    w = st.slider("WACC", 0.05, 0.15, float(x.result.wacc), 0.0025, format="%.4f")

if (g1, g, m0, m, tg, round(w, 4)) != (a.growth_year1, a.growth_start, a.margin_start,
                                        a.margin_target, a.terminal_growth, round(x.result.wacc, 4)):
    if w <= tg:
        st.error("WACC has to be above terminal growth.")
        st.stop()
    x = revalue(x, a.with_(growth_year1=g1, growth_start=g, margin_start=m0, margin_target=m,
                           terminal_growth=tg, wacc_override=w))

r, b = x.result, x.base
st.subheader(f"{x.company} ({x.ticker})")
st.caption(f"Base period {b.label}. Price as of {x.market.as_of}.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Value per share", f"${r.value_per_share:,.2f}",
          f"{r.value_per_share / b.price - 1:+.0%} vs price")
c2.metric("Share price", f"${b.price:,.2f}")
c3.metric("Enterprise value", f"${r.enterprise_value / 1e9:,.2f}B")
c4.metric("Terminal value share of EV", pct(r.terminal_share_of_ev))

st.markdown("#### What the price implies")
rows = []
for iv in x.implied.values():
    label = {"growth_start": "Revenue growth (start of fade)",
             "margin_target": "Long-run EBIT margin"}[iv.field]
    rows.append({"Input": label, "Your assumption": pct(iv.assumed),
                 "Implied by price": "no solution" if iv.implied is None else pct(iv.implied)})
st.table(pd.DataFrame(rows).set_index("Input"))
st.caption("Each row changes one input, holding the rest, until value per share equals the price.")

left, right = st.columns(2)
for col, make in ((left, margin_chart), (right, tornado_chart)):
    fig = make(x)
    col.pyplot(fig)
    plt.close(fig)
fig = scenario_chart(x)
left.pyplot(fig)
plt.close(fig)

with right:
    st.markdown("#### WACC vs terminal growth")
    grid = x.grid.copy()
    grid.index = [pct(v) for v in grid.index]
    grid.columns = [pct(v) for v in grid.columns]
    st.dataframe(grid.style.format("${:,.0f}", na_rep="-"))

with st.expander("Forecast"):
    proj = x.result.projection.copy()
    money = ["revenue", "ebit", "taxes", "nopat", "d_and_a", "capex", "nwc", "change_in_nwc",
             "fcff", "pv_fcff"]
    proj.loc[money] = proj.loc[money] / 1e6
    st.caption("$M except rates")
    st.dataframe(proj.style.format("{:,.2f}"))

buf = io.BytesIO()
build_workbook(x).save(buf)
st.download_button("Download the Excel model", buf.getvalue(), f"{x.ticker}_dcf.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.caption("The workbook uses live formulas, so you can change any input in Excel. "
           "Source: github.com/aasasingh/dcf-engine")
