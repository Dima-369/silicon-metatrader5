import argparse
import time
from datetime import datetime, timedelta

import pandas as pd

from siliconmetatrader5 import MetaTrader5


TF_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
}


def to_df(rates):
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates).copy()
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def print_summary(name, df):
    print(f"\n[{name}] rows={len(df)}")
    if df.empty:
        print("No data")
        return
    print("first:", df.iloc[0]["time"], "last:", df.iloc[-1]["time"])
    print(df.tail(5)[["time", "open", "high", "low", "close", "tick_volume", "spread"]])


def freshness_minutes(df, server_now):
    if df.empty:
        return None
    return (server_now - df.iloc[-1]["time"]).total_seconds() / 60.0


def main():
    parser = argparse.ArgumentParser(description="Detailed MT5 fetch diagnostics (3 methods)")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--tf", default="M5", choices=sorted(TF_MAP.keys()))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--range-hours", type=int, default=6)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--retry-sleep", type=float, default=3.0)
    args = parser.parse_args()

    print("=== MT5 Fetch Diagnostic (3 Methods) ===")
    print(f"symbol={args.symbol} tf={args.tf} count={args.count} range_hours={args.range_hours}")

    print("\nConnecting to MT5...")
    mt5 = MetaTrader5(host="localhost", port=8001, keepalive=True)

    connected = False
    for i in range(args.retries):
        print(f"Connection attempt {i+1}/{args.retries}...")
        if mt5.initialize():
            print("Initialization successful!")
            connected = True
            break
        try:
            print(f"Error: {mt5.last_error()}, waiting {args.retry_sleep}s...")
        except Exception:
            print(f"Error reading last_error, waiting {args.retry_sleep}s...")
        time.sleep(args.retry_sleep)

    if not connected:
        print("All attempts failed. Is MT5 open?")
        return 1

    timeframe = getattr(mt5, TF_MAP[args.tf])

    print(f"\nChecking symbol {args.symbol}...")
    if not mt5.symbol_select(args.symbol, True):
        print(f"{args.symbol} not found or could not be added to Market Watch.")
        print("last_error:", mt5.last_error())
        mt5.close()
        return 2

    server_now = datetime.now()
    range_start = server_now - timedelta(hours=args.range_hours)

    print(f"\nFetching data for {args.symbol}...")

    rates_pos = mt5.copy_rates_from_pos(args.symbol, timeframe, 0, args.count)
    rates_from = mt5.copy_rates_from(args.symbol, timeframe, server_now, args.count)
    rates_range = mt5.copy_rates_range(args.symbol, timeframe, range_start, server_now)

    df_pos = to_df(rates_pos)
    df_from = to_df(rates_from)
    df_range = to_df(rates_range)

    if not df_range.empty and len(df_range) > args.count:
        df_range = df_range.tail(args.count).reset_index(drop=True)

    print_summary("copy_rates_from_pos", df_pos)
    print_summary("copy_rates_from", df_from)
    print_summary("copy_rates_range", df_range)

    f_pos = freshness_minutes(df_pos, server_now)
    f_from = freshness_minutes(df_from, server_now)
    f_range = freshness_minutes(df_range, server_now)

    print("\nFreshness (minutes):")
    print("  from_pos:", "N/A" if f_pos is None else f"{f_pos:.2f}")
    print("  from    :", "N/A" if f_from is None else f"{f_from:.2f}")
    print("  range   :", "N/A" if f_range is None else f"{f_range:.2f}")

    if not df_pos.empty and not df_from.empty:
        delta = (df_pos.iloc[-1]["time"] - df_from.iloc[-1]["time"]).total_seconds() / 60.0
        print(f"\nLast-bar delta (from_pos - from): {delta:.2f} min")

    if not df_pos.empty and not df_range.empty:
        delta = (df_pos.iloc[-1]["time"] - df_range.iloc[-1]["time"]).total_seconds() / 60.0
        print(f"Last-bar delta (from_pos - range): {delta:.2f} min")

    all_empty = df_pos.empty and df_from.empty and df_range.empty
    if all_empty:
        print("\nFAILED: All 3 methods returned no data.")
        print("last_error:", mt5.last_error())
        mt5.close()
        return 3

    print("\nSuccess! Data fetch diagnostics completed.")
    print("last_error:", mt5.last_error())

    # Use close() so this test does not intentionally stop shared remote terminal.
    mt5.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
