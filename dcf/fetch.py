"""Raw data acquisition: SEC EDGAR company facts and market data from Yahoo Finance.

Everything fetched is cached under data/raw/ so the model can be re-run offline.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# The SEC requires a descriptive User-Agent. Override with the SEC_USER_AGENT env var.
USER_AGENT = os.environ.get("SEC_USER_AGENT", "dcf-engine student research project")
CACHE_MAX_AGE_DAYS = 7


def _get_json(url: str) -> dict:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    time.sleep(0.15)  # stay well under the SEC's 10 requests/second limit
    return resp.json()


def _cached(path: Path, refresh: bool) -> bool:
    if refresh or not path.exists():
        return False
    age_days = (time.time() - path.stat().st_mtime) / 86400
    return age_days < CACHE_MAX_AGE_DAYS


def ticker_to_cik(ticker: str, refresh: bool = False) -> int:
    path = RAW_DIR / "company_tickers.json"
    if not _cached(path, refresh):
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_get_json("https://www.sec.gov/files/company_tickers.json")))
    for row in json.loads(path.read_text()).values():
        if row["ticker"].upper() == ticker.upper():
            return int(row["cik_str"])
    raise ValueError(f"Ticker {ticker!r} not found in SEC company list")


def company_facts(ticker: str, refresh: bool = False) -> dict:
    """All XBRL facts the company has ever filed, as the SEC's companyfacts JSON."""
    path = RAW_DIR / f"{ticker.upper()}.json"
    if not _cached(path, refresh):
        cik = ticker_to_cik(ticker, refresh)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")))
    return json.loads(path.read_text())


@dataclass
class MarketData:
    price: float
    risk_free: float          # 10-year US Treasury yield, decimal
    beta_raw: float           # OLS slope of monthly returns vs. S&P 500
    beta_adjusted: float      # Blume adjustment: 0.67 * raw + 0.33
    beta_observations: int
    as_of: str


def market_data(ticker: str, refresh: bool = False) -> MarketData:
    path = RAW_DIR / f"{ticker.upper()}_market.json"
    # Prices move daily, so market data is cached for one day rather than a week.
    if not refresh and path.exists() and time.time() - path.stat().st_mtime < 86400:
        return MarketData(**json.loads(path.read_text()))

    import yfinance as yf

    price = float(yf.Ticker(ticker).history(period="5d")["Close"].dropna().iloc[-1])

    tnx = float(yf.Ticker("^TNX").history(period="5d")["Close"].dropna().iloc[-1])
    risk_free = tnx / 100  # ^TNX is quoted in percent, e.g. 4.25

    closes = yf.download([ticker, "^GSPC"], period="5y", interval="1mo",
                         progress=False, auto_adjust=True)["Close"]
    returns = closes.pct_change().dropna()
    beta_raw = float(np.cov(returns[ticker], returns["^GSPC"])[0, 1] / returns["^GSPC"].var())

    md = MarketData(
        price=price,
        risk_free=risk_free,
        beta_raw=beta_raw,
        beta_adjusted=0.67 * beta_raw + 0.33,
        beta_observations=len(returns),
        as_of=pd.Timestamp.today().strftime("%Y-%m-%d"),
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(md.__dict__))
    return md
