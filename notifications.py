"""
notifications.py – Email notification system for trade signals.

Provides functions to format and send trade signal alerts via SMTP.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logger import get_logger
import config as cfg

log = get_logger("notifications")

def send_signal_email(signal_data: dict) -> bool:
    """
    Format and send a trade signal alert via email.
    
    Parameters
    ----------
    signal_data : dict
        A dictionary containing signal details (symbol, direction, entry_price, etc.)
    """
    if not cfg.ENABLE_EMAIL:
        log.debug("Email notifications are disabled in config.")
        return False

    if not all([cfg.SMTP_SERVER, cfg.SMTP_USERNAME, cfg.SMTP_PASSWORD, cfg.NOTIFICATION_EMAIL]):
        log.warning("Email configuration is incomplete. Skipping notification.")
        return False

    symbol = signal_data["symbol"]
    direction = signal_data["direction"]
    entry = signal_data["entry_price"]
    sl = signal_data["stop_loss"]
    tp = signal_data["take_profit"]
    rr = signal_data["risk_reward"]
    confluence = signal_data["confluence"]
    factors = ", ".join(signal_data["factors"])
    date = signal_data["signal_date"]
    timeframe = signal_data.get("timeframe", cfg.ACTIVE_TIMEFRAME).upper()

    subject = f"TRADE SIGNAL [{timeframe}]: {direction} {symbol} @ ${entry:.2f}"
    
    body = f"""
    QUANT-TRADING SIGNAL DETECTED [{timeframe}]
    ============================================
    
    Symbol:      {symbol}
    Timeframe:   {timeframe}
    Direction:   {direction}
    Signal Date: {date}
    
    Entry:       ${entry:.2f}
    Stop-Loss:   ${sl:.2f}
    Take-Profit: ${tp:.2f}
    Risk:Reward: 1:{rr:.1f}
    
    Confluence:  {confluence}/8
    Factors:     {factors}
    
    Review the terminal output or scan manually for details.
    ---
    This is an automated alert from your quant-trading system.
    """

    msg = MIMEMultipart()
    msg['From'] = cfg.SMTP_USERNAME
    msg['To'] = cfg.NOTIFICATION_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        log.info(f"Sending email alert for {symbol} to {cfg.NOTIFICATION_EMAIL} ...")
        with smtplib.SMTP(cfg.SMTP_SERVER, cfg.SMTP_PORT) as server:
            server.starttls()
            server.login(cfg.SMTP_USERNAME, cfg.SMTP_PASSWORD)
            server.send_message(msg)
        log.info("Email sent successfully.")
        return True
    except Exception as e:
        log.error(f"Failed to send email alert: {e}")
        return False


def send_grouped_signal_email(symbol: str, signals: list[dict]) -> bool:
    """
    Send ONE email per symbol containing signals from all scanned timeframes.
    
    Parameters
    ----------
    symbol : str
        The ticker symbol (e.g. SGOL, GC=F).
    signals : list[dict]
        A list of signal_data dicts, each with a 'timeframe' key.
    """
    if not cfg.ENABLE_EMAIL:
        log.debug("Email notifications are disabled in config.")
        return False

    if not all([cfg.SMTP_SERVER, cfg.SMTP_USERNAME, cfg.SMTP_PASSWORD, cfg.NOTIFICATION_EMAIL]):
        log.warning("Email configuration is incomplete. Skipping notification.")
        return False

    if not signals:
        return False

    tf_labels = [s.get("timeframe", "?").upper() for s in signals]
    subject = f"TRADE SIGNALS: {symbol} [{', '.join(tf_labels)}]"

    body_parts = [
        f"    QUANT-TRADING SIGNAL REPORT: {symbol}",
        f"    {'=' * 45}",
        "",
    ]

    for s in signals:
        tf = s.get("timeframe", "?").upper()
        direction = s["direction"]
        entry = s["entry_price"]
        sl = s["stop_loss"]
        tp = s["take_profit"]
        rr = s["risk_reward"]
        confluence = s["confluence"]
        factors = ", ".join(s["factors"])
        date = s["signal_date"]

        body_parts.extend([
            f"    --- {tf} Timeframe ---",
            f"    Direction:   {direction}",
            f"    Signal Date: {date}",
            f"    Entry:       ${entry:.2f}",
            f"    Stop-Loss:   ${sl:.2f}",
            f"    Take-Profit: ${tp:.2f}",
            f"    Risk:Reward: 1:{rr:.1f}",
            f"    Confluence:  {confluence}/8",
            f"    Factors:     {factors}",
            "",
        ])

    body_parts.extend([
        "    ---",
        "    This is an automated alert from your quant-trading system.",
    ])

    body = "\n".join(body_parts)

    msg = MIMEMultipart()
    msg['From'] = cfg.SMTP_USERNAME
    msg['To'] = cfg.NOTIFICATION_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        log.info(f"Sending grouped email for {symbol} ({tf_labels}) to {cfg.NOTIFICATION_EMAIL} ...")
        with smtplib.SMTP(cfg.SMTP_SERVER, cfg.SMTP_PORT) as server:
            server.starttls()
            server.login(cfg.SMTP_USERNAME, cfg.SMTP_PASSWORD)
            server.send_message(msg)
        log.info("Grouped email sent successfully.")
        return True
    except Exception as e:
        log.error(f"Failed to send grouped email: {e}")
        return False


def send_execution_email(symbol: str, side: str, qty: float, price: float) -> bool:
    """Send an alert when the paper bot executes a trade."""
    if not cfg.ENABLE_EMAIL:
        return False

    subject = f"TRADE EXECUTED: {side.upper()} {qty} {symbol} @ ${price:.2f}"
    body = f"Paper bot just executed a {side.upper()} order for {qty} shares of {symbol} at ${price:.2f}."
    
    msg = MIMEMultipart()
    msg['From'] = cfg.SMTP_USERNAME
    msg['To'] = cfg.NOTIFICATION_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(cfg.SMTP_SERVER, cfg.SMTP_PORT) as server:
            server.starttls()
            server.login(cfg.SMTP_USERNAME, cfg.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        log.error(f"Failed to send execution email: {e}")
        return False
