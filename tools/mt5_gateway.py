#!/usr/bin/env python3
"""Read-only JSON-lines gateway for the authenticated MT5 terminal.

The process owns one long-lived SiliconMetaTrader5 client. It deliberately exposes
observation only: there is no order_check/order_send path in this module. Rust talks
through stdin/stdout so it does not need to know anything about RPyC.

Timestamps sent to MT5 are integer Unix epochs. MT5 returns broker-server-labelled
epochs; ``--server-offset-seconds`` converts those labels to UTC while retaining the
raw value in every rate/tick row.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from typing import Any, Iterable

from siliconmetatrader5 import MetaTrader5


def log(message: str) -> None:
    print(f"mt5-gateway: {message}", file=sys.stderr, flush=True)


def plain(value: Any) -> Any:
    """Turn RPyC/numpy/namedtuple values into JSON-safe Python values."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return plain(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "_asdict"):
        return {str(k): plain(v) for k, v in value._asdict().items()}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    names = getattr(getattr(value, "dtype", None), "names", None)
    if names:
        return [
            {str(name): plain(row[name]) for name in names}
            for row in value
        ]
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return repr(value)


def epoch_utc(raw: int, offset_seconds: int) -> str:
    return dt.datetime.fromtimestamp(
        raw - offset_seconds, tz=dt.timezone.utc
    ).isoformat().replace("+00:00", "Z")


def row_dicts(rows: Any) -> list[dict[str, Any]]:
    value = plain(rows)
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return [row for row in value if isinstance(row, dict)]


def raw_time(row: dict[str, Any]) -> int:
    raw = row.get("time")
    if raw is None and row.get("time_msc") is not None:
        raw = int(row["time_msc"]) // 1000
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def normalize_tick(row: dict[str, Any], offset_seconds: int) -> dict[str, Any]:
    raw = raw_time(row)
    out = dict(row)
    out["time_raw"] = raw
    out["time_utc"] = epoch_utc(raw, offset_seconds) if raw else None
    if row.get("time_msc") is not None:
        try:
            out["time_msc_raw"] = int(row["time_msc"])
        except (TypeError, ValueError):
            out["time_msc_raw"] = None
    return out


def normalize_rate(row: dict[str, Any], offset_seconds: int) -> dict[str, Any]:
    raw = raw_time(row)
    out = dict(row)
    out["time_raw"] = raw
    out["time_utc"] = epoch_utc(raw, offset_seconds) if raw else None
    return out


def last_error(mt5: MetaTrader5) -> Any:
    try:
        return plain(mt5.last_error())
    except Exception as exc:  # pragma: no cover - only bridge failure path
        return {"error": repr(exc)}


def call_rows(fn: Any) -> tuple[list[dict[str, Any]], Any]:
    try:
        return row_dicts(fn()), None
    except Exception as exc:
        return [], {"type": type(exc).__name__, "message": str(exc)}


