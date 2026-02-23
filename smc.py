"""
smc.py – Smart Money Concepts: Fair Value Gaps, Order Blocks, Liquidity Sweeps.

All functions operate on a DataFrame with standard OHLCV + ATR columns
and return enrichment columns that the strategy can query per-bar.
"""

import pandas as pd
import numpy as np

from config import (
    FVG_MIN_BODY_ATR,
    FVG_LOOKBACK,
    OB_LOOKBACK,
    LIQ_SWEEP_LOOKBACK,
    STRUCTURE_BREAK_BARS,
)
from logger import get_logger

log = get_logger("smc")


# ═══════════════════════════════════════════════════════════════
# 1. Fair Value Gaps (FVG)
# ═══════════════════════════════════════════════════════════════
#
#   Bullish FVG  (3-candle pattern):
#       candle[i-2].High  <  candle[i].Low
#       → gap between bar i-2 high and bar i low; middle bar = displacement
#
#   Bearish FVG:
#       candle[i-2].Low  >  candle[i].High
#       → gap between bar i-2 low and bar i high
#
#   The middle candle must show "strong displacement":
#       abs(Close - Open) of middle candle  >=  ATR × FVG_MIN_BODY_ATR
# ═══════════════════════════════════════════════════════════════

def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add FVG columns to df:
        FVG_bull : +1 on bars where a bullish FVG was just formed
        FVG_bear : -1 on bars where a bearish FVG was just formed
        FVG_bull_zone_lo / FVG_bull_zone_hi : unfilled bullish gap zone
        FVG_bear_zone_lo / FVG_bear_zone_hi : unfilled bearish gap zone
    """
    n = len(df)
    bull = np.zeros(n, dtype=int)
    bear = np.zeros(n, dtype=int)
    bull_lo = np.full(n, np.nan)
    bull_hi = np.full(n, np.nan)
    bear_lo = np.full(n, np.nan)
    bear_hi = np.full(n, np.nan)

    highs  = df["High"].values
    lows   = df["Low"].values
    opens  = df["Open"].values
    closes = df["Close"].values
    atrs   = df["ATR"].values if "ATR" in df.columns else np.ones(n)

    for i in range(2, n):
        mid_body = abs(closes[i - 1] - opens[i - 1])
        displacement = mid_body >= atrs[i - 1] * FVG_MIN_BODY_ATR if not np.isnan(atrs[i - 1]) else False

        # Bullish FVG: gap up — bar[i-2] high < bar[i] low
        if highs[i - 2] < lows[i] and displacement:
            bull[i] = 1
            bull_lo[i] = highs[i - 2]
            bull_hi[i] = lows[i]

        # Bearish FVG: gap down — bar[i-2] low > bar[i] high
        if lows[i - 2] > highs[i] and displacement:
            bear[i] = -1
            bear_lo[i] = highs[i]
            bear_hi[i] = lows[i - 2]

    df = df.copy()
    df["FVG_bull"]         = bull
    df["FVG_bear"]         = bear
    df["FVG_bull_zone_lo"] = bull_lo
    df["FVG_bull_zone_hi"] = bull_hi
    df["FVG_bear_zone_lo"] = bear_lo
    df["FVG_bear_zone_hi"] = bear_hi
    return df


def price_in_fvg_zone(df: pd.DataFrame, idx: int, direction: str) -> bool:
    """
    Check whether the close at `idx` is near an unfilled FVG zone
    from the last FVG_LOOKBACK bars.

    direction: 'LONG' checks bullish FVGs, 'SHORT' checks bearish.
    """
    start = max(0, idx - FVG_LOOKBACK)
    close = df["Close"].iloc[idx]

    if direction == "LONG":
        for j in range(start, idx):
            lo = df["FVG_bull_zone_lo"].iloc[j]
            hi = df["FVG_bull_zone_hi"].iloc[j]
            if not np.isnan(lo) and lo <= close <= hi:
                return True
    else:
        for j in range(start, idx):
            lo = df["FVG_bear_zone_lo"].iloc[j]
            hi = df["FVG_bear_zone_hi"].iloc[j]
            if not np.isnan(lo) and lo <= close <= hi:
                return True
    return False


# ═══════════════════════════════════════════════════════════════
# 2. Order Blocks
# ═══════════════════════════════════════════════════════════════
#
#   Bullish Order Block:
#       The last bearish (red) candle before an impulsive bullish move
#       that breaks a recent swing high (structure break).
#
#   Bearish Order Block:
#       The last bullish (green) candle before an impulsive bearish move
#       that breaks a recent swing low.
# ═══════════════════════════════════════════════════════════════

def detect_order_blocks(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add columns:
        OB_bull : +1 on bars that ARE the bullish order block candle
        OB_bear : -1 on bars that ARE the bearish order block candle
        OB_bull_lo / OB_bull_hi : zone of the bullish OB
        OB_bear_lo / OB_bear_hi : zone of the bearish OB
    """
    n = len(df)
    ob_bull = np.zeros(n, dtype=int)
    ob_bear = np.zeros(n, dtype=int)
    ob_bull_lo = np.full(n, np.nan)
    ob_bull_hi = np.full(n, np.nan)
    ob_bear_lo = np.full(n, np.nan)
    ob_bear_hi = np.full(n, np.nan)

    highs  = df["High"].values
    lows   = df["Low"].values
    opens  = df["Open"].values
    closes = df["Close"].values

    for i in range(OB_LOOKBACK, n):
        lookback_high = highs[i - OB_LOOKBACK: i].max()
        lookback_low  = lows[i - OB_LOOKBACK: i].min()

        # ── Bullish structure break: current close breaks above recent high
        if closes[i] > lookback_high:
            # Find the last bearish candle before this break
            for j in range(i - 1, max(i - OB_LOOKBACK, 0) - 1, -1):
                if closes[j] < opens[j]:  # bearish candle
                    ob_bull[j] = 1
                    ob_bull_lo[j] = lows[j]
                    ob_bull_hi[j] = highs[j]
                    break

        # ── Bearish structure break: current close breaks below recent low
        if closes[i] < lookback_low:
            # Find the last bullish candle before this break
            for j in range(i - 1, max(i - OB_LOOKBACK, 0) - 1, -1):
                if closes[j] > opens[j]:  # bullish candle
                    ob_bear[j] = -1
                    ob_bear_lo[j] = lows[j]
                    ob_bear_hi[j] = highs[j]
                    break

    df = df.copy()
    df["OB_bull"]    = ob_bull
    df["OB_bear"]    = ob_bear
    df["OB_bull_lo"] = ob_bull_lo
    df["OB_bull_hi"] = ob_bull_hi
    df["OB_bear_lo"] = ob_bear_lo
    df["OB_bear_hi"] = ob_bear_hi
    return df


