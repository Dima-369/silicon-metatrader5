#!/usr/bin/env python3
"""Explicitly opt-in, demo-only MT5 order gateway.

This is separate from ``mt5_gateway.py`` on purpose. The normal observer remains
read-only. Rust must start this process with ``--allow-demo-orders`` and the exact
FundingPips demo login/server; this process still accepts only the five narrow
operations below:

* ``demo_place_order``: pending bracket order after ``order_check`` succeeds;
* ``demo_flatten``: remove/close only orders and positions carrying our magic AND
  comment prefix;
* ``demo_partial_close``: close part of an owned open position (the rest stays
  open) -- same ownership check as ``demo_flatten``, but by explicit ticket and
  strictly less than the full position volume (use ``demo_close_position`` or
  ``demo_flatten`` for a full close);
* ``demo_close_position``: fully close ONE owned open position by ticket, for
  exactly its current volume -- same ownership check, scoped to a single ticket.
  Added 2026-08-03 to fix a real bug: `trader.rs`'s `check_striking_system`
  emergency close used to call `demo_partial_close` with a position's full
  remaining volume, which this gateway's own full-volume guard always rejected
  -- a live strike breach never actually closed the position;
* ``demo_modify_position``: move an owned open position's SL/TP (breakeven arm,
  runner trail, or the partial-bank's stop+target update) -- same ownership
  check, ticket-scoped.

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
TRADE_ACTION_SLTP = 6
TRADE_ACTION_REMOVE = 8
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
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
    if account.get("trade_allowed") is not True:
        raise RuntimeError("MT5 account does not explicitly allow trading")
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


def invoke_trade_call(mt5: MetaTrader5, method: str, request: dict[str, Any]) -> Any:
    # siliconmetatrader5 1.2.3 exposes order_check(*args, **kwargs), but the
    # MT5 terminal accepts the MqlTradeRequest only as a positional argument.
    # Keyword form returns an invalid empty request on this bridge. Keep the
    # private-connection escape hatch inside this guarded gateway only; no
    # generic operation is exposed to callers.
    connection = getattr(mt5, "_MetaTrader5__conn", None)
    if connection is None:
        raise RuntimeError("MT5 bridge does not expose its trade connection")
    if method not in {"order_check", "order_send"}:
        raise RuntimeError(f"unsupported guarded trade method: {method}")
    return connection.eval(f"mt5.{method}({request!r})")


def invoke_order_check(mt5: MetaTrader5, request: dict[str, Any]) -> Any:
    return invoke_trade_call(mt5, "order_check", request)


def invoke_order_send(mt5: MetaTrader5, request: dict[str, Any]) -> Any:
    return invoke_trade_call(mt5, "order_send", request)


def executable_filling_modes(mt5: MetaTrader5, symbol: str) -> list[int]:
    info = plain(mt5.symbol_info(symbol)) or {}
    mask = info.get("filling_mode")
    if isinstance(mask, int):
        modes = [mode for mode in (ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN) if mask & (1 << mode)]
        if modes:
            return modes
    # FundingPips FX currently accepts FOK/IOC for market closes. Pending
    # brackets still use RETURN as required by MT5 for pending orders.
    return [ORDER_FILLING_FOK, ORDER_FILLING_IOC]


def check_and_send(
    mt5: MetaTrader5,
    request: dict[str, Any],
    args: argparse.Namespace,
    require_margin: bool,
) -> dict[str, Any]:
    checked = plain(invoke_order_check(mt5, request))
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
    sent = plain(invoke_order_send(mt5, request))
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
        # Rust request epochs are UTC; MT5 trade requests expect the broker's
        # server epoch (currently UTC+3 on FundingPips-Trial).
        "expiration": expiration + args.server_offset_seconds
        if int(request.get("type_time", ORDER_TIME_SPECIFIED)) != ORDER_TIME_GTC
        else 0,
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


def find_owned_position(
    mt5: MetaTrader5, ticket: int, symbol: str, magic: int, prefix: str
) -> dict[str, Any]:
    """Looks up an open position by ticket and refuses anything we don't own --
    shared by ``demo_partial_close``/``demo_modify_position`` so neither can ever
    act on a position outside our own magic+comment-prefix, regardless of what
    ticket a caller (or a bug) passes in."""
    position = next(
        (p for p in row_dicts(mt5.positions_get()) if p.get("ticket") == ticket),
        None,
    )
    if position is None:
        raise RuntimeError(f"no open position for ticket {ticket}")
    if not ours(position, magic, prefix):
        raise RuntimeError(f"refusing to act on a position we don't own: ticket {ticket}")
    if position.get("symbol") != symbol:
        raise RuntimeError("symbol does not match the open position")
    return position


def close_volume(
    mt5: MetaTrader5,
    position: dict[str, Any],
    volume: float,
    args: argparse.Namespace,
    magic: int,
    comment: str,
) -> dict[str, Any]:
    """Sends a TRADE_ACTION_DEAL market close for exactly ``volume`` lots of an
    already-owned ``position`` (full close from ``flatten``, or a smaller partial
    from ``demo_partial_close``) -- the filling-mode retry loop is the same either
    way, so this is the one place that logic lives."""
    symbol = position.get("symbol")
    ticket = position.get("ticket")
    if not isinstance(symbol, str) or not isinstance(ticket, int):
        return {"sent": False, "error": "position missing symbol/ticket"}
    tick = plain(mt5.symbol_info_tick(symbol)) or {}
    bid = tick.get("bid")
    ask = tick.get("ask")
    position_type = position.get("type")
    price = bid if position_type == ORDER_TYPE_BUY else ask
    close_type = ORDER_TYPE_SELL if position_type == ORDER_TYPE_BUY else ORDER_TYPE_BUY
    if not isinstance(price, (int, float)) or float(price) <= 0:
        return {"sent": False, "error": "no executable tick"}
    close_base = {
        "action": TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": close_type,
        "position": ticket,
        "price": float(price),
        "deviation": 5,
        "magic": magic,
        "comment": comment,
        "type_time": ORDER_TIME_GTC,
    }
    close_result = None
    for filling in executable_filling_modes(mt5, symbol):
        close = {**close_base, "type_filling": filling}
        close_result = check_and_send(mt5, close, args, False)
        check = close_result.get("check") or {}
        if check.get("retcode") != 10030:
            break
    return close_result or {"sent": False, "error": "no filling mode"}


def demo_partial_close(mt5: MetaTrader5, request: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    require_confirmation(request)
    require_demo_account(mt5, args)
    ticket = request.get("ticket")
    if not isinstance(ticket, int) or ticket <= 0:
        raise RuntimeError("positive ticket is required")
    symbol = request.get("symbol")
    if not isinstance(symbol, str) or symbol not in args.allowed_symbols:
        raise RuntimeError(f"symbol is not allowlisted: {symbol!r}")
    volume = require_number(request, "volume", positive=True)
    magic = args.expected_magic
    prefix = args.comment_prefix
    position = find_owned_position(mt5, ticket, symbol, magic, prefix)
    position_volume = position.get("volume")
    if not isinstance(position_volume, (int, float)):
        raise RuntimeError("position volume is unavailable")
    if volume >= float(position_volume):
        raise RuntimeError(
            "partial-close volume must be less than the full position volume; "
            "use demo_flatten for a full close"
        )
    result = close_volume(mt5, position, volume, args, magic, f"{prefix}-partial")
    return {"operation": "demo_partial_close", "ticket": ticket, **result}


def demo_close_position(mt5: MetaTrader5, request: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Fully closes an already-owned open position by ticket, for exactly its
    current full volume -- the caller never supplies a volume. Added 2026-08-03:
    `demo_partial_close` deliberately REJECTS a full-volume close ("use
    demo_flatten for a full close"), but `demo_flatten` closes EVERY owned
    order/position, not just one -- unusable for a single-position emergency
    close (the Rust side's striking-system check) or a single leg's own
    force-close deadline when other unrelated positions are still legitimately
    open. `trader.rs`'s `check_striking_system` used to call `demo_partial_close`
    with a position's full remaining volume, which this gateway's own guard
    always rejected -- a live strike breach never actually closed the position.
    This op is the fix; see `Mt5DemoGateway::close_position`'s doc comment in
    the main repo's `crates/tradebot-broker/src/mt5.rs`."""
    require_confirmation(request)
    require_demo_account(mt5, args)
    ticket = request.get("ticket")
    if not isinstance(ticket, int) or ticket <= 0:
        raise RuntimeError("positive ticket is required")
    symbol = request.get("symbol")
    if not isinstance(symbol, str) or symbol not in args.allowed_symbols:
        raise RuntimeError(f"symbol is not allowlisted: {symbol!r}")
    magic = args.expected_magic
    prefix = args.comment_prefix
    position = find_owned_position(mt5, ticket, symbol, magic, prefix)
    position_volume = position.get("volume")
    if not isinstance(position_volume, (int, float)) or float(position_volume) <= 0:
        raise RuntimeError("position volume is unavailable")
    result = close_volume(mt5, position, float(position_volume), args, magic, f"{prefix}-close")
    return {"operation": "demo_close_position", "ticket": ticket, **result}


