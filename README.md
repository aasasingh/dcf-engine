# DCF Engine: what's priced in?

A discounted cash flow model that pulls a company's financials straight from its SEC filings.
It values the company the usual way, then runs the model in reverse to answer a more useful
question: what does the current share price assume about future growth and margins?

**Try it: [dcf-engine-app.streamlit.app](https://dcf-engine-app.streamlit.app/)** (enter a ticker, move the assumption sliders, download the Excel model)

## Result: lululemon (LULU), October 2026

At $99.01, the market is pricing lululemon as if its operating margin falls to about **10.4%**
and stays there. That would be lower than any year in the last decade (the low was 16.4% in FY22).
My base case has margins recover partway, to 17%, and gives **$153 per share, 54% above the price**.

![EBIT margin: reported, base case, and what the price implies](output/LULU_margin.png)

| | Value per share | vs. price |
|---|---|---|
| Bull | $198 | +100% |
| Base | $153 | +54% |
| Bear | $115 | +17% |
| Margin 10%, no growth | $89 | -10% |

![Value per share when one input changes](output/LULU_tornado.png)

- **[Open the web app](https://dcf-engine-app.streamlit.app/)**: the same model with sliders, for any US ticker.
- **[Read the memo (PDF)](docs/LULU_memo.pdf)**: the full write-up, with assumptions, stress tests and risks.
- **[Download the Excel model](output/LULU_dcf.xlsx)**: live formulas. Change any blue input and the whole model updates.
- **Assumptions**: [`assumptions/LULU_base.yaml`](assumptions/LULU_base.yaml), with the reasoning behind each number.

## Run it yourself

Needs Python 3.11+. The SEC requires a contact email in every request, so set `SEC_USER_AGENT` first.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
$env:SEC_USER_AGENT = "Your Name you@email.com"   # macOS/Linux: export SEC_USER_AGENT="..."

python -m dcf LULU            # writes output/LULU_dcf.xlsx and charts
python -m dcf LULU --refresh  # re-downloads SEC and market data
streamlit run app.py          # web version with sliders
```

Any US company that files 10-Ks should work. The first run for a new ticker creates
`assumptions/<TICKER>_base.yaml` with default values based on history. Edit that file and
run again to use your own numbers. To rebuild the memo PDF: `python scripts/build_memo.py docs/LULU_memo.md`.

## How it works

| Step | File | What it does |
|---|---|---|
| Fetch | `dcf/fetch.py` | Downloads financial data from SEC EDGAR, plus the share price, 10-year Treasury yield and 5-year beta from Yahoo Finance. Results are cached in `data/raw/`. |
| Clean | `dcf/clean.py` | Keeps one value per fiscal year from 10-K filings, removes duplicates and quarterly figures, and joins up accounting tags that changed names over the years. Builds a trailing twelve month base period from the latest 10-Q. Also picks up share classes the cover page leaves out, like lululemon's exchangeable shares. |
| Assumptions | `dcf/assumptions.py` | Starts with simple defaults based on history and saves them to `assumptions/<TICKER>_base.yaml`. Edit that file to use your own numbers. `growth_year1` lets next year be set on its own (for example from company guidance) while later years follow a gradual fade. |
| Model | `dcf/model.py` | Free cash flow to the firm (NOPAT + D&A - capex - change in working capital), discounted at a CAPM-based WACC, with a Gordon growth terminal value. |
| Reverse DCF | `dcf/reverse.py` | Solves for the growth rate or margin that makes the model's value equal the share price. |
| Sensitivity | `dcf/sensitivity.py` | WACC vs terminal growth grid, a tornado chart of which inputs matter most, and bear/base/bull cases. |
| Excel | `dcf/excel.py` | Writes the workbook. Inputs are named cells, so changing one updates the whole model. |
| Charts | `dcf/charts.py` | Margin, tornado and scenario charts, used by the README, the memo and the web app. |
| Web app | `app.py` | Streamlit front end: enter a ticker, move the assumption sliders, download the workbook. |

## Tests

`python -m pytest` checks that:
- a small made-up company matches a valuation done by hand
- the reverse DCF recovers the inputs it was given
- the cleaning rules work (duplicates, quarterly filtering, tag changes, share classes)
- the Excel formulas give the same value per share as the Python model

## Limitations

- Cash flows are discounted from the end of the base period, not from today.
- The default assumptions just extend history. They're a starting point, not a forecast.
- Doesn't work for banks, insurers or REITs, since their cash flows don't fit this model.
- Only US filers (10-K). Companies that don't report an operating income line, like Nike, aren't supported yet.
