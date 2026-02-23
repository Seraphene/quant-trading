"""
indicators.py – Pure-pandas technical indicator calculations.

Every function takes a DataFrame with at least ['Open','High','Low','Close','Volume']
columns and returns a new column (or columns) that get merged in data_fetch.py.

Includes: EMA, RSI, ATR, MACD, RSI divergence, MACD divergence.
"""

import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════
# Core indicators
# ═══════════════════════════════════════════════════════════════

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def macd(series: pd.Series,
         fast: int = 12, slow: int = 26, signal: int = 9
         ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD (Moving Average Convergence Divergence).

    Returns
    -------
    macd_line   : fast EMA − slow EMA
    signal_line : EMA of macd_line
    histogram   : macd_line − signal_line
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ═══════════════════════════════════════════════════════════════
# Divergence detection
# ═══════════════════════════════════════════════════════════════

def _swing_lows(series: pd.Series, order: int = 5) -> pd.Series:
    """Mark local minima (swing lows) with True."""
    result = pd.Series(False, index=series.index)
    for i in range(order, len(series) - order):
        window = series.iloc[i - order: i + order + 1]
        if series.iloc[i] == window.min():
            result.iloc[i] = True
    return result


def _swing_highs(series: pd.Series, order: int = 5) -> pd.Series:
    """Mark local maxima (swing highs) with True."""
    result = pd.Series(False, index=series.index)
    for i in range(order, len(series) - order):
        window = series.iloc[i - order: i + order + 1]
        if series.iloc[i] == window.max():
            result.iloc[i] = True
    return result


def detect_divergence(price: pd.Series, oscillator: pd.Series,
                      order: int = 5) -> pd.Series:
    """
    Detect bullish and bearish divergence between price and an oscillator.

    Returns a Series with values:
        +1 = bullish divergence  (price lower-low, oscillator higher-low)
        -1 = bearish divergence  (price higher-high, oscillator lower-high)
         0 = no divergence
    """
    div = pd.Series(0, index=price.index, dtype=int)

    # ── Bullish divergence (swing lows) ───────────────────────
    sw_low = _swing_lows(price, order)
    low_idx = price.index[sw_low]
    for i in range(1, len(low_idx)):
        prev, curr = low_idx[i - 1], low_idx[i]
        # Price made a lower low but oscillator made a higher low
        if price.loc[curr] < price.loc[prev] and oscillator.loc[curr] > oscillator.loc[prev]:
            div.loc[curr] = 1

    # ── Bearish divergence (swing highs) ──────────────────────
    sw_high = _swing_highs(price, order)
    high_idx = price.index[sw_high]
    for i in range(1, len(high_idx)):
        prev, curr = high_idx[i - 1], high_idx[i]
        # Price made a higher high but oscillator made a lower high
        if price.loc[curr] > price.loc[prev] and oscillator.loc[curr] < oscillator.loc[prev]:
            div.loc[curr] = -1

    return div


# ═══════════════════════════════════════════════════════════════
# Master enrichment function
# ═══════════════════════════════════════════════════════════════

def add_indicators(df: pd.DataFrame,
                   ema_fast: int = 20,
                   ema_slow: int = 50,
                   rsi_period: int = 14,
                   atr_period: int = 14,
                   macd_fast: int = 12,
                   macd_slow: int = 26,
                   macd_signal: int = 9) -> pd.DataFrame:
    """Attach all indicators needed by the strategy as new columns."""
    df = df.copy()

    # Trend
    df["EMA_fast"] = ema(df["Close"], ema_fast)
    df["EMA_slow"] = ema(df["Close"], ema_slow)

    # Momentum
    df["RSI"]      = rsi(df["Close"], rsi_period)

    # Volatility
    df["ATR"]      = atr(df, atr_period)

    # MACD
    ml, sl, hist   = macd(df["Close"], macd_fast, macd_slow, macd_signal)
    df["MACD"]          = ml
    df["MACD_signal"]   = sl
    df["MACD_hist"]     = hist

    # Divergences
    df["RSI_div"]  = detect_divergence(df["Close"], df["RSI"], order=5)
    df["MACD_div"] = detect_divergence(df["Close"], df["MACD"], order=5)

    return df
