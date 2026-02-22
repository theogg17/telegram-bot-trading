import argparse
import csv
import datetime
import os
import sys
import time
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # type: ignore

import pandas as pd
import MetaTrader5 as mt5

from config_operador import (
    OPEN_TRADES_CSV,
    OPERACIONES_ABIERTAS_CSV,
    ERRORES_APERTURAS_CSV,
    VERIFY_POLL_SECONDS,
    AUTO_CLOSE_ON_MISMATCH,
)
from daemon import mt5_init
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
from common.csv_guard import atomic_write_dataframe_csv, csv_file_lock

URUGUAY_TZ = ZoneInfo('America/Montevideo') if ZoneInfo is not None else datetime.timezone(datetime.timedelta(hours=-3))

OPERACIONES_FIELDS = [
    "kind","ticket","symbol","side","volume","price","sl","tp","comment","time"
]
ERROR_FIELDS = ["timestamp","event_id","action","symbol","side","volume","comment","reason","retcode","details"]

def _ensure_csv(path: str, fieldnames: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with csv_file_lock(path):
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()

def _append_row(path: str, row: dict, fieldnames: list):
    with csv_file_lock(path):
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writerow(row)

def _snapshot_operations():
    rows = []
    positions = mt5.positions_get() or []
    for p in positions:
        rows.append({
            "kind": "POSITION",
            "ticket": p.ticket,
            "symbol": p.symbol,
            "side": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
            "volume": p.volume,
            "price": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "comment": p.comment,
            "time": datetime.datetime.fromtimestamp(p.time, URUGUAY_TZ).isoformat(timespec="seconds"),
        })
    orders = mt5.orders_get() or []
    for o in orders:
        side = "BUY" if o.type in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP) else "SELL"
        rows.append({
            "kind": "PENDING",
            "ticket": o.ticket,
            "symbol": o.symbol,
            "side": side,
            "volume": o.volume_current,
            "price": o.price_open,
            "sl": o.sl,
            "tp": o.tp,
            "comment": o.comment,
            "time": datetime.datetime.fromtimestamp(o.time_setup, URUGUAY_TZ).isoformat(timespec="seconds"),
        })
    df = pd.DataFrame(rows, columns=OPERACIONES_FIELDS)
    with csv_file_lock(OPERACIONES_ABIERTAS_CSV):
        atomic_write_dataframe_csv(df, OPERACIONES_ABIERTAS_CSV, index=False, encoding="utf-8")
    return positions, orders

def _log_error(action, symbol, side, volume, comment, reason, details=""):
    _append_row(
        ERRORES_APERTURAS_CSV,
        {
            "timestamp": datetime.datetime.now(URUGUAY_TZ).isoformat(timespec="seconds"),
            "event_id": "",
            "action": action,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "comment": comment,
            "reason": reason,
            "retcode": "",
            "details": details,
        },
        ERROR_FIELDS,
    )

def _close_position(position):
    side = "SELL" if position.type == mt5.POSITION_TYPE_BUY else "BUY"
    tick = mt5.symbol_info_tick(position.symbol)
    if not tick:
        return False, "no tick"
    price = tick.ask if side == "BUY" else tick.bid
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": mt5.ORDER_TYPE_SELL if side=="SELL" else mt5.ORDER_TYPE_BUY,
        "position": position.ticket,
        "price": price,
        "deviation": 20,
        "comment": f"{position.comment}|VERIFY_CLOSE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    result = mt5.order_send(req)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return True, "closed"
    return False, getattr(result, "comment", "close_failed")

def _cancel_order(order):
    result = mt5.order_delete(order.ticket)
    if isinstance(result, bool):
        return (result, "deleted" if result else str(mt5.last_error()))
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return True, "deleted"
    return False, getattr(result, "comment", "delete_failed")

def verify_open_trades():
    if not os.path.exists(OPEN_TRADES_CSV):
        return
    try:
        df = pd.read_csv(OPEN_TRADES_CSV)
    except Exception:
        df = pd.read_csv(OPEN_TRADES_CSV, on_bad_lines="skip", engine="python")
    if df.empty:
        return

    positions, orders = _snapshot_operations()
    pos_map = {p.ticket: p for p in positions}
    ord_map = {o.ticket: o for o in orders}

    for _, r in df.iterrows():
        ticket = r.get("ticket")
        if pd.isna(ticket) or str(ticket).strip() == "":
            continue
        try:
            ticket = int(ticket)
        except Exception:
            continue

        symbol = str(r.get("symbol", "")).upper()
        comment = str(r.get("comment", ""))
        volume = r.get("volume", "")
        side = str(r.get("side", ""))

        if ticket in pos_map:
            p = pos_map[ticket]
            if symbol and p.symbol != symbol:
                _log_error("VERIFY", symbol, side, volume, comment, "symbol_mismatch", f"mt5={p.symbol}")
                if AUTO_CLOSE_ON_MISMATCH:
                    ok, info = _close_position(p)
                    if not ok:
                        _log_error("VERIFY_CLOSE", symbol, side, volume, comment, "close_failed", info)
            continue
        if ticket in ord_map:
            o = ord_map[ticket]
            if symbol and o.symbol != symbol:
                _log_error("VERIFY", symbol, side, volume, comment, "symbol_mismatch", f"mt5={o.symbol}")
                if AUTO_CLOSE_ON_MISMATCH:
                    ok, info = _cancel_order(o)
                    if not ok:
                        _log_error("VERIFY_CANCEL", symbol, side, volume, comment, "cancel_failed", info)
            continue

        _log_error("VERIFY", symbol, side, volume, comment, "ticket_not_found", "")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Ejecuta una sola verificacion y termina.")
    args = parser.parse_args()

    mt5_init()
    _ensure_csv(ERRORES_APERTURAS_CSV, ERROR_FIELDS)
    _ensure_csv(OPERACIONES_ABIERTAS_CSV, OPERACIONES_FIELDS)

    if args.once:
        verify_open_trades()
        return

    while True:
        verify_open_trades()
        time.sleep(VERIFY_POLL_SECONDS)

if __name__ == "__main__":
    main()


