#!/usr/bin/env python
"""
Supertrend Automated Trading Strategy for OpenAlgo
Calculates Supertrend (10, 3.0) on specified symbol & exchange (e.g. SILVER, GOLD, NIFTY)
and executes automated BUY / SHORT / SQUAREOFF orders on AC Agarwal broker.
"""

import os
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from openalgo import api

# OpenAlgo client auto-initializes using environment variables
api_key = os.getenv("OPENALGO_API_KEY")
host = os.getenv("HOST_SERVER", "http://127.0.0.1:5001")
ws_url = os.getenv("WEBSOCKET_URL", "ws://127.0.0.1:8765")

client = api(api_key=api_key, host=host, ws_url=ws_url)

# Configuration Parameters (Easily set via Strategy UI or Environment)
STRATEGY_NAME = "Supertrend Automated Strategy"
SYMBOL = os.getenv("STRATEGY_SYMBOL", "SILVER100")
EXCHANGE = os.getenv("STRATEGY_EXCHANGE", "MCX")
TIMEFRAME = os.getenv("STRATEGY_TIMEFRAME", "5m")
QUANTITY = int(os.getenv("STRATEGY_QUANTITY", "1"))
PRODUCT = os.getenv("STRATEGY_PRODUCT", "MIS")
PERIOD = int(os.getenv("SUPERTREND_PERIOD", "10"))
MULTIPLIER = float(os.getenv("SUPERTREND_MULTIPLIER", "3.0"))


def calculate_supertrend(df, period=10, multiplier=3.0):
    """Calculates Supertrend ATR upper and lower bands and trend direction (+1 for BUY, -1 for SELL)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Calculate Average True Range (ATR)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    # Basic Upper & Lower Bands
    hl2 = (high + low) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    final_upper = pd.Series(0.0, index=df.index)
    final_lower = pd.Series(0.0, index=df.index)
    supertrend = pd.Series(0.0, index=df.index)
    trend = pd.Series(1, index=df.index)

    for i in range(1, len(df)):
        # Final Upperband
        if basic_upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        # Final Lowerband
        if basic_lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        # Trend Direction
        if trend.iloc[i - 1] == 1:
            if close.iloc[i] < final_lower.iloc[i]:
                trend.iloc[i] = -1
                supertrend.iloc[i] = final_upper.iloc[i]
            else:
                trend.iloc[i] = 1
                supertrend.iloc[i] = final_lower.iloc[i]
        else:
            if close.iloc[i] > final_upper.iloc[i]:
                trend.iloc[i] = 1
                supertrend.iloc[i] = final_lower.iloc[i]
            else:
                trend.iloc[i] = -1
                supertrend.iloc[i] = final_upper.iloc[i]

    df["supertrend"] = supertrend
    df["trend"] = trend
    return df


def run_supertrend_bot():
    print(f"🤖 Starting Supertrend Bot for {EXCHANGE}:{SYMBOL} ({TIMEFRAME}) using AC Agarwal...")
    current_trend = None

    while True:
        try:
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

            candles = client.history(
                symbol=SYMBOL,
                exchange=EXCHANGE,
                interval=TIMEFRAME,
                start_date=from_date,
                end_date=to_date,
            )

            if candles is not None and not candles.empty and len(candles) > PERIOD:
                df = calculate_supertrend(candles, period=PERIOD, multiplier=MULTIPLIER)
                latest_trend = df["trend"].iloc[-1]
                latest_close = df["close"].iloc[-1]
                latest_st = df["supertrend"].iloc[-1]

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] {SYMBOL} Close: {latest_close} | Supertrend: {latest_st:.2f} | Signal: {'BUY 🟢' if latest_trend == 1 else 'SELL 🔴'}"
                )

                # Check for Trend Crossover
                if current_trend is not None and latest_trend != current_trend:
                    if latest_trend == 1:
                        print(f"🚀 SUPERTREND BUY SIGNAL DETECTED! Placing BUY Order for {QUANTITY} qty of {SYMBOL}...")
                        client.placesmartorder(
                            strategy=STRATEGY_NAME,
                            symbol=SYMBOL,
                            exchange=EXCHANGE,
                            action="BUY",
                            product=PRODUCT,
                            quantity=QUANTITY,
                            price_type="MARKET",
                        )
                    elif latest_trend == -1:
                        print(f"🔻 SUPERTREND SELL SIGNAL DETECTED! Placing SELL Order for {QUANTITY} qty of {SYMBOL}...")
                        client.placesmartorder(
                            strategy=STRATEGY_NAME,
                            symbol=SYMBOL,
                            exchange=EXCHANGE,
                            action="SELL",
                            product=PRODUCT,
                            quantity=QUANTITY,
                            price_type="MARKET",
                        )

                current_trend = latest_trend

        except Exception as e:
            print(f"⚠️ Strategy loop error: {e}")

        time.sleep(30)


if __name__ == "__main__":
    run_supertrend_bot()
