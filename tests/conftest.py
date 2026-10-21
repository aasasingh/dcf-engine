import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcf.assumptions import Assumptions  # noqa: E402
from dcf.model import BaseYear  # noqa: E402


@pytest.fixture
def toy_assumptions() -> Assumptions:
    """Round numbers so the DCF can be checked by hand (see test_model.py)."""
    return Assumptions(
        growth_start=0.10, terminal_growth=0.02, forecast_years=2,
        margin_start=0.20, margin_target=0.20, margin_fade_years=1,
        tax_rate=0.25, d_and_a_pct_revenue=0.05, capex_pct_revenue=0.05, nwc_pct_revenue=0.10,
        risk_free=0.04, beta=1.0, equity_risk_premium=0.05, pre_tax_cost_of_debt=0.06,
        wacc_override=0.10, mid_year_convention=False,
    )


@pytest.fixture
def toy_base() -> BaseYear:
    return BaseYear(label="FY2025", period_end=date(2025, 12, 31), revenue=100.0, cash=10.0, debt=0.0,
                    lease_liabilities=5.0, shares=10.0, price=10.0)


@pytest.fixture
def toy_hist() -> pd.DataFrame:
    return pd.DataFrame({2024: [90.0, 0.2], 2025: [100.0, 0.2]},
                        index=["revenue", "ebit_margin"])