def observe(
    mt5: MetaTrader5,
    request: dict[str, Any],
    server_offset_seconds: int,
) -> dict[str, Any]:
    symbols = request.get("symbols") or ["EURUSD"]
    bars = max(1, min(int(request.get("bars", 300)), 10_000))
    history_bars = max(0, min(int(request.get("history_bars", bars)), 10_000))
    tick_seconds = max(60, min(int(request.get("tick_seconds", 3600)), 86_400))
    history_days = max(1, min(int(request.get("history_days", 7)), 365))
    now_epoch = int(time.time())
    # MT5's bridge labels timestamps in broker-server time (currently UTC+3),
    # while `time.time()` is UTC. Date-range APIs must receive server-labelled
    # epochs or they return a window offset by the calibration amount. Keep the
    # observation timestamp itself in host UTC; only MT5 query bounds use this.
    now_server_epoch = now_epoch + server_offset_seconds
    history_from = now_server_epoch - history_days * 86_400

    account = plain(mt5.account_info())
    terminal = plain(mt5.terminal_info())
    symbol_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        selected = bool(mt5.symbol_select(symbol, True))
        info = plain(mt5.symbol_info(symbol)) if selected else None
        tick = plain(mt5.symbol_info_tick(symbol)) if selected else None
        rates = (
            mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bars)
            if selected
            else None
        )
        ticks = (
            mt5.copy_ticks_range(
                symbol,
                now_server_epoch - tick_seconds,
                now_server_epoch,
                mt5.COPY_TICKS_ALL,
            )
            if selected
            else None
        )
        history_rates = (
            mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, bars, history_bars)
            if selected and history_bars
            else None
        )
        rate_rows = [normalize_rate(row, server_offset_seconds) for row in row_dicts(rates)]
        history_rate_rows = [
            normalize_rate(row, server_offset_seconds)
            for row in row_dicts(history_rates)
        ]
        tick_rows = [normalize_tick(row, server_offset_seconds) for row in row_dicts(ticks)]
        current_tick = normalize_tick(tick, server_offset_seconds) if isinstance(tick, dict) else None
        symbol_rows.append(
            {
                "symbol": symbol,
                "selected": selected,
                "select_error": None if selected else last_error(mt5),
                "info": info,
                "tick": current_tick,
                "rates_m5": rate_rows,
                "history_rates_m5": history_rate_rows,
                "ticks": tick_rows,
            }
        )

    positions, positions_error = call_rows(mt5.positions_get)
    orders, orders_error = call_rows(mt5.orders_get)
    try:
        history_orders_raw = mt5.history_orders_get(history_from, now_server_epoch)
        history_orders = row_dicts(history_orders_raw)
        history_orders_error = None
    except Exception as exc:
        history_orders = []
        history_orders_error = {"type": type(exc).__name__, "message": str(exc)}
    try:
        history_deals_raw = mt5.history_deals_get(history_from, now_server_epoch)
        history_deals = row_dicts(history_deals_raw)
        history_deals_error = None
    except Exception as exc:
        history_deals = []
        history_deals_error = {"type": type(exc).__name__, "message": str(exc)}

    for rows in (positions, orders, history_orders, history_deals):
        for row in rows:
            if "time" in row:
                row["time_raw"] = raw_time(row)
                row["time_utc"] = epoch_utc(row["time_raw"], server_offset_seconds)
            if "time_setup" in row:
                try:
                    raw = int(row["time_setup"])
                    row["time_setup_raw"] = raw
                    row["time_setup_utc"] = epoch_utc(raw, server_offset_seconds)
                except (TypeError, ValueError):
                    pass
            if "time_done" in row:
                try:
                    raw = int(row["time_done"])
                    row["time_done_raw"] = raw
                    row["time_done_utc"] = epoch_utc(raw, server_offset_seconds)
                except (TypeError, ValueError):
                    pass

    return {
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "observed_at_epoch": now_epoch,
        "server_offset_seconds": server_offset_seconds,
        "account": account,
        "terminal": terminal,
        "symbols": symbol_rows,
        "positions": positions,
        "positions_error": positions_error,
        "orders": orders,
        "orders_error": orders_error,
        "history_orders": history_orders,
        "history_orders_error": history_orders_error,
        "history_deals": history_deals,
        "history_deals_error": history_deals_error,
        "last_error": last_error(mt5),
    }


def response(request_id: Any, result: Any = None, error: Any = None) -> None:
    payload = {"id": request_id, "ok": error is None}
    if error is None:
        payload["result"] = result
    else:
        payload["error"] = error
    print(json.dumps(payload, separators=(",", ":"), allow_nan=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--server-offset-seconds", type=int, default=10_800)
    args = parser.parse_args()

    mt5 = MetaTrader5(host=args.host, port=args.port, keepalive=True)
    try:
        if not mt5.initialize():
            response(None, error={"operation": "initialize", "last_error": last_error(mt5)})
            return 1
        log(f"connected to bridge {args.host}:{args.port}; offset={args.server_offset_seconds}s")
        for line in sys.stdin:
            if not line.strip():
                continue
            request_id: Any = None
            try:
                request = json.loads(line)
                request_id = request.get("id")
                if request.get("op") != "observe":
                    raise ValueError("only the read-only observe operation is supported")
                result = observe(mt5, request, args.server_offset_seconds)
                response(request_id, result=result)
            except Exception as exc:
                response(
                    request_id,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
    finally:
        try:
            mt5.close()
        except Exception as exc:  # pragma: no cover - shutdown best effort
            log(f"close failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