def demo_modify_position(mt5: MetaTrader5, request: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    require_confirmation(request)
    require_demo_account(mt5, args)
    ticket = request.get("ticket")
    if not isinstance(ticket, int) or ticket <= 0:
        raise RuntimeError("positive ticket is required")
    symbol = request.get("symbol")
    if not isinstance(symbol, str) or symbol not in args.allowed_symbols:
        raise RuntimeError(f"symbol is not allowlisted: {symbol!r}")
    sl = require_number(request, "sl", positive=True)
    tp = require_number(request, "tp", positive=True)
    magic = args.expected_magic
    prefix = args.comment_prefix
    position = find_owned_position(mt5, ticket, symbol, magic, prefix)
    position_type = position.get("type")
    # Same bracket-direction sanity check `place_order` applies to a fresh
    # order: a modify that would put the stop on the wrong side of price (or
    # invert sl/tp) is almost certainly a caller bug, not something MT5 should
    # be asked to accept. Skipped only if the current tick is unavailable --
    # `order_check` still gets the final say either way.
    tick = plain(mt5.symbol_info_tick(symbol)) or {}
    current = tick.get("bid") if position_type == ORDER_TYPE_BUY else tick.get("ask")
    if isinstance(current, (int, float)):
        # <=/>= (not strict <): a legitimate breakeven-arm or trail update can
        # land exactly on the current tick during a fast market, and rejecting
        # that here would just force an identical retry next cycle anyway --
        # `order_check` still gets the final say on anything genuinely invalid.
        if position_type == ORDER_TYPE_BUY and not sl <= float(current) <= tp:
            raise RuntimeError("buy position modify must satisfy sl <= current_price <= tp")
        if position_type == ORDER_TYPE_SELL and not tp <= float(current) <= sl:
            raise RuntimeError("sell position modify must satisfy tp <= current_price <= sl")
    normalized = {
        "action": TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": ticket,
        "sl": sl,
        "tp": tp,
        "magic": magic,
    }
    return {
        "operation": "demo_modify_position",
        "ticket": ticket,
        **check_and_send(mt5, normalized, args, False),
    }


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
        ticket = position.get("ticket")
        volume = position.get("volume")
        if not isinstance(ticket, int) or not isinstance(volume, (int, float)):
            continue
        result = close_volume(mt5, position, float(volume), args, magic, f"{prefix}-flatten")
        actions.append({"kind": "close", "ticket": ticket, **result})
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
    parser.add_argument("--server-offset-seconds", type=int, default=10_800)
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
                elif operation == "demo_partial_close":
                    result = demo_partial_close(mt5, request, args)
                elif operation == "demo_close_position":
                    result = demo_close_position(mt5, request, args)
                elif operation == "demo_modify_position":
                    result = demo_modify_position(mt5, request, args)
                else:
                    raise ValueError(
                        "only demo_place_order, demo_flatten, demo_partial_close, "
                        "demo_close_position, and demo_modify_position are supported"
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
