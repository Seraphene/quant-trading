"""
paper_bot.py – Live paper-trading bot using Alpaca's paper API.

Runs once daily (or on a schedule). Designed to be lightweight enough
for an i3 / 4 GB machine – the heavy ML phase runs in Colab and this
bot only loads a tiny pre-trained model if one exists.

Usage
─────
    python paper_bot.py                     # run one decision cycle (1d)
    python paper_bot.py --timeframe 4h      # run with 4-hour candles
    python paper_bot.py --loop              # run continuously on schedule
"""

import argparse
import time
from datetime import datetime
import joblib
import os

import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    GetAssetsRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, AssetClass

import config as cfg
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    SIGNAL_SYMBOL, TRADE_SYMBOL,
    MAX_OPEN_POSITIONS, DAILY_LOSS_LIMIT,
)
from data_fetch import fetch_and_enrich
from strategy import latest_signal, Direction
from risk_manager import RiskManager, OrderRequest
from logger import get_logger
from notifications import send_execution_email

log = get_logger("paper_bot")


# ── Alpaca helpers ────────────────────────────────────────────

def get_client() -> TradingClient:
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise RuntimeError(
            "Alpaca keys not found. "
            "Copy .env.example → .env and paste your paper-trading keys."
        )
    return TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)


def get_account_equity(client: TradingClient) -> float:
    account = client.get_account()
    return float(account.equity)


def get_open_position_count(client: TradingClient) -> int:
    positions = client.get_all_positions()
    return len(positions)


def submit_bracket_order(client: TradingClient, order: OrderRequest) -> None:
    """
    Submit a market order with attached stop-loss and take-profit (OTO bracket).
    Alpaca's bracket orders handle SL/TP automatically.
    """
    side = OrderSide.BUY if order.direction == Direction.LONG else OrderSide.SELL

    req = MarketOrderRequest(
        symbol=order.symbol,
        qty=order.qty,
        side=side,
        time_in_force=TimeInForce.DAY,
        order_class="bracket",
        stop_loss={"stop_price": round(order.stop_loss, 2)},
        take_profit={"limit_price": round(order.take_profit, 2)},
    )

    submitted = client.submit_order(req)
    log.info(
        f"ORDER SUBMITTED  id={submitted.id}  "
        f"{side.value} {order.qty} × {order.symbol}  "
        f"SL={order.stop_loss:.2f}  TP={order.take_profit:.2f}"
    )
    # Send notification for the executed order
    send_execution_email(
        symbol=order.symbol,
        side=side.value,
        qty=order.qty,
        price=order.entry_price # Use intended entry price from signal
    )


# ── Main decision cycle ──────────────────────────────────────

