"""
retrain_model.py – Retrain the logistic regression model WITHOUT data leakage.

The original model was trained using `exit_price` as a feature, which is
unknowable at prediction time (you can't know the exit price before taking
the trade). This script retrains the model using ONLY features that are
available at the moment of signal generation.

Usage
─────
    python retrain_model.py
"""

import os
import joblib
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score

from data_fetch import fetch_and_enrich
from config import SIGNAL_SYMBOL, LOGS_DIR
from logger import get_logger

log = get_logger("retrain")

# ── Features available at entry time (NO leakage) ────────────
# These are the ONLY features we can know when the signal fires.
# Excluded: exit_price (unknown), qty (derived from equity, not predictive)
ENTRY_FEATURES = [
    "entry_price", "stop_loss", "take_profit", "confluence",
    "entry_year", "entry_month", "entry_day", "entry_dayofweek",
    "RSI", "MACD", "MACDs", "EMA_Gap", "ATR", "ATR_Ratio",
    "Recent_Price_Momentum", "Volume_Changes",
    "direction_SHORT",
    "factor_FVG_zone", "factor_LIQ_sweep", "factor_EMA_trend",
    "factor_MACD_confirm", "factor_Order_Block",
    "factor_RSI_filter", "factor_EMA_cross",
]


def build_training_data() -> pd.DataFrame:
    """
    Load the trade journal and enrich each trade with indicator values
    from the signal DataFrame, producing a clean training set.
    """
    journal_path = LOGS_DIR / "trade_journal.csv"
    if not journal_path.exists():
        raise FileNotFoundError(
            f"No trade journal at {journal_path}. "
            "Run `python backtest.py` first to generate training data."
        )

    journal = pd.read_csv(journal_path, parse_dates=["entry_date", "exit_date"])
    if journal.empty:
        raise ValueError("Trade journal is empty. Run a baseline backtest first.")

    log.info(f"Loaded {len(journal)} trades from {journal_path.name}")

    # Load enriched data for indicator values
    df = fetch_and_enrich(SIGNAL_SYMBOL)

    rows = []
    for _, trade in journal.iterrows():
        entry_date = pd.Timestamp(trade["entry_date"])

        # Find the closest date in the enriched DataFrame
        if entry_date in df.index:
            bar = df.loc[entry_date]
        else:
            # Find the nearest previous date
            mask = df.index <= entry_date
            if mask.any():
                bar = df.loc[df.index[mask][-1]]
            else:
                continue

        bar_idx = df.index.get_loc(bar.name)

        # Calculate derived features
        ema_gap = (bar["EMA_fast"] - bar["EMA_slow"]) / bar["EMA_slow"] if bar["EMA_slow"] != 0 else 0
        atr_ratio = bar["ATR"] / bar["Close"] if bar["Close"] != 0 else 0
        momentum = bar["Close"] - df.iloc[max(0, bar_idx - 5)]["Close"]
        prev_vol = df.iloc[max(0, bar_idx - 1)]["Volume"]
        vol_change = bar["Volume"] / prev_vol if prev_vol != 0 else 1.0

        # Parse factors from the pipe-separated string
        factors_str = str(trade.get("factors", ""))
        factors_list = factors_str.split("|") if factors_str else []

        # Target: WIN = 1, LOSS = 0
        target = 1 if trade["pnl"] > 0 else 0

        rows.append({
            "entry_price": trade["entry_price"],
            "stop_loss": trade["stop_loss"],
            "take_profit": trade["take_profit"],
            "confluence": trade["confluence"],
            "entry_year": entry_date.year,
            "entry_month": entry_date.month,
            "entry_day": entry_date.day,
            "entry_dayofweek": entry_date.dayofweek,
            "RSI": bar["RSI"],
            "MACD": bar.get("MACD", 0),
            "MACDs": bar.get("MACD_signal", 0),
            "EMA_Gap": ema_gap,
            "ATR": bar["ATR"],
            "ATR_Ratio": atr_ratio,
            "Recent_Price_Momentum": momentum,
            "Volume_Changes": vol_change,
            "direction_SHORT": 1 if trade["direction"] == "SHORT" else 0,
            "factor_FVG_zone": 1 if "FVG_zone" in factors_list else 0,
            "factor_LIQ_sweep": 1 if "LIQ_sweep" in factors_list else 0,
            "factor_EMA_trend": 1 if "EMA_trend" in factors_list else 0,
            "factor_MACD_confirm": 1 if "MACD_confirm" in factors_list else 0,
            "factor_Order_Block": 1 if "Order_Block" in factors_list else 0,
            "factor_RSI_filter": 1 if "RSI_filter" in factors_list else 0,
            "factor_EMA_cross": 1 if "EMA_cross" in factors_list else 0,
            "target": target,
        })

    training_df = pd.DataFrame(rows)
    log.info(f"Built training set: {len(training_df)} samples, "
             f"{training_df['target'].sum()} wins, "
             f"{(1 - training_df['target']).sum():.0f} losses")
    return training_df


def train_model(training_df: pd.DataFrame) -> Pipeline:
    """Train a Logistic Regression with StandardScaler (no leakage)."""
    X = training_df[ENTRY_FEATURES]
    y = training_df["target"]

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(
            max_iter=1000,
            C=1.0,
            solver="lbfgs",
            random_state=42,
        ))
    ])

    # Cross-validation score
    scores = cross_val_score(pipeline, X, y, cv=5, scoring="accuracy")
    log.info(f"Cross-validation accuracy: {scores.mean():.2%} (+/- {scores.std():.2%})")

    # Fit on full data
    pipeline.fit(X, y)

    # Print feature importance
    coefs = pipeline.named_steps["classifier"].coef_[0]
    log.info("Feature importance (|coefficient|):")
    for name, coef in sorted(zip(ENTRY_FEATURES, coefs), key=lambda x: abs(x[1]), reverse=True):
        log.info(f"  {name:30s}  {coef:+.4f}")

    return pipeline


def main():
    log.info("=== Retraining ML model (no data leakage) ===")

    training_df = build_training_data()

    pipeline = train_model(training_df)

    # Save the new model
    model_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(model_dir, exist_ok=True)

    # Backup old model
    old_path = os.path.join(model_dir, "logistic_regression_model.pkl")
    if os.path.exists(old_path):
        backup_path = os.path.join(model_dir, "logistic_regression_model_BACKUP.pkl")
        os.rename(old_path, backup_path)
        log.info(f"Old model backed up to {backup_path}")

    # Save new model
    joblib.dump(pipeline, old_path)
    log.info(f"New model saved to {old_path}")

    # Quick validation: predict probabilities on training data
    X = training_df[ENTRY_FEATURES]
    probs = pipeline.predict_proba(X)[:, 1]
    log.info(f"Prediction stats on training data:")
    log.info(f"  Min:    {probs.min():.4f}")
    log.info(f"  Max:    {probs.max():.4f}")
    log.info(f"  Mean:   {probs.mean():.4f}")
    log.info(f"  Median: {np.median(probs):.4f}")
    log.info(f"  Above 50%: {(probs >= 0.50).sum()} / {len(probs)}")

    log.info("=== Retraining complete ===")


if __name__ == "__main__":
    main()
