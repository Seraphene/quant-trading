"""
paper_bot.py – Live paper-trading bot using Alpaca's paper API.

Runs once daily (or on a schedule). Designed to be lightweight enough
for an i3 / 4 GB machine – the heavy ML phase runs in Colab and this
bot only loads a tiny pre-trained model if one exists.

Usage
─────
    python paper_bot.py              # run one decision cycle
    python paper_bot.py --loop       # run continuously, checking once per day
"""

import argparse
import time
from datetime import datetime

import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    GetAssetsRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, AssetClass

from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    SIGNAL_SYMBOL, TRADE_SYMBOL,
    MAX_OPEN_POSITIONS, DAILY_LOSS_LIMIT,
)
from data_fetch import fetch_and_enrich
from strategy import latest_signal, Direction
from risk_manager import RiskManager, OrderRequest
from logger import get_logger

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


# ── Main decision cycle ──────────────────────────────────────

def run_cycle() -> None:
    log.info("═══ Paper-bot cycle starting ═══")

    client = get_client()
    equity = get_account_equity(client)
    open_pos = get_open_position_count(client)
    log.info(f"Account equity: ${equity:,.2f}  |  Open positions: {open_pos}")

    # Fetch latest data and get a signal from the strategy
    log.info(f"Fetching latest data for {SIGNAL_SYMBOL} …")
    df = fetch_and_enrich(SIGNAL_SYMBOL, force=True)   # always refresh
    sig = latest_signal(df)

    if sig is None:
        log.info("No actionable signal today – standing aside.")
        return

    log.info(
        f"Signal: {sig.direction.value} @ {sig.entry_price:.2f}  "
        f"SL={sig.stop_loss:.2f}  TP={sig.take_profit:.2f}  "
        f"Date={sig.date.date()}"
    )

    # Only act on today's signal (avoid replaying stale signals)
    today = pd.Timestamp(datetime.today().date())
    if sig.date.normalize() != today:
        log.info(f"Latest signal is from {sig.date.date()}, not today – skipping.")
        return

    # Risk-check the signal
    rm = RiskManager(equity=equity, open_positions=open_pos)
    order = rm.evaluate(sig, TRADE_SYMBOL)
    if order is None:
        log.info("Risk manager rejected the signal.")
        return

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
            run_cycle()
        except Exception as e:
            log.exception(f"Cycle failed: {e}")

    schedule.every().day.at(f"{check_hour:02d}:{check_minute:02d}").do(_job)
    log.info(f"Scheduler active – will run daily at {check_hour:02d}:{check_minute:02d}")

    while True:
        schedule.run_pending()
        time.sleep(30)


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Gold paper-trading bot (Alpaca)")
    parser.add_argument("--loop", action="store_true", help="Run on daily schedule")
    parser.add_argument("--hour", type=int, default=16, help="Hour to run (24h)")
    parser.add_argument("--minute", type=int, default=5, help="Minute to run")
    args = parser.parse_args()

    if args.loop:
        loop(args.hour, args.minute)
    else:
        run_cycle()


if __name__ == "__main__":
    main()
