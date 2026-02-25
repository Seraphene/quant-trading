"""
scanner.py – Market signal scanner.

Scans one or more symbols for trade signals using the same strategy engine
that powers the backtester and paper-bot.  No broker connection needed.

Usage
─────
    python scanner.py                           # scan default symbol (SGOL)
    python scanner.py --symbols GC=F --force    # scan Gold Futures
    python scanner.py --symbols GC=F NQ=F SGOL  # scan multiple symbols
    python scanner.py --symbols GC=F --timeframe 4h --force

yfinance ticker examples:
    GC=F       Gold Futures (COMEX)
    SI=F       Silver Futures
    NQ=F       Nasdaq 100 Futures
    ES=F       S&P 500 Futures
    EURUSD=X   EUR / USD forex
    GBPUSD=X   GBP / USD forex
    SGOL       Aberdeen Gold ETF
    GLD        SPDR Gold Trust ETF
    SPY        S&P 500 ETF
"""

import argparse
from datetime import datetime, timedelta

import pandas as pd

import config as cfg
from data_fetch import fetch_and_enrich
from strategy import generate_signals, latest_signal, Direction
from logger import get_logger

log = get_logger("scanner")


# ── Apply timeframe override (same as backtest/paper_bot) ─────

def _apply_timeframe_override(tf: str) -> None:
    if tf == cfg.ACTIVE_TIMEFRAME:
        return
    if tf not in cfg.TIMEFRAME_PRESETS:
        raise ValueError(f"Unknown timeframe '{tf}'. Choose from: {list(cfg.TIMEFRAME_PRESETS.keys())}")
    log.info(f"Overriding timeframe: {cfg.ACTIVE_TIMEFRAME} → {tf}")
    cfg.ACTIVE_TIMEFRAME = tf
    for key, value in cfg.TIMEFRAME_PRESETS[tf].items():
        setattr(cfg, key, value)


# ── Scan a single symbol ──────────────────────────────────────

def scan_symbol(symbol: str, force: bool = False) -> dict | None:
    """
    Fetch data, run strategy, return latest signal details or None.
    """
    try:
        # Scanner is an advisory tool — include the current forming
        # candle so the user sees what the market looks like RIGHT NOW.
        # (drop_incomplete is for the paper_bot which actually executes)
        df = fetch_and_enrich(symbol, force=force, drop_incomplete=False)
    except Exception as e:
        log.error(f"Failed to fetch data for {symbol}: {e}")
        return None

    if df is None or len(df) < 50:
        log.warning(f"{symbol}: Not enough data ({len(df) if df is not None else 0} bars)")
        return None

    sig = latest_signal(df)
    if sig is None:
        return None

    # Calculate risk/reward ratio (from original signal entry)
    risk = abs(sig.entry_price - sig.stop_loss)
    reward = abs(sig.take_profit - sig.entry_price)
    rr = reward / risk if risk > 0 else 0.0

    # Calculate distance to current price
    current_price = df["Close"].iloc[-1]
    pct_from_signal = ((current_price - sig.entry_price) / sig.entry_price) * 100

    # Adjusted R:R if entering NOW at current price
    # (the original SL/TP levels stay the same — they're price levels on the chart)
    if sig.direction == Direction.LONG:
        adj_risk = abs(current_price - sig.stop_loss)
        adj_reward = abs(sig.take_profit - current_price)
        # Price above TP = totally missed
        price_missed = current_price >= sig.take_profit
        # Price below SL = already invalidated
        price_invalid = current_price <= sig.stop_loss
    else:  # SHORT
        adj_risk = abs(sig.stop_loss - current_price)
        adj_reward = abs(current_price - sig.take_profit)
        price_missed = current_price <= sig.take_profit
        price_invalid = current_price >= sig.stop_loss

    adj_rr = adj_reward / adj_risk if adj_risk > 0 else 0.0

    if price_missed:
        entry_verdict = "❌ MISSED — price already past TP"
    elif price_invalid:
        entry_verdict = "❌ INVALID — price already past SL"
    elif adj_rr >= 1.5:
        entry_verdict = f"✅ FAVORABLE — adjusted R:R 1:{adj_rr:.1f}"
    elif adj_rr >= 1.0:
        entry_verdict = f"⚠️ MARGINAL — adjusted R:R 1:{adj_rr:.1f}"
    else:
        entry_verdict = f"❌ POOR — adjusted R:R 1:{adj_rr:.1f} (risk > reward)"

    # Signal age in TRADING BARS (not calendar days)
    try:
        sig_idx = df.index.get_loc(sig.date)
        bars_ago = len(df) - 1 - sig_idx
    except KeyError:
        bars_ago = 999

    log.debug(f"{symbol}: signal={sig.date}, last_bar={df.index[-1]}, bars_ago={bars_ago}, len={len(df)}")

    return {
        "symbol": symbol,
        "direction": sig.direction.value,
        "entry_price": sig.entry_price,
        "current_price": current_price,
        "stop_loss": sig.stop_loss,
        "take_profit": sig.take_profit,
        "risk_reward": rr,
        "adj_rr": adj_rr,
        "entry_verdict": entry_verdict,
        "confluence": sig.confluence,
        "factors": sig.factors,
        "signal_date": sig.date,
        "atr": sig.atr,
        "pct_from_signal": pct_from_signal,
        "bars_ago": bars_ago,
    }


