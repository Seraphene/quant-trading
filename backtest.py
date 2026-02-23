"""
backtest.py – Walk-forward backtester with equity curve and performance report.

Usage
─────
    python backtest.py                  # default: backtest GC=F signal on GLD
    python backtest.py --equity 50000   # start with $50 000
"""

import argparse
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")                   # headless – no GUI needed
import matplotlib.pyplot as plt
from tabulate import tabulate

from config import (
    SIGNAL_SYMBOL, TRADE_SYMBOL, DATA_DIR, LOGS_DIR,
    RISK_PER_TRADE, MAX_OPEN_POSITIONS, DAILY_LOSS_LIMIT,
    ATR_SL_MULT, ATR_TP_MULT, SLIPPAGE_PCT,
)
from data_fetch import fetch_and_enrich
from strategy import generate_signals, Signal, Direction
from risk_manager import RiskManager, OrderRequest
from logger import get_logger

log = get_logger("backtest")

INITIAL_EQUITY = 170.0                  # default paper capital ($170)


# ── Trade record ──────────────────────────────────────────────

@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: Optional[pd.Timestamp] = None
    direction: str = ""
    qty: float = 0
    entry_price: float = 0.0
    exit_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    status: str = "OPEN"
    confluence: int = 0
    factors: str = ""


# ── Backtester ────────────────────────────────────────────────

