"""
risk_manager.py – Position sizing and portfolio-level risk guards.

Responsibilities
────────────────
1. Calculate share quantity so that a stop-loss hit = max RISK_PER_TRADE of equity
   (Fixed-Fractional model).
2. Optionally cap size via Kelly-Lite criterion when enough trade history exists.
3. Enforce MAX_OPEN_POSITIONS cap.
4. Enforce DAILY_LOSS_LIMIT circuit breaker.
"""

from dataclasses import dataclass
from typing import Optional

from config import (
    RISK_PER_TRADE,
    MAX_OPEN_POSITIONS,
    DAILY_LOSS_LIMIT,
    USE_KELLY,
    KELLY_FRACTION,
    KELLY_MIN_TRADES,
    USE_FRACTIONAL,
)
from strategy import Signal, Direction
from logger import get_logger

log = get_logger("risk_mgr")


@dataclass
class OrderRequest:
    """Validated, risk-adjusted order ready for execution."""
    symbol: str
    direction: Direction
    qty: float              # float to support fractional shares
    entry_price: float
    stop_loss: float
    take_profit: float


class RiskManager:
    """Stateful risk gate that sits between the strategy and the broker."""

    def __init__(self,
                 equity: float,
                 open_positions: int = 0,
                 daily_pnl: float = 0.0,
                 trade_history: list[float] | None = None):
        self.equity = equity
        self.open_positions = open_positions
        self.daily_pnl = daily_pnl
        self._starting_equity = equity
        # List of per-trade P&L values (for Kelly computation)
        self.trade_history: list[float] = trade_history or []

    # ── Public API ────────────────────────────────────────────

    def evaluate(self, signal: Signal, symbol: str) -> Optional[OrderRequest]:
        """
        Run all risk checks.  Returns an OrderRequest if approved, None if rejected.
        """
        # Guard 1 – daily loss breaker
        if self._daily_loss_breached():
            log.warning("DAILY LOSS LIMIT hit – no new trades today")
            return None

        # Guard 2 – max positions
        if self.open_positions >= MAX_OPEN_POSITIONS:
            log.warning(f"MAX_OPEN_POSITIONS ({MAX_OPEN_POSITIONS}) reached – skipping")
            return None

        # Guard 3 – calculate risk-adjusted size
        qty = self._size_position(signal)
        if qty < 0.01:
            log.warning("Position size < 0.01 shares after risk sizing – skipping")
            return None

        order = OrderRequest(
            symbol=symbol,
            direction=signal.direction,
            qty=qty,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )
        log.info(
            f"APPROVED {order.direction.value} {order.qty} × {order.symbol} "
            f"@ ~{order.entry_price:.2f}  SL={order.stop_loss:.2f}  TP={order.take_profit:.2f}"
        )
        return order

    def record_fill(self, pnl: float = 0.0) -> None:
        """Call after a position is opened (pnl=0) or closed (pnl=realised)."""
        self.daily_pnl += pnl
        self.equity += pnl
        if pnl != 0.0:
            self.trade_history.append(pnl)

    def add_position(self) -> None:
        self.open_positions += 1

    def remove_position(self) -> None:
        self.open_positions = max(0, self.open_positions - 1)

    def reset_daily(self, new_equity: float) -> None:
        """Call at the start of each trading day."""
        self.equity = new_equity
        self._starting_equity = new_equity
        self.daily_pnl = 0.0

    # ── Kelly Criterion ───────────────────────────────────────

    def kelly_fraction(self) -> float:
        """
        Compute Kelly-Lite optimal risk fraction from trade history.

        f* = (p × W − (1 − p)) / W
        where:
            p = win rate
            W = avg_win / avg_loss  (reward-to-risk ratio)

        Returns
        -------
        Fraction of equity to risk (already scaled by KELLY_FRACTION).
        Returns 0 if not enough data or edge is negative.
        """
        if len(self.trade_history) < KELLY_MIN_TRADES:
            return 0.0

        wins   = [t for t in self.trade_history if t > 0]
        losses = [t for t in self.trade_history if t <= 0]

        if not wins or not losses:
            return 0.0

        p = len(wins) / len(self.trade_history)
        avg_win  = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))

        if avg_loss == 0:
            return 0.0

        W = avg_win / avg_loss
        full_kelly = (p * W - (1 - p)) / W

        if full_kelly <= 0:
            return 0.0   # no edge → don't trade via Kelly

        kelly_lite = full_kelly * KELLY_FRACTION
        log.debug(
            f"Kelly: p={p:.2%} W={W:.2f} full={full_kelly:.3f} "
            f"lite={kelly_lite:.3f} ({len(self.trade_history)} trades)"
        )
        return kelly_lite

    # ── Internals ─────────────────────────────────────────────

    def _daily_loss_breached(self) -> bool:
        if self._starting_equity == 0:
            return False
        return (self.daily_pnl / self._starting_equity) <= -DAILY_LOSS_LIMIT

    def _size_position(self, signal: Signal) -> float:
        """
        Position sizing hierarchy:
        1. Fixed-Fractional:  risk_amount = equity × RISK_PER_TRADE
        2. Kelly cap (if enabled and enough data):
              kelly_risk = equity × kelly_fraction()
              use the SMALLER of fixed-fractional and Kelly to be conservative.
        3. Shares = risk_amount / |entry − stop_loss|

        Returns float if USE_FRACTIONAL, else int.
        """
        risk_frac = RISK_PER_TRADE

        if USE_KELLY:
            kf = self.kelly_fraction()
            if kf > 0:
                risk_frac = min(risk_frac, kf)
                log.debug(f"Kelly cap active: risk_frac={risk_frac:.4f}")

        risk_amount = self.equity * risk_frac
        distance = abs(signal.entry_price - signal.stop_loss)

        if distance == 0:
            return 0

        raw = risk_amount / distance

        if USE_FRACTIONAL:
            return round(raw, 4)    # Alpaca accepts up to 9 decimals
        return int(raw)             # floor to whole shares
