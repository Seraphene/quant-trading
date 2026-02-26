"""
data_fetch.py – Download, clean, cache and enrich OHLCV data.

Supports both daily and intraday timeframes.  When config selects "4h",
data is downloaded as 1-hour bars (yfinance max for intraday) and then
resampled to 4-hour candles before caching.

Usage
─────
    python data_fetch.py          # download + enrich both symbols
    python data_fetch.py --force  # re-download even if cached CSVs exist
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# NOTE: We use `import config` (not `from config import ...`) so that
# runtime overrides from backtest.py --timeframe / paper_bot.py --timeframe
# are visible.  `from config import X` binds at import time, which means
# changes made by _apply_timeframe_override() would be invisible here.
import config as cfg
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY
from indicators import add_indicators
from smc import add_smc
from logger import get_logger

log = get_logger("data_fetch")


# ── Helpers ────────────────────────────────────────────────────

def _csv_path(symbol: str) -> Path:
    """Standardised filename for cached data, unique per timeframe."""
    safe_sym = symbol.replace("=", "_")
    return cfg.DATA_DIR / f"{safe_sym}_{cfg.ACTIVE_TIMEFRAME}.csv"


def _resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-hour bars to 4-hour OHLCV candles.
    yfinance does not support a native '4h' interval, so we download
    '1h' and aggregate here.
    """
    ohlcv = {
        "Open":   "first",
        "High":   "max",
        "Low":    "min",
        "Close":  "last",
        "Volume": "sum",
    }
    df_4h = df.resample("4h").agg(ohlcv).dropna(subset=["Open", "Close"])
    return df_4h


