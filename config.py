"""
config.py – Central configuration for the quant-trading project.

Loads secrets from .env and exposes all tuneable parameters in one place.

TIMEFRAME SWITCHING
───────────────────
Change `ACTIVE_TIMEFRAME` below (or set the TIMEFRAME env var) to switch
the entire system between presets.  Every parameter that differs between
Daily and 4-Hour trading is captured in TIMEFRAME_PRESETS — no other
file needs to be touched.

    ACTIVE_TIMEFRAME = "1d"   # swing trading on daily candles
    ACTIVE_TIMEFRAME = "4h"   # intraday on 4-hour candles
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from project root ───────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

# ── Alpaca Credentials ────────────────────────────────────────
ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY: str = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# ── Symbol Mapping ────────────────────────────────────────────
# SGOL (Aberdeen Physical Gold Shares) tracks spot gold price directly.
# At ~$24/share it is affordable for small accounts ($170+).
SIGNAL_SYMBOL: str = "SGOL"        # Analyse SGOL candles
TRADE_SYMBOL: str  = "SGOL"        # Trade SGOL on Alpaca paper

# ── Fractional Shares ─────────────────────────────────────────
USE_FRACTIONAL: bool = True         # Alpaca supports fractional shares

# ═══════════════════════════════════════════════════════════════
# TIMEFRAME PRESETS
# ═══════════════════════════════════════════════════════════════
# Each preset is a complete set of strategy / indicator / risk
# parameters tuned for that candle granularity.  To switch the
# whole system, change ACTIVE_TIMEFRAME (or set the TIMEFRAME
# env var).
#
#   python backtest.py --timeframe 4h
#   python backtest.py --timeframe 1d
#   set TIMEFRAME=4h && python paper_bot.py
# ═══════════════════════════════════════════════════════════════

ACTIVE_TIMEFRAME: str = os.getenv("TIMEFRAME", "1d")  # "1d" or "4h"

TIMEFRAME_PRESETS: dict = {
    # ── Daily (1D) Swing-Trading Preset ───────────────────────
    "1d": {
        "TIMEFRAME":            "1d",
        "LOOKBACK_YEARS":       5,       # 5 years of daily history

        # Strategy – Moving Averages
        "EMA_FAST":             20,
        "EMA_SLOW":             50,

        # Strategy – RSI
        "RSI_PERIOD":           14,
        "RSI_OVERSOLD":         30.0,
        "RSI_OVERBOUGHT":       70.0,

        # Strategy – ATR Stop-Loss / Take-Profit
        "ATR_PERIOD":           14,
        "ATR_SL_MULT":          1.5,
        "ATR_TP_MULT":          3.0,

        # Strategy – MACD
        "MACD_FAST":            12,
        "MACD_SLOW":            26,
        "MACD_SIGNAL":          9,

        # Smart Money Concepts (SMC)
        "FVG_MIN_BODY_ATR":     1.0,
        "FVG_LOOKBACK":         50,
        "OB_LOOKBACK":          20,
        "LIQ_SWEEP_LOOKBACK":   20,
        "STRUCTURE_BREAK_BARS": 5,

        # Confluence & Cooldown
        "MIN_CONFLUENCE":       2,
        "SIGNAL_COOLDOWN":      5,       # 5 bars ≈ 1 week on daily

        # Risk Management
        "RISK_PER_TRADE":       0.02,    # 2 % of equity per trade
        "DAILY_LOSS_LIMIT":     0.02,    # halt at −2 % daily P&L
    },

    # ── 4-Hour Intraday Preset ────────────────────────────────
    "4h": {
        "TIMEFRAME":            "4h",
        "LOOKBACK_YEARS":       2,       # yfinance intraday limit ~730 days

        # Strategy – Moving Averages
        "EMA_FAST":             20,
        "EMA_SLOW":             50,

        # Strategy – RSI
        "RSI_PERIOD":           14,
        "RSI_OVERSOLD":         30.0,
        "RSI_OVERBOUGHT":       70.0,

        # Strategy – ATR Stop-Loss / Take-Profit
        "ATR_PERIOD":           14,
        "ATR_SL_MULT":          1.5,
        "ATR_TP_MULT":          2.5,     # tighter TP for intraday moves

        # Strategy – MACD
        "MACD_FAST":            12,
        "MACD_SLOW":            26,
        "MACD_SIGNAL":          9,

        # Smart Money Concepts (SMC)
        "FVG_MIN_BODY_ATR":     0.8,     # lower displacement threshold
        "FVG_LOOKBACK":         80,      # more bars to scan (4h bars)
        "OB_LOOKBACK":          30,
        "LIQ_SWEEP_LOOKBACK":   30,
        "STRUCTURE_BREAK_BARS": 8,

        # Confluence & Cooldown
        "MIN_CONFLUENCE":       2,
        "SIGNAL_COOLDOWN":      3,       # 3 bars = 12 hours

        # Risk Management
        "RISK_PER_TRADE":       0.015,   # slightly lower risk per trade
        "DAILY_LOSS_LIMIT":     0.02,
    },
}

# ═══════════════════════════════════════════════════════════════
# Unpack the active preset into module-level variables
# ═══════════════════════════════════════════════════════════════
# All downstream code (strategy.py, data_fetch.py, smc.py, etc.)
# continues to import the same names – they just now resolve from
# the active preset instead of being individually hardcoded.

if ACTIVE_TIMEFRAME not in TIMEFRAME_PRESETS:
    raise ValueError(
        f"Unknown ACTIVE_TIMEFRAME '{ACTIVE_TIMEFRAME}'. "
        f"Choose from: {list(TIMEFRAME_PRESETS.keys())}"
    )

_preset = TIMEFRAME_PRESETS[ACTIVE_TIMEFRAME]

# Data Settings
TIMEFRAME: str          = _preset["TIMEFRAME"]
LOOKBACK_YEARS: int     = _preset["LOOKBACK_YEARS"]

# Strategy Parameters
EMA_FAST: int           = _preset["EMA_FAST"]
EMA_SLOW: int           = _preset["EMA_SLOW"]
RSI_PERIOD: int         = _preset["RSI_PERIOD"]
RSI_OVERSOLD: float     = _preset["RSI_OVERSOLD"]
RSI_OVERBOUGHT: float   = _preset["RSI_OVERBOUGHT"]
ATR_PERIOD: int         = _preset["ATR_PERIOD"]
ATR_SL_MULT: float      = _preset["ATR_SL_MULT"]
ATR_TP_MULT: float      = _preset["ATR_TP_MULT"]

# MACD Parameters
MACD_FAST: int          = _preset["MACD_FAST"]
MACD_SLOW: int          = _preset["MACD_SLOW"]
MACD_SIGNAL: int        = _preset["MACD_SIGNAL"]

# Smart Money Concepts (SMC)
FVG_MIN_BODY_ATR: float  = _preset["FVG_MIN_BODY_ATR"]
FVG_LOOKBACK: int        = _preset["FVG_LOOKBACK"]
OB_LOOKBACK: int         = _preset["OB_LOOKBACK"]
LIQ_SWEEP_LOOKBACK: int  = _preset["LIQ_SWEEP_LOOKBACK"]
STRUCTURE_BREAK_BARS: int = _preset["STRUCTURE_BREAK_BARS"]

# Confluence Requirements
MIN_CONFLUENCE: int     = _preset["MIN_CONFLUENCE"]
SIGNAL_COOLDOWN: int    = _preset["SIGNAL_COOLDOWN"]

# Risk Management
RISK_PER_TRADE: float   = _preset["RISK_PER_TRADE"]
DAILY_LOSS_LIMIT: float = _preset["DAILY_LOSS_LIMIT"]

# ── Non-preset settings (same for all timeframes) ────────────
DATA_DIR: Path          = ROOT_DIR / "data"
MAX_OPEN_POSITIONS: int = 5

# ── Execution Realism ─────────────────────────────────────────
# These model the frictions that exist between a theoretical backtest
# and real-world order fills.
FILL_RANDOMIZE: bool    = True      # randomize fill within early bar range
SLIPPAGE_FACTOR: float  = 0.10      # dynamic slip = ATR/price × this factor
SPREAD_PCT: float       = 0.0002    # 0.02% half-spread (bid-ask) per side
COMMISSION: float       = 0.0       # $0 for Alpaca stocks; set > 0 for futures
MAX_DRAWDOWN_PCT: float = 0.30      # 30% portfolio drawdown → halt all trading

# Legacy flat slippage (kept as fallback when FILL_RANDOMIZE is False)
SLIPPAGE_PCT: float     = 0.0005    # 0.05 % slippage per fill

# Kelly Criterion
USE_KELLY: bool         = True
KELLY_FRACTION: float   = 0.25      # Kelly-Lite: use only 25 %
KELLY_MIN_TRADES: int   = 30

# Paths
MODELS_DIR: Path        = ROOT_DIR / "models"
LOGS_DIR: Path          = ROOT_DIR / "logs"
JOURNAL_CSV: Path       = ROOT_DIR / "logs" / "trade_journal.csv"

# Ensure directories exist
for d in (DATA_DIR, MODELS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)
