"""Turn raw XBRL company facts into tidy annual financial statements.

The raw data is messy in three ways this module handles:
  1. Duplicates - each year's figure is re-reported as a comparative in later 10-Ks.
  2. Tag drift  - companies switch tags over time (e.g. SalesRevenueNet -> RevenueFrom...).
  3. Periods    - quarterly and annual facts are mixed together.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

# For each line item, the XBRL tags to try in priority order. For every year the first
# tag with a value wins, so a company that switched tags mid-history is stitched together.
FLOW_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "gross_profit": ["GrossProfit"],
    "ebit": ["OperatingIncomeLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "d_and_a": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}

INSTANT_TAGS = {
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "short_term_investments": [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ],
    "current_assets": ["AssetsCurrent"],
    "total_assets": ["Assets"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "total_liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "inventory": ["InventoryNet"],
    # Debt components. Missing means the company has none of that type.
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "current_debt": ["LongTermDebtCurrent", "DebtCurrent"],
    "short_term_borrowings": ["ShortTermBorrowings", "LineOfCredit", "CommercialPaper"],
    "operating_lease_liability": ["OperatingLeaseLiability"],
    "operating_lease_liability_current": ["OperatingLeaseLiabilityCurrent"],
    "operating_lease_liability_noncurrent": ["OperatingLeaseLiabilityNoncurrent"],
}

ZERO_IF_MISSING = {
    "short_term_investments", "long_term_debt", "current_debt", "short_term_borrowings",
    "interest_expense", "buybacks",
}


def fiscal_year(end: str) -> int:
    """Label a fiscal year by the calendar year in which most of it fell.

    Retailers like Lululemon end their year in late January / early February, so the
    year ending 2026-02-01 is "fiscal 2025".
    """
    d = date.fromisoformat(end)
    return d.year - 1 if d.month <= 3 else d.year


def _annual_facts(facts: dict, tag: str, instant: bool) -> pd.Series:
    """One value per fiscal year for a single tag, taken from 10-K filings only."""
    node = facts["facts"].get("us-gaap", {}).get(tag)
    if node is None:
        return pd.Series(dtype=float)
    unit = "shares" if "shares" in node["units"] else "USD"
    rows = []
    for f in node["units"].get(unit, []):
        if not f.get("form", "").startswith("10-K"):
            continue
        if not instant:
            if "start" not in f:
                continue
            days = (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days
            if not 350 <= days <= 380:  # full fiscal year only (52 or 53 weeks)
                continue
        rows.append({"fy": fiscal_year(f["end"]), "end": f["end"],
                     "filed": f["filed"], "val": f["val"]})
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    # Within a fiscal year keep the latest period end (instants appear for several dates),
    # then the latest filing, which reflects any restatement.
    df = df.sort_values(["fy", "end", "filed"]).groupby("fy").tail(1)
    return df.set_index("fy")["val"].astype(float)


def _stitch(facts: dict, tags: list[str], instant: bool) -> pd.Series:
    out = pd.Series(dtype=float)
    for tag in tags:
        s = _annual_facts(facts, tag, instant)
        out = s if out.empty else out.combine_first(s)
    return out


def annual_financials(facts: dict, years: int = 10) -> pd.DataFrame:
    """Rows = line items, columns = fiscal years (oldest -> newest)."""
    data = {k: _stitch(facts, tags, False) for k, tags in FLOW_TAGS.items()}
    data |= {k: _stitch(facts, tags, True) for k, tags in INSTANT_TAGS.items()}
    df = pd.DataFrame(data).T.sort_index(axis=1)

    # Keep years where the core statements exist, then the most recent N of those.
    core = df.loc[["revenue", "ebit", "cfo", "total_assets"]].notna().all()
    df = df.loc[:, core[core].index].iloc[:, -years:]

    for item in ZERO_IF_MISSING:
        df.loc[item] = df.loc[item].fillna(0.0)

    leases = df.loc["operating_lease_liability"].combine_first(
        df.loc["operating_lease_liability_current"] + df.loc["operating_lease_liability_noncurrent"])
    df.loc["operating_lease_liability"] = leases.fillna(0.0)
    df.loc["operating_lease_liability_current"] = df.loc["operating_lease_liability_current"].fillna(0.0)
    df = df.drop(index="operating_lease_liability_noncurrent")

    return _add_derived(df)


def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.loc["total_debt"] = (df.loc["long_term_debt"] + df.loc["current_debt"]
                            + df.loc["short_term_borrowings"])
    # Operating working capital: strip out cash and debt-like items so that only the
    # money tied up in running the business (inventory, receivables, payables) remains.
    df.loc["nwc"] = ((df.loc["current_assets"] - df.loc["cash"] - df.loc["short_term_investments"])
                     - (df.loc["current_liabilities"] - df.loc["current_debt"]
                        - df.loc["short_term_borrowings"]
                        - df.loc["operating_lease_liability_current"]))
    df.loc["fcff_hist"] = (df.loc["cfo"] - df.loc["capex"]
                           + df.loc["interest_expense"] * (1 - 0.25))

    rev = df.loc["revenue"]
    df.loc["revenue_growth"] = rev.pct_change()
    df.loc["gross_margin"] = df.loc["gross_profit"] / rev
    df.loc["ebit_margin"] = df.loc["ebit"] / rev
    df.loc["effective_tax_rate"] = df.loc["income_tax"] / df.loc["pretax_income"]
    df.loc["d_and_a_pct_revenue"] = df.loc["d_and_a"] / rev
    df.loc["capex_pct_revenue"] = df.loc["capex"] / rev
    df.loc["nwc_pct_revenue"] = df.loc["nwc"] / rev
    df.loc["sbc_pct_revenue"] = df.loc["sbc"] / rev
    invested_capital = df.loc["equity"] + df.loc["total_debt"] - df.loc["cash"] - df.loc["short_term_investments"]
    df.loc["roic"] = df.loc["ebit"] * (1 - df.loc["effective_tax_rate"]) / invested_capital
    return df


def _duration_facts(facts: dict, tag: str) -> list[dict]:
    """Every duration fact for a tag (10-K and 10-Q), with its length in days."""
    node = facts["facts"].get("us-gaap", {}).get(tag)
    if node is None:
        return []
    unit = "shares" if "shares" in node["units"] else "USD"
    out = []
    for f in node["units"].get(unit, []):
        if "start" in f and f.get("form", "")[:4] in ("10-K", "10-Q"):
            end = date.fromisoformat(f["end"])
            out.append({"end": end, "days": (end - date.fromisoformat(f["start"])).days,
                        "filed": f["filed"], "val": float(f["val"])})
    return out


def _find(rows: list[dict], end: date, days: int, tol: int = 10) -> float | None:
    """Latest-filed value for a period ending near `end` with length near `days`."""
    hits = [r for r in rows if abs((r["end"] - end).days) <= tol and abs(r["days"] - days) <= tol]
    return max(hits, key=lambda r: r["filed"])["val"] if hits else None


def _latest_instant(facts: dict, tags: list[str], end: date) -> float | None:
    for tag in tags:
        node = facts["facts"].get("us-gaap", {}).get(tag)
        if node is None:
            continue
        hits = [f for f in node["units"].get("USD", [])
                if "start" not in f and f["end"] == end.isoformat()]
        if hits:
            return float(max(hits, key=lambda f: f["filed"])["val"])
    return None


def fiscal_year_end(facts: dict, fy: int) -> date:
    """Period end date of a fiscal year, read from the annual revenue facts."""
    ends = [r["end"] for t in FLOW_TAGS["revenue"] for r in _duration_facts(facts, t)
            if 350 <= r["days"] <= 380 and fiscal_year(r["end"].isoformat()) == fy]
    if not ends:
        raise ValueError(f"No annual revenue found for fiscal {fy}")
    return max(ends)


def trailing_twelve_months(facts: dict, hist: pd.DataFrame) -> pd.Series | None:
    """Most recent twelve months: last fiscal year + year-to-date - prior year-to-date.

    Balance sheet items come from the latest 10-Q. Returns None if no 10-Q has been
    filed since the last 10-K (the fiscal year is then already the latest data).
    """
    rev_rows = [r for t in FLOW_TAGS["revenue"] for r in _duration_facts(facts, t)]
    quarterly = [r for r in rev_rows if r["days"] < 350]
    if not quarterly:
        return None
    q_end = max(r["end"] for r in quarterly)
    last_fy = int(hist.columns[-1])
    if fiscal_year(q_end.isoformat()) != last_fy + 1:
        return None
    ytd_days = max(r["days"] for r in quarterly if r["end"] == q_end)
    one_year = 364  # 52-week retail years; the tolerance in _find absorbs 53-week years

    def ttm_value(item: str, years_back: int = 0) -> float | None:
        for tag in FLOW_TAGS[item]:
            rows = _duration_facts(facts, tag)
            now = _find(rows, q_end - pd.Timedelta(days=one_year * years_back), ytd_days)
            prior = _find(rows, q_end - pd.Timedelta(days=one_year * (years_back + 1)), ytd_days)
            fy = hist.loc[item, last_fy - years_back] if last_fy - years_back in hist.columns else None
            if now is not None and prior is not None and fy is not None and fy == fy:
                return float(fy + now - prior)
        return None

    s = pd.Series(index=hist.index, dtype=float)
    for item in FLOW_TAGS:
        if item == "diluted_shares":
            continue  # a share count isn't summed over periods
        v = ttm_value(item)
        s[item] = 0.0 if v is None and item in ZERO_IF_MISSING else v
    for item, tags in INSTANT_TAGS.items():
        if item in s.index:
            v = _latest_instant(facts, tags, q_end)
            if item == "operating_lease_liability" and v is None:
                cur = _latest_instant(facts, INSTANT_TAGS["operating_lease_liability_current"], q_end)
                non = _latest_instant(facts, INSTANT_TAGS["operating_lease_liability_noncurrent"], q_end)
                v = cur + non if cur is not None and non is not None else None
            s[item] = 0.0 if v is None and item in ZERO_IF_MISSING else v
    s["diluted_shares"] = hist.loc["diluted_shares"].iloc[-1]

    out = _add_derived(s.to_frame("TTM")).iloc[:, 0]
    prior_rev = ttm_value("revenue", years_back=1)
    out["revenue_growth"] = out["revenue"] / prior_rev - 1 if prior_rev else float("nan")
    out.attrs["period_end"] = q_end
    out.attrs["label"] = f"TTM {q_end:%b-%y}"
    return out


def latest_shares_outstanding(facts: dict) -> float | None:
    """Most recent share count from a filing cover page (dei:EntityCommonStockSharesOutstanding)."""
    node = facts["facts"].get("dei", {}).get("EntityCommonStockSharesOutstanding")
    if node is None:
        return None
    vals = sorted(node["units"]["shares"], key=lambda f: (f["end"], f["filed"]))
    return float(vals[-1]["val"])


def other_share_classes(facts: dict) -> float:
    """Shares that count toward EPS but not the common count on the cover page.

    Example: lululemon's exchangeable shares, which convert one-for-one into common stock.
    Estimated from the latest quarter as basic weighted average shares minus the average
    of common shares outstanding at the start and end of that quarter. Zero if the data
    is missing or the gap is negative (buyback timing noise).
    """
    quarters = [r for r in _duration_facts(facts, "WeightedAverageNumberOfSharesOutstandingBasic")
                if 80 <= r["days"] <= 100]
    node = facts["facts"].get("us-gaap", {}).get("CommonStockSharesOutstanding")
    if not quarters or node is None:
        return 0.0
    q = max(quarters, key=lambda r: (r["end"], r["filed"]))
    start = q["end"] - pd.Timedelta(days=q["days"])
    outstanding = {}
    for f in node["units"].get("shares", []):
        outstanding[date.fromisoformat(f["end"])] = float(f["val"])

    def near(d: date) -> float | None:
        hits = [k for k in outstanding if abs((k - d).days) <= 10]
        return outstanding[min(hits, key=lambda k: abs((k - d).days))] if hits else None

    s, e = near(start), near(q["end"])
    if s is None or e is None:
        return 0.0
    return max(q["val"] - (s + e) / 2, 0.0)
