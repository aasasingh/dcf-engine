from dcf.clean import _annual_facts, _stitch, fiscal_year


def _fact(start, end, val, filed, form="10-K"):
    f = {"end": end, "val": val, "filed": filed, "form": form}
    if start:
        f["start"] = start
    return f


def _facts(**tags):
    return {"facts": {"us-gaap": {t: {"units": {"USD": rows}} for t, rows in tags.items()}}}


def test_fiscal_year_labels_january_year_ends_as_prior_year():
    assert fiscal_year("2026-02-01") == 2025
    assert fiscal_year("2025-12-31") == 2025
    assert fiscal_year("2025-06-30") == 2025


def test_annual_facts_dedupes_and_ignores_quarters():
    facts = _facts(Revenues=[
        _fact("2023-01-01", "2023-12-31", 100, "2024-02-01"),
        _fact("2023-01-01", "2023-12-31", 101, "2025-02-01"),          # restated comparative
        _fact("2024-01-01", "2024-12-31", 120, "2025-02-01"),
        _fact("2024-10-01", "2024-12-31", 35, "2025-02-01"),           # Q4 inside the 10-K
        _fact("2025-01-01", "2025-03-31", 30, "2025-05-01", "10-Q"),  # quarterly filing
    ])
    s = _annual_facts(facts, "Revenues", instant=False)
    assert s.to_dict() == {2023: 101, 2024: 120}


def test_stitch_prefers_first_tag_and_fills_gaps_from_later_tags():
    facts = _facts(
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            _fact("2024-01-01", "2024-12-31", 120, "2025-02-01")],
        SalesRevenueNet=[
            _fact("2023-01-01", "2023-12-31", 100, "2024-02-01"),
            _fact("2024-01-01", "2024-12-31", 999, "2025-02-01")],
    )
    s = _stitch(facts, ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
                instant=False)
    assert s.to_dict() == {2023: 100, 2024: 120}


def test_ttm_is_last_fiscal_year_plus_ytd_minus_prior_ytd():
    import pandas as pd
    from dcf.clean import trailing_twelve_months

    def rows(fy_vals, ytd_vals):
        out = [_fact(f"{y}-01-01", f"{y}-12-31", v, f"{y + 1}-02-15") for y, v in fy_vals.items()]
        out += [_fact(f"{y}-01-01", f"{y}-06-30", v, f"{y}-08-01", "10-Q") for y, v in ytd_vals.items()]
        return out

    facts = _facts(
        Revenues=rows({2024: 100, 2025: 110}, {2024: 45, 2025: 50, 2026: 60}),
        OperatingIncomeLoss=rows({2024: 10, 2025: 12}, {2024: 4, 2025: 5, 2026: 4}),
    )
    from dcf.clean import FLOW_TAGS, INSTANT_TAGS
    items = [k for k in (*FLOW_TAGS, *INSTANT_TAGS) if k != "operating_lease_liability_noncurrent"]
    hist = pd.DataFrame(float("nan"), index=items, columns=[2024, 2025])
    hist.loc["revenue"] = [100.0, 110.0]
    hist.loc["ebit"] = [10.0, 12.0]
    ttm = trailing_twelve_months(facts, hist)
    assert ttm["revenue"] == 110 + 60 - 50
    assert ttm["ebit"] == 12 + 4 - 5
    assert ttm["revenue_growth"] == (120 / (100 + 50 - 45)) - 1
    assert ttm.attrs["label"] == "TTM Jun-26"


def test_other_share_classes_is_basic_average_minus_average_common():
    from dcf.clean import other_share_classes
    facts = {"facts": {"us-gaap": {
        "WeightedAverageNumberOfSharesOutstandingBasic": {"units": {"shares": [
            _fact("2026-05-04", "2026-08-02", 113, "2026-09-03", "10-Q"),
            _fact("2026-02-02", "2026-08-02", 114, "2026-09-03", "10-Q"),  # year-to-date, ignored
        ]}},
        "CommonStockSharesOutstanding": {"units": {"shares": [
            _fact(None, "2026-05-03", 109, "2026-06-04", "10-Q"),
            _fact(None, "2026-08-02", 107, "2026-09-03", "10-Q"),
        ]}},
    }}}
    assert other_share_classes(facts) == 5
