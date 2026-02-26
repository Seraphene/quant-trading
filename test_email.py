"""
test_email.py – Verify SMTP configuration and email delivery.
"""

from notifications import send_signal_email
import config as cfg
import sys

def main():
    print("Testing Email Notifications...")
    print(f"SMTP Server:      {cfg.SMTP_SERVER}")
    print(f"SMTP Port:        {cfg.SMTP_PORT}")
    print(f"SMTP User:        {cfg.SMTP_USERNAME}")
    print(f"Recipient:        {cfg.NOTIFICATION_EMAIL}")
    print(f"Enabled in cfg:   {cfg.ENABLE_EMAIL}")
    
    if not cfg.ENABLE_EMAIL:
        print("\nERROR: Email notifications are disabled in config.py.")
        print("Set ENABLE_EMAIL = True (or use environment variables) to test.")
        sys.exit(1)

    test_data = {
        "symbol": "TEST",
        "direction": "LONG",
        "entry_price": 1234.56,
        "stop_loss": 1200.00,
        "take_profit": 1300.00,
        "risk_reward": 1.5,
        "confluence": 4,
        "factors": ["Test_Factor_1", "Test_Factor_2"],
        "signal_date": "2026-02-26 12:00:00"
    }

    print("\nSending test signal email...")
    success = send_signal_email(test_data)
    
    if success:
        print("\nSUCCESS: Test email sent.")
    else:
        print("\nFAILURE: Check your .env credentials and logs for errors.")

if __name__ == "__main__":
    main()
