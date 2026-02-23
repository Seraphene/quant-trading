# SETUP GUIDE — Gold Algorithmic Trading System

> A complete walkthrough for the **SGOL (gold ETF) algo-trading bot**.
> Covers local setup, how each indicator works, paper trading, and the
> future Google Colab ML phase.

---

## System Overview

This project trades **SGOL** (Aberdeen Physical Gold Shares, ~$24/share) as an
affordable proxy for spot gold (XAUUSD).  It uses a **multi-factor confluence
strategy** — a trade only fires when several independent technical and
structural signals agree in the same direction.

### Architecture at a Glance

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  yfinance    │────▶│  indicators  │────▶│   strategy   │
│  OHLCV data  │     │  + smc.py    │     │  confluence   │
└─────────────┘     └──────────────┘     │  scoring     │
                                          └──────┬───────┘
                                                 │ Signal
                                          ┌──────▼───────┐
                                          │ risk_manager  │
                                          │ sizing + caps │
                                          └──────┬───────┘
                                                 │ OrderRequest
                                 ┌───────────────┼───────────────┐
                                 ▼               ▼               ▼
                          ┌───────────┐   ┌───────────┐   ┌───────────┐
                          │ backtest  │   │ paper_bot │   │  (future) │
                          │ simulator │   │  Alpaca   │   │  ML layer │
                          └───────────┘   └───────────┘   └───────────┘
```

---

## How the Indicators Work

### EMA (Exponential Moving Average)

Two EMAs track trend direction:
- **EMA 20 (fast)** — reacts quickly to recent price
- **EMA 50 (slow)** — smoother, captures the larger trend

When fast > slow = **bullish trend**.  The strategy requires this directional
bias as a mandatory gate before any long signal can fire.

### RSI (Relative Strength Index)

Measures momentum on a 0 – 100 scale over 14 bars.

**Formula:**
```
delta      = Close - Previous Close
avg_gain   = Wilder-smoothed average of positive deltas (alpha = 1/14)
avg_loss   = Wilder-smoothed average of negative deltas (alpha = 1/14)
RS         = avg_gain / avg_loss
RSI        = 100 - 100 / (1 + RS)
```

**Usage as a filter (not a trigger):**
- RSI > 70 → overbought → skip new longs
- RSI < 30 → oversold   → skip new shorts

### MACD (Moving Average Convergence Divergence)

Measures trend strength via the gap between two EMAs.

```
MACD line   = EMA_12(Close) - EMA_26(Close)
Signal line = EMA_9(MACD line)
Histogram   = MACD line - Signal line
```

**Usage:**
- **MACD Confirmation**: Histogram expanding positive → supports longs;
  expanding negative → supports shorts.
- **MACD Divergence**: Price makes a lower low but MACD makes a higher low
  → hidden buying pressure (bullish divergence). Detected by comparing
  consecutive swing points over a ±5 bar window.

### ATR (Average True Range)

Measures daily volatility.  Used to set dynamic stop-loss and take-profit:

```
Stop-loss   = Entry ± ATR × 1.5
Take-profit = Entry ± ATR × 3.0
```

This means profit targets are always 2× the risk (reward-to-risk = 2:1).

### Smart Money Concepts (smc.py)

| Concept | What it detects | How the strategy uses it |
|---------|-----------------|--------------------------|
| **Fair Value Gap (FVG)** | 3-candle gaps where the middle candle had strong displacement | Price inside a recent FVG zone = mean-reversion magnet |
| **Order Block** | Institutional supply/demand zones (last opposing candle before a strong move) | Price at an OB = institutional interest zone |
| **Liquidity Sweep** | False breakouts past swing highs/lows that quickly reverse | A recent sweep in trade direction = stop-hunt reversal signal |

### Confluence System (strategy.py)

Each bar is scored against **9 independent factors**:

| # | Factor | Type |
|---|--------|------|
| 1a | EMA Trend (fast > slow) | **Mandatory gate** |
| 1b | EMA Crossover (exact cross bar) | Bonus trigger |
| 2 | RSI Filter (not overbought/oversold) | Veto filter |
| 3 | MACD Confirmation (histogram expanding) | Momentum |
| 4 | RSI Divergence | Reversal signal |
| 5 | MACD Divergence | Reversal signal |
| 6 | Fair Value Gap zone | Structural |
| 7 | Order Block zone | Structural |
| 8 | Liquidity Sweep | Structural |

A signal fires when: **EMA Trend is present** AND **≥ 2 other factors align**
in the same direction. A 5-bar cooldown prevents signal clustering.

### Risk Management (risk_manager.py)

| Guard | Rule |
|-------|------|
| Fixed-fractional sizing | Max 2% of equity risked per trade |
| Kelly-Lite | After 30+ trades, Kelly criterion caps size (25% of full Kelly) |
| Position cap | Max 5 concurrent open positions |
| Daily loss limit | Halt all trading if daily P&L drops below −2% |
| Fractional shares | Enabled — allows full use of small accounts ($170+) |

---

## Step 0 — Prerequisites (one-time)

| #  | Action | How |
|----|--------|-----|
| 0a | **Install Python 3.10+** | <https://www.python.org/downloads/> — tick **"Add to PATH"** during install |
| 0b | **Open a terminal** in the project folder | VS Code: `` Ctrl+` `` or Windows Terminal → `cd C:\Users\Lenovo\Documents\quant-trading` |
| 0c | **Create a virtual environment** | `python -m venv .venv` |
| 0d | **Activate it** | `.\.venv\Scripts\activate` |
| 0e | **Install all dependencies** | `pip install -r requirements.txt` |

