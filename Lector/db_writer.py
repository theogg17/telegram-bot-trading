# db_writer.py

import pandas as pd
import os
import json
import uuid
import sqlite3
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # type: ignore

# Path to the channels DB CSV file (adjust to your actual path)
BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(BASE_DIR)
TRADING_BOT_DB_PATH = os.getenv(
    "TRADING_BOT_DB_PATH",
    os.path.join(ROOT_DIR, "config", "trading_bot.db"),
)

CHANNELS_DB_PATH = os.path.join(BASE_DIR, 'CanalesDB', 'canalesDB.csv')
DEFAULT_SIGNALS_CSV = os.path.join(BASE_DIR, 'data', 'signals.csv')
DEFAULT_NON_SIGNALS_CSV = os.path.join(BASE_DIR, 'data', 'non_signals.csv')
EVENTS_QUEUE_DIR = os.path.join(ROOT_DIR, 'queue', 'pending')
URUGUAY_TZ = ZoneInfo("America/Montevideo") if ZoneInfo is not None else timezone(timedelta(hours=-3))
_SIGNAL_EVENTS_READY = False

# Desired column order for signals.csv
SIGNALS_COLUMNS = [
    'event_id',
    'type', 'timestamp', 'message_id', 'reply_to', 'channel',
    'channel_id',
    'channel_index', 'symbol', 'operation', 'entry_price',
    'stop_loss', 'take_profit', 'close_reason',
    'operator_class',           # nuevo
    'new_stop_loss',            # nuevo
    'new_take_profit',          # nuevo
    'move_to_breakeven',        # nuevo
    'close_pnl_pips',           # nuevo
    'message_text'              # texto original del mensaje Telegram
]

NON_SIGNALS_COLUMNS = [
    'timestamp', 'message_id', 'reply_to', 'channel', 'text', 'reason'
]

def _normalize_to_schema(df: pd.DataFrame) -> pd.DataFrame:
    # agrega las que falten
    for col in SIGNALS_COLUMNS:
        if col not in df.columns:
            df[col] = ''
    # reordena y elimina extrañas
    df = df.reindex(columns=SIGNALS_COLUMNS)
    return df

def _ensure_event_id(trade_data: dict) -> str:
    event_id = trade_data.get("event_id")
    if not event_id:
        event_id = uuid.uuid4().hex
        trade_data["event_id"] = event_id
    return event_id