def run_cycle(provider: str = None) -> None:
    log.info("═══ Paper-bot cycle starting ═══")

    client = get_client()
    equity = get_account_equity(client)
    open_pos = get_open_position_count(client)
    log.info(f"Account equity: ${equity:,.2f}  |  Open positions: {open_pos}")

    # Fetch latest data and get a signal from the strategy.
    # drop_incomplete=True ensures we only compute indicators on fully
    # CLOSED candles.  yfinance includes the current forming candle
    # whose H/L/C are still moving — using it would produce unreliable
    # signals (the "candle is still moving" problem).
    log.info(f"Fetching latest data for {SIGNAL_SYMBOL} …")
    df = fetch_and_enrich(SIGNAL_SYMBOL, force=True, drop_incomplete=True, provider=provider)
    sig = latest_signal(df)

    if sig is None:
        log.info("No actionable signal – standing aside.")
        return

    log.info(
        f"Signal: {sig.direction.value} @ {sig.entry_price:.2f}  "
        f"SL={sig.stop_loss:.2f}  TP={sig.take_profit:.2f}  "
        f"Date={sig.date}"
    )

    # ── Signal freshness check ────────────────────────────────
    # Only act on recent signals.  For daily candles the signal must
    # be from today; for 4H candles it must be from the last 8 hours
    # (2 × candle period) to allow some scheduler flexibility.
    now = pd.Timestamp(datetime.now())
    if cfg.ACTIVE_TIMEFRAME == "1d":
        max_age = pd.Timedelta(days=1)
    else:
        # For 4H: allow up to 2 candle-periods of lag
        max_age = pd.Timedelta(hours=8)

    signal_age = now - sig.date
    if signal_age > max_age:
        log.info(
            f"Latest signal is from {sig.date} "
            f"({signal_age} ago, max={max_age}) – too stale, skipping."
        )
        return

    # Risk-check the signal
    rm = RiskManager(equity=equity, open_positions=open_pos)
    order = rm.evaluate(sig, TRADE_SYMBOL)
    if order is None:
        log.info("Risk manager rejected the signal.")
        return

    # ── ML Veto Filter ─────────────────────────────────────────
    model_path = os.path.join(os.path.dirname(__file__), "models", "logistic_regression_model.pkl")
    if os.path.exists(model_path):
        log.info("Found ML model. Running AI prediction...")
        try:
            model = joblib.load(model_path)
            
            # ── Calculate 26 derived features expected by model ──
            bar_index = df.index.get_loc(sig.date)
            row = df.iloc[bar_index]
            
            # Date features
            entry_yr = sig.date.year
            entry_mo = sig.date.month
            entry_dy = sig.date.day
            entry_dow = sig.date.dayofweek
            
            # Engineered Technicals
            atr_ratio = row["ATR"] / row["Close"] if row["Close"] != 0 else 0
            ema_gap = (row["EMA_fast"] - row["EMA_slow"]) / row["EMA_slow"] if row["EMA_slow"] != 0 else 0
            macd = row.get("MACD", 0)
            macds = row.get("MACD_signal", 0)
            momentum = row["Close"] - df.iloc[max(0, bar_index - 5)]["Close"]
            vol_change = row["Volume"] / df.iloc[max(0, bar_index - 1)]["Volume"] if df.iloc[max(0, bar_index - 1)]["Volume"] != 0 else 1.0
            
            # Factor One-Hot Encoding
            f_list = sig.factors
            
            features_dict = {
                'entry_price': row["Close"],
                'stop_loss': sig.stop_loss,
                'take_profit': sig.take_profit,
                'confluence': sig.confluence,
                'entry_year': entry_yr,
                'entry_month': entry_mo,
                'entry_day': entry_dy,
                'entry_dayofweek': entry_dow,
                'RSI': row["RSI"],
                'MACD': macd,
                'MACDs': macds,
                'EMA_Gap': ema_gap,
                'ATR': row["ATR"],
                'ATR_Ratio': atr_ratio,
                'Recent_Price_Momentum': momentum,
                'Volume_Changes': vol_change,
                'direction_SHORT': 1 if sig.direction == Direction.SHORT else 0,
                'factor_FVG_zone': 1 if "FVG_zone" in f_list else 0,
                'factor_LIQ_sweep': 1 if "LIQ_sweep" in f_list else 0,
                'factor_EMA_trend': 1 if "EMA_trend" in f_list else 0,
                'factor_MACD_confirm': 1 if "MACD_confirm" in f_list else 0,
                'factor_Order_Block': 1 if "Order_Block" in f_list else 0,
                'factor_RSI_filter': 1 if "RSI_filter" in f_list else 0,
                'factor_EMA_cross': 1 if "EMA_cross" in f_list else 0
            }
            
            features = pd.DataFrame([features_dict])
            
            # Ensure column order perfectly matches model expectations
            if hasattr(model, "feature_names_in_"):
                features = features[model.feature_names_in_]
                
            
            # predict_proba returns [[prob_loss, prob_win]]
            win_prob = model.predict_proba(features)[0][1]
            log.info(f"AI Win Probability: {win_prob:.2%}")
            
            if win_prob < 0.50:
                log.warning(f"AI VETO: Win probability ({win_prob:.2%}) is below 50%. Skipping trade.")
                return
            else:
                log.info("AI APPROVED: Trade passes the machine learning filter.")
        except Exception as e:
            log.error(f"Failed to run ML prediction: {e}. Proceeding without AI filter.")
    else:
        log.info("No ML model found in models/ - running pure rule-based strategy.")

    # Fire the bracket order
    submit_bracket_order(client, order)
    log.info("═══ Cycle complete ═══")


# ── Scheduler ─────────────────────────────────────────────────

def loop(check_hour: int = 16, check_minute: int = 5) -> None:
    """
    Run indefinitely, executing one cycle per day at the specified
    local time (default: 16:05, shortly after US market close).
    """
    import schedule

    def _job():
        try:
            run_cycle(provider=None) # Uses cfg.DATA_PROVIDER
        except Exception as e:
            log.exception(f"Cycle failed: {e}")

    schedule.every().day.at(f"{check_hour:02d}:{check_minute:02d}").do(_job)
    log.info(f"Scheduler active – will run daily at {check_hour:02d}:{check_minute:02d}")

    while True:
        schedule.run_pending()
        time.sleep(30)


# ── CLI ───────────────────────────────────────────────────────

def _apply_timeframe_override(tf: str) -> None:
    """Hot-swap the active timeframe preset at runtime."""
    if tf == cfg.ACTIVE_TIMEFRAME:
        return
    if tf not in cfg.TIMEFRAME_PRESETS:
        raise ValueError(f"Unknown timeframe '{tf}'. Choose from: {list(cfg.TIMEFRAME_PRESETS.keys())}")
    log.info(f"Overriding timeframe: {cfg.ACTIVE_TIMEFRAME} → {tf}")
    cfg.ACTIVE_TIMEFRAME = tf
    for key, value in cfg.TIMEFRAME_PRESETS[tf].items():
        setattr(cfg, key, value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold paper-trading bot (Alpaca)")
    parser.add_argument("--loop", action="store_true", help="Run on daily schedule")
    parser.add_argument("--hour", type=int, default=16, help="Hour to run (24h)")
    parser.add_argument("--minute", type=int, default=5, help="Minute to run")
    parser.add_argument(
        "--timeframe", "-tf",
        choices=list(cfg.TIMEFRAME_PRESETS.keys()),
        default=None,
        help="Override active timeframe (e.g. 1d, 4h)",
    )
    parser.add_argument(
        "--provider", type=str, choices=["yfinance", "alpaca"], default=None,
        help="Data provider to use (default: config.DATA_PROVIDER)",
    )
    args = parser.parse_args()

    if args.timeframe:
        _apply_timeframe_override(args.timeframe)

    log.info(f"Active timeframe: {cfg.ACTIVE_TIMEFRAME}")

    if args.loop:
        loop(args.hour, args.minute)
    else:
        run_cycle(provider=args.provider)


if __name__ == "__main__":
    main()