**Dependencies installed:**
yfinance, pandas, numpy, alpaca-py, python-dotenv, matplotlib, tabulate, schedule

---

## Step 1 — Create Alpaca Paper-Trading Account & Keys

| #  | Action | How |
|----|--------|-----|
| 1a | Sign up at **[Alpaca](https://app.alpaca.markets/signup)** | Free account; no deposit needed |
| 1b | Switch to **Paper Trading** mode | Toggle in the top-right of the dashboard |
| 1c | Go to **API Keys** | Left sidebar → "API Keys" → click **Generate** |
| 1d | Copy the **API Key** and **Secret Key** | You will only see the Secret once! |

---

## Step 2 — Configure Your Local `.env` File

| #  | Action | How |
|----|--------|-----|
| 2a | Copy the template | `copy .env.example .env` |
| 2b | Open `.env` in any text editor | |
| 2c | Paste your Alpaca keys | Replace `PASTE_YOUR_KEY_HERE` and `PASTE_YOUR_SECRET_HERE` |
| 2d | **Save** the file | |

> **Security rule:** Never paste your Secret Key into any AI chat, browser form,
> or public repo.  The `.gitignore` already excludes `.env`.

---

## Step 3 — Download Historical Data

```
python data_fetch.py
```

This downloads ~2 years of daily **SGOL** data (from 2024) into the `data/`
folder, then enriches it with all indicators (EMA, RSI, ATR, MACD, divergences)
and Smart Money Concepts (FVGs, Order Blocks, Liquidity Sweeps).

Add `--force` to re-download fresh data later:
```
python data_fetch.py --force
```

---

## Step 4 — Run the Backtest

```
python backtest.py
```

**What you'll see:**
- A performance table: trades, win rate, profit factor, max drawdown, etc.
- `logs/equity_curve.png` — visual equity curve chart
- `logs/trade_journal.csv` — every trade with entry/exit, P&L, confluence factors

**Example output (as of Feb 2026):**
```
Metric              Value
------------------  ---------
Start Equity        $170.00
End Equity          $510.22
Return              +200.13 %
Total Trades        59
Win Rate            67.8 %
Profit Factor       4.12
Max Drawdown        -11.49 %
```

**Review these numbers.** If the strategy is unprofitable on historical data,
do **not** proceed to paper trading.  Come back and ask for parameter tuning.

To test with a different starting balance:
```
python backtest.py --equity 500
```

---

## Step 5 — Paper Trade (Live Simulation)

### One-shot (test it works)
```
python paper_bot.py
```

### Daily auto-run (set-and-forget)
```
python paper_bot.py --loop
```
By default this fires at **16:05** local time (after US market close).
Override with `--hour 21 --minute 0` for your timezone.

**What to monitor:**
- Your Alpaca dashboard → "Paper Orders" tab
- `logs/bot.log` on your machine

> Run paper trading for **at least 2–4 weeks** before considering real money.

**How the bot works each day:**
1. Downloads latest SGOL daily data via yfinance
2. Computes all indicators + SMC enrichment
3. Runs the confluence strategy → checks if today's bar has a signal
4. If a signal exists and risk manager approves → submits a **bracket order**
   (market entry + stop-loss + take-profit) to Alpaca
5. Logs everything to `logs/bot.log`

---

## Step 6 — Tuneable Parameters (config.py)

All settings live in `config.py`.  Key knobs you might want to adjust:

| Parameter | Default | What it controls |
|-----------|---------|------------------|
| `LOOKBACK_YEARS` | 2 | How many years of history to download |
| `EMA_FAST` / `EMA_SLOW` | 20 / 50 | Trend detection sensitivity |
| `RSI_PERIOD` | 14 | RSI calculation window |
| `RSI_OVERBOUGHT` / `RSI_OVERSOLD` | 70 / 30 | RSI filter thresholds |
| `ATR_SL_MULT` / `ATR_TP_MULT` | 1.5 / 3.0 | Stop-loss and take-profit as ATR multiples |
| `MIN_CONFLUENCE` | 2 | Minimum factors needed for a signal |
| `SIGNAL_COOLDOWN` | 5 | Minimum bars between signals |
| `RISK_PER_TRADE` | 0.02 (2%) | Max equity risked per trade |
| `MAX_OPEN_POSITIONS` | 5 | Max concurrent positions |
| `DAILY_LOSS_LIMIT` | 0.02 (2%) | Daily loss circuit breaker |

After changing parameters, always re-run `python backtest.py` to validate.

---

## Step 7 (Future) — Google Colab ML Phase

### Why Colab?
Your laptop (i3, 4 GB RAM) cannot efficiently train ML models. Google Colab
provides **free GPU/TPU** access, more than enough for this project.

### What the ML layer does
The ML model does **NOT** replace the rule-based strategy. It acts as a
**second filter on top** — vetoing the weaker signals:

```
Rule-based strategy                ML filter               Broker
   59 candidate     ──────▶   30 high-confidence   ──────▶  Alpaca
      signals                     signals                   orders
```

### How it works

1. **Feature engineering** — For each signal bar, extract a feature vector:
   - RSI value, MACD histogram, EMA gap, ATR ratio
   - Distance to nearest FVG / Order Block
   - Confluence score, factor list
   - Recent price momentum, volume changes

2. **Labelling** — Use the backtest trade journal (`logs/trade_journal.csv`)
   to label each trade as WIN (1) or LOSS (0)

3. **Train a classifier** on Colab (Random Forest / XGBoost / small neural net):
   - Input: feature vector at signal time
   - Output: probability the trade will be profitable
   - Target: `model.predict_proba(features) > threshold`

4. **Export the model** — Download the `.pkl` (scikit-learn) or `.h5` (Keras)
   file and place it in the `models/` folder on your local machine

5. **Bot integration** — `paper_bot.py` auto-detects and loads the model.
   It only executes signals where the ML model gives a green light.

### Step-by-step Colab workflow

| #  | Action |
|----|--------|
| 7a | Open [Google Colab](https://colab.research.google.com) and sign in with Google |
| 7b | Ask the AI to generate a **Colab training notebook** for this project |
| 7c | Upload `data/SGOL_daily.csv` and `logs/trade_journal.csv` to the Colab file browser |
| 7d | Click **Runtime → Run all** — training takes 2-10 minutes on free GPU |
| 7e | Download the resulting model file (e.g. `gold_signal_filter.pkl`) |
| 7f | Place it in `models/` on your local machine |
| 7g | Run `python paper_bot.py` — it will auto-load the model |

> **Important:** Colab is for **training only**. The bot itself runs on your
> local machine (or any always-on server). Colab sessions time out after ~90
> minutes of inactivity, so it cannot run a daily bot.

---

## Quick Reference — Commands

| Task | Command |
|------|---------|
| Activate env | `.\.venv\Scripts\activate` |
| Install deps | `pip install -r requirements.txt` |
| Download data | `python data_fetch.py` |
| Re-download data | `python data_fetch.py --force` |
| Backtest | `python backtest.py` |
| Backtest (custom equity) | `python backtest.py --equity 500` |
| Paper trade (once) | `python paper_bot.py` |
| Paper trade (daily loop) | `python paper_bot.py --loop` |

---

## File Map

```
quant-trading/
├── .env.example        ← template for your Alpaca API secrets
├── .env                ← YOUR secrets (git-ignored, never commit)
├── .gitignore
├── requirements.txt    ← pip dependencies
├── config.py           ← all tuneable parameters + .env loader
├── logger.py           ← unified logging (console + file)
├── indicators.py       ← EMA, RSI, ATR, MACD, divergence detection
├── smc.py              ← Smart Money Concepts: FVG, Order Blocks, Liquidity Sweeps
├── data_fetch.py       ← yfinance download + indicator/SMC enrichment
├── strategy.py         ← 9-factor confluence scoring + signal generation
├── risk_manager.py     ← fixed-fractional + Kelly-Lite sizing, position/daily caps
├── backtest.py         ← walk-forward historical simulation + report + equity chart
├── paper_bot.py        ← Alpaca paper-trading execution with bracket orders
├── SETUP_GUIDE.md      ← this file
├── data/               ← cached SGOL_daily.csv (git-ignored)
├── models/             ← trained ML model files (git-ignored)
└── logs/               ← bot.log, equity_curve.png, trade_journal.csv
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Make sure venv is activated: `.\.venv\Scripts\activate` then `pip install -r requirements.txt` |
| `ALPACA_API_KEY is empty` | Check that `.env` exists and keys are filled in (not the example placeholders) |
| `No signal today – skipping` | Normal! The strategy only trades when confluence conditions are met. Not every day produces a signal. |
| `MAX_OPEN_POSITIONS reached` | The bot already has 5 open positions. Wait for existing trades to hit SL/TP. |
| `Daily loss limit reached` | The circuit breaker halted trading for today. Resets next trading day. |
| Backtest shows different results | Re-download data with `python data_fetch.py --force`. Market data updates daily. |
| Unicode arrow error in redirected output | Cosmetic only. Run `backtest.py` directly (not redirected) to see clean output. |