# ── Pretty-print results ─────────────────────────────────────

def print_results(results: list[dict], timeframe: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print()
    print(f"{'═' * 60}")
    print(f"  📊 Market Scanner  |  {timeframe.upper()}  |  {now}")
    print(f"{'═' * 60}")

    if not results:
        print(f"\n  No actionable signals found.\n")
        return

    for r in results:
        direction_icon = "🟢 LONG" if r["direction"] == "LONG" else "🔴 SHORT"
        factors_str = ", ".join(r["factors"])

        # Freshness badge (based on trading bars, not calendar days)
        bars = r["bars_ago"]
        if bars <= 1:
            freshness = "🟢 FRESH"
        elif bars <= 3:
            freshness = f"🟡 {bars} bars ago"
        else:
            freshness = f"🔴 STALE ({bars} bars ago)"

        print(f"\n  ┌─ {r['symbol']} ─────────────────────────────")
        print(f"  │ Direction:    {direction_icon}")
        print(f"  │ Signal Date:  {r['signal_date']}  {freshness}")
        print(f"  │")
        print(f"  │ Signal Entry: ${r['entry_price']:.2f}  (original)")
        print(f"  │ Current:      ${r['current_price']:.2f}  ({r['pct_from_signal']:+.1f}%)")
        print(f"  │ Stop-Loss:    ${r['stop_loss']:.2f}")
        print(f"  │ Take-Profit:  ${r['take_profit']:.2f}")
        print(f"  │")
        print(f"  │ Original R:R: 1:{r['risk_reward']:.1f}")
        print(f"  │ If Enter Now: {r['entry_verdict']}")
        print(f"  │")
        print(f"  │ ATR:          ${r['atr']:.2f}")
        print(f"  │ Confluence:   {r['confluence']}/8  ({factors_str})")
        print(f"  └{'─' * 45}")

    print(f"\n  ⚠️  These are signals, not financial advice.")
    print(f"  └  Always verify before placing real trades.\n")


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan symbols for trade signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scanner.py                              # scan SGOL (default)
  python scanner.py --symbols GC=F --force       # scan Gold Futures
  python scanner.py --symbols GC=F NQ=F SGOL     # scan multiple
  python scanner.py --symbols GC=F -tf 4h        # Gold on 4H timeframe
  python scanner.py --max-age 2                   # only show signals ≤ 2 days old

Common tickers:
  GC=F  Gold Futures    SGOL  Gold ETF     SPY  S&P 500 ETF
  NQ=F  Nasdaq Futures  SI=F  Silver       ES=F  S&P Futures
        """,
    )
    parser.add_argument(
        "--symbols", "-s",
        nargs="+",
        default=[cfg.SIGNAL_SYMBOL],
        help="One or more yfinance tickers to scan (default: SGOL)",
    )
    parser.add_argument(
        "--timeframe", "-tf",
        choices=list(cfg.TIMEFRAME_PRESETS.keys()),
        default=None,
        help="Override active timeframe (e.g. 1d, 4h)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-download data (default: use cache if available)",
    )
    parser.add_argument(
        "--max-age", type=int, default=None,
        help="Only show signals ≤ this many trading bars old (e.g. 3 = last 3 bars)",
    )
    args = parser.parse_args()

    if args.timeframe:
        _apply_timeframe_override(args.timeframe)

    log.info(f"Scanning {len(args.symbols)} symbol(s) on {cfg.ACTIVE_TIMEFRAME} timeframe")

    results = []
    for sym in args.symbols:
        log.info(f"Scanning {sym} …")
        result = scan_symbol(sym, force=args.force)
        if result:
            if args.max_age is not None and result["bars_ago"] > args.max_age:
                log.info(f"{sym}: Signal too old ({result['bars_ago']} bars > {args.max_age})")
            else:
                results.append(result)
        else:
            log.info(f"{sym}: No signal")

    print_results(results, cfg.ACTIVE_TIMEFRAME)


if __name__ == "__main__":
    main()
