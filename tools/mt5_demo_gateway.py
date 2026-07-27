#!/usr/bin/env python3
"""Explicitly opt-in, demo-only MT5 order gateway.

This is separate from ``mt5_gateway.py`` on purpose. The normal observer remains
read-only. Rust must start this process with ``--allow-demo-orders`` and the exact
FundingPips demo login/server; this process still accepts only the two narrow
operations below:

* ``demo_place_order``: pending bracket order after ``order_check`` succeeds;
* ``demo_flatten``: remove/close only orders and positions carrying our magic AND
  comment prefix.

No generic ``order_send`` operation is exposed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from typing import Any

from siliconmetatrader5 import MetaTrader5

CONFIRMATION = "FUNDINGPIPS-DEMO-ONLY"
TRADE_ACTION_DEAL = 1
TRADE_ACTION_PENDING = 5
TRADE_ACTION_REMOVE = 8
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_FILLING_RETURN = 2
ORDER_TIME_GTC = 0
ORDER_TIME_SPECIFIED = 2
ACCOUNT_TRADE_MODE_DEMO = 0
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_PLACED = 10008
TRADE_RETCODE_DONE_PARTIAL = 10010
ORDER_TYPES_PENDING = {2, 3, 4, 5}  # buy/sell limit + buy/sell stop


def log(message: str) -> None:
    print(f"mt5-demo-gateway: {message}", file=sys.stderr, flush=True)


def plain(value: Any) -> Any:
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
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return repr(value)


def last_error(mt5: MetaTrader5) -> Any:
    try:
        return plain(mt5.last_error())
    except Exception as exc:  # pragma: no cover - bridge failure path
        return {"type": type(exc).__name__, "message": str(exc)}


def row_dicts(rows: Any) -> list[dict[str, Any]]:
    value = plain(rows)
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return [row for row in value if isinstance(row, dict)]


def require_demo_account(mt5: MetaTrader5, args: argparse.Namespace) -> dict[str, Any]:
    account = plain(mt5.account_info()) or {}
    terminal = plain(mt5.terminal_info()) or {}
    if account.get("login") != args.expected_login:
        raise RuntimeError(
            f"demo gateway login mismatch: {account.get('login')} != {args.expected_login}"
        )
    if account.get("server") != args.expected_server:
        raise RuntimeError(
            f"demo gateway server mismatch: {account.get('server')!r} != {args.expected_server!r}"
        )
    if account.get("trade_mode") != ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError(f"refusing non-demo trade_mode={account.get('trade_mode')}")
    if terminal.get("connected") is not True:
        raise RuntimeError("MT5 terminal is not connected")
    if terminal.get("trade_allowed") is not True:
        raise RuntimeError("MT5 terminal does not allow trading")
    if account.get("trade_allowed") is False:
        raise RuntimeError("MT5 account does not allow trading")
    return account


def require_confirmation(request: dict[str, Any]) -> None:
    if request.get("confirmation") != CONFIRMATION:
        raise RuntimeError("missing or invalid demo confirmation")


def require_number(request: dict[str, Any], key: str, positive: bool = False) -> float:
    value = request.get(key)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise RuntimeError(f"invalid numeric request field {key}")
    value = float(value)
    if positive and value <= 0:
        raise RuntimeError(f"request field {key} must be positive")
    return value


def check_and_send(
    mt5: MetaTrader5,
    request: dict[str, Any],
    args: argparse.Namespace,
    require_margin: bool,
) -> dict[str, Any]:
    checked = plain(mt5.order_check(request))
    if not isinstance(checked, dict):
        raise RuntimeError("order_check returned no structured result")
    check_code = checked.get("retcode")
    # MT5 order_check normally returns retcode=0 on success. Accept DONE too for
    # bridge/broker variants that normalize a successful check differently.
    if check_code not in (0, TRADE_RETCODE_DONE):
        return {"check": checked, "send": None, "sent": False}
    margin = checked.get("margin")
    if require_margin:
        if not isinstance(margin, (int, float)) or not math.isfinite(float(margin)):
            return {
                "check": checked,
                "send": None,
                "sent": False,
                "error": "order_check omitted margin",
            }
        if float(margin) > args.max_margin:
            return {
                "check": checked,
                "send": None,
                "sent": False,
                "error": "margin cap exceeded",
            }
    sent = plain(mt5.order_send(request))
    if not isinstance(sent, dict):
        return {
            "check": checked,
            "send": sent,
            "sent": False,
            "error": "order_send returned no structured result",
        }
    retcode = sent.get("retcode")
    accepted = retcode in (
        TRADE_RETCODE_DONE,
        TRADE_RETCODE_PLACED,
        TRADE_RETCODE_DONE_PARTIAL,
    )
    return {
        "check": checked,
        "send": sent,
        "sent": accepted,
        **({} if accepted else {"error": f"order_send retcode={retcode}"}),
    }


def place_order(mt5: MetaTrader5, request: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    require_confirmation(request)
    require_demo_account(mt5, args)
    symbol = request.get("symbol")
    if not isinstance(symbol, str) or symbol not in args.allowed_symbols:
        raise RuntimeError(f"symbol is not allowlisted: {symbol!r}")
    order_type = request.get("type")
    if order_type not in ORDER_TYPES_PENDING:
        raise RuntimeError("only pending bracket orders are allowed")
    client_key = request.get("client_key")
    if not isinstance(client_key, str) or not client_key:
        raise RuntimeError("client_key is required")
    volume = require_number(request, "volume", positive=True)
    if volume > args.max_volume:
        raise RuntimeError(f"volume {volume} exceeds max {args.max_volume}")
    price = require_number(request, "price", positive=True)
    sl = require_number(request, "sl", positive=True)
    tp = require_number(request, "tp", positive=True)
    if order_type in (2, 4) and not sl < price < tp:
        raise RuntimeError("buy bracket must satisfy sl < price < tp")
    if order_type in (3, 5) and not tp < price < sl:
        raise RuntimeError("sell bracket must satisfy tp < price < sl")
    magic = request.get("magic")
    comment = request.get("comment")
    if magic != args.expected_magic:
        raise RuntimeError("magic does not match the demo allowlist")
    if not isinstance(comment, str) or not comment.startswith(args.comment_prefix):
        raise RuntimeError("comment does not use the allowed prefix")
    expiration = request.get("expiration")
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    if (
        not isinstance(expiration, int)
        or expiration <= now
        or expiration > now + args.max_order_age_seconds
    ):
        raise RuntimeError("expiration is outside the allowed order-age window")
    # Protect the order_send-success/process-crash gap: the same exact magic and
    # comment already present on the account is treated as an idempotent duplicate.
    for existing in row_dicts(mt5.orders_get()) + row_dicts(mt5.positions_get()):
        if existing.get("magic") == magic and existing.get("comment") == comment:
            return {
                "operation": "demo_place_order",
                "client_key": client_key,
                "duplicate": True,
                "sent": False,
                "existing": existing,
            }
    normalized = {
        "action": TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": int(order_type),
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": int(request.get("deviation", 0)),
        "magic": magic,
        "comment": comment,
        "type_time": int(request.get("type_time", ORDER_TIME_SPECIFIED)),
        "expiration": expiration,
        # Pending orders use RETURN filling. The broker's symbol filling mask is
        # checked by order_check; Rust never skips that preflight.
        "type_filling": ORDER_FILLING_RETURN,
    }
    return {
        "operation": "demo_place_order",
        "client_key": client_key,
        **check_and_send(mt5, normalized, args, True),
    }


def ours(row: dict[str, Any], magic: int, prefix: str) -> bool:
    return row.get("magic") == magic and str(row.get("comment", "")).startswith(prefix)


def flatten(mt5: MetaTrader5, request: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    require_confirmation(request)
    require_demo_account(mt5, args)
    magic = request.get("magic")
    prefix = request.get("comment_prefix")
    if not isinstance(magic, int) or magic <= 0:
        raise RuntimeError("positive magic is required")
    if not isinstance(prefix, str) or not prefix.startswith(args.comment_prefix):
        raise RuntimeError("invalid flatten comment prefix")

    actions: list[dict[str, Any]] = []
    for order in row_dicts(mt5.orders_get()):
        if not ours(order, magic, prefix) or order.get("symbol") not in args.allowed_symbols:
            continue
        ticket = order.get("ticket")
        if not isinstance(ticket, int):
            continue
        remove = {
            "action": TRADE_ACTION_REMOVE,
            "order": ticket,
            "symbol": order.get("symbol", ""),
            "magic": magic,
            "comment": f"{prefix}-flatten",
            "type_time": ORDER_TIME_GTC,
            "type_filling": ORDER_FILLING_RETURN,
        }
        actions.append({"kind": "cancel", "ticket": ticket, **check_and_send(mt5, remove, args, False)})

    for position in row_dicts(mt5.positions_get()):
        if not ours(position, magic, prefix) or position.get("symbol") not in args.allowed_symbols:
            continue
        symbol = position.get("symbol")
        ticket = position.get("ticket")
        volume = position.get("volume")
        if not isinstance(symbol, str) or not isinstance(ticket, int) or not isinstance(volume, (int, float)):
            continue
        tick = plain(mt5.symbol_info_tick(symbol)) or {}
        bid = tick.get("bid")
        ask = tick.get("ask")
        position_type = position.get("type")
        price = bid if position_type == ORDER_TYPE_BUY else ask
        close_type = ORDER_TYPE_SELL if position_type == ORDER_TYPE_BUY else ORDER_TYPE_BUY
        if not isinstance(price, (int, float)) or float(price) <= 0:
            actions.append({"kind": "close", "ticket": ticket, "sent": False, "error": "no executable tick"})
            continue
        close = {
            "action": TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": close_type,
            "position": ticket,
            "price": float(price),
            "deviation": 5,
            "magic": magic,
            "comment": f"{prefix}-flatten",
            "type_time": ORDER_TIME_GTC,
            "type_filling": ORDER_FILLING_RETURN,
        }
        actions.append({"kind": "close", "ticket": ticket, **check_and_send(mt5, close, args, False)})
    return {"operation": "demo_flatten", "actions": actions}


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
    parser.add_argument("--expected-login", type=int, required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--comment-prefix", default="tb-demo")
    parser.add_argument("--expected-magic", type=int, required=True)
    parser.add_argument("--allowed-symbol", action="append", dest="allowed_symbols", required=True)
    parser.add_argument("--max-volume", type=float, default=0.01)
    parser.add_argument("--max-margin", type=float, default=100.0)
    parser.add_argument("--max-order-age-seconds", type=int, default=3600)
    parser.add_argument("--allow-demo-orders", action="store_true")
    args = parser.parse_args()
    if not args.allow_demo_orders:
        parser.error("--allow-demo-orders is required; use the read-only gateway otherwise")

    mt5 = MetaTrader5(host=args.host, port=args.port, keepalive=True)
    try:
        if not mt5.initialize():
            response(None, error={"operation": "initialize", "last_error": last_error(mt5)})
            return 1
        log(f"connected; DEMO-only order gateway for {args.expected_server}/{args.expected_login}")
        for line in sys.stdin:
            if not line.strip():
                continue
            request_id: Any = None
            try:
                request = json.loads(line)
                request_id = request.get("id")
                operation = request.get("op")
                if operation == "demo_place_order":
                    result = place_order(mt5, request.get("order") or {}, args)
                elif operation == "demo_flatten":
                    result = flatten(mt5, request, args)
                else:
                    raise ValueError("only demo_place_order and demo_flatten are supported")
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