def price_in_order_block(df: pd.DataFrame, idx: int, direction: str) -> bool:
    """Check if current close is within a recent order block zone."""
    start = max(0, idx - OB_LOOKBACK)
    close = df["Close"].iloc[idx]

    if direction == "LONG":
        for j in range(start, idx):
            lo = df["OB_bull_lo"].iloc[j]
            hi = df["OB_bull_hi"].iloc[j]
            if not np.isnan(lo) and lo <= close <= hi:
                return True
    else:
        for j in range(start, idx):
            lo = df["OB_bear_lo"].iloc[j]
            hi = df["OB_bear_hi"].iloc[j]
            if not np.isnan(lo) and lo <= close <= hi:
                return True
    return False


# ═══════════════════════════════════════════════════════════════
# 3. Liquidity Sweeps
# ═══════════════════════════════════════════════════════════════
#
#   Bullish liquidity sweep:
#       Price dips BELOW a recent swing low (triggering stop-losses)
#       then closes back ABOVE it in the same or next bar → reversal.
#
#   Bearish liquidity sweep:
#       Price spikes ABOVE a recent swing high (triggering stops)
#       then closes back BELOW it → reversal.
# ═══════════════════════════════════════════════════════════════

def detect_liquidity_sweeps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add columns:
        LIQ_sweep_bull : +1 when a bullish sweep occurs
        LIQ_sweep_bear : -1 when a bearish sweep occurs
    """
    n = len(df)
    sweep_bull = np.zeros(n, dtype=int)
    sweep_bear = np.zeros(n, dtype=int)

    highs  = df["High"].values
    lows   = df["Low"].values
    closes = df["Close"].values

    for i in range(LIQ_SWEEP_LOOKBACK, n):
        window_lo = lows[i - LIQ_SWEEP_LOOKBACK: i].min()
        window_hi = highs[i - LIQ_SWEEP_LOOKBACK: i].max()

        # Bullish sweep: wick below recent low, close back above
        if lows[i] < window_lo and closes[i] > window_lo:
            sweep_bull[i] = 1

        # Bearish sweep: wick above recent high, close back below
        if highs[i] > window_hi and closes[i] < window_hi:
            sweep_bear[i] = -1

    df = df.copy()
    df["LIQ_sweep_bull"] = sweep_bull
    df["LIQ_sweep_bear"] = sweep_bear
    return df


# ═══════════════════════════════════════════════════════════════
# Master enrichment
# ═══════════════════════════════════════════════════════════════

def add_smc(df: pd.DataFrame) -> pd.DataFrame:
    """Run all Smart Money Concept detections and attach to df."""
    df = detect_fvg(df)
    df = detect_order_blocks(df)
    df = detect_liquidity_sweeps(df)
    log.info(
        f"SMC enrichment: "
        f"FVG_bull={int(df['FVG_bull'].sum())}  FVG_bear={int(abs(df['FVG_bear']).sum())}  "
        f"OB_bull={int(df['OB_bull'].sum())}  OB_bear={int(abs(df['OB_bear']).sum())}  "
        f"LIQ_bull={int(df['LIQ_sweep_bull'].sum())}  LIQ_bear={int(abs(df['LIQ_sweep_bear']).sum())}"
    )
    return df