def _queue_event(trade_data: dict):
    if str(trade_data.get("type", "")).lower() == "raw":
        return
    os.makedirs(EVENTS_QUEUE_DIR, exist_ok=True)
    event_id = _ensure_event_id(trade_data)
    payload = dict(trade_data)
    ts = payload.get("timestamp")
    if hasattr(ts, "isoformat"):
        payload["timestamp"] = ts.isoformat()
    tmp_path = os.path.join(EVENTS_QUEUE_DIR, f"{event_id}.json.tmp")
    final_path = os.path.join(EVENTS_QUEUE_DIR, f"{event_id}.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, default=str)
    os.replace(tmp_path, final_path)

def _ensure_csv_schema(filename=DEFAULT_SIGNALS_CSV):
    """Si el CSV existe con columnas viejas o filas inconsistentes, normaliza al esquema nuevo."""
    if not os.path.exists(filename):
        return
    try:
        df = pd.read_csv(filename)
        df = _normalize_to_schema(df)
        df.to_csv(filename, index=False)
    except Exception:
        # lectura tolerante si hay líneas inválidas
        try:
            df = pd.read_csv(filename, on_bad_lines='skip', engine='python', header=0)
            df = _normalize_to_schema(df)
            df.to_csv(filename, index=False)
        except Exception as e:
            print(f"Warning: could not normalize {filename}: {e}")

def _load_channel_index_mapping():
    """Loads the channel to index mapping from CHANNELS_DB_PATH."""
    if os.path.exists(CHANNELS_DB_PATH):
        df_channels = pd.read_csv(CHANNELS_DB_PATH)
        # Expect columns 'canal' and 'indice'
        return dict(zip(df_channels['canal'], df_channels['indice']))
    else:
        print(f"Warning: Channels DB file not found at {CHANNELS_DB_PATH}. 'channel_index' will be blank.")
        return {}


def _load_channel_id_mapping_sqlite():
    mapping = {}
    conn = None
    try:
        conn = sqlite3.connect(TRADING_BOT_DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name
            FROM telegram_channels
            ORDER BY id ASC
            """
        ).fetchall()
        for r in rows:
            name = str(r["name"] or "").strip()
            if not name:
                continue
            mapping[name] = int(r["id"])
    except Exception:
        return {}
    finally:
        if conn is not None:
            conn.close()
    return mapping


def _db_conn():
    dir_name = os.path.dirname(TRADING_BOT_DB_PATH)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    conn = sqlite3.connect(TRADING_BOT_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_signal_events_table(conn: sqlite3.Connection):
    global _SIGNAL_EVENTS_READY
    if _SIGNAL_EVENTS_READY:
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            ts TEXT NOT NULL,
            message_id TEXT NOT NULL,
            reply_to TEXT,
            channel TEXT NOT NULL,
            channel_id TEXT,
            channel_index TEXT,
            symbol TEXT,
            operation TEXT,
            entry_price TEXT,
            stop_loss TEXT,
            take_profit TEXT,
            close_reason TEXT,
            operator_class TEXT,
            new_stop_loss TEXT,
            new_take_profit TEXT,
            move_to_breakeven TEXT,
            close_pnl_pips TEXT,
            message_text TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_events_msg ON signal_events(channel, message_id, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_events_reply ON signal_events(channel, reply_to, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_events_type ON signal_events(type, ts)")
    _SIGNAL_EVENTS_READY = True


def _to_iso_uy(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.astimezone(URUGUAY_TZ).isoformat(timespec="seconds")
        except Exception:
            try:
                return value.isoformat(timespec="seconds")
            except Exception:
                return str(value)
    s = str(value or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            return dt.astimezone(URUGUAY_TZ).isoformat(timespec="seconds")
        return dt.replace(tzinfo=URUGUAY_TZ).isoformat(timespec="seconds")
    except Exception:
        return s


def _save_trade_sqlite(row: dict):
    event_id = str(row.get("event_id") or "").strip()
    if not event_id:
        return
    payload = json.dumps(row, ensure_ascii=True, default=str)
    with _db_conn() as conn:
        _ensure_signal_events_table(conn)
        conn.execute(
            """
            INSERT INTO signal_events (
                event_id, type, ts, message_id, reply_to, channel, channel_id, channel_index,
                symbol, operation, entry_price, stop_loss, take_profit, close_reason,
                operator_class, new_stop_loss, new_take_profit, move_to_breakeven,
                close_pnl_pips, message_text, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                type = excluded.type,
                ts = excluded.ts,
                message_id = excluded.message_id,
                reply_to = excluded.reply_to,
                channel = excluded.channel,
                channel_id = excluded.channel_id,
                channel_index = excluded.channel_index,
                symbol = excluded.symbol,
                operation = excluded.operation,
                entry_price = excluded.entry_price,
                stop_loss = excluded.stop_loss,
                take_profit = excluded.take_profit,
                close_reason = excluded.close_reason,
                operator_class = excluded.operator_class,
                new_stop_loss = excluded.new_stop_loss,
                new_take_profit = excluded.new_take_profit,
                move_to_breakeven = excluded.move_to_breakeven,
                close_pnl_pips = excluded.close_pnl_pips,
                message_text = excluded.message_text,
                raw_json = excluded.raw_json
            """,
            (
                event_id,
                str(row.get("type") or ""),
                _to_iso_uy(row.get("timestamp")),
                str(row.get("message_id") or ""),
                str(row.get("reply_to") or ""),
                str(row.get("channel") or ""),
                str(row.get("channel_id") or ""),
                str(row.get("channel_index") or ""),
                str(row.get("symbol") or ""),
                str(row.get("operation") or ""),
                str(row.get("entry_price") or ""),
                str(row.get("stop_loss") or ""),
                str(row.get("take_profit") or ""),
                str(row.get("close_reason") or ""),
                str(row.get("operator_class") or ""),
                str(row.get("new_stop_loss") or ""),
                str(row.get("new_take_profit") or ""),
                str(row.get("move_to_breakeven") or ""),
                str(row.get("close_pnl_pips") or ""),
                str(row.get("message_text") or ""),
                payload,
            ),
        )
        conn.commit()


def fetch_reply_context(reply_to_msg_id, channel_name=None):
    reply_id = str(reply_to_msg_id or "").strip()
    if not reply_id:
        return {"symbol": None, "operation": None, "entry_price": None}
    chan = str(channel_name or "").strip()
    with _db_conn() as conn:
        _ensure_signal_events_table(conn)
        row = None
        if chan:
            row = conn.execute(
                """
                SELECT symbol, operation, entry_price
                FROM signal_events
                WHERE channel = ?
                  AND message_id = ?
                  AND type = 'entry'
                ORDER BY id DESC
                LIMIT 1
                """,
                (chan, reply_id),
            ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT symbol, operation, entry_price
                FROM signal_events
                WHERE message_id = ?
                  AND type = 'entry'
                ORDER BY id DESC
                LIMIT 1
                """,
                (reply_id,),
            ).fetchone()
    return {
        "symbol": str(row["symbol"] or "").strip() if row is not None else None,
        "operation": str(row["operation"] or "").strip() if row is not None else None,
        "entry_price": str(row["entry_price"] or "").strip() if row is not None else None,
    }


def save_trade(trade_data, filename=DEFAULT_SIGNALS_CSV):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    _ensure_csv_schema(filename)  # <-- AÑADIDO
    _ensure_event_id(trade_data)

    # (resto igual que tenías)
    mapping = _load_channel_index_mapping()
    mapping_sql = _load_channel_id_mapping_sqlite()
    canal = trade_data.get('channel')
    stable_channel_id = mapping_sql.get(canal)
    if stable_channel_id is not None:
        trade_data['channel_id'] = stable_channel_id
        trade_data['channel_index'] = stable_channel_id
    else:
        trade_data['channel_id'] = ''
        trade_data['channel_index'] = mapping.get(canal, '')

    ordered_data = {col: trade_data.get(col, '') for col in SIGNALS_COLUMNS}
    df = pd.DataFrame([ordered_data])

    if not os.path.exists(filename):
        df.to_csv(filename, index=False, columns=SIGNALS_COLUMNS)
    else:
        df.to_csv(filename, mode='a', header=False, index=False, columns=SIGNALS_COLUMNS)
    try:
        _save_trade_sqlite(ordered_data)
    except Exception as e:
        print(f"Warning: could not save signal event in SQLite: {e}")
    _queue_event(trade_data)

def save_non_signal(data, filename=DEFAULT_NON_SIGNALS_CSV):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    row = {col: data.get(col, '') for col in NON_SIGNALS_COLUMNS}
    df = pd.DataFrame([row])
    if not os.path.exists(filename):
        df.to_csv(filename, index=False, columns=NON_SIGNALS_COLUMNS)
    else:
        df.to_csv(filename, mode='a', header=False, index=False, columns=NON_SIGNALS_COLUMNS)


def update_trade(trade_id, close_data, filename=DEFAULT_SIGNALS_CSV):
    """Updates an existing trade in the CSV file with closing information."""
    try:
        signals_df = pd.read_csv(filename)
    except FileNotFoundError:
        print(f"Error: File not found: {filename}")
        return

    if 'message_id' not in signals_df.columns:
        print("Error: 'message_id' column not found in the CSV.")
        return

    trade_index = signals_df[signals_df['message_id'] == trade_id].index
    if not trade_index.empty:
        for key, value in close_data.items():
            if key in signals_df.columns:
                signals_df.at[trade_index[0], key] = value

        # Reorder columns before saving
        signals_df = signals_df.reindex(columns=SIGNALS_COLUMNS)
        signals_df.to_csv(filename, index=False)

def read_signals(filename=DEFAULT_SIGNALS_CSV):
    """Lee el CSV de manera robusta. Si hay problemas de parseo, los corrige y devuelve un DF normalizado."""
    if not os.path.exists(filename):
        # devolver DF vacío con columnas correctas
        return pd.DataFrame(columns=SIGNALS_COLUMNS)

    try:
        df = pd.read_csv(filename)
        return _normalize_to_schema(df)
    except pd.errors.ParserError:
        # si hay filas con diferente número de campos, las salteamos una vez y normalizamos
        df = pd.read_csv(filename, on_bad_lines='skip', engine='python', header=0)
        df = _normalize_to_schema(df)
        df.to_csv(filename, index=False)
        return df
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return pd.DataFrame(columns=SIGNALS_COLUMNS)


def trade_exists(trade_id, filename=DEFAULT_SIGNALS_CSV):
    """Checks if a trade with a given message_id exists in the CSV."""
    try:
        signals_df = pd.read_csv(filename)
        return trade_id in signals_df['message_id'].values
    except FileNotFoundError:
        return False
