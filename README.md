# Quant-Trading – Gold Swing & Intraday Bot

A quantitative trading system for SGOL (Gold ETF) using **Price Action + Smart Money Concepts (SMC)** with an optional Machine Learning filter. Designed for Alpaca paper trading.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy .env.example → .env and add your Alpaca API keys
cp .env.example .env

# 3. Run a backtest
python backtest.py --timeframe 1d --equity 170
```

## CLI Commands

### Backtesting

```bash
# Daily timeframe (default)
python backtest.py

# 4-hour timeframe
python backtest.py --timeframe 4h

# Custom equity
python backtest.py --equity 5000

# With ML model filter
python backtest.py --use-ml

# Combine flags
python backtest.py --timeframe 4h --equity 500 --use-ml
```

### Data Fetching

```bash
# Download & cache data for active timeframe
python data_fetch.py

# Force re-download (clear cache)
python data_fetch.py --force
```

### Signal Scanner

```bash
# Scan default symbol (SGOL)
python scanner.py

# Scan Gold Futures
python scanner.py --symbols GC=F --force

# Scan multiple symbols at once
python scanner.py --symbols GC=F SGOL NQ=F SPY --force

# Scan on 4-hour timeframe
python scanner.py --symbols GC=F --timeframe 4h --force

# Force fresh download (default: uses cache)
python scanner.py --symbols GC=F --force
```

**Common Tickers:**
| Ticker | Asset |
|--------|-------|
| `GC=F` | Gold Futures (COMEX) |
| `SI=F` | Silver Futures |
| `NQ=F` | Nasdaq 100 Futures |
| `ES=F` | S&P 500 Futures |
| `EURUSD=X` | EUR / USD forex |
| `GBPUSD=X` | GBP / USD forex |
| `SGOL` | Aberdeen Gold ETF |
| `GLD` | SPDR Gold Trust ETF |
| `SPY` | S&P 500 ETF |

### Paper Trading (Alpaca)

```bash
# Run one decision cycle
python paper_bot.py

# Run with 4-hour candles
python paper_bot.py --timeframe 4h

# Run on daily schedule (auto-loop)
python paper_bot.py --loop

# Custom schedule (run at 10:30 daily)
python paper_bot.py --loop --hour 10 --minute 30
```

### ML Model Retraining

```bash
# Retrain logistic regression on latest journal data
python retrain_model.py
```

### Timeframe Switching

```bash
# Method 1: CLI flag (per-run, no file edits)
python backtest.py --timeframe 4h
python paper_bot.py --timeframe 4h

# Method 2: Edit config.py (permanent)
# Change: ACTIVE_TIMEFRAME = "4h"

# Method 3: Environment variable
set TIMEFRAME=4h
python backtest.py
```

## Strategy Overview

**8 Confluence Factors** — a trade triggers only when ≥ 2 align:

| # | Factor | Description |
|---|--------|-------------|
| 1 | EMA Trend | EMA 20 vs 50 directional bias |
| 2 | EMA Crossover | Exact cross bar (bonus) |
| 3 | RSI Filter | Not overbought/oversold |
| 4 | MACD Confirm | Histogram expanding in direction |
| 5 | RSI Divergence | Price vs RSI divergence |
| 6 | MACD Divergence | Price vs MACD divergence |
| 7 | Fair Value Gap | Price in recent FVG zone (SMC) |
| 8 | Order Block | Price in institutional OB zone (SMC) |

**Risk Management:** ATR-based SL/TP, 2% risk per trade, Kelly Criterion sizing, 5-position cap, daily loss circuit breaker.

## Backtest Results

### Daily (1D) – 5 Years

| Metric | Value |
|--------|-------|
| Return | +264% |
| Trades | 114 |
| Win Rate | 54.4% |
| Profit Factor | 2.63 |
| Max Drawdown | -17.57% |

### 4-Hour (4H) – 2 Years

| Metric | Value |
|--------|-------|
| Return | +123% |
| Trades | 171 |
| Win Rate | 51.5% |
| Profit Factor | 1.75 |
| Max Drawdown | -23.94% |

## Project Structure

```
config.py          ← Central config + timeframe presets
data_fetch.py      ← Download, cache & enrich OHLCV data
indicators.py      ← EMA, RSI, ATR, MACD, divergence
smc.py             ← Fair Value Gaps, Order Blocks, Liquidity Sweeps
strategy.py        ← 8-factor confluence signal engine
risk_manager.py    ← Position sizing, Kelly, circuit breakers
backtest.py        ← Walk-forward backtester with equity curve
paper_bot.py       ← Live paper-trading bot (Alpaca)
scanner.py         ← Multi-symbol signal scanner (no broker needed)
retrain_model.py   ← ML model retraining (logistic regression)
```

## Docs

- [SYSTEM_ANALYSIS.md](SYSTEM_ANALYSIS.md) – Full system analysis, performance diagnostics, timeframe preset docs
- [SETUP_GUIDE.md](SETUP_GUIDE.md) – Detailed setup instructions