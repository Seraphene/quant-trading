"""
config.py – Central configuration for the quant-trading project.

Loads secrets from .env and exposes all tuneable parameters in one place.
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
SIGNAL_SYMBOL: str = "SGOL"        # Analyse SGOL daily candles
TRADE_SYMBOL: str  = "SGOL"        # Trade SGOL on Alpaca paper

# ── Fractional Shares ─────────────────────────────────────────
USE_FRACTIONAL: bool = True         # Alpaca supports fractional shares

# ── Data Settings ─────────────────────────────────────────────
DATA_DIR: Path         = ROOT_DIR / "data"
LOOKBACK_YEARS: int    = 5          # years of daily history to download (from 2024)
TIMEFRAME: str         = "1d"       # candle granularity

# ── Strategy Parameters ───────────────────────────────────────
EMA_FAST: int          = 20         # fast exponential moving average period
EMA_SLOW: int          = 50         # slow exponential moving average period
RSI_PERIOD: int        = 14         # relative strength index lookback
RSI_OVERSOLD: float    = 30.0       # SHORT filter: skip if RSI already below this
RSI_OVERBOUGHT: float  = 70.0       # LONG filter:  skip if RSI already above this
ATR_PERIOD: int        = 14         # average true range lookback (for SL/TP)
ATR_SL_MULT: float     = 1.5       # stop-loss  = ATR × this multiplier
ATR_TP_MULT: float     = 3.0       # take-profit = ATR × this multiplier

# ── MACD Parameters ───────────────────────────────────────────
MACD_FAST: int         = 12         # MACD fast EMA
MACD_SLOW: int         = 26         # MACD slow EMA
MACD_SIGNAL: int       = 9          # MACD signal line EMA

# ── Smart Money Concepts (SMC) ────────────────────────────────
FVG_MIN_BODY_ATR: float = 1.0      # middle candle body ≥ ATR × this → "displacement"
FVG_LOOKBACK: int       = 50       # how far back to search for unfilled FVGs
OB_LOOKBACK: int        = 20       # bars to look back for Order Blocks
LIQ_SWEEP_LOOKBACK: int = 20       # bars to detect swing highs/lows for sweeps
STRUCTURE_BREAK_BARS: int = 5      # minimum bars between structural breaks

# ── Confluence Requirements ───────────────────────────────────
# Minimum number of confluence factors required to trigger a trade.
# Possible factors: EMA crossover, RSI filter, MACD confirmation,
#                   FVG proximity, Order Block, Liquidity Sweep,
#                   RSI divergence, MACD divergence
MIN_CONFLUENCE: int    = 2          # need at least 2 factors aligned
SIGNAL_COOLDOWN: int   = 5          # minimum bars between signals (avoid clustering)

# ── Risk Management ───────────────────────────────────────────
RISK_PER_TRADE: float  = 0.02       # max 2 % of equity risked per trade
MAX_OPEN_POSITIONS: int = 5         # concurrent position cap
DAILY_LOSS_LIMIT: float = 0.02     # halt trading if daily P&L drops below −2 %
SLIPPAGE_PCT: float    = 0.0005    # 0.05 % slippage added to each entry fill

# ── Kelly Criterion ───────────────────────────────────────────
USE_KELLY: bool         = True      # enable Kelly-based sizing
KELLY_FRACTION: float   = 0.25     # Kelly-Lite: use only 25 % of full Kelly
KELLY_MIN_TRADES: int   = 30       # need at least this many closed trades for stats

# ── Paths ─────────────────────────────────────────────────────
MODELS_DIR: Path       = ROOT_DIR / "models"
LOGS_DIR: Path         = ROOT_DIR / "logs"
JOURNAL_CSV: Path      = ROOT_DIR / "logs" / "trade_journal.csv"

# Ensure directories exist
for d in (DATA_DIR, MODELS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)