class Backtester:
    def __init__(self, equity: float = INITIAL_EQUITY):
        self.start_equity = equity
        self.equity = equity
        self.trades: list[Trade] = []
        self.equity_curve: list[float] = []
        self._open_trades: list[Trade] = []

    def run(self, signal_df: pd.DataFrame, trade_df: pd.DataFrame) -> None:
        """
        Walk bar-by-bar through *trade_df*, using pre-computed signals
        from *signal_df*.

        Realism improvements
        ────────────────────
        • **Next-bar entry**: signal on day N → order queued → fills at
          day N+1's Open (+ slippage).  This is what actually happens in
          live trading: the bot runs after close, sees the signal, and
          the market order fills at the next open.
        • **Slippage**: entry price is nudged against the trader by
          SLIPPAGE_PCT to simulate real-world fill costs.
        • **Worst-case SL/TP**: when both SL *and* TP were touched in the
          same bar, the stop-loss is always assumed to have hit first
          (conservative / pessimistic assumption).
        """
        # Build a signal lookup:  date → Signal
        signals = generate_signals(signal_df)
        sig_lookup: dict[pd.Timestamp, Signal] = {s.date: s for s in signals}

        rm = RiskManager(self.equity)

        # Pending orders: signal evaluated on bar N, executed on bar N+1
        pending: list[tuple[OrderRequest, Signal]] = []

        for i in range(len(trade_df)):
            row = trade_df.iloc[i]
            date = trade_df.index[i]
            open_ = row["Open"]
            close = row["Close"]
            high  = row["High"]
            low   = row["Low"]

            # Reset daily P&L tracker at each new bar (daily bars = 1 bar/day)
            rm.reset_daily(self.equity)

            # ── 1. Fill pending orders at today's Open ────────
            #    These were queued yesterday; in live trading the market
            #    order would fill at today's opening price.
            new_pending: list[tuple[OrderRequest, Signal]] = []
            for order, sig_obj in pending:
                # Apply slippage: nudge price against the trader
                if order.direction == Direction.LONG:
                    fill_price = open_ * (1 + SLIPPAGE_PCT)
                else:
                    fill_price = open_ * (1 - SLIPPAGE_PCT)

                # Recalculate SL/TP from actual fill price (same ATR multiples)
                atr_val = sig_obj.atr
                if order.direction == Direction.LONG:
                    sl = fill_price - atr_val * ATR_SL_MULT
                    tp = fill_price + atr_val * ATR_TP_MULT
                else:
                    sl = fill_price + atr_val * ATR_SL_MULT
                    tp = fill_price - atr_val * ATR_TP_MULT

                t = Trade(
                    entry_date=date,
                    direction=order.direction.value,
                    qty=order.qty,
                    entry_price=fill_price,
                    stop_loss=sl,
                    take_profit=tp,
                    confluence=sig_obj.confluence,
                    factors="|".join(sig_obj.factors),
                )
                self._open_trades.append(t)
                self.trades.append(t)
                rm.add_position()
                log.debug(
                    f"FILL  {t.direction} {date.date()} {t.qty:.4f}x{TRADE_SYMBOL} "
                    f"@ {fill_price:.2f} (open={open_:.2f} +slip)"
                )
            pending = new_pending          # always empty after processing

            # ── 2. Check open trades for SL / TP hit ──────────
            #    Worst-case rule: if *both* SL and TP could fire in the
            #    same bar, assume the stop-loss hit first (pessimistic).
            still_open: list[Trade] = []
            for t in self._open_trades:
                hit = False
                if t.direction == Direction.LONG.value:
                    sl_hit = low <= t.stop_loss
                    tp_hit = high >= t.take_profit
                    if sl_hit:                       # SL checked first (worst case)
                        t.exit_price = t.stop_loss
                        hit = True
                    elif tp_hit:
                        t.exit_price = t.take_profit
                        hit = True
                else:  # SHORT
                    sl_hit = high >= t.stop_loss
                    tp_hit = low <= t.take_profit
                    if sl_hit:
                        t.exit_price = t.stop_loss
                        hit = True
                    elif tp_hit:
                        t.exit_price = t.take_profit
                        hit = True

                if hit:
                    multiplier = 1 if t.direction == Direction.LONG.value else -1
                    t.pnl = (t.exit_price - t.entry_price) * t.qty * multiplier
                    t.exit_date = date
                    t.status = "CLOSED"
                    rm.record_fill(t.pnl)
                    rm.remove_position()
                    self.equity += t.pnl
                    log.debug(f"EXIT  {t.direction} {date.date()} @ {t.exit_price:.2f}  PnL={t.pnl:+.2f}")
                else:
                    still_open.append(t)
            self._open_trades = still_open

            # ── 3. Queue new signal for NEXT-bar execution ────
            #    Signal appears on this bar → order evaluated now →
            #    actually filled at tomorrow's Open (step 1 on next bar).
            sig = sig_lookup.get(date)
            if sig is not None:
                order = rm.evaluate(sig, TRADE_SYMBOL)
                if order is not None:
                    pending.append((order, sig))
                    log.debug(
                        f"QUEUED {order.direction.value} {date.date()} "
                        f"(will fill next bar's Open)"
                    )

            self.equity_curve.append(self.equity)

        # Force-close anything still open at last bar
        last_close = trade_df.iloc[-1]["Close"]
        last_date  = trade_df.index[-1]
        for t in self._open_trades:
            multiplier = 1 if t.direction == Direction.LONG.value else -1
            t.exit_price = last_close
            t.pnl = (t.exit_price - t.entry_price) * t.qty * multiplier
            t.exit_date = last_date
            t.status = "FORCE_CLOSED"
            self.equity += t.pnl
        self._open_trades.clear()
        self.equity_curve.append(self.equity)

    # ── Reporting ─────────────────────────────────────────────

    def report(self) -> str:
        closed = [t for t in self.trades if t.status != "OPEN"]
        if not closed:
            return "No closed trades to report."

        wins   = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl <= 0]
        pnls   = [t.pnl for t in closed]

        total_pnl   = sum(pnls)
        win_rate    = len(wins) / len(closed) * 100 if closed else 0
        avg_win     = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss    = np.mean([t.pnl for t in losses]) if losses else 0
        profit_factor = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else float("inf")
        max_dd      = self._max_drawdown()
        expectancy  = np.mean(pnls) if pnls else 0

        rows = [
            ["Start Equity",    f"${self.start_equity:,.2f}"],
            ["End Equity",      f"${self.equity:,.2f}"],
            ["Total P&L",       f"${total_pnl:+,.2f}"],
            ["Return",          f"{(total_pnl / self.start_equity) * 100:+.2f} %"],
            ["Total Trades",    len(closed)],
            ["Win Rate",        f"{win_rate:.1f} %"],
            ["Avg Win",         f"${avg_win:+,.2f}"],
            ["Avg Loss",        f"${avg_loss:+,.2f}"],
            ["Profit Factor",   f"{profit_factor:.2f}"],
            ["Expectancy / trade", f"${expectancy:+,.2f}"],
            ["Max Drawdown",    f"{max_dd:.2f} %"],
        ]
        return tabulate(rows, headers=["Metric", "Value"], tablefmt="simple")

    def _max_drawdown(self) -> float:
        curve = pd.Series(self.equity_curve)
        peak  = curve.cummax()
        dd    = ((curve - peak) / peak) * 100
        return dd.min()

    def save_journal(self, path=None) -> None:
        from config import JOURNAL_CSV
        path = path or JOURNAL_CSV
        rows = []
        for t in self.trades:
            rows.append({
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "direction": t.direction,
                "qty": t.qty,
                "entry_price": round(t.entry_price, 4),
                "exit_price": round(t.exit_price, 4),
                "stop_loss": round(t.stop_loss, 4),
                "take_profit": round(t.take_profit, 4),
                "pnl": round(t.pnl, 2),
                "status": t.status,
                "confluence": t.confluence,
                "factors": t.factors,
            })
        pd.DataFrame(rows).to_csv(path, index=False)
        log.info(f"Trade journal saved → {path}")

    def plot_equity(self, path=None) -> None:
        path = path or (LOGS_DIR / "equity_curve.png")
        plt.figure(figsize=(12, 5))
        plt.plot(self.equity_curve, linewidth=1)
        plt.title("Equity Curve (Backtest)")
        plt.xlabel("Bar #")
        plt.ylabel("Equity ($)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(path, dpi=120)
        plt.close()
        log.info(f"Equity curve saved → {path}")


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the gold strategy")
    parser.add_argument("--equity", type=float, default=INITIAL_EQUITY, help="Starting equity")
    args = parser.parse_args()

    log.info("Fetching signal data …")
    signal_df = fetch_and_enrich(SIGNAL_SYMBOL)

    log.info("Fetching trade-proxy data …")
    trade_df  = fetch_and_enrich(TRADE_SYMBOL)

    # Align to shared dates
    common = signal_df.index.intersection(trade_df.index)
    signal_df = signal_df.loc[common]
    trade_df  = trade_df.loc[common]
    log.info(f"Aligned {len(common)} shared trading days")

    bt = Backtester(equity=args.equity)
    bt.run(signal_df, trade_df)

    print("\n" + bt.report() + "\n")
    bt.save_journal()
    bt.plot_equity()


if __name__ == "__main__":
    main()
