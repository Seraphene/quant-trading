"""
data_fetch.py – Download, clean, cache and enrich OHLCV data.

Usage
─────
    python data_fetch.py          # download + enrich both symbols
    python data_fetch.py --force  # re-download even if cached CSVs exist
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import (
    SIGNAL_SYMBOL, TRADE_SYMBOL, DATA_DIR,
    LOOKBACK_YEARS, TIMEFRAME,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, ATR_PERIOD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
)
from indicators import add_indicators
from smc import add_smc
from logger import get_logger

log = get_logger("data_fetch")


# ── Helpers ────────────────────────────────────────────────────

def _csv_path(symbol: str) -> Path:
    """Standardised filename for cached data."""
    return DATA_DIR / f"{symbol.replace('=', '_')}_daily.csv"


def download_symbol(symbol: str, force: bool = False) -> pd.DataFrame:
    """
    Download daily OHLCV data via yfinance.
    Returns a cleaned DataFrame indexed by Date.
    """
    csv = _csv_path(symbol)

    if csv.exists() and not force:
        log.info(f"Loading cached data for {symbol} from {csv.name}")
        df = pd.read_csv(csv, index_col="Date", parse_dates=True)
        return df

    end   = datetime.today()
    start = end - timedelta(days=LOOKBACK_YEARS * 365)

    log.info(f"Downloading {symbol}  {start.date()} → {end.date()} …")
    df: pd.DataFrame = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=TIMEFRAME,
        auto_adjust=True,
        progress=False,
    )

    if df.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")

    # Flatten multi-level columns if present (yfinance ≥ 0.2.31)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Keep only standard OHLCV columns
    expected = ["Open", "High", "Low", "Close", "Volume"]
    df = df[[c for c in expected if c in df.columns]]

    # Remove rows with all-NaN OHLC
    df.dropna(subset=["Open", "High", "Low", "Close"], how="all", inplace=True)

    # Forward-fill minor gaps, then drop any remaining NaN
    df.ffill(inplace=True)
    df.dropna(inplace=True)

    df.index.name = "Date"
    df.to_csv(csv)
    log.info(f"Saved {len(df)} rows → {csv.name}")

    return df


def fetch_and_enrich(symbol: str, force: bool = False) -> pd.DataFrame:
    """Download + attach technical indicators + Smart Money Concepts."""
    df = download_symbol(symbol, force=force)
    df = add_indicators(
        df, EMA_FAST, EMA_SLOW, RSI_PERIOD, ATR_PERIOD,
        MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    )
    df = add_smc(df)
    return df


# ── CLI entry-point ────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch & cache OHLCV data")
    parser.add_argument("--force", action="store_true", help="Re-download even if CSV exists")
    args = parser.parse_args()

    for sym in (SIGNAL_SYMBOL, TRADE_SYMBOL):
        df = fetch_and_enrich(sym, force=args.force)
        log.info(f"{sym}: {len(df)} rows, columns = {list(df.columns)}")
        log.info(f"{sym} tail:\n{df.tail(3).to_string()}")


if __name__ == "__main__":
    main()
