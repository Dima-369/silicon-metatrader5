#!/usr/bin/env python3
"""One-off swap-probe tool for the local FundingPips-Trial demo account.

Empirically resolves the swap_mode=5 interpretation contradiction logged in
rust-tradebot/FUTURE_IDEAS.md: does swap_long/swap_short mean a flat
account-currency amount per 1.0 lot per night, or an annual percentage of
notional? Opens small market positions and reports MT5's own accruing
``swap`` field against both candidate formulas -- whichever formula matches
the broker's real number wins.

Deliberately separate from mt5_demo_gateway.py (which only accepts pending
bracket orders originating from the Rust bot's own signal pipeline, gated by
magic/comment/expiration checks meant for autonomous live trading). This
script sends market orders directly for a human-supervised one-off test.
Never wire this into the Rust trader's own gateway path.

Usage:
    python3 tools/swap_probe.py open   --symbols BTCUSD ETHUSD NDX100
    python3 tools/swap_probe.py report --symbols BTCUSD ETHUSD NDX100
    python3 tools/swap_probe.py close  --symbols BTCUSD ETHUSD NDX100
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
from typing import Any

from siliconmetatrader5 import MetaTrader5

DEFAULT_SERVER = "FundingPips-Trial"
DEFAULT_LOGIN = 40000197502
DEFAULT_SYMBOLS = ["BTCUSD", "ETHUSD", "NDX100"]
MAGIC = 990001
COMMENT_PREFIX = "swap-probe"
# Hard safety cap independent of any CLI input -- this is a manual research
# tool, not the production gateway's own --max-volume guard.
MAX_VOLUME = 0.05

TRADE_ACTION_DEAL = 1
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
# Distinct MT5 enum from ORDER_TYPE_* above (position.type, not order.type) --
# numerically identical (BUY=0/SELL=1 in both) but kept separate for clarity
# wherever a position's own side is being read, e.g. cmd_close below.
POSITION_TYPE_BUY = 0
POSITION_TYPE_SELL = 1
ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
ORDER_FILLING_RETURN = 2
ORDER_TIME_GTC = 0
ACCOUNT_TRADE_MODE_DEMO = 0
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_DONE_PARTIAL = 10010
TRADE_RETCODE_REQUOTE = 10004
FILLING_MODE_NOT_SUPPORTED = 10030


def log(message: str) -> None:
    print(f"swap-probe: {message}", file=sys.stderr, flush=True)


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


def row_dicts(rows: Any) -> list[dict[str, Any]]:
    value = plain(rows)
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, (list, tuple)):
        return [row for row in value if isinstance(row, dict)]
    return []


def require_demo_account(mt5: MetaTrader5, args: argparse.Namespace) -> dict[str, Any]:
    account = plain(mt5.account_info()) or {}
    terminal = plain(mt5.terminal_info()) or {}
    if account.get("login") != args.login:
        raise RuntimeError(f"login mismatch: {account.get('login')} != {args.login}")
    if account.get("server") != args.server:
        raise RuntimeError(f"server mismatch: {account.get('server')!r} != {args.server!r}")
    if account.get("trade_mode") != ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError(f"refusing non-demo trade_mode={account.get('trade_mode')}")
    if terminal.get("connected") is not True:
        raise RuntimeError("MT5 terminal is not connected")
    if terminal.get("trade_allowed") is not True:
        raise RuntimeError("MT5 terminal does not allow trading")
    if account.get("trade_allowed") is not True:
        raise RuntimeError("MT5 account does not explicitly allow trading")
    return account


def invoke_trade_call(mt5: MetaTrader5, method: str, request: dict[str, Any]) -> Any:
    # order_check/order_send only accept the MqlTradeRequest positionally on
    # this bridge (siliconmetatrader5 1.2.3's keyword form returns an empty
    # request) -- same escape hatch mt5_demo_gateway.py uses, kept narrowly
    # scoped to just these two methods.
    connection = getattr(mt5, "_MetaTrader5__conn", None)
    if connection is None:
        raise RuntimeError("MT5 bridge does not expose its trade connection")
    if method not in {"order_check", "order_send"}:
        raise RuntimeError(f"unsupported guarded trade method: {method}")
    return connection.eval(f"mt5.{method}({request!r})")


def executable_filling_modes(mt5: MetaTrader5, symbol: str) -> list[int]:
    info = plain(mt5.symbol_info(symbol)) or {}
    mask = info.get("filling_mode")
    if isinstance(mask, int):
        modes = [
            mode
            for mode in (ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN)
            if mask & (1 << mode)
        ]
        if modes:
            return modes
    return [ORDER_FILLING_FOK, ORDER_FILLING_IOC]


def check_and_send(mt5: MetaTrader5, request: dict[str, Any]) -> dict[str, Any]:
    checked = plain(invoke_trade_call(mt5, "order_check", request))
    if not isinstance(checked, dict):
        raise RuntimeError("order_check returned no structured result")
    if checked.get("retcode") not in (0, TRADE_RETCODE_DONE):
        return {"check": checked, "send": None, "sent": False}
    sent = plain(invoke_trade_call(mt5, "order_send", request))
    if not isinstance(sent, dict):
        return {
            "check": checked,
            "send": sent,
            "sent": False,
            "error": "order_send returned no structured result",
        }
    retcode = sent.get("retcode")
    accepted = retcode in (TRADE_RETCODE_DONE, TRADE_RETCODE_DONE_PARTIAL)
    return {
        "check": checked,
        "send": sent,
        "sent": accepted,
        **({} if accepted else {"error": f"order_send retcode={retcode}"}),
    }


def clamp_volume(mt5: MetaTrader5, symbol: str, requested: float) -> float:
    info = plain(mt5.symbol_info(symbol)) or {}
    vol_min = float(info.get("volume_min") or requested)
    if vol_min > MAX_VOLUME:
        raise ValueError(f"{symbol} volume_min ({vol_min}) exceeds the safety cap MAX_VOLUME ({MAX_VOLUME})")
    vol_step = float(info.get("volume_step") or vol_min) or vol_min
    if vol_step <= 0:
        raise ValueError(f"{symbol} has no usable volume_step/volume_min to size against")
    volume = max(requested, vol_min)
    steps = math.ceil(round((volume - vol_min) / vol_step, 6))
    volume = vol_min + steps * vol_step
    return round(min(volume, MAX_VOLUME), 8)


def own_positions(mt5: MetaTrader5, symbol: str) -> list[dict[str, Any]]:
    return [
        p
        for p in row_dicts(mt5.positions_get())
        if p.get("symbol") == symbol
        and p.get("magic") == MAGIC
        and str(p.get("comment", "")).startswith(COMMENT_PREFIX)
    ]


def market_order(mt5: MetaTrader5, symbol: str, volume: float, side: int) -> dict[str, Any]:
    tick = plain(mt5.symbol_info_tick(symbol)) or {}
    price = tick.get("ask") if side == ORDER_TYPE_BUY else tick.get("bid")
    if not isinstance(price, (int, float)) or price <= 0:
        return {"sent": False, "error": "no executable tick"}
    base = {
        "action": TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": side,
        "price": float(price),
        "deviation": 20,
        "magic": MAGIC,
        "comment": COMMENT_PREFIX,
        "type_time": ORDER_TIME_GTC,
    }
    result = None
    for filling in executable_filling_modes(mt5, symbol):
        result = check_and_send(mt5, {**base, "type_filling": filling})
        check = result.get("check") or {}
        if check.get("retcode") != FILLING_MODE_NOT_SUPPORTED:
            break
    return result or {"sent": False, "error": "no filling mode"}


def cmd_open(mt5: MetaTrader5, args: argparse.Namespace) -> int:
    require_demo_account(mt5, args)
    ok = True
    for symbol in args.symbols:
        existing = own_positions(mt5, symbol)
        if existing:
            log(f"{symbol}: already have a probe position (ticket {existing[0].get('ticket')}), skipping")
            continue
        volume = clamp_volume(mt5, symbol, args.volume)
        result = market_order(mt5, symbol, volume, ORDER_TYPE_BUY)
        if result.get("sent"):
            send = result.get("send") or {}
            log(f"{symbol}: opened {volume} lots @ {send.get('price')}, order={send.get('order')}")
        else:
            ok = False
            log(f"{symbol}: FAILED to open -- {result}")
    return 0 if ok else 1


def cmd_report(mt5: MetaTrader5, args: argparse.Namespace) -> int:
    require_demo_account(mt5, args)
    for symbol in args.symbols:
        info = plain(mt5.symbol_info(symbol)) or {}
        swap_long = info.get("swap_long")
        swap_mode = info.get("swap_mode")
        contract_size = info.get("trade_contract_size")
        print(f"--- {symbol} (swap_mode={swap_mode} swap_long={swap_long} trade_contract_size={contract_size}) ---")
        positions = own_positions(mt5, symbol)
        if not positions:
            print("  no open probe position")
            continue
        # MT5's `time` fields (both position.time and tick.time below) are
        # epoch seconds computed from the broker server's own clock, not
        # corrected to true UTC -- comparing position.time against
        # datetime.now(utc) would bias nights_held by the broker's UTC
        # offset. Diffing two MT5-server-clock epochs against each other
        # cancels that offset instead, regardless of what it actually is.
        tick = plain(mt5.symbol_info_tick(symbol)) or {}
        current_broker_epoch = tick.get("time")
        for position in positions:
            opened_epoch = position.get("time")
            volume = position.get("volume")
            price_current = position.get("price_current")
            actual_swap = position.get("swap")
            nights = None
            if isinstance(opened_epoch, (int, float)) and isinstance(current_broker_epoch, (int, float)):
                nights = (current_broker_epoch - opened_epoch) / 86400.0

            def flat_per_lot(nights_value: float) -> float | None:
                # Candidate A: flat account-currency amount per 1.0 lot per night.
                if isinstance(swap_long, (int, float)) and isinstance(volume, (int, float)):
                    return swap_long * volume * nights_value
                return None

            def pct_of_notional(nights_value: float, days_per_year: float) -> float | None:
                # Candidate B: SYMBOL_SWAP_MODE_INTEREST_CURRENT -- annual % of
                # current notional. MT5 brokers don't agree on a single
                # day-count convention (365 vs the 360-day money-market
                # basis), so both are reported -- don't assume one.
                if (
                    isinstance(swap_long, (int, float))
                    and isinstance(contract_size, (int, float))
                    and isinstance(price_current, (int, float))
                    and isinstance(volume, (int, float))
                ):
                    return contract_size * volume * price_current * (swap_long / 100.0) / days_per_year * nights_value
                return None

            flat_prediction = flat_per_lot(nights) if nights is not None else None
            pct_prediction_365 = pct_of_notional(nights, 365.0) if nights is not None else None
            pct_prediction_360 = pct_of_notional(nights, 360.0) if nights is not None else None
            # MT5 posts swap once at the daily rollover, not continuously --
            # a single-night baseline is what to compare against the first
            # real ACTUAL-swap step change, not the continuous nights_held
            # scaling above (which is only a fair comparison once enough
            # whole rollovers have posted that fractional timing washes out).
            flat_one_night = flat_per_lot(1.0)
            pct_one_night_365 = pct_of_notional(1.0, 365.0)
            pct_one_night_360 = pct_of_notional(1.0, 360.0)
            nights_display = f"{nights:.2f}" if nights is not None else "n/a"
            print(
                f"  ticket={position.get('ticket')} volume={volume} price_open={position.get('price_open')} "
                f"price_current={price_current} nights_held={nights_display}"
            )
            print(
                f"    ACTUAL swap={actual_swap} | predicted flat($/lot/night)={flat_prediction} "
                f"| predicted pct(365d)={pct_prediction_365} | predicted pct(360d)={pct_prediction_360}"
            )
            print(
                f"    -- single-rollover baseline (nights=1): "
                f"flat={flat_one_night} | pct(365d)={pct_one_night_365} | pct(360d)={pct_one_night_360}"
            )
    return 0


def cmd_close(mt5: MetaTrader5, args: argparse.Namespace) -> int:
    require_demo_account(mt5, args)
    ok = True
    for symbol in args.symbols:
        for position in own_positions(mt5, symbol):
            volume = position.get("volume")
            position_type = position.get("type")
            ticket = position.get("ticket")
            if not isinstance(volume, (int, float)) or not isinstance(ticket, int):
                continue
            close_side = ORDER_TYPE_SELL if position_type == POSITION_TYPE_BUY else ORDER_TYPE_BUY
            tick = plain(mt5.symbol_info_tick(symbol)) or {}
            price = tick.get("bid") if close_side == ORDER_TYPE_SELL else tick.get("ask")
            if not isinstance(price, (int, float)) or price <= 0:
                ok = False
                log(f"{symbol}: no executable tick, cannot close ticket {ticket}")
                continue
            base = {
                "action": TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(volume),
                "type": close_side,
                "position": ticket,
                "price": float(price),
                "deviation": 20,
                "magic": MAGIC,
                "comment": f"{COMMENT_PREFIX}-close",
                "type_time": ORDER_TIME_GTC,
            }
            result = None
            for filling in executable_filling_modes(mt5, symbol):
                result = check_and_send(mt5, {**base, "type_filling": filling})
                check = result.get("check") or {}
                if check.get("retcode") != FILLING_MODE_NOT_SUPPORTED:
                    break
            if result and result.get("sent"):
                send = result.get("send") or {}
                log(f"{symbol}: closed ticket {ticket} @ {send.get('price')}, final swap={position.get('swap')}")
            else:
                ok = False
                log(f"{symbol}: FAILED to close ticket {ticket} -- {result}")
    return 0 if ok else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--login", type=int, default=DEFAULT_LOGIN)
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open", help="open a small market long per symbol")
    open_parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    open_parser.add_argument("--volume", type=float, default=0.01)

    report_parser = subparsers.add_parser("report", help="print accrued swap vs both candidate formulas")
    report_parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)

    close_parser = subparsers.add_parser("close", help="market-close any open probe positions")
    close_parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mt5 = MetaTrader5(host=args.host, port=args.port, keepalive=True)
    try:
        if not mt5.initialize():
            log(f"initialize failed: {plain(mt5.last_error())}")
            return 1
        if args.command == "open":
            return cmd_open(mt5, args)
        if args.command == "report":
            return cmd_report(mt5, args)
        if args.command == "close":
            return cmd_close(mt5, args)
        raise ValueError(f"unknown command {args.command!r}")
    finally:
        try:
            mt5.close()
        except Exception as exc:  # pragma: no cover - shutdown best effort
            log(f"close failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
