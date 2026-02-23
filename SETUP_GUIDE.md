# SETUP GUIDE — Human Action Checklist

> Everything the **AI cannot do for you**.  Follow in order.

---

## Step 0 — Prerequisites (one-time)

| #  | Action | How |
|----|--------|-----|
| 0a | **Install Python 3.10+** | <https://www.python.org/downloads/> — tick "Add to PATH" during install |
| 0b | **Open a terminal** in the project folder | In VS Code: `Ctrl+`` ` or Windows Terminal → `cd C:\Users\Lenovo\Documents\quant-trading` |
| 0c | **Create a virtual environment** | `python -m venv venv` |
| 0d | **Activate it** | `.\venv\Scripts\activate` |
| 0e | **Install all dependencies** | `pip install -r requirements.txt` |

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

This downloads ~5 years of daily gold (GC=F) and GLD data into the `data/` folder.
Add `--force` to re-download if you want fresh data later.

---

## Step 4 — Run the Backtest

```
python backtest.py
```

**What you'll see:**
- A performance table (win rate, profit factor, max drawdown, etc.)
- `logs/equity_curve.png` – visual equity curve
- `logs/trade_journal.csv` – every trade logged

**Review these numbers.** If the strategy is unprofitable on historical data,
do **not** proceed to paper trading.  Come back to the AI and ask for parameter
tuning or alternative rules.

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

---

## Step 6 (Later) — Google Colab ML Phase

When you are ready to add a machine-learning filter **on top of** the rule-based
strategy:

| #  | Action |
|----|--------|
| 6a | Open [Google Colab](https://colab.research.google.com) and sign in |
| 6b | Ask the AI to generate a Colab training notebook |
| 6c | Upload `data/GC_F_daily.csv` into the Colab file browser |
| 6d | Click **Runtime → Run all** |
| 6e | Download the resulting `.pkl` or `.h5` model file to `models/` |

The paper bot will auto-detect and load the model if it exists in `models/`.

---

## Quick Reference — Commands

| Task | Command |
|------|---------|
| Activate env | `.\venv\Scripts\activate` |
| Install deps | `pip install -r requirements.txt` |
| Download data | `python data_fetch.py` |
| Re-download data | `python data_fetch.py --force` |
| Backtest | `python backtest.py` |
| Backtest (custom equity) | `python backtest.py --equity 50000` |
| Paper trade (once) | `python paper_bot.py` |
| Paper trade (daily loop) | `python paper_bot.py --loop` |

---

## File Map

```
quant-trading/
├── .env.example        ← template for your secrets
├── .env                ← YOUR secrets (git-ignored)
├── .gitignore
├── requirements.txt
├── config.py           ← all tuneable parameters + .env loader
├── logger.py           ← unified logging (console + file)
├── indicators.py       ← EMA, RSI, ATR calculations
├── data_fetch.py       ← yfinance download + caching
├── strategy.py         ← EMA crossover + RSI filter rules
├── risk_manager.py     ← position sizing, SL/TP, daily loss cap
├── backtest.py         ← historical simulation + report
├── paper_bot.py        ← Alpaca paper-trading execution
├── SETUP_GUIDE.md      ← this file
├── data/               ← cached CSV files (git-ignored)
├── models/             ← trained ML artefacts (git-ignored)
└── logs/               ← bot.log, equity_curve.png, trade_journal.csv
```
