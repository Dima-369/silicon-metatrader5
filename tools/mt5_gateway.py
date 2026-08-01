#!/usr/bin/env python3
"""Read-only JSON-lines gateway for the authenticated MT5 terminal.

The process owns one long-lived SiliconMetaTrader5 client. It deliberately exposes
observation only: there is no order_check/order_send path in this module. Rust talks
through stdin/stdout so it does not need to know anything about RPyC.

The collector uses one request per symbol. This matters: one wedged MT5 history call
must not discard the other 19 symbols' quote evidence. Rust puts a wall-clock deadline
around every request and replaces this child when that deadline expires.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from typing import Any, Callable

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
        return [{str(name): plain(row[name]) for name in names} for row in value]
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return repr(value)


def epoch_utc(raw: int, offset_seconds: int) -> str:
    return dt.datetime.fromtimestamp(raw - offset_seconds, tz=dt.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


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


def timed_call(
    diagnostics: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    operation: str,
    fn: Callable[[], Any],
) -> Any:
    started = time.monotonic()
    try:
        return fn()
    except Exception as exc:
        errors.append(
            {
                "operation": operation,
                "message": str(exc),
                "type": type(exc).__name__,
                "transport": True,
            }
        )
        return None
    finally:
        diagnostics.append(
            {
                "operation": operation,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
        )


def record_empty(
    errors: list[dict[str, Any]],
    operation: str,
    value: Any,
) -> None:
    if value is None and not any(error.get("operation") == operation for error in errors):
        errors.append(
            {
                "operation": operation,
                "message": "MT5 returned no data",
                "type": "EmptyResult",
                "transport": False,
            }
        )


def safe_rows(
    diagnostics: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    operation: str,
    fn: Callable[[], Any],
) -> tuple[list[dict[str, Any]], Any]:
    raw = timed_call(diagnostics, errors, operation, fn)
    record_empty(errors, operation, raw)
    if raw is None:
        return [], errors[-1] if errors and errors[-1].get("operation") == operation else None
    try:
        return row_dicts(raw), None
    except Exception as exc:
        error = {"operation": operation, "message": str(exc), "type": type(exc).__name__}
        errors.append(error)
        return [], error


def observation_clock(server_offset_seconds: int) -> dict[str, Any]:
    epoch = int(time.time())
    return {
        "observed_at_utc": epoch_utc(epoch, 0),
        "observed_at_epoch": epoch,
        "server_offset_seconds": server_offset_seconds,
    }


def observe_symbol(
    mt5: MetaTrader5,
    symbol: str,
    bars: int,
    history_bars: int,
    tick_seconds: int,
    query_epoch: int,
    server_offset_seconds: int,
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    now_server_epoch = query_epoch + server_offset_seconds

    selected_raw = timed_call(
        diagnostics,
        errors,
        f"{symbol}.symbol_select",
        lambda: mt5.symbol_select(symbol, True),
    )
    selected = bool(selected_raw)
    if not selected and not errors:
        errors.append(
            {
                "operation": f"{symbol}.symbol_select",
                "message": "returned false",
                "type": "SelectionError",
                "transport": False,
            }
        )

    info_raw = (
        timed_call(diagnostics, errors, f"{symbol}.symbol_info", lambda: mt5.symbol_info(symbol))
        if selected
        else None
    )
    tick_raw = (
        timed_call(
            diagnostics,
            errors,
            f"{symbol}.symbol_info_tick",
            lambda: mt5.symbol_info_tick(symbol),
        )
        if selected
        else None
    )
    rates_raw = (
        timed_call(
            diagnostics,
            errors,
            f"{symbol}.copy_rates_recent",
            lambda: mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bars),
        )
        if selected
        else None
    )
    ticks_raw = (
        timed_call(
            diagnostics,
            errors,
            f"{symbol}.copy_ticks",
            lambda: mt5.copy_ticks_range(
                symbol,
                now_server_epoch - tick_seconds,
                now_server_epoch,
                mt5.COPY_TICKS_ALL,
            ),
        )
        if selected
        else None
    )
    history_rates_raw = (
        timed_call(
            diagnostics,
            errors,
            f"{symbol}.copy_rates_context",
            lambda: mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, bars, history_bars),
        )
        if selected and history_bars
        else None
    )
    for operation, value in (
        (f"{symbol}.symbol_info", info_raw),
        (f"{symbol}.symbol_info_tick", tick_raw),
        (f"{symbol}.copy_rates_recent", rates_raw),
        (f"{symbol}.copy_ticks", ticks_raw),
        (f"{symbol}.copy_rates_context", history_rates_raw),
    ):
        if selected and (history_bars or operation != f"{symbol}.copy_rates_context"):
            record_empty(errors, operation, value)

    try:
        rate_rows = [normalize_rate(row, server_offset_seconds) for row in row_dicts(rates_raw)]
        history_rate_rows = [
            normalize_rate(row, server_offset_seconds) for row in row_dicts(history_rates_raw)
        ]
        tick_rows = [normalize_tick(row, server_offset_seconds) for row in row_dicts(ticks_raw)]
        tick_value = plain(tick_raw)
        current_tick = (
            normalize_tick(tick_value, server_offset_seconds)
            if isinstance(tick_value, dict)
            else None
        )
        info = plain(info_raw) if info_raw is not None else None
    except Exception as exc:
        errors.append(
            {
                "operation": f"{symbol}.normalize",
                "message": str(exc),
                "type": type(exc).__name__,
                "transport": False,
            }
        )
        rate_rows = []
        history_rate_rows = []
        tick_rows = []
        current_tick = None
        info = None

    observed_at_epoch = int(time.time())
    return {
        "symbol": symbol,
        "selected": selected,
        "select_error": errors[0] if errors and not selected else None,
        "info": info,
        "tick": current_tick,
        "rates_m5": rate_rows,
        "history_rates_m5": history_rate_rows,
        "ticks": tick_rows,
        "errors": errors,
        "diagnostics": diagnostics,
        "observed_at_epoch": observed_at_epoch,
        "observed_at_utc": epoch_utc(observed_at_epoch, 0),
        "market_as_of_epoch": query_epoch,
        "server_offset_seconds": server_offset_seconds,
    }


def observe_account(mt5: MetaTrader5, server_offset_seconds: int) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    account_raw = timed_call(diagnostics, errors, "account_info", mt5.account_info)
    terminal_raw = timed_call(diagnostics, errors, "terminal_info", mt5.terminal_info)
    return {
        **observation_clock(server_offset_seconds),
        "account": plain(account_raw) if account_raw is not None else None,
        "terminal": plain(terminal_raw) if terminal_raw is not None else None,
        "errors": errors,
        "diagnostics": diagnostics,
    }


def observe_symbols(
    mt5: MetaTrader5, server_offset_seconds: int, group: str | None
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total = timed_call(diagnostics, errors, "symbols_total", mt5.symbols_total)
    fetch = (lambda: mt5.symbols_get(group)) if group else mt5.symbols_get
    rows, rows_error = safe_rows(diagnostics, errors, "symbols_get", fetch)
    return {
        **observation_clock(server_offset_seconds),
        "symbols_total": plain(total),
        "symbols": rows,
        "symbols_error": rows_error,
        "errors": errors,
        "diagnostics": diagnostics,
    }


def observe_open(mt5: MetaTrader5, server_offset_seconds: int) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    positions, positions_error = safe_rows(
        diagnostics, errors, "positions_get", mt5.positions_get
    )
    orders, orders_error = safe_rows(diagnostics, errors, "orders_get", mt5.orders_get)
    return {
        **observation_clock(server_offset_seconds),
        "positions": positions,
        "positions_error": positions_error,
        "orders": orders,
        "orders_error": orders_error,
        "errors": errors,
        "diagnostics": diagnostics,
    }


def annotate_history(rows: list[dict[str, Any]], offset: int) -> None:
    for row in rows:
        if "time" in row:
            row["time_raw"] = raw_time(row)
            row["time_utc"] = epoch_utc(row["time_raw"], offset)
        if "time_setup" in row:
            try:
                raw = int(row["time_setup"])
                row["time_setup_raw"] = raw
                row["time_setup_utc"] = epoch_utc(raw, offset)
            except (TypeError, ValueError):
                pass
        if "time_done" in row:
            try:
                raw = int(row["time_done"])
                row["time_done_raw"] = raw
                row["time_done_utc"] = epoch_utc(raw, offset)
            except (TypeError, ValueError):
                pass


def observe_history(
    mt5: MetaTrader5,
    history_days: int,
    server_offset_seconds: int,
) -> dict[str, Any]:
    query_epoch = int(time.time())
    now_server_epoch = query_epoch + server_offset_seconds
    history_from = now_server_epoch - history_days * 86_400
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    history_orders, history_orders_error = safe_rows(
        diagnostics,
        errors,
        "history_orders_get",
        lambda: mt5.history_orders_get(history_from, now_server_epoch),
    )
    history_deals, history_deals_error = safe_rows(
        diagnostics,
        errors,
        "history_deals_get",
        lambda: mt5.history_deals_get(history_from, now_server_epoch),
    )
    annotate_history(history_orders, server_offset_seconds)
    annotate_history(history_deals, server_offset_seconds)
    return {
        **observation_clock(server_offset_seconds),
        "history_orders": history_orders,
        "history_orders_error": history_orders_error,
        "history_deals": history_deals,
        "history_deals_error": history_deals_error,
        "errors": errors,
        "diagnostics": diagnostics,
    }


def request_params(request: dict[str, Any]) -> tuple[int, int, int, int]:
    bars = max(1, min(int(request.get("bars", 300)), 10_000))
    history_bars = max(0, min(int(request.get("history_bars", bars)), 10_000))
    tick_seconds = max(60, min(int(request.get("tick_seconds", 3600)), 86_400))
    history_days = max(1, min(int(request.get("history_days", 7)), 365))
    return bars, history_bars, tick_seconds, history_days


def observe_batch(
    mt5: MetaTrader5,
    request: dict[str, Any],
    server_offset_seconds: int,
) -> dict[str, Any]:
    requested_symbols = [str(symbol) for symbol in (request.get("symbols") or ["EURUSD"])]
    bars, history_bars, tick_seconds, history_days = request_params(request)
    include_history = bool(request.get("include_history", True))
    query_started_at_epoch = int(time.time())

    account = observe_account(mt5, server_offset_seconds)
    symbol_rows: list[dict[str, Any]] = []
    collection_errors = list(account["errors"])
    diagnostics = list(account["diagnostics"])
    for symbol in requested_symbols:
        snapshot = observe_symbol(
            mt5,
            symbol,
            bars,
            history_bars,
            tick_seconds,
            int(time.time()),
            server_offset_seconds,
        )
        symbol_rows.append(snapshot)
        collection_errors.extend(snapshot["errors"])
        diagnostics.extend(snapshot["diagnostics"])

    open_state = observe_open(mt5, server_offset_seconds)
    collection_errors.extend(open_state["errors"])
    diagnostics.extend(open_state["diagnostics"])
    if include_history:
        history_state = observe_history(mt5, history_days, server_offset_seconds)
        collection_errors.extend(history_state["errors"])
        diagnostics.extend(history_state["diagnostics"])
    else:
        history_state = {
            "history_orders": [],
            "history_orders_error": None,
            "history_deals": [],
            "history_deals_error": None,
            "errors": [],
            "diagnostics": [],
        }

    received = {row["symbol"] for row in symbol_rows}
    missing_symbols = [symbol for symbol in requested_symbols if symbol not in received]
    observed_at_epoch = int(time.time())
    return {
        "observed_at_utc": epoch_utc(observed_at_epoch, 0),
        "observed_at_epoch": observed_at_epoch,
        "query_started_at_epoch": query_started_at_epoch,
        "server_offset_seconds": server_offset_seconds,
        "requested_symbols": requested_symbols,
        "missing_symbols": missing_symbols,
        "incomplete_symbols": [row["symbol"] for row in symbol_rows if row["errors"]],
        "collection_complete": not missing_symbols and not collection_errors,
        "symbols_complete": not missing_symbols
        and not any(row["errors"] for row in symbol_rows),
        "global_complete": not open_state["errors"] and not history_state["errors"],
        "collection_errors": collection_errors,
        "call_diagnostics": diagnostics,
        "account": account["account"],
        "terminal": account["terminal"],
        "symbols": symbol_rows,
        "positions": open_state["positions"],
        "positions_error": open_state["positions_error"],
        "orders": open_state["orders"],
        "orders_error": open_state["orders_error"],
        "history_orders": history_state["history_orders"],
        "history_orders_error": history_state["history_orders_error"],
        "history_deals": history_state["history_deals"],
        "history_deals_error": history_state["history_deals_error"],
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
                op = request.get("op")
                if op == "observe":
                    result = observe_batch(mt5, request, args.server_offset_seconds)
                elif op == "observe_account":
                    result = observe_account(mt5, args.server_offset_seconds)
                elif op == "observe_symbol":
                    symbols = request.get("symbols") or [request.get("symbol")]
                    symbol = str(symbols[0]) if symbols[0] else ""
                    if not symbol:
                        raise ValueError("observe_symbol requires a symbol")
                    bars, history_bars, tick_seconds, _ = request_params(request)
                    result = observe_symbol(
                        mt5,
                        symbol,
                        bars,
                        history_bars,
                        tick_seconds,
                        int(time.time()),
                        args.server_offset_seconds,
                    )
                elif op == "observe_open":
                    result = observe_open(mt5, args.server_offset_seconds)
                elif op == "observe_history":
                    _, _, _, history_days = request_params(request)
                    result = observe_history(mt5, history_days, args.server_offset_seconds)
                elif op == "list_symbols":
                    group = request.get("group")
                    result = observe_symbols(
                        mt5, args.server_offset_seconds, str(group) if group else None
                    )
                else:
                    raise ValueError(
                        "only read-only observe, observe_account, observe_symbol, "
                        "observe_open, observe_history, and list_symbols operations "
                        "are supported"
                    )
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
