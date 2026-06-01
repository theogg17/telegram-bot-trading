# telegram_reader.py

import os
import asyncio
from telethon.sync import TelegramClient, events
from message_parser_chatgpt import parse_signal_chatgpt as parse_signal
from db_writer import save_trade, save_non_signal, update_trade, read_signals, fetch_reply_context
from config import API_ID, API_HASH, CHANNELS
import pytz
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(BASE_DIR, "session_name")

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
processed_entries = {} # To store entry signals in memory
uruguay_timezone = pytz.timezone('America/Montevideo')
PARSE_TIMEOUT_SEC = max(10.0, float(os.getenv("PARSER_TIMEOUT_SEC", "35")))
PARSE_MAX_CONCURRENCY = max(1, int(os.getenv("PARSER_MAX_CONCURRENCY", "4")))
parse_sem = asyncio.Semaphore(PARSE_MAX_CONCURRENCY)

@client.on(events.NewMessage(chats=list(CHANNELS.values())))
async def handler(event):
    # --- metadatos del mensaje ---
    message = event.raw_text
    timestamp_utc = event.date
    timestamp = timestamp_utc.astimezone(uruguay_timezone)
    message_id = event.message.id
    reply_to_msg_id = event.message.reply_to_msg_id
    channel_id = event.chat_id
    channel_name = next((name for name, cid in CHANNELS.items() if cid == channel_id), str(channel_id))


    print(f"[{channel_name}, {timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
 
    # --- parseo (puede devolver múltiples eventos) ---
    try:
        async with parse_sem:
            parsed = await asyncio.wait_for(
                asyncio.to_thread(parse_signal, message, timestamp, message_id, reply_to_msg_id, channel_name),
                timeout=PARSE_TIMEOUT_SEC,
            )
    except asyncio.TimeoutError:
        save_non_signal({
            "timestamp": timestamp,
            "message_id": message_id,
            "reply_to": reply_to_msg_id,
            "channel": channel_name,
            "text": message,
            "reason": "parser_timeout",
        })
        print(f"⚠️ Parser timeout ({PARSE_TIMEOUT_SEC}s). Guardado como no señal.")
        return
    except Exception as e:
        save_non_signal({
            "timestamp": timestamp,
            "message_id": message_id,
            "reply_to": reply_to_msg_id,
            "channel": channel_name,
            "text": message,
            "reason": f"parser_exception:{type(e).__name__}",
        })
        print(f"⚠️ Parser excepción: {e}")
        return

    if not parsed:
        save_non_signal({
            "timestamp": timestamp,
            "message_id": message_id,
            "reply_to": reply_to_msg_id,
            "channel": channel_name,
            "text": message,
            "reason": "parser_none",
        })
        print("⚠️ Parser devolvió None. Guardado como no señal.")
        return

    symbol = parsed.get("symbol", "unknown")
    operation = parsed.get("operation", "unknown")
    events = parsed.get("events", [])

    # Si el modelo no devolvió eventos, no hay nada que registrar
    if not events:
        save_non_signal({
            "timestamp": timestamp,
            "message_id": message_id,
            "reply_to": reply_to_msg_id,
            "channel": channel_name,
            "text": message,
            "reason": "no_events",
        })
        print("ℹ️ Parser sin eventos. Guardado como no señal.")
        return

    # Resolver contexto de reply desde SQLite (rápido e indexado), con fallback CSV.
    prev_symbol = None
    prev_operation = None
    prev_entry_price = None
    if reply_to_msg_id:
        try:
            ctx = fetch_reply_context(reply_to_msg_id, channel_name=channel_name)
            prev_symbol = str(ctx.get("symbol") or "").strip() or None
            prev_operation = str(ctx.get("operation") or "").strip() or None
            prev_entry_price = str(ctx.get("entry_price") or "").strip() or None
        except Exception:
            prev_symbol = None
            prev_operation = None
            prev_entry_price = None
        if (not prev_symbol or not prev_operation or not prev_entry_price):
            df_all = read_signals()
            if df_all is not None and not df_all.empty:
                base = df_all[df_all["message_id"].astype(str) == str(reply_to_msg_id)]
                if "type" in base.columns:
                    base_entry = base[base["type"] == "entry"]
                    if not base_entry.empty:
                        base = base_entry
                if not base.empty:
                    if not prev_symbol:
                        prev_symbol = str(base.iloc[0].get("symbol") or "").strip() or None
                    if not prev_operation:
                        prev_operation = str(base.iloc[0].get("operation") or "").strip() or None
                    if not prev_entry_price:
                        prev_entry_price = str(base.iloc[0].get("entry_price") or "").strip() or None

    # --- GUARDAR 1 FILA POR EVENTO ---
    for ev in events:
        ev_type = ev.get("type", "unknown")
        operator_class = str(ev.get("operator_class", "") or "").strip().upper()
        if operator_class == "STANDARD":
            operator_class = "SWING"
        if not operator_class and ev_type == "entry":
            operator_class = "SWING"

        symbol_for_event = ev.get("symbol", symbol)
        operation_for_event = ev.get("operation", operation)
        if reply_to_msg_id and ev_type in ("close", "modification"):
            if prev_symbol:
                symbol_for_event = prev_symbol
            if prev_operation:
                operation_for_event = prev_operation

        row = {
            "type": ev_type,
            "timestamp": timestamp,
            "message_id": message_id,          # ID del mensaje actual (mod/cierre)
            "reply_to": reply_to_msg_id,       # enlaza con la entrada original
            "channel": channel_name,
            "message_text": message,
            "symbol": symbol_for_event,
            "operation": operation_for_event,
            # si fuera entry, pueden venir estos campos:
            "entry_price": ev.get("entry_price", ""),
            "stop_loss": ev.get("stop_loss", ""),
            "take_profit": ev.get("take_profit", ""),
            "close_reason": ev.get("close_reason", ""),
            # nuevos campos para eventos:
            "operator_class": operator_class,
            "new_stop_loss": ev.get("new_stop_loss", ""),
            "new_take_profit": ev.get("new_take_profit", ""),
            "move_to_breakeven": "true" if ev.get("move_to_breakeven") else "false",
            "close_pnl_pips": ev.get("close_pnl_pips", "")
        }

        # Resolver "breakeven" a precio numérico si hay reply_to y entry previo
        if (
            row["type"] == "modification"
            and row["move_to_breakeven"] == "true"
            and reply_to_msg_id
        ):
            be = str(prev_entry_price or "").strip()
            if be not in ("", "unknown", "instantly"):
                row["new_stop_loss"] = be  # usamos el precio de entrada como BE

        save_trade(row)  # escribe/append en data/signals.csv con columnas extendidas:contentReference[oaicite:4]{index=4}
        print(f"✅ Guardado evento: type={row['type']} operator={row['operator_class']} reply_to={row['reply_to']}")

def run():
    print("📡 Listening to Telegram channels:", list(CHANNELS.keys()))
    try:
        asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    client.start()
    client.run_until_disconnected()

if __name__ == '__main__':
    run()
