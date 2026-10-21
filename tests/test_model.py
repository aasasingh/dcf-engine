import pytest

from dcf.model import growth_path, margin_path, run_dcf, wacc
from dcf.reverse import reverse_dcf


def test_toy_company_matches_hand_calculation(toy_assumptions, toy_base):
    # Year 1: revenue 110, EBIT 22, NOPAT 16.5, D&A = capex = 5.5, NWC 10 -> 11
    fcff1 = 16.5 + 5.5 - 5.5 - 1.0
    # Year 2: growth fades to 2%: revenue 112.2, NOPAT 16.83, NWC 11 -> 11.22
    fcff2 = 16.83 + 5.61 - 5.61 - 0.22
    tv = fcff2 * 1.02 / (0.10 - 0.02)
    ev = fcff1 / 1.1 + fcff2 / 1.1**2 + tv / 1.1**2
    equity = ev + 10.0  # net cash; leases excluded by default

    r = run_dcf(toy_assumptions, toy_base)
    assert r.projection.loc["fcff"].tolist() == pytest.approx([fcff1, fcff2])
    assert r.terminal_value == pytest.approx(tv)
    assert r.enterprise_value == pytest.approx(ev)
    assert r.value_per_share == pytest.approx(equity / 10.0)


def test_mid_year_convention_raises_value(toy_assumptions, toy_base):
    end = run_dcf(toy_assumptions, toy_base).value_per_share
    mid = run_dcf(toy_assumptions.with_(mid_year_convention=True), toy_base).value_per_share
    assert mid > end


def test_leases_as_debt_reduces_equity(toy_assumptions, toy_base):
    without = run_dcf(toy_assumptions, toy_base).equity_value
    with_leases = run_dcf(toy_assumptions.with_(leases_as_debt=True), toy_base).equity_value
    assert without - with_leases == pytest.approx(5.0)


def test_paths_start_and_end_where_expected(toy_assumptions):
    a = toy_assumptions.with_(forecast_years=10, margin_start=0.15, margin_target=0.25,
                              margin_fade_years=5)
    g = growth_path(a)
    assert g[0] == pytest.approx(0.10) and g[-1] == pytest.approx(0.02)
    m = margin_path(a)
    assert m[4] == pytest.approx(0.25) and m[-1] == pytest.approx(0.25)


def test_capm_wacc_with_no_debt_equals_cost_of_equity(toy_assumptions, toy_base):
    ke, w = wacc(toy_assumptions.with_(wacc_override=None), toy_base)
    assert ke == pytest.approx(0.04 + 1.0 * 0.05)
    assert w == pytest.approx(ke)


def test_wacc_must_exceed_terminal_growth(toy_assumptions, toy_base):
    with pytest.raises(ValueError):
        run_dcf(toy_assumptions.with_(wacc_override=0.02), toy_base)


def test_reverse_dcf_recovers_assumptions_when_price_equals_value(toy_assumptions, toy_base):
    from dataclasses import replace
    value = run_dcf(toy_assumptions, toy_base).value_per_share
    implied = reverse_dcf(toy_assumptions, replace(toy_base, price=value))
    assert implied["growth_start"].implied == pytest.approx(0.10, abs=1e-6)
    assert implied["margin_target"].implied == pytest.approx(0.20, abs=1e-6)