def _download_via_yfinance(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Download OHLCV data via yfinance."""
    # yfinance does not support "4h" natively — download "1h" instead
    # "1h" is natively supported and used directly
    yf_interval = "1h" if cfg.ACTIVE_TIMEFRAME == "4h" else cfg.TIMEFRAME

    # yfinance enforces a strict 730-day max for intraday data.
    # Cap the start date to stay safely within that window.
    if yf_interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"):
        max_intraday_start = end - timedelta(days=729)
        if start < max_intraday_start:
            log.info(f"Capping intraday lookback to 729 days (yfinance limit)")
            start = max_intraday_start

    log.info(
        f"Downloading {symbol} via yfinance {start.date()} -> {end.date()}  "
        f"interval={yf_interval} (target={cfg.ACTIVE_TIMEFRAME}) ..."
    )
    df: pd.DataFrame = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=yf_interval,
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
    return df


def _download_via_alpaca(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Download OHLCV data via Alpaca Market Data API."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise RuntimeError("Alpaca API keys missing. Fallback to yfinance or set keys in .env.")

    client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

    # Map timeframes
    if cfg.ACTIVE_TIMEFRAME == "1d":
        tf = TimeFrame.Day
    elif cfg.ACTIVE_TIMEFRAME in ("4h", "1h"):
        tf = TimeFrame.Hour
    else:
        raise ValueError(f"Timeframe {cfg.ACTIVE_TIMEFRAME} not yet supported via Alpaca")

    # Alpaca Free Tier has a 15-minute delay. If we request too close to "now",
    # it fails with a subscription error. Use UTC-aware timestamps with a buffer.
    now_utc = datetime.now(timezone.utc)
    alpaca_end = now_utc - timedelta(minutes=16)
    
    # Alpaca expects the start to be at least some time before end
    alpaca_start = alpaca_end - (end - start)

    log.info(f"Downloading {symbol} via Alpaca {alpaca_start.date()} -> {alpaca_end.date()}  timeframe={tf} ...")

    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf,
        start=alpaca_start,
        end=alpaca_end,
    )

    bars = client.get_stock_bars(request_params)
    df = bars.df

    if df.empty:
        raise RuntimeError(f"Alpaca returned no data for {symbol}")

    # Alpaca returns a multi-index (symbol, timestamp). Reset and rename.
    df = df.reset_index(level=0, drop=True)
    df.index.name = "Date"

    # Standardise column names (Alpaca returns lowercase)
    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })

    return df[["Open", "High", "Low", "Close", "Volume"]]


def download_symbol(symbol: str, force: bool = False, provider: str = None) -> pd.DataFrame:
    """
    Download OHLCV data for the active timeframe.
    Returns a cleaned DataFrame indexed by Date.
    """
    csv = _csv_path(symbol)

    if csv.exists() and not force:
        log.info(f"Loading cached data for {symbol} from {csv.name}")
        df = pd.read_csv(csv, index_col="Date", parse_dates=True)
        return df

    end   = datetime.today()
    start = end - timedelta(days=cfg.LOOKBACK_YEARS * 365)

    # Determine provider
    active_provider = provider or cfg.DATA_PROVIDER

    # Fallback for Futures (Alpaca only supports Stocks/ETFs)
    if active_provider == "alpaca" and ("=F" in symbol or "=X" in symbol):
        log.warning(f"Alpaca does not support futures/forex ({symbol}). Falling back to yfinance.")
        active_provider = "yfinance"

    try:
        if active_provider == "alpaca":
            df = _download_via_alpaca(symbol, start, end)
        else:
            df = _download_via_yfinance(symbol, start, end)
    except Exception as e:
        log.error(f"Download via {active_provider} failed: {e}")
        if active_provider == "alpaca":
            log.info("Attempting fallback to yfinance...")
            df = _download_via_yfinance(symbol, start, end)
        else:
            raise

    # Remove rows with all-NaN OHLC
    df.dropna(subset=["Open", "High", "Low", "Close"], how="all", inplace=True)

    # Forward-fill minor gaps, then drop any remaining NaN
    df.ffill(inplace=True)
    df.dropna(inplace=True)

    # Resample 1h → 4h when needed
    if cfg.ACTIVE_TIMEFRAME == "4h":
        log.info(f"Resampling {len(df)} × 1h bars → 4h candles …")
        df = _resample_to_4h(df)
        log.info(f"After resample: {len(df)} × 4h bars")

    df.index.name = "Date"
    df.to_csv(csv)
    log.info(f"Saved {len(df)} rows to {csv.name}")

    return df


def fetch_and_enrich(symbol: str, force: bool = False,
                     drop_incomplete: bool = False,
                     provider: str = None) -> pd.DataFrame:
    """
    Download + attach technical indicators + Smart Money Concepts.

    Parameters
    ----------
    drop_incomplete : bool
        If True, drop the last candle before computing indicators.
        Use this for LIVE trading — yfinance includes the current
        (still-forming) candle, whose Open/High/Low/Close are not
        final. Indicators computed on partial data produce unreliable
        signals. For backtesting this should be False (all candles
        are already closed).
    provider : str, optional
        Data provider to use ("yfinance" or "alpaca").
    """
    df = download_symbol(symbol, force=force, provider=provider)

    if drop_incomplete and len(df) > 1:
        last_ts = df.index[-1]
        df = df.iloc[:-1]
        log.info(
            f"Dropped incomplete candle @ {last_ts}  "
            f"({len(df)} closed bars remain)"
        )

    df = add_indicators(
        df, cfg.EMA_FAST, cfg.EMA_SLOW, cfg.RSI_PERIOD, cfg.ATR_PERIOD,
        cfg.MACD_FAST, cfg.MACD_SLOW, cfg.MACD_SIGNAL,
    )
    df = add_smc(df)
    return df


# ── CLI entry-point ────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch & cache OHLCV data")
    parser.add_argument("--force", action="store_true", help="Re-download even if CSV exists")
    args = parser.parse_args()

    for sym in (cfg.SIGNAL_SYMBOL, cfg.TRADE_SYMBOL):
        df = fetch_and_enrich(sym, force=args.force)
        log.info(f"{sym}: {len(df)} rows, columns = {list(df.columns)}")
        log.info(f"{sym} tail:\n{df.tail(3).to_string()}")


if __name__ == "__main__":
    main()
