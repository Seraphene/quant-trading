"""
strategy.py – Confluence-based trading strategy for Gold (GLD).

Architecture
────────────
The strategy scores each bar against **8 independent confluence factors**.
A trade is only triggered when ≥ MIN_CONFLUENCE factors align in the same
direction.  This multi-layer approach filters out noise and dramatically
reduces false signals compared to any single-indicator system.

Confluence Factors (per-bar, per-direction)
───────────────────────────────────────────
 #  Factor              Description
 1  EMA Crossover       EMA_fast crosses EMA_slow (trend trigger)
 2  RSI Filter          RSI not yet overbought (long) / not yet oversold (short)
 3  MACD Confirmation   MACD histogram expanding in trade direction
 4  RSI Divergence      Bullish / bearish divergence detected recently
 5  MACD Divergence     Bullish / bearish divergence detected recently
 6  Fair Value Gap      Price is inside a recent FVG zone (mean-reversion magnet)
 7  Order Block         Price is inside a recent institutional OB zone
 8  Liquidity Sweep     A recent liquidity grab (stop-hunt → reversal)

EXIT: ATR-based stop-loss / take-profit set at order time.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd
import numpy as np

import config as cfg
from smc import price_in_fvg_zone, price_in_order_block
from logger import get_logger

log = get_logger("strategy")


# ── Signal types ──────────────────────────────────────────────

class Direction(str, Enum):
    LONG  = "LONG"
    SHORT = "SHORT"


@dataclass
class Signal:
    """Immutable trade signal produced by the strategy."""
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    date: pd.Timestamp
    confluence: int = 0
    factors: list[str] = field(default_factory=list)


# ── Confluence scoring ────────────────────────────────────────

def _score_bar(df: pd.DataFrame, i: int) -> tuple[int, list[str], int, list[str]]:
    """
    Evaluate all confluence factors for bar `i`.

    Returns (long_score, long_factors, short_score, short_factors)
    """
    row  = df.iloc[i]
    prev = df.iloc[i - 1] if i > 0 else row

    long_f: list[str]  = []
    short_f: list[str] = []

    # ── 1a. EMA Trend (directional bias) ──────────────────────
    #    Fast EMA above slow = bullish bias, below = bearish bias.
    #    This is the minimum directional requirement.
    ema_f      = row["EMA_fast"]
    ema_s      = row["EMA_slow"]
    ema_f_prev = prev["EMA_fast"]
    ema_s_prev = prev["EMA_slow"]

    if ema_f > ema_s:
        long_f.append("EMA_trend")
    if ema_f < ema_s:
        short_f.append("EMA_trend")

    # ── 1b. EMA Crossover (bonus — exact cross bar) ──────────
    if ema_f_prev <= ema_s_prev and ema_f > ema_s:
        long_f.append("EMA_cross")
    if ema_f_prev >= ema_s_prev and ema_f < ema_s:
        short_f.append("EMA_cross")

    # ── 2. RSI Filter ─────────────────────────────────────────
    rsi_val = row["RSI"]
    if not pd.isna(rsi_val):
        if rsi_val < cfg.RSI_OVERBOUGHT:
            long_f.append("RSI_filter")
        if rsi_val > cfg.RSI_OVERSOLD:
            short_f.append("RSI_filter")

    # ── 3. MACD Confirmation ──────────────────────────────────
    macd_hist      = row.get("MACD_hist", np.nan)
    macd_hist_prev = prev.get("MACD_hist", np.nan)
    if not pd.isna(macd_hist) and not pd.isna(macd_hist_prev):
        if macd_hist > macd_hist_prev and macd_hist > 0:
            long_f.append("MACD_confirm")
        elif macd_hist_prev < 0 and macd_hist >= 0:
            long_f.append("MACD_confirm")

        if macd_hist < macd_hist_prev and macd_hist < 0:
            short_f.append("MACD_confirm")
        elif macd_hist_prev > 0 and macd_hist <= 0:
            short_f.append("MACD_confirm")

    # ── 4. RSI Divergence ─────────────────────────────────────
    rsi_div = row.get("RSI_div", 0)
    if rsi_div == 1:
        long_f.append("RSI_divergence")
    elif rsi_div == -1:
        short_f.append("RSI_divergence")

    # ── 5. MACD Divergence ────────────────────────────────────
    macd_div = row.get("MACD_div", 0)
    if macd_div == 1:
        long_f.append("MACD_divergence")
    elif macd_div == -1:
        short_f.append("MACD_divergence")

    # ── 6. Fair Value Gap proximity ───────────────────────────
    if "FVG_bull" in df.columns:
        if price_in_fvg_zone(df, i, "LONG"):
            long_f.append("FVG_zone")
        if price_in_fvg_zone(df, i, "SHORT"):
            short_f.append("FVG_zone")

    # ── 7. Order Block proximity ──────────────────────────────
    if "OB_bull" in df.columns:
        if price_in_order_block(df, i, "LONG"):
            long_f.append("Order_Block")
        if price_in_order_block(df, i, "SHORT"):
            short_f.append("Order_Block")

    # ── 8. Liquidity Sweep ────────────────────────────────────
    if "LIQ_sweep_bull" in df.columns:
        start = max(0, i - cfg.LIQ_SWEEP_LOOKBACK)
        if df["LIQ_sweep_bull"].iloc[start:i + 1].sum() > 0:
            long_f.append("LIQ_sweep")
        if df["LIQ_sweep_bear"].iloc[start:i + 1].sum() < 0:
            short_f.append("LIQ_sweep")

    return len(long_f), long_f, len(short_f), short_f


# ── Core signal generation ────────────────────────────────────

def generate_signals(df: pd.DataFrame) -> list[Signal]:
    """
    Scan an enriched DataFrame and return Signals where
    confluence ≥ MIN_CONFLUENCE.
    """
    required = {"Close", "High", "Low", "EMA_fast", "EMA_slow", "RSI", "ATR"}
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        raise ValueError(f"DataFrame missing columns: {missing}")

    signals: list[Signal] = []
    last_signal_bar: int = -999      # cooldown tracker

    for i in range(1, len(df)):
        row = df.iloc[i]

        if pd.isna(row["EMA_slow"]) or pd.isna(row["RSI"]) or pd.isna(row["ATR"]):
            continue

        # Cooldown: skip if too close to the last signal
        if (i - last_signal_bar) < cfg.SIGNAL_COOLDOWN:
            continue

        close   = row["Close"]
        atr_val = row["ATR"]
        date    = df.index[i]

        long_score, long_factors, short_score, short_factors = _score_bar(df, i)

        # ── LONG ──────────────────────────────────────────────
        #   Require: EMA_trend (directional bias) + enough confluence.
        #   EMA_cross is no longer mandatory — allows continuation entries.
        if (long_score >= cfg.MIN_CONFLUENCE
                and "EMA_trend" in long_factors
                and long_score > short_score):
            sl = close - atr_val * cfg.ATR_SL_MULT
            tp = close + atr_val * cfg.ATR_TP_MULT
            sig = Signal(Direction.LONG, close, sl, tp, atr_val, date,
                         long_score, long_factors)
            signals.append(sig)
            last_signal_bar = i
            log.debug(
                f"LONG  {date.date()} @ {close:.2f}  "
                f"confluence={long_score}  factors={long_factors}"
            )

        # ── SHORT ─────────────────────────────────────────────
        elif (short_score >= cfg.MIN_CONFLUENCE
                and "EMA_trend" in short_factors
                and short_score > long_score):
            sl = close + atr_val * cfg.ATR_SL_MULT
            tp = close - atr_val * cfg.ATR_TP_MULT
            sig = Signal(Direction.SHORT, close, sl, tp, atr_val, date,
                         short_score, short_factors)
            signals.append(sig)
            last_signal_bar = i
            log.debug(
                f"SHORT {date.date()} @ {close:.2f}  "
                f"confluence={short_score}  factors={short_factors}"
            )

    log.info(f"Generated {len(signals)} signals over {len(df)} bars  (min_confluence={cfg.MIN_CONFLUENCE})")
    return signals


def latest_signal(df: pd.DataFrame) -> Optional[Signal]:
    """Return only the most recent signal, or None."""
    sigs = generate_signals(df)
    return sigs[-1] if sigs else None
