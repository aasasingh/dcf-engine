# DCF Engine: what's priced in?

A discounted cash flow model that pulls a company's financials straight from its SEC filings.
It values the company the usual way, then runs the model in reverse to answer a more useful
question: what does the current share price assume about future growth and margins?

The output is an Excel model with live formulas, so every number can be traced and changed.

```
python -m dcf LULU            # uses cached data
python -m dcf LULU --refresh  # re-downloads SEC and market data
```

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
