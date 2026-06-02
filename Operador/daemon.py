# Operador/daemon.py
import os, time, csv, datetime, hashlib, json, sqlite3, re, sys
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # type: ignore

from config_operador import (
    SIGNALS_CSV, ORDERS_SENT_CSV, ORDERS_INDEX_CSV, PROCESSED_EVENTS_CSV,
    TERMINAL_PATH, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TIMEOUT_MS, MT5_PORTABLE,
    EXECUTION_PROFILE, TOTAL_VOLUME,
    MAX_DEVIATION, FILLING_MODE,
    COMMENT_STYLE_SUFFIX, SYMBOLS_ALWAYS_SELECT, SYMBOLS_REQUIRED,
    MAGIC_NUMBER, SYMBOL_ALIASES,
    OPEN_TRADES_CSV,  # base viva
    NEAR_ENTRY_PIPS_MIN, NEAR_ENTRY_SPREAD_MULT,
    EVENTS_QUEUE_DIR, EVENTS_QUEUE_PROCESSED_DIR,
    OPERACIONES_ABIERTAS_CSV, ERRORES_APERTURAS_CSV,
    VERIFY_ORDER_AFTER_SEND, AUTO_CLOSE_ON_MISMATCH,
)

BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
from common.csv_guard import atomic_write_dataframe_csv, csv_file_lock
TRADING_BOT_DB_PATH = os.getenv("TRADING_BOT_DB_PATH", os.path.join(ROOT_DIR, "config", "trading_bot.db"))
QUEUE_FAILED_DIR = os.path.join(ROOT_DIR, "queue", "failed")
QUEUE_MAX_RETRIES = max(1, int(os.getenv("QUEUE_MAX_RETRIES", "5")))
MANUAL_CLOSE_CONFIRM_CHECKS = max(2, int(os.getenv("MANUAL_CLOSE_CONFIRM_CHECKS", "3")))
LIVE_SYNC_INTERVAL_SEC = max(1.0, float(os.getenv("LIVE_SYNC_INTERVAL_SEC", "1")))
EVENT_RETRY_MAX = max(1, int(os.getenv("EVENT_RETRY_MAX", "8")))
EVENT_RETRY_BASE_SEC = max(1, int(os.getenv("EVENT_RETRY_BASE_SEC", "2")))
EVENT_RETRY_MAX_SEC = max(5, int(os.getenv("EVENT_RETRY_MAX_SEC", "300")))
MT5_RECONNECT_BASE_SEC = max(1, int(os.getenv("MT5_RECONNECT_BASE_SEC", "2")))
MT5_RECONNECT_MAX_SEC = max(10, int(os.getenv("MT5_RECONNECT_MAX_SEC", "60")))
VIRTUAL_AUTOCLOSE_SLTP = str(os.getenv("VIRTUAL_AUTOCLOSE_SLTP", "true")).strip().lower() in ("1", "true", "yes", "on")
STARTUP_STALE_CLOSE_AGE_SEC = max(300, int(os.getenv("STARTUP_STALE_CLOSE_AGE_SEC", "1800")))
LOG_PARSE_CORRECTIONS = str(os.getenv("LOG_PARSE_CORRECTIONS", "false")).strip().lower() in ("1", "true", "yes", "on")
URUGUAY_TZ = ZoneInfo("America/Montevideo") if ZoneInfo is not None else datetime.timezone(datetime.timedelta(hours=-3))
_mt5_ready = False
_mt5_reconnect_attempts = 0
_mt5_next_reconnect_ts = 0.0
_startup_reconcile_done = False
STARTUP_RECONCILE_MODE = str(os.getenv("STARTUP_RECONCILE_MODE", "warn")).strip().lower()
if STARTUP_RECONCILE_MODE not in ("warn", "close"):
    STARTUP_RECONCILE_MODE = "warn"

# =============== utilidades CSV básicas ===============
def _ensure_csv_unlocked(path: str, fieldnames: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()

def _ensure_csv(path: str, fieldnames: list):
    with csv_file_lock(path):
        _ensure_csv_unlocked(path, fieldnames)

def _append_row(path: str, row: dict, fieldnames: list):
    with csv_file_lock(path):
        _ensure_csv_unlocked(path, fieldnames)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writerow(row)

def _load_df(path: str, fields=None):
    if not os.path.exists(path):
        return pd.DataFrame(columns=fields or [])
    with csv_file_lock(path):
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.read_csv(path, on_bad_lines='skip', engine='python')

def _normalize_id(value):
    if value is None:
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if pd.isna(value):
            return ""
        if float(value).is_integer():
            return str(int(value))
        return str(value).strip()
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return s

def _ticket_set(values):
    out = set()
    for v in (values or []):
        sid = _normalize_id(v)
        if not sid:
            continue
        try:
            out.add(int(sid))
        except Exception:
            continue
    return out


KNOWN_PROFILE_CODES = {"SCALP", "SWING"}
_FX_CODES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "XAU", "XAG", "BTC", "ETH",
}
_SYMBOL_SLASH = re.compile(r"\b([A-Z]{3})\s*/\s*([A-Z]{3})\b", re.I)
_SYMBOL_TOKEN = re.compile(r"\b([A-Z]{6,7})\b", re.I)
_SIDE_TOKEN = re.compile(r"\b(BUY|SELL)\b", re.I)


def _normalize_profile_code(value, default="SWING"):
    code = str(value or "").strip().upper()
    if code == "STANDARD":
        code = "SWING"
    if not code:
        code = str(default or "SWING").upper()
    if code == "STANDARD":
        code = "SWING"
    if code not in KNOWN_PROFILE_CODES:
        code = str(default or "SWING").strip().upper()
        if code == "STANDARD" or code not in KNOWN_PROFILE_CODES:
            code = "SWING"
    return code


def _symbol_from_text(message_text: str):
    text = str(message_text or "").upper()
    for m in _SYMBOL_SLASH.finditer(text):
        cand = f"{m.group(1)}{m.group(2)}"
        if cand[:3] in _FX_CODES and cand[3:] in _FX_CODES:
            return cand
    for m in _SYMBOL_TOKEN.finditer(text):
        cand = str(m.group(1) or "").upper()
        if cand == "BTCUSDT":
            return cand
        if len(cand) == 6 and cand[:3] in _FX_CODES and cand[3:] in _FX_CODES:
            return cand
    return None


def _side_from_text(message_text: str):
    m = _SIDE_TOKEN.search(str(message_text or "").upper())
    if not m:
        return None
    return str(m.group(1)).upper()


def _now_iso():
    return datetime.datetime.now(URUGUAY_TZ).isoformat(timespec="seconds")


def _uy_from_epoch_iso(epoch_ts: float):
    return datetime.datetime.fromtimestamp(float(epoch_ts), URUGUAY_TZ).isoformat(timespec="seconds")


def _parse_iso_or_none(value):
    s = str(value or "").strip()
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s)
    except Exception:
        try:
            dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is not None:
        return dt.astimezone(URUGUAY_TZ).replace(tzinfo=None)
    return dt


def _elapsed_seconds(start_ts, end_ts=None):
    start_dt = _parse_iso_or_none(start_ts)
    if start_dt is None:
        return None
    end_dt = _parse_iso_or_none(end_ts) if end_ts else datetime.datetime.now(URUGUAY_TZ).replace(tzinfo=None)
    if end_dt is None:
        end_dt = datetime.datetime.now(URUGUAY_TZ).replace(tzinfo=None)
    try:
        return max(0, int((end_dt - start_dt).total_seconds()))
    except Exception:
        return None


def _operation_key_real(channel_index, entry_message_id, style):
    return f"real:{_normalize_id(channel_index)}:{_normalize_id(entry_message_id)}:{_normalize_profile_code(style, default='SWING')}"


def _operation_key_virtual(channel_id, config_id, entry_message_id):
    return f"virtual:{int(channel_id)}:{int(config_id)}:{_normalize_id(entry_message_id)}"

def _db_conn():
    os.makedirs(os.path.dirname(TRADING_BOT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(TRADING_BOT_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _ensure_experiment_tables():
    with _db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_system INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        now = _now_iso()
        defaults = [
            ("SCALP", "Scalp", "Perfil rapido", 1),
            ("SWING", "Swing", "Perfil largo", 1),
        ]
        for code, name, description, is_system in defaults:
            row = conn.execute("SELECT id FROM execution_profiles WHERE code = ?", (code,)).fetchone()
            if not row:
                conn.execute(
                    """
                    INSERT INTO execution_profiles (code, name, description, is_system, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (code, name, description, int(is_system), now, now),
                )

        op_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='operator_presets'").fetchone()
        if op_table:
            op_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(operator_presets)").fetchall()]
            if "execution_profile_id" not in op_cols:
                conn.execute("ALTER TABLE operator_presets ADD COLUMN execution_profile_id INTEGER NOT NULL DEFAULT 0")
            swing_row = conn.execute("SELECT id FROM execution_profiles WHERE code = 'SWING'").fetchone()
            swing_id = int(swing_row["id"]) if swing_row else 0
            conn.execute(
                """
                UPDATE operator_presets
                SET execution_profile_id = ?
                WHERE COALESCE(execution_profile_id, 0) <= 0
                   OR execution_profile_id IN (
                       SELECT id FROM execution_profiles WHERE UPPER(code) NOT IN ('SCALP','SWING')
                   )
                """,
                (swing_id,),
            )
        conn.execute("DELETE FROM execution_profiles WHERE UPPER(code) NOT IN ('SCALP','SWING')")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_config_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                config_id INTEGER NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('real','virtual')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(channel_id, config_id)
            )
            """
        )
        # Robustez: modo real solo para presets SWING y máximo 1 real por canal.
        conn.execute(
            """
            UPDATE channel_config_assignments
            SET mode = 'virtual', updated_at = ?
            WHERE mode = 'real'
              AND config_id IN (
                  SELECT p.id
                  FROM operator_presets p
                  LEFT JOIN execution_profiles ep ON ep.id = p.execution_profile_id
                  WHERE UPPER(COALESCE(ep.code, 'SWING')) <> 'SWING'
              )
            """,
            (now,),
        )
        ch_rows = conn.execute(
            """
            SELECT channel_id, MIN(id) AS keep_id
            FROM channel_config_assignments
            WHERE mode = 'real'
            GROUP BY channel_id
            HAVING COUNT(1) > 1
            """
        ).fetchall()
        for ch in ch_rows:
            conn.execute(
                """
                UPDATE channel_config_assignments
                SET mode = 'virtual', updated_at = ?
                WHERE channel_id = ?
                  AND mode = 'real'
                  AND id <> ?
                """,
                (now, int(ch["channel_id"]), int(ch["keep_id"])),
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event_id TEXT,
                message_id TEXT,
                channel_id INTEGER,
                channel_name TEXT,
                config_id INTEGER,
                config_name TEXT,
                mode TEXT,
                event_type TEXT,
                symbol TEXT,
                side TEXT,
                operator_class TEXT,
                entry_message_id TEXT,
                reply_to TEXT,
                status TEXT,
                error_type TEXT,
                pnl_usd REAL,
                pnl_pips REAL,
                details TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS virtual_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                config_id INTEGER NOT NULL,
                config_name TEXT NOT NULL,
                entry_message_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                volume REAL NOT NULL,
                entry_price REAL NOT NULL,
                sl REAL,
                tp REAL,
                opened_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                closed_at TEXT,
                close_price REAL,
                pnl_usd REAL,
                pnl_pips REAL
            )
            """
        )
        strategy_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(strategy_event_log)").fetchall()]
        if "message_id" not in strategy_cols:
            conn.execute("ALTER TABLE strategy_event_log ADD COLUMN message_id TEXT")
        if "operator_class" not in strategy_cols:
            conn.execute("ALTER TABLE strategy_event_log ADD COLUMN operator_class TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_key TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                is_virtual INTEGER NOT NULL DEFAULT 0,
                channel_id INTEGER,
                channel_name TEXT,
                channel_index TEXT,
                preset_id INTEGER,
                preset_name TEXT,
                execution_profile TEXT,
                symbol TEXT,
                side TEXT,
                entry_message_id TEXT,
                entry_event_id TEXT,
                entry_trigger_message_id TEXT,
                entry_ts TEXT,
                opened_at TEXT,
                ticket TEXT,
                comment TEXT,
                volume REAL,
                entry_price REAL,
                sl REAL,
                tp REAL,
                had_modifications INTEGER NOT NULL DEFAULT 0,
                modifications_count INTEGER NOT NULL DEFAULT 0,
                last_modification_message_id TEXT,
                last_modified_at TEXT,
                closed_at TEXT,
                close_event_id TEXT,
                close_trigger_message_id TEXT,
                close_reason TEXT,
                close_source TEXT,
                close_error_id TEXT,
                close_error_type TEXT,
                close_details TEXT,
                pnl_usd REAL,
                pnl_pips REAL,
                last_pips REAL,
                last_profit_usd REAL,
                duration_seconds INTEGER,
                last_sync_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        op_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(operation_records)").fetchall()]
        op_missing_sql = {
            "operation_key": "TEXT NOT NULL DEFAULT ''",
            "mode": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT ''",
            "is_virtual": "INTEGER NOT NULL DEFAULT 0",
            "channel_id": "INTEGER",
            "channel_name": "TEXT",
            "channel_index": "TEXT",
            "preset_id": "INTEGER",
            "preset_name": "TEXT",
            "execution_profile": "TEXT",
            "symbol": "TEXT",
            "side": "TEXT",
            "entry_message_id": "TEXT",
            "entry_event_id": "TEXT",
            "entry_trigger_message_id": "TEXT",
            "entry_ts": "TEXT",
            "opened_at": "TEXT",
            "ticket": "TEXT",
            "comment": "TEXT",
            "volume": "REAL",
            "entry_price": "REAL",
            "sl": "REAL",
            "tp": "REAL",
            "had_modifications": "INTEGER NOT NULL DEFAULT 0",
            "modifications_count": "INTEGER NOT NULL DEFAULT 0",
            "last_modification_message_id": "TEXT",
            "last_modified_at": "TEXT",
            "closed_at": "TEXT",
            "close_event_id": "TEXT",
            "close_trigger_message_id": "TEXT",
            "close_reason": "TEXT",
            "close_source": "TEXT",
            "close_error_id": "TEXT",
            "close_error_type": "TEXT",
            "close_details": "TEXT",
            "pnl_usd": "REAL",
            "pnl_pips": "REAL",
            "last_pips": "REAL",
            "last_profit_usd": "REAL",
            "duration_seconds": "INTEGER",
            "last_sync_at": "TEXT",
            "missing_from_mt5_checks": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for col, col_sql in op_missing_sql.items():
            if col not in op_cols:
                conn.execute(f"ALTER TABLE operation_records ADD COLUMN {col} {col_sql}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER NOT NULL,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_id TEXT,
                message_id TEXT,
                reply_to TEXT,
                status TEXT,
                error_type TEXT,
                sl REAL,
                tp REAL,
                pnl_usd REAL,
                pnl_pips REAL,
                details TEXT
            )
            """
        )
        op_ev_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(operation_events)").fetchall()]
        op_ev_missing = {
            "operation_id": "INTEGER NOT NULL DEFAULT 0",
            "ts": "TEXT NOT NULL DEFAULT ''",
            "event_type": "TEXT NOT NULL DEFAULT ''",
            "event_id": "TEXT",
            "message_id": "TEXT",
            "reply_to": "TEXT",
            "status": "TEXT",
            "error_type": "TEXT",
            "sl": "REAL",
            "tp": "REAL",
            "pnl_usd": "REAL",
            "pnl_pips": "REAL",
            "details": "TEXT",
        }
        for col, col_sql in op_ev_missing.items():
            if col not in op_ev_cols:
                conn.execute(f"ALTER TABLE operation_events ADD COLUMN {col} {col_sql}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_uid TEXT NOT NULL,
                message_key TEXT NOT NULL DEFAULT '',
                message_id TEXT NOT NULL,
                channel_name TEXT,
                channel_index TEXT,
                ts TEXT,
                reply_to TEXT,
                event_id TEXT,
                event_type TEXT,
                symbol TEXT,
                operation TEXT,
                operator_class TEXT,
                message_text TEXT,
                raw_payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                event_uid TEXT PRIMARY KEY,
                event_id TEXT,
                message_id TEXT,
                channel_index TEXT,
                source TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'done',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queue_event_failures (
                event_path TEXT PRIMARY KEY,
                event_id TEXT,
                retries INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                quarantined INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_retry_state (
                event_uid TEXT PRIMARY KEY,
                retries INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                last_error_type TEXT NOT NULL DEFAULT '',
                next_retry_at TEXT NOT NULL DEFAULT '',
                quarantined INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        tmsg_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(telegram_messages)").fetchall()]
        tmsg_missing = {
            "message_uid": "TEXT NOT NULL DEFAULT ''",
            "message_key": "TEXT NOT NULL DEFAULT ''",
            "message_id": "TEXT NOT NULL DEFAULT ''",
            "channel_name": "TEXT",
            "channel_index": "TEXT",
            "ts": "TEXT",
            "reply_to": "TEXT",
            "event_id": "TEXT",
            "event_type": "TEXT",
            "symbol": "TEXT",
            "operation": "TEXT",
            "operator_class": "TEXT",
            "message_text": "TEXT",
            "raw_payload": "TEXT",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for col, col_sql in tmsg_missing.items():
            if col not in tmsg_cols:
                conn.execute(f"ALTER TABLE telegram_messages ADD COLUMN {col} {col_sql}")
        conn.execute(
            """
            UPDATE telegram_messages
            SET message_key = CASE
                WHEN COALESCE(message_key, '') = '' AND COALESCE(channel_name, '') <> '' AND COALESCE(message_id, '') <> ''
                THEN channel_name || ':' || message_id
                WHEN COALESCE(message_key, '') = '' THEN COALESCE(message_uid, '')
                ELSE message_key
            END
            WHERE COALESCE(message_key, '') = ''
            """
        )
        pe_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(processed_events)").fetchall()]
        pe_missing = {
            "event_uid": "TEXT",
            "event_id": "TEXT",
            "message_id": "TEXT",
            "channel_index": "TEXT",
            "source": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'done'",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for col, col_sql in pe_missing.items():
            if col not in pe_cols:
                conn.execute(f"ALTER TABLE processed_events ADD COLUMN {col} {col_sql}")
        qf_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(queue_event_failures)").fetchall()]
        qf_missing = {
            "event_path": "TEXT",
            "event_id": "TEXT",
            "retries": "INTEGER NOT NULL DEFAULT 0",
            "last_error": "TEXT NOT NULL DEFAULT ''",
            "first_seen": "TEXT NOT NULL DEFAULT ''",
            "last_seen": "TEXT NOT NULL DEFAULT ''",
            "quarantined": "INTEGER NOT NULL DEFAULT 0",
        }
        for col, col_sql in qf_missing.items():
            if col not in qf_cols:
                conn.execute(f"ALTER TABLE queue_event_failures ADD COLUMN {col} {col_sql}")
        ers_cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(event_retry_state)").fetchall()]
        ers_missing = {
            "event_uid": "TEXT",
            "retries": "INTEGER NOT NULL DEFAULT 0",
            "last_error": "TEXT NOT NULL DEFAULT ''",
            "last_error_type": "TEXT NOT NULL DEFAULT ''",
            "next_retry_at": "TEXT NOT NULL DEFAULT ''",
            "quarantined": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for col, col_sql in ers_missing.items():
            if col not in ers_cols:
                conn.execute(f"ALTER TABLE event_retry_state ADD COLUMN {col} {col_sql}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy_log_ts ON strategy_event_log(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy_log_combo ON strategy_event_log(channel_id, config_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vpos_open ON virtual_positions(channel_id, config_id, entry_message_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_op_records_state ON operation_records(status, mode, opened_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_op_records_entry ON operation_records(channel_index, entry_message_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_op_events_operation ON operation_events(operation_id, ts)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tmsg_uid ON telegram_messages(message_uid)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tmsg_message_key ON telegram_messages(message_key, ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tmsg_message_id ON telegram_messages(message_id, ts)")
        conn.execute(
            """
            DELETE FROM processed_events
            WHERE rowid NOT IN (
                SELECT MIN(rowid) FROM processed_events GROUP BY event_uid
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_processed_events_uid ON processed_events(event_uid)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_events_updated ON processed_events(updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_failures_quarantined ON queue_event_failures(quarantined, retries)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_retry_next ON event_retry_state(quarantined, next_retry_at)")
        conn.commit()

def _load_assignments_for_channel(channel_name: str):
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    ca.id AS assignment_id,
                    ca.mode AS mode,
                    tc.id AS channel_id,
                    tc.name AS channel_name,
                    op.id AS config_id,
                    op.name AS config_name,
                    op.execution_profile_id AS execution_profile_id,
                    COALESCE(ep.code, 'SWING') AS execution_profile,
                    op.total_volume AS total_volume,
                    op.near_entry_pips_min AS near_entry_pips_min,
                    op.near_entry_spread_mult AS near_entry_spread_mult,
                    op.verify_order_after_send AS verify_order_after_send,
                    op.auto_close_on_mismatch AS auto_close_on_mismatch
                FROM channel_config_assignments ca
                JOIN telegram_channels tc ON tc.id = ca.channel_id
                JOIN operator_presets op ON op.id = ca.config_id
                LEFT JOIN execution_profiles ep ON ep.id = op.execution_profile_id
                WHERE ca.is_active = 1
                  AND tc.is_active = 1
                  AND tc.name = ?
                ORDER BY CASE ca.mode WHEN 'real' THEN 0 ELSE 1 END, ca.id ASC
                """,
                (str(channel_name),),
            ).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        profile_code = _normalize_profile_code(r["execution_profile"], default=EXECUTION_PROFILE)
        mode = str(r["mode"])
        if mode == "real" and profile_code != "SWING":
            # Robustez: nunca operar real con perfil distinto de SWING.
            mode = "virtual"
        out.append({
            "assignment_id": int(r["assignment_id"]),
            "mode": mode,
            "channel_id": int(r["channel_id"]),
            "channel_name": str(r["channel_name"]),
            "config_id": int(r["config_id"]),
            "config_name": str(r["config_name"]),
            "execution_profile_id": int(r["execution_profile_id"]) if r["execution_profile_id"] is not None else 0,
            "execution_profile": profile_code,
            "total_volume": float(r["total_volume"] if r["total_volume"] is not None else TOTAL_VOLUME),
            "near_entry_pips_min": float(r["near_entry_pips_min"] if r["near_entry_pips_min"] is not None else NEAR_ENTRY_PIPS_MIN),
            "near_entry_spread_mult": float(r["near_entry_spread_mult"] if r["near_entry_spread_mult"] is not None else NEAR_ENTRY_SPREAD_MULT),
            "verify_order_after_send": bool(r["verify_order_after_send"]),
            "auto_close_on_mismatch": bool(r["auto_close_on_mismatch"]),
        })
    return out

def _select_real_assignment(assignments: list):
    for a in assignments:
        if str(a.get("mode", "")).lower() == "real":
            return a
    return None

def _select_virtual_assignments(assignments: list):
    return [a for a in assignments if str(a.get("mode", "")).lower() == "virtual"]


def _safe_float_or_none(value):
    try:
        if value is None:
            return None
        s = str(value).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _upsert_telegram_message(row: dict, event_id: str):
    message_id = _normalize_id(row.get("message_id", ""))
    channel_name = str(row.get("channel", "") or "").strip()
    if not message_id or not channel_name:
        return
    event_uid = str(event_id or "").strip() or hashlib.sha1(
        json.dumps(row, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    channel_index = _normalize_id(row.get("channel_index", ""))
    message_key = f"{channel_name}:{message_id}"
    message_uid = f"{message_key}:{event_uid}"
    now = _now_iso()
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT id FROM telegram_messages WHERE message_uid = ?",
            (message_uid,),
        ).fetchone()
        payload_raw = json.dumps(row, ensure_ascii=True, default=str)
        values = (
            message_uid,
            message_key,
            message_id,
            channel_name,
            channel_index,
            str(row.get("timestamp", "") or ""),
            _normalize_id(row.get("reply_to", "")),
            str(event_id or ""),
            str(row.get("type", "") or "").lower(),
            str(row.get("symbol", "") or "").upper(),
            str(row.get("operation", "") or "").upper(),
            str(row.get("operator_class", "") or "").upper(),
            str(row.get("message_text", "") or ""),
            payload_raw,
            now,
        )
        if cur:
            conn.execute(
                """
                UPDATE telegram_messages
                SET message_uid = ?, message_key = ?, message_id = ?, channel_name = ?, channel_index = ?, ts = ?, reply_to = ?,
                    event_id = ?, event_type = ?, symbol = ?, operation = ?, operator_class = ?,
                    message_text = ?, raw_payload = ?, updated_at = ?
                WHERE id = ?
                """,
                (*values, int(cur["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO telegram_messages (
                    message_uid, message_key, message_id, channel_name, channel_index, ts, reply_to,
                    event_id, event_type, symbol, operation, operator_class, message_text,
                    raw_payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_uid,
                    message_key,
                    message_id,
                    channel_name,
                    channel_index,
                    str(row.get("timestamp", "") or ""),
                    _normalize_id(row.get("reply_to", "")),
                    str(event_id or ""),
                    str(row.get("type", "") or "").lower(),
                    str(row.get("symbol", "") or "").upper(),
                    str(row.get("operation", "") or "").upper(),
                    str(row.get("operator_class", "") or "").upper(),
                    str(row.get("message_text", "") or ""),
                    payload_raw,
                    now,
                    now,
                ),
            )
        conn.commit()


def _operation_id_by_key(conn, operation_key):
    row = conn.execute("SELECT id FROM operation_records WHERE operation_key = ?", (str(operation_key),)).fetchone()
    if row:
        return int(row["id"])
    return None


def _operation_id_real(conn, channel_index, entry_message_id, style):
    op_id = _operation_id_by_key(conn, _operation_key_real(channel_index, entry_message_id, style))
    if op_id:
        return op_id
    row = conn.execute(
        """
        SELECT id
        FROM operation_records
        WHERE mode = 'real'
          AND COALESCE(channel_index,'') = ?
          AND COALESCE(entry_message_id,'') = ?
        ORDER BY CASE status WHEN 'OPEN' THEN 0 WHEN 'PENDING' THEN 1 ELSE 2 END, updated_at DESC, id DESC
        LIMIT 1
        """,
        (_normalize_id(channel_index), _normalize_id(entry_message_id)),
    ).fetchone()
    if row:
        return int(row["id"])
    return None


def _operation_id_virtual(conn, channel_id, config_id, entry_message_id):
    op_id = _operation_id_by_key(conn, _operation_key_virtual(channel_id, config_id, entry_message_id))
    if op_id:
        return op_id
    row = conn.execute(
        """
        SELECT id
        FROM operation_records
        WHERE mode = 'virtual'
          AND COALESCE(channel_id,0) = ?
          AND COALESCE(preset_id,0) = ?
          AND COALESCE(entry_message_id,'') = ?
        ORDER BY CASE status WHEN 'OPEN' THEN 0 WHEN 'PENDING' THEN 1 ELSE 2 END, updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(channel_id), int(config_id), _normalize_id(entry_message_id)),
    ).fetchone()
    if row:
        return int(row["id"])
    return None


def _operation_event_add(
    conn,
    operation_id,
    *,
    event_type="",
    event_id="",
    message_id="",
    reply_to="",
    status="",
    error_type="",
    sl=None,
    tp=None,
    pnl_usd=None,
    pnl_pips=None,
    details="",
):
    conn.execute(
        """
        INSERT INTO operation_events (
            operation_id, ts, event_type, event_id, message_id, reply_to, status, error_type,
            sl, tp, pnl_usd, pnl_pips, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(operation_id),
            _now_iso(),
            str(event_type or ""),
            str(event_id or ""),
            _normalize_id(message_id),
            _normalize_id(reply_to),
            str(status or ""),
            str(error_type or ""),
            _safe_float_or_none(sl),
            _safe_float_or_none(tp),
            _safe_float_or_none(pnl_usd),
            _safe_float_or_none(pnl_pips),
            str(details or ""),
        ),
    )


def _operation_upsert_entry(
    conn,
    *,
    operation_key,
    mode,
    status,
    is_virtual,
    channel_id=None,
    channel_name="",
    channel_index="",
    preset_id=None,
    preset_name="",
    execution_profile="",
    symbol="",
    side="",
    entry_message_id="",
    entry_event_id="",
    entry_trigger_message_id="",
    entry_ts="",
    ticket="",
    comment="",
    volume=None,
    entry_price=None,
    sl=None,
    tp=None,
):
    now = _now_iso()
    row = conn.execute(
        "SELECT id FROM operation_records WHERE operation_key = ?",
        (str(operation_key),),
    ).fetchone()
    values = (
        str(mode or ""),
        str(status or ""),
        1 if bool(is_virtual) else 0,
        int(channel_id) if channel_id is not None else None,
        str(channel_name or ""),
        _normalize_id(channel_index),
        int(preset_id) if preset_id is not None else None,
        str(preset_name or ""),
        _normalize_profile_code(execution_profile, default="SWING"),
        str(symbol or ""),
        str(side or "").upper(),
        _normalize_id(entry_message_id),
        str(entry_event_id or ""),
        _normalize_id(entry_trigger_message_id),
        str(entry_ts or ""),
        str(entry_ts or now),
        _normalize_id(ticket),
        str(comment or ""),
        _safe_float_or_none(volume),
        _safe_float_or_none(entry_price),
        _safe_float_or_none(sl),
        _safe_float_or_none(tp),
        now,
    )
    if row:
        conn.execute(
            """
            UPDATE operation_records
            SET mode = ?, status = ?, is_virtual = ?, channel_id = ?, channel_name = ?, channel_index = ?,
                preset_id = ?, preset_name = ?, execution_profile = ?, symbol = ?, side = ?,
                entry_message_id = ?, entry_event_id = ?, entry_trigger_message_id = ?, entry_ts = ?,
                opened_at = ?, ticket = ?, comment = ?, volume = ?, entry_price = ?, sl = ?, tp = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (*values, int(row["id"])),
        )
        return int(row["id"])
    conn.execute(
        """
        INSERT INTO operation_records (
            operation_key, mode, status, is_virtual, channel_id, channel_name, channel_index,
            preset_id, preset_name, execution_profile, symbol, side, entry_message_id, entry_event_id,
            entry_trigger_message_id, entry_ts, opened_at, ticket, comment, volume, entry_price, sl, tp,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(operation_key),
            *values,
            now,
        ),
    )
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return int(rid)


def _operation_apply_modification(
    conn,
    operation_id,
    *,
    message_id="",
    new_sl=None,
    new_tp=None,
):
    now = _now_iso()
    row = conn.execute(
        "SELECT modifications_count, sl, tp FROM operation_records WHERE id = ?",
        (int(operation_id),),
    ).fetchone()
    if not row:
        return
    sl_val = _safe_float_or_none(new_sl)
    tp_val = _safe_float_or_none(new_tp)
    if sl_val is None:
        sl_val = _safe_float_or_none(row["sl"])
    if tp_val is None:
        tp_val = _safe_float_or_none(row["tp"])
    conn.execute(
        """
        UPDATE operation_records
        SET had_modifications = 1,
            modifications_count = ?,
            last_modification_message_id = ?,
            last_modified_at = ?,
            sl = ?, tp = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            int(row["modifications_count"] or 0) + 1,
            _normalize_id(message_id),
            now,
            sl_val,
            tp_val,
            now,
            int(operation_id),
        ),
    )


def _operation_mark_closed(
    conn,
    operation_id,
    *,
    status="CLOSED",
    close_event_id="",
    close_message_id="",
    close_trigger_message_id="",
    close_reason="",
    close_source="",
    close_error_id="",
    close_error_type="",
    close_details="",
    pnl_usd=None,
    pnl_pips=None,
):
    now = _now_iso()
    trigger_message_id = close_trigger_message_id if close_trigger_message_id not in ("", None) else close_message_id
    row = conn.execute(
        "SELECT opened_at FROM operation_records WHERE id = ?",
        (int(operation_id),),
    ).fetchone()
    opened_at = str(row["opened_at"] or "") if row else ""
    duration = _elapsed_seconds(opened_at, now)
    conn.execute(
        """
        UPDATE operation_records
        SET status = ?,
            closed_at = ?,
            close_event_id = ?,
            close_trigger_message_id = ?,
            close_reason = ?,
            close_source = ?,
            close_error_id = ?,
            close_error_type = ?,
            close_details = ?,
            pnl_usd = COALESCE(?, pnl_usd),
            pnl_pips = COALESCE(?, pnl_pips),
            last_pips = COALESCE(?, last_pips),
            last_profit_usd = COALESCE(?, last_profit_usd),
            duration_seconds = COALESCE(?, duration_seconds),
            missing_from_mt5_checks = 0,
            last_sync_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(status or "CLOSED"),
            now,
            str(close_event_id or ""),
            _normalize_id(trigger_message_id),
            str(close_reason or ""),
            str(close_source or ""),
            str(close_error_id or ""),
            str(close_error_type or ""),
            str(close_details or ""),
            _safe_float_or_none(pnl_usd),
            _safe_float_or_none(pnl_pips),
            _safe_float_or_none(pnl_pips),
            _safe_float_or_none(pnl_usd),
            int(duration) if duration is not None else None,
            now if duration is not None else "",
            now,
            int(operation_id),
        ),
    )

def _report_log(
    *,
    event_id="",
    message_id="",
    channel_id=None,
    channel_name="",
    config_id=None,
    config_name="",
    mode="",
    event_type="",
    symbol="",
    side="",
    operator_class="",
    entry_message_id="",
    reply_to="",
    status="",
    error_type="",
    pnl_usd=None,
    pnl_pips=None,
    details="",
):
    try:
        with _db_conn() as conn:
            conn.execute(
                """
                INSERT INTO strategy_event_log (
                    ts, event_id, message_id, channel_id, channel_name, config_id, config_name, mode,
                    event_type, symbol, side, operator_class, entry_message_id, reply_to, status, error_type,
                    pnl_usd, pnl_pips, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    str(event_id or ""),
                    _normalize_id(message_id),
                    int(channel_id) if channel_id is not None else None,
                    str(channel_name or ""),
                    int(config_id) if config_id is not None else None,
                    str(config_name or ""),
                    str(mode or ""),
                    str(event_type or ""),
                    str(symbol or ""),
                    str(side or ""),
                    str(operator_class or ""),
                    str(entry_message_id or ""),
                    str(reply_to or ""),
                    str(status or ""),
                    str(error_type or ""),
                    float(pnl_usd) if pnl_usd is not None else None,
                    float(pnl_pips) if pnl_pips is not None else None,
                    str(details or ""),
                ),
            )
            conn.commit()
    except Exception:
        pass

def _order_calc_profit_usd(symbol: str, side: str, volume: float, entry_price: float, close_price: float):
    try:
        order_type = mt5.ORDER_TYPE_BUY if str(side).upper() == "BUY" else mt5.ORDER_TYPE_SELL
        val = mt5.order_calc_profit(order_type, symbol, float(volume), float(entry_price), float(close_price))
        if val is None:
            return None
        return float(val)
    except Exception:
        return None

def _pips_between(symbol: str, side: str, entry_price: float, close_price: float):
    pip = _pip_size(symbol)
    if pip <= 0:
        return None
    if str(side).upper() == "BUY":
        return (float(close_price) - float(entry_price)) / pip
    return (float(entry_price) - float(close_price)) / pip

def _virtual_open_position(channel_id, channel_name, cfg, entry_message_id, symbol, side, volume, entry_price, sl=None, tp=None):
    try:
        with _db_conn() as conn:
            conn.execute(
                """
                INSERT INTO virtual_positions (
                    channel_id, channel_name, config_id, config_name, entry_message_id, symbol, side,
                    volume, entry_price, sl, tp, opened_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                """,
                (
                    int(channel_id), str(channel_name), int(cfg["config_id"]), str(cfg["config_name"]),
                    str(entry_message_id), str(symbol), str(side), float(volume), float(entry_price),
                    float(sl) if _parse_float_or_none(sl) is not None else None,
                    float(tp) if _parse_float_or_none(tp) is not None else None,
                    _now_iso(),
                ),
            )
            conn.commit()
    except Exception:
        return False
    return True

def _virtual_modify_positions(channel_id, cfg, entry_message_id, new_sl=None, new_tp=None):
    sl_val = _parse_float_or_none(new_sl)
    tp_val = _parse_float_or_none(new_tp)
    if sl_val is None and tp_val is None:
        return 0
    try:
        with _db_conn() as conn:
            row = conn.execute(
                """
                SELECT id FROM virtual_positions
                WHERE channel_id = ? AND config_id = ? AND entry_message_id = ? AND status = 'OPEN'
                """,
                (int(channel_id), int(cfg["config_id"]), str(entry_message_id)),
            ).fetchall()
            if not row:
                return 0
            if sl_val is not None and tp_val is not None:
                conn.execute(
                    """
                    UPDATE virtual_positions SET sl = ?, tp = ?
                    WHERE channel_id = ? AND config_id = ? AND entry_message_id = ? AND status = 'OPEN'
                    """,
                    (float(sl_val), float(tp_val), int(channel_id), int(cfg["config_id"]), str(entry_message_id)),
                )
            elif sl_val is not None:
                conn.execute(
                    """
                    UPDATE virtual_positions SET sl = ?
                    WHERE channel_id = ? AND config_id = ? AND entry_message_id = ? AND status = 'OPEN'
                    """,
                    (float(sl_val), int(channel_id), int(cfg["config_id"]), str(entry_message_id)),
                )
            else:
                conn.execute(
                    """
                    UPDATE virtual_positions SET tp = ?
                    WHERE channel_id = ? AND config_id = ? AND entry_message_id = ? AND status = 'OPEN'
                    """,
                    (float(tp_val), int(channel_id), int(cfg["config_id"]), str(entry_message_id)),
                )
            conn.commit()
            return len(row)
    except Exception:
        return 0

def _virtual_close_positions(channel_id, cfg, entry_message_id, symbol, side, close_pnl_pips=None):
    closed = []
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, symbol, side, volume, entry_price
                FROM virtual_positions
                WHERE channel_id = ? AND config_id = ? AND entry_message_id = ? AND status = 'OPEN'
                """,
                (int(channel_id), int(cfg["config_id"]), str(entry_message_id)),
            ).fetchall()
            for r in rows:
                sid = str(r["symbol"])
                sside = str(r["side"]).upper()
                vol = float(r["volume"])
                entry_price = float(r["entry_price"])

                # Siempre cerramos virtual por precio de mercado actual.
                # close_pnl_pips se ignora por consistencia/fiabilidad.
                close_side = "SELL" if sside == "BUY" else "BUY"
                close_price = _price_now(sid, close_side)
                pnl_pips = _pips_between(sid, sside, entry_price, close_price)

                pnl_usd = _order_calc_profit_usd(sid, sside, vol, entry_price, close_price)
                conn.execute(
                    """
                    UPDATE virtual_positions
                    SET status = 'CLOSED', closed_at = ?, close_price = ?, pnl_usd = ?, pnl_pips = ?
                    WHERE id = ?
                    """,
                    (
                        _now_iso(),
                        float(close_price),
                        float(pnl_usd) if pnl_usd is not None else None,
                        float(pnl_pips) if pnl_pips is not None else None,
                        int(r["id"]),
                    ),
                )
                closed.append(
                    {
                        "id": int(r["id"]),
                        "pnl_usd": pnl_usd,
                        "pnl_pips": pnl_pips,
                    }
                )
            conn.commit()
    except Exception:
        return []
    return closed


def _sync_live_operation_metrics():
    try:
        # Si MT5 no responde, no actualizar estados para evitar cierres falsos.
        if mt5.terminal_info() is None or mt5.account_info() is None:
            _mark_mt5_disconnected()
            return
        live_positions = mt5.positions_get()
        if live_positions is None:
            _mark_mt5_disconnected()
            return
        live_orders = mt5.orders_get()
        if live_orders is None:
            _mark_mt5_disconnected()
            return

        pos_by_ticket = {}
        ord_by_ticket = {}
        pos_by_comment = {}
        ord_by_comment = {}
        for p in (live_positions or []):
            try:
                t = int(getattr(p, "ticket", 0))
                if t > 0:
                    pos_by_ticket[t] = p
            except Exception:
                pass
            c = str(getattr(p, "comment", "") or "").strip()
            if c:
                pos_by_comment.setdefault(c, []).append(p)
        for o in (live_orders or []):
            try:
                t = int(getattr(o, "ticket", 0))
                if t > 0:
                    ord_by_ticket[t] = o
            except Exception:
                pass
            c = str(getattr(o, "comment", "") or "").strip()
            if c:
                ord_by_comment.setdefault(c, []).append(o)
        live_ticket_set = set(pos_by_ticket.keys()).union(set(ord_by_ticket.keys()))
        live_comment_set = set(pos_by_comment.keys()).union(set(ord_by_comment.keys()))

        def _pick_by_symbol_side(candidates, expected_symbol: str, expected_side: str, *, is_position: bool):
            if not candidates:
                return None
            exp_symbol = str(expected_symbol or "").upper()
            exp_side = str(expected_side or "").upper()
            for it in candidates:
                sym = str(getattr(it, "symbol", "") or "").upper()
                if exp_symbol and sym != exp_symbol:
                    continue
                if is_position and exp_side in ("BUY", "SELL"):
                    it_side = "BUY" if int(getattr(it, "type", 0)) == int(mt5.POSITION_TYPE_BUY) else "SELL"
                    if it_side != exp_side:
                        continue
                return it
            return candidates[0]

        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, mode, status, symbol, side, ticket, comment, volume, entry_price, sl, tp, opened_at, missing_from_mt5_checks,
                       channel_id, channel_name, channel_index, preset_id, preset_name, execution_profile, entry_message_id
                FROM operation_records
                WHERE status IN ('OPEN', 'PENDING')
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                op_id = int(row["id"])
                mode = str(row["mode"] or "")
                status = str(row["status"] or "").upper()
                symbol = str(row["symbol"] or "")
                side = str(row["side"] or "").upper()
                now = _now_iso()

                if mode == "virtual":
                    entry_price = _safe_float_or_none(row["entry_price"])
                    volume = _safe_float_or_none(row["volume"])
                    if not symbol or side not in ("BUY", "SELL") or entry_price is None:
                        continue
                    try:
                        close_side = "SELL" if side == "BUY" else "BUY"
                        close_price = _price_now(symbol, close_side)
                        live_pips = _pips_between(symbol, side, float(entry_price), float(close_price))
                        live_usd = _order_calc_profit_usd(symbol, side, float(volume or 0.0), float(entry_price), float(close_price))
                    except Exception:
                        continue
                    sl_val = _safe_float_or_none(row["sl"])
                    tp_val = _safe_float_or_none(row["tp"])
                    hit_sl = False
                    hit_tp = False
                    if VIRTUAL_AUTOCLOSE_SLTP:
                        if side == "BUY":
                            hit_sl = sl_val is not None and float(close_price) <= float(sl_val)
                            hit_tp = tp_val is not None and float(close_price) >= float(tp_val)
                        else:
                            hit_sl = sl_val is not None and float(close_price) >= float(sl_val)
                            hit_tp = tp_val is not None and float(close_price) <= float(tp_val)
                    if hit_sl or hit_tp:
                        close_reason = "SL tocado (virtual)" if hit_sl else "TP tocado (virtual)"
                        close_source = "virtual_sl_hit" if hit_sl else "virtual_tp_hit"
                        _operation_mark_closed(
                            conn,
                            op_id,
                            status="CLOSED",
                            close_reason=close_reason,
                            close_source=close_source,
                            close_details=f"auto_close price={close_price}",
                            pnl_usd=_safe_float_or_none(live_usd),
                            pnl_pips=_safe_float_or_none(live_pips),
                        )
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="close",
                            status="CLOSED",
                            pnl_usd=_safe_float_or_none(live_usd),
                            pnl_pips=_safe_float_or_none(live_pips),
                            details=f"{close_source};price={close_price}",
                        )
                        conn.execute(
                            """
                            UPDATE virtual_positions
                            SET status = 'CLOSED', closed_at = ?, close_price = ?, pnl_usd = ?, pnl_pips = ?
                            WHERE channel_id = ? AND config_id = ? AND entry_message_id = ? AND status = 'OPEN'
                            """,
                            (
                                now,
                                _safe_float_or_none(close_price),
                                _safe_float_or_none(live_usd),
                                _safe_float_or_none(live_pips),
                                int(row["channel_id"]) if row["channel_id"] is not None else -1,
                                int(row["preset_id"]) if row["preset_id"] is not None else -1,
                                str(row["entry_message_id"] or ""),
                            ),
                        )
                        conn.execute(
                            """
                            INSERT INTO strategy_event_log (
                                ts, event_id, message_id, channel_id, channel_name, config_id, config_name, mode,
                                event_type, symbol, side, operator_class, entry_message_id, reply_to, status, error_type,
                                pnl_usd, pnl_pips, details
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                now,
                                f"virtual_auto_close:{op_id}:{int(time.time()*1000)}",
                                "",
                                int(row["channel_id"]) if row["channel_id"] is not None else None,
                                str(row["channel_name"] or ""),
                                int(row["preset_id"]) if row["preset_id"] is not None else None,
                                str(row["preset_name"] or ""),
                                "virtual",
                                "close",
                                symbol,
                                side,
                                str(row["execution_profile"] or ""),
                                str(row["entry_message_id"] or ""),
                                "",
                                "OK",
                                "",
                                _safe_float_or_none(live_usd),
                                _safe_float_or_none(live_pips),
                                f"{close_source};price={close_price}",
                            ),
                        )
                        continue
                    conn.execute(
                        """
                        UPDATE operation_records
                        SET status = 'OPEN',
                            last_pips = ?,
                            last_profit_usd = ?,
                            last_sync_at = ?,
                            missing_from_mt5_checks = 0,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            _safe_float_or_none(live_pips),
                            _safe_float_or_none(live_usd),
                            now,
                            now,
                            op_id,
                        ),
                    )
                    continue

                ticket = _normalize_id(row["ticket"])
                comment = str(row["comment"] or "").strip()
                channel_index = _normalize_id(row["channel_index"])
                entry_message_id = _normalize_id(row["entry_message_id"])
                expected_style = _normalize_profile_code(row["execution_profile"], default="SWING")
                ticket_i = None
                if ticket:
                    try:
                        ticket_i = int(ticket)
                    except Exception:
                        ticket_i = None

                matched_pos = None
                matched_ord = None
                matched_ticket = ticket_i
                matched_comment = comment
                matched_by = "none"

                if ticket_i is not None:
                    if ticket_i in pos_by_ticket:
                        matched_pos = pos_by_ticket[ticket_i]
                        matched_by = "ticket_position"
                    elif ticket_i in ord_by_ticket:
                        matched_ord = ord_by_ticket[ticket_i]
                        matched_by = "ticket_order"

                if matched_pos is None and matched_ord is None and comment:
                    pcands = pos_by_comment.get(comment, [])
                    ocands = ord_by_comment.get(comment, [])
                    mp = _pick_by_symbol_side(pcands, symbol, side, is_position=True)
                    mo = _pick_by_symbol_side(ocands, symbol, side, is_position=False)
                    if mp is not None:
                        matched_pos = mp
                        matched_by = "comment_position"
                    elif mo is not None:
                        matched_ord = mo
                        matched_by = "comment_order"
                    if matched_pos is not None or matched_ord is not None:
                        try:
                            matched_ticket = int(getattr((matched_pos or matched_ord), "ticket", 0))
                        except Exception:
                            matched_ticket = ticket_i
                        matched_comment = str(getattr((matched_pos or matched_ord), "comment", "") or "").strip() or comment

                lookup_method = ""
                if matched_pos is None and matched_ord is None and entry_message_id:
                    rtickets, rcomments, lookup_method = _resolve_tickets_and_comments(
                        channel_index,
                        entry_message_id,
                        expected_style,
                    )
                    for tk in _ticket_set(rtickets):
                        if int(tk) in pos_by_ticket:
                            matched_pos = pos_by_ticket[int(tk)]
                            matched_ticket = int(tk)
                            matched_comment = str(getattr(matched_pos, "comment", "") or "").strip() or comment
                            matched_by = f"resolver_ticket_position:{lookup_method}"
                            break
                        if int(tk) in ord_by_ticket:
                            matched_ord = ord_by_ticket[int(tk)]
                            matched_ticket = int(tk)
                            matched_comment = str(getattr(matched_ord, "comment", "") or "").strip() or comment
                            matched_by = f"resolver_ticket_order:{lookup_method}"
                            break
                    if matched_pos is None and matched_ord is None:
                        for cm in _uniq_text(rcomments):
                            if cm in pos_by_comment:
                                matched_pos = _pick_by_symbol_side(pos_by_comment.get(cm), symbol, side, is_position=True)
                                matched_by = f"resolver_comment_position:{lookup_method}"
                                if matched_pos is not None:
                                    matched_comment = str(getattr(matched_pos, "comment", "") or "").strip() or cm
                                    try:
                                        matched_ticket = int(getattr(matched_pos, "ticket", 0))
                                    except Exception:
                                        pass
                                    break
                            if cm in ord_by_comment:
                                matched_ord = _pick_by_symbol_side(ord_by_comment.get(cm), symbol, side, is_position=False)
                                matched_by = f"resolver_comment_order:{lookup_method}"
                                if matched_ord is not None:
                                    matched_comment = str(getattr(matched_ord, "comment", "") or "").strip() or cm
                                    try:
                                        matched_ticket = int(getattr(matched_ord, "ticket", 0))
                                    except Exception:
                                        pass
                                    break

                if matched_pos is not None:
                    p = matched_pos
                    rside = side if side in ("BUY", "SELL") else ("BUY" if int(p.type) == int(mt5.POSITION_TYPE_BUY) else "SELL")
                    close_side = "SELL" if rside == "BUY" else "BUY"
                    try:
                        close_price = _price_now(str(p.symbol), close_side)
                        live_pips = _pips_between(str(p.symbol), rside, float(p.price_open), float(close_price))
                    except Exception:
                        live_pips = None
                    live_usd = _safe_float_or_none(getattr(p, "profit", None))
                    conn.execute(
                        """
                        UPDATE operation_records
                        SET status = 'OPEN',
                            ticket = ?,
                            comment = ?,
                            sl = ?, tp = ?,
                            last_pips = ?,
                            last_profit_usd = ?,
                            last_sync_at = ?,
                            missing_from_mt5_checks = 0,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            str(matched_ticket or ""),
                            str(matched_comment or ""),
                            _safe_float_or_none(getattr(p, "sl", None)),
                            _safe_float_or_none(getattr(p, "tp", None)),
                            _safe_float_or_none(live_pips),
                            _safe_float_or_none(live_usd),
                            now,
                            now,
                            op_id,
                        ),
                    )
                    continue

                if matched_ord is not None:
                    conn.execute(
                        """
                        UPDATE operation_records
                        SET status = 'PENDING',
                            ticket = ?,
                            comment = ?,
                            last_sync_at = ?,
                            missing_from_mt5_checks = 0,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (str(matched_ticket or ""), str(matched_comment or ""), now, now, op_id),
                    )
                    continue

                # No aparece ni en posiciones ni pendientes.
                missing_checks = int(row["missing_from_mt5_checks"] or 0) + 1
                if status in ("OPEN", "PENDING"):
                    if missing_checks < MANUAL_CLOSE_CONFIRM_CHECKS:
                        conn.execute(
                            """
                            UPDATE operation_records
                            SET missing_from_mt5_checks = ?,
                                last_sync_at = ?,
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (missing_checks, now, now, op_id),
                        )
                    else:
                        ticket_info = str(ticket_i) if ticket_i is not None else "-"
                        resolver_hint = f";resolver={lookup_method}" if lookup_method else ""
                        _operation_mark_closed(
                            conn,
                            op_id,
                            status="CLOSED",
                            close_reason="No visible en MT5 en múltiples chequeos: posible cierre/cancelación manual.",
                            close_source="manual_mt5",
                            close_details=f"ticket={ticket_info};missing_checks={missing_checks};matched_by={matched_by}{resolver_hint}",
                        )
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="system",
                            status="CLOSED",
                            details=f"manual_mt5_detected ticket={ticket_info};missing_checks={missing_checks};matched_by={matched_by}{resolver_hint}",
                        )
                        if ticket_i is not None:
                            open_trades_delete_by_tickets([ticket_i])
                        if matched_ticket is not None and matched_ticket != ticket_i:
                            open_trades_delete_by_tickets([matched_ticket])

            conn.commit()
    except Exception:
        pass


def _bootstrap_operation_records():
    try:
        _ensure_open_trades()
        open_df = _load_open_trades()
    except Exception:
        open_df = pd.DataFrame(columns=OPEN_TRADES_FIELDS)
    try:
        with _db_conn() as conn:
            op_total = int(conn.execute("SELECT COUNT(1) FROM operation_records").fetchone()[0])
            if op_total > 0:
                # Reinicio normal: no rehidratar ni mutar registros existentes.
                return
            live_pos_tickets, live_ord_tickets = _live_mt5_ticket_sets()
            live_tickets = {str(t) for t in live_pos_tickets.union(live_ord_tickets)}
            if not open_df.empty:
                for _, row in open_df.iterrows():
                    ch_idx = _normalize_id(row.get("channel_index", ""))
                    entry_id = _normalize_id(row.get("entry_message_id", ""))
                    style = _normalize_profile_code(row.get("style", "SWING"), default="SWING")
                    symbol = str(row.get("symbol", "") or "")
                    side = str(row.get("side", "") or "").upper()
                    if not entry_id or not symbol:
                        continue
                    t_norm = _normalize_id(row.get("ticket", ""))
                    if t_norm and live_tickets and t_norm not in live_tickets:
                        # Fila vieja en open_trades (no visible en MT5): no rehidratar.
                        continue
                    status = str(row.get("status", "OPEN") or "OPEN").upper()
                    op_key = _operation_key_real(ch_idx, entry_id, style)
                    existing = conn.execute(
                        "SELECT id, status FROM operation_records WHERE operation_key = ?",
                        (op_key,),
                    ).fetchone()
                    if existing:
                        # En reinicio normal no mutar registros existentes.
                        continue
                    meta = conn.execute(
                        """
                        SELECT channel_id, channel_name, config_id, config_name
                        FROM strategy_event_log
                        WHERE mode = 'real' AND event_type = 'entry' AND entry_message_id = ?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (entry_id,),
                    ).fetchone()
                    op_id = _operation_upsert_entry(
                        conn,
                        operation_key=op_key,
                        mode="real",
                        status="PENDING" if status == "PENDING" else "OPEN",
                        is_virtual=False,
                        channel_id=int(meta["channel_id"]) if meta and meta["channel_id"] is not None else None,
                        channel_name=str(meta["channel_name"] if meta else "") or "",
                        channel_index=ch_idx,
                        preset_id=int(meta["config_id"]) if meta and meta["config_id"] is not None else None,
                        preset_name=str(meta["config_name"] if meta else "") or "",
                        execution_profile=style,
                        symbol=symbol,
                        side=side,
                        entry_message_id=entry_id,
                        entry_event_id="",
                        entry_trigger_message_id=entry_id,
                        entry_ts=str(row.get("opened_at", "") or ""),
                        ticket=row.get("ticket", ""),
                        comment=row.get("comment", ""),
                        volume=row.get("volume", ""),
                        entry_price=row.get("entry_price_used", ""),
                        sl=row.get("sl", ""),
                        tp=row.get("tp", ""),
                    )
                    _operation_event_add(
                        conn,
                        op_id,
                        event_type="system",
                        status="OPEN" if status != "PENDING" else "PENDING",
                        details="bootstrap_from_open_trades_insert_only",
                    )

            vrows = conn.execute(
                """
                SELECT channel_id, channel_name, config_id, config_name, entry_message_id,
                       symbol, side, volume, entry_price, sl, tp, opened_at
                FROM virtual_positions
                WHERE status = 'OPEN'
                """
            ).fetchall()
            profile_by_config: dict[int, str] = {}
            try:
                prow = conn.execute(
                    """
                    SELECT p.id AS config_id, COALESCE(ep.code, 'SWING') AS profile_code
                    FROM operator_presets p
                    LEFT JOIN execution_profiles ep ON ep.id = p.execution_profile_id
                    """
                ).fetchall()
                for pr in prow:
                    profile_by_config[int(pr["config_id"])] = _normalize_profile_code(pr["profile_code"], default="SWING")
            except Exception:
                profile_by_config = {}
            for v in vrows:
                v_config_id = int(v["config_id"])
                v_profile = profile_by_config.get(v_config_id, "SWING")
                v_key = _operation_key_virtual(v["channel_id"], v["config_id"], v["entry_message_id"])
                v_existing = conn.execute(
                    "SELECT id FROM operation_records WHERE operation_key = ?",
                    (v_key,),
                ).fetchone()
                if v_existing:
                    continue
                op_id = _operation_upsert_entry(
                    conn,
                    operation_key=v_key,
                    mode="virtual",
                    status="OPEN",
                    is_virtual=True,
                    channel_id=int(v["channel_id"]),
                    channel_name=str(v["channel_name"] or ""),
                    channel_index="",
                    preset_id=v_config_id,
                    preset_name=str(v["config_name"] or ""),
                    execution_profile=v_profile,
                    symbol=str(v["symbol"] or ""),
                    side=str(v["side"] or "").upper(),
                    entry_message_id=_normalize_id(v["entry_message_id"]),
                    entry_event_id="",
                    entry_trigger_message_id=_normalize_id(v["entry_message_id"]),
                    entry_ts=str(v["opened_at"] or ""),
                    volume=v["volume"],
                    entry_price=v["entry_price"],
                    sl=v["sl"],
                    tp=v["tp"],
                )
                _operation_event_add(
                    conn,
                    op_id,
                    event_type="system",
                    status="OPEN",
                    details="bootstrap_from_virtual_positions",
                )

            conn.commit()
    except Exception:
        pass

# =============== MT5 & helpers ===============
def mt5_init():
    try:
        mt5.shutdown()
    except Exception:
        pass

    if not (MT5_LOGIN and MT5_PASSWORD and MT5_SERVER):
        raise RuntimeError("Faltan credenciales MT5 (MT5_LOGIN/MT5_PASSWORD/MT5_SERVER)")

    if not TERMINAL_PATH or not os.path.exists(TERMINAL_PATH):
        raise RuntimeError(f"MT5 terminal no encontrado: {TERMINAL_PATH}")

    server = str(MT5_SERVER).strip()
    login = int(MT5_LOGIN)
    password = str(MT5_PASSWORD)

    # Algunos terminales fallan con "Authorization failed" si se inicializan
    # usando una sesion guardada vieja. Primero inicializamos ya autenticando.
    init_ok = mt5.initialize(
        path=TERMINAL_PATH,
        login=login,
        password=password,
        server=server,
        timeout=MT5_TIMEOUT_MS,
        portable=MT5_PORTABLE,
    )
    init_error = mt5.last_error()
    if not init_ok:
        try:
            mt5.shutdown()
        except Exception:
            pass
        # Fallback compatible con instalaciones donde el terminal necesita
        # abrir primero y loguear despues.
        init_ok = mt5.initialize(
            path=TERMINAL_PATH,
            timeout=MT5_TIMEOUT_MS,
            portable=MT5_PORTABLE,
        )
        if not init_ok:
            raise RuntimeError(f"MT5 initialize failed: {init_error}; fallback={mt5.last_error()}")

    time.sleep(0.5)
    if not mt5.login(login=login, password=password, server=server):
        raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")

    if SYMBOLS_ALWAYS_SELECT:
        for s in SYMBOLS_ALWAYS_SELECT:
            try:
                mt5.symbol_select(s, True)
            except Exception:
                pass
    _validate_watchlist_symbols()


def _mt5_connection_alive() -> bool:
    try:
        return mt5.terminal_info() is not None and mt5.account_info() is not None
    except Exception:
        return False


def _mark_mt5_disconnected() -> None:
    global _mt5_ready, _mt5_reconnect_attempts, _mt5_next_reconnect_ts
    _mt5_ready = False
    _mt5_reconnect_attempts = max(0, int(_mt5_reconnect_attempts))
    if _mt5_next_reconnect_ts <= 0:
        _mt5_next_reconnect_ts = time.time()


def _ensure_mt5_connection() -> bool:
    global _mt5_ready, _mt5_reconnect_attempts, _mt5_next_reconnect_ts
    if _mt5_connection_alive():
        if not _mt5_ready:
            print("[MT5] conexión restaurada.")
        _mt5_ready = True
        _mt5_reconnect_attempts = 0
        _mt5_next_reconnect_ts = 0.0
        return True

    now = time.time()
    if now < float(_mt5_next_reconnect_ts or 0.0):
        return False

    try:
        mt5_init()
        if _mt5_connection_alive():
            if not _mt5_ready:
                print("[MT5] reconexión exitosa.")
            _mt5_ready = True
            _mt5_reconnect_attempts = 0
            _mt5_next_reconnect_ts = 0.0
            return True
    except Exception as e:
        _mt5_reconnect_attempts += 1
        backoff = min(MT5_RECONNECT_MAX_SEC, MT5_RECONNECT_BASE_SEC * (2 ** min(6, _mt5_reconnect_attempts - 1)))
        _mt5_next_reconnect_ts = now + backoff
        print(f"[MT5] reconexión fallida intento={_mt5_reconnect_attempts} next_in={backoff}s err={e}")
        _mt5_ready = False
        return False

    _mt5_ready = False
    _mt5_reconnect_attempts += 1
    backoff = min(MT5_RECONNECT_MAX_SEC, MT5_RECONNECT_BASE_SEC * (2 ** min(6, _mt5_reconnect_attempts - 1)))
    _mt5_next_reconnect_ts = now + backoff
    print(f"[MT5] desconectado; reintento en {backoff}s")
    return False

def _symbol_candidates(base_symbol: str):
    base = str(base_symbol or "").upper().strip()
    if not base:
        return []
    candidates = [base]
    for alt in SYMBOL_ALIASES.get(base, []):
        candidates.append(str(alt).upper().strip())
    try:
        all_symbols = mt5.symbols_get()
    except Exception:
        all_symbols = None
    if all_symbols:
        for s in all_symbols:
            name = str(getattr(s, "name", "") or "").upper().strip()
            if not name:
                continue
            if name.startswith(base):
                candidates.append(name)
    seen = set()
    ordered = []
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        ordered.append(c)
    return ordered

def _symbol_ready_info(symbol_name: str):
    info = mt5.symbol_info(symbol_name)
    if not info:
        return False, "not_found", None
    selected = bool(mt5.symbol_select(symbol_name, True))
    info2 = mt5.symbol_info(symbol_name)
    trade_mode = getattr(info2, "trade_mode", None)
    visible = bool(getattr(info2, "visible", False))
    tick = mt5.symbol_info_tick(symbol_name)

    disabled_mode = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)
    if trade_mode == disabled_mode:
        return False, "trade_disabled", symbol_name
    if not selected or not visible:
        return False, "not_visible", symbol_name
    if tick is None:
        return False, "no_tick", symbol_name
    return True, "ready", symbol_name

def _validate_watchlist_symbols():
    required = [str(s).upper().strip() for s in (SYMBOLS_REQUIRED or []) if str(s).strip()]
    if not required:
        print("[WATCHLIST] No hay símbolos requeridos configurados.")
        return

    ready = []
    failed = []

    for req in required:
        ok = False
        last_reason = "not_found"
        resolved = req
        for candidate in _symbol_candidates(req):
            is_ready, reason, resolved_name = _symbol_ready_info(candidate)
            resolved = resolved_name or candidate
            last_reason = reason
            if is_ready:
                ready.append((req, resolved))
                ok = True
                break
        if not ok:
            failed.append((req, resolved, last_reason))

    print(f"[WATCHLIST] Ready: {len(ready)} | Failed: {len(failed)}")
    if ready:
        print("[WATCHLIST] Símbolos listos:", ", ".join([f"{src}->{dst}" for src, dst in ready]))
    if failed:
        print("[WATCHLIST] No listos:", ", ".join([f"{src}->{dst}({reason})" for src, dst, reason in failed]))

def resolve_symbol(broker_symbol: str) -> str:
    s = (broker_symbol or "").upper()
    info = mt5.symbol_info(s)
    if info:
        mt5.symbol_select(s, True)
        return s
    for alt in [a.upper() for a in SYMBOL_ALIASES.get(s, [])]:
        info = mt5.symbol_info(alt)
        if info:
            mt5.symbol_select(alt, True)
            return alt
    mt5.symbol_select(s, True)
    return s

def _price_now(symbol: str, side: str):
    info = mt5.symbol_info_tick(symbol)
    if info is None:
        sinfo = mt5.symbol_info(symbol)
        raise RuntimeError(
            f"No tick for {symbol} (selected={bool(sinfo)}, visible={getattr(sinfo,'visible','NA')})"
        )
    return info.ask if side.upper()=="BUY" else info.bid

def _pip_size(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.0001
    if info.digits in (3, 5):
        return info.point * 10
    return info.point or 0.0001

def _spread_pips(symbol: str):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    pip = _pip_size(symbol)
    if pip <= 0:
        return None
    return (tick.ask - tick.bid) / pip

def _filling():
    return int(FILLING_MODE)

def _candidate_fillings(symbol: str):
    candidates = []
    info = mt5.symbol_info(symbol)
    if info and info.filling_mode is not None:
        candidates.append(int(info.filling_mode))

    candidates.append(_filling())

    for mode in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN):
        candidates.append(int(mode))

    seen = set()
    ordered = []
    for m in candidates:
        if m in seen:
            continue
        seen.add(m)
        ordered.append(m)
    return ordered

def _send_with_fallback(build_request, build_args, symbol: str):
    last = None
    for mode in _candidate_fillings(symbol):
        req = build_request(*build_args, filling=mode)
        result = mt5.order_send(req)
        if result is None:
            last = None
            continue
        if result.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
            return result
        if result.retcode == mt5.TRADE_RETCODE_INVALID_FILL or "Unsupported filling mode" in str(result.comment):
            last = result
            continue
        return result
    return last

def _list_queue_files():
    if not os.path.exists(EVENTS_QUEUE_DIR):
        return []
    files = []
    for name in os.listdir(EVENTS_QUEUE_DIR):
        if name.lower().endswith(".json"):
            files.append(os.path.join(EVENTS_QUEUE_DIR, name))
    files.sort(key=os.path.getmtime)
    return files

def _load_queue_event(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _mark_queue_processed(path: str):
    os.makedirs(EVENTS_QUEUE_PROCESSED_DIR, exist_ok=True)
    dest = os.path.join(EVENTS_QUEUE_PROCESSED_DIR, os.path.basename(path))
    try:
        os.replace(path, dest)
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass


def _queue_event_id(path: str, event_obj: dict | None = None) -> str:
    ev = event_obj or {}
    eid = str(ev.get("event_id", "") or "").strip()
    if eid:
        return eid
    name = os.path.basename(path)
    if name.lower().endswith(".json"):
        return name[:-5]
    return name


def _queue_register_failure(path: str, event_obj: dict | None, err_text: str) -> int:
    event_path = os.path.basename(path)
    event_id = _queue_event_id(path, event_obj)
    now = _now_iso()
    retries = 1
    try:
        with _db_conn() as conn:
            row = conn.execute(
                "SELECT retries FROM queue_event_failures WHERE event_path = ?",
                (event_path,),
            ).fetchone()
            if row:
                retries = int(row["retries"] or 0) + 1
                conn.execute(
                    """
                    UPDATE queue_event_failures
                    SET event_id = ?, retries = ?, last_error = ?, last_seen = ?, quarantined = 0
                    WHERE event_path = ?
                    """,
                    (event_id, retries, str(err_text or ""), now, event_path),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO queue_event_failures (
                        event_path, event_id, retries, last_error, first_seen, last_seen, quarantined
                    ) VALUES (?, ?, 1, ?, ?, ?, 0)
                    """,
                    (event_path, event_id, str(err_text or ""), now, now),
                )
            conn.commit()
    except Exception:
        pass
    return retries


def _queue_mark_quarantined(path: str):
    event_path = os.path.basename(path)
    try:
        with _db_conn() as conn:
            conn.execute(
                """
                UPDATE queue_event_failures
                SET quarantined = 1, last_seen = ?
                WHERE event_path = ?
                """,
                (_now_iso(), event_path),
            )
            conn.commit()
    except Exception:
        pass


def _queue_clear_failure(path: str):
    event_path = os.path.basename(path)
    try:
        with _db_conn() as conn:
            conn.execute("DELETE FROM queue_event_failures WHERE event_path = ?", (event_path,))
            conn.commit()
    except Exception:
        pass


def _queue_quarantine_file(path: str):
    os.makedirs(QUEUE_FAILED_DIR, exist_ok=True)
    stamp = datetime.datetime.now(URUGUAY_TZ).strftime("%Y%m%d_%H%M%S")
    name = os.path.basename(path)
    dest = os.path.join(QUEUE_FAILED_DIR, f"{stamp}__{name}")
    try:
        os.replace(path, dest)
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
    _queue_mark_quarantined(path)


def _retry_delay_seconds(retries: int) -> int:
    r = max(1, int(retries))
    delay = EVENT_RETRY_BASE_SEC * (2 ** max(0, r - 1))
    return int(min(EVENT_RETRY_MAX_SEC, max(EVENT_RETRY_BASE_SEC, delay)))


def _event_retry_is_due(event_uid: str) -> bool:
    suid = str(event_uid or "").strip()
    if not suid:
        return True
    try:
        with _db_conn() as conn:
            row = conn.execute(
                """
                SELECT retries, quarantined, next_retry_at
                FROM event_retry_state
                WHERE event_uid = ?
                """,
                (suid,),
            ).fetchone()
    except Exception:
        return True
    if not row:
        return True
    if int(row["quarantined"] or 0) != 0:
        return False
    next_retry_at = str(row["next_retry_at"] or "").strip()
    if not next_retry_at:
        return True
    next_dt = _parse_iso_or_none(next_retry_at)
    if next_dt is None:
        return True
    now_dt = _parse_iso_or_none(_now_iso())
    if now_dt is None:
        return True
    return now_dt >= next_dt


def _event_retry_register(event_uid: str, err_text: str, *, error_type: str = "runtime") -> int:
    suid = str(event_uid or "").strip()
    if not suid:
        return 0
    now = _now_iso()
    retries = 1
    quarantined = 0
    try:
        with _db_conn() as conn:
            row = conn.execute(
                """
                SELECT retries
                FROM event_retry_state
                WHERE event_uid = ?
                """,
                (suid,),
            ).fetchone()
            if row:
                retries = int(row["retries"] or 0) + 1
                quarantined = 1 if retries >= EVENT_RETRY_MAX else 0
                next_retry_at = _uy_from_epoch_iso(time.time() + _retry_delay_seconds(retries))
                conn.execute(
                    """
                    UPDATE event_retry_state
                    SET retries = ?, last_error = ?, last_error_type = ?, next_retry_at = ?,
                        quarantined = ?, updated_at = ?
                    WHERE event_uid = ?
                    """,
                    (
                        retries,
                        str(err_text or ""),
                        str(error_type or "runtime"),
                        next_retry_at,
                        quarantined,
                        now,
                        suid,
                    ),
                )
            else:
                next_retry_at = _uy_from_epoch_iso(time.time() + _retry_delay_seconds(retries))
                conn.execute(
                    """
                    INSERT INTO event_retry_state (
                        event_uid, retries, last_error, last_error_type, next_retry_at, quarantined, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        suid,
                        retries,
                        str(err_text or ""),
                        str(error_type or "runtime"),
                        next_retry_at,
                        now,
                        now,
                    ),
                )
            conn.commit()
    except Exception:
        pass
    return retries


def _event_retry_mark_permanent(event_uid: str, err_text: str, *, error_type: str = "permanent") -> None:
    suid = str(event_uid or "").strip()
    if not suid:
        return
    now = _now_iso()
    try:
        with _db_conn() as conn:
            row = conn.execute("SELECT retries FROM event_retry_state WHERE event_uid = ?", (suid,)).fetchone()
            retries = int(row["retries"] or 0) if row else 0
            conn.execute(
                """
                INSERT INTO event_retry_state (
                    event_uid, retries, last_error, last_error_type, next_retry_at, quarantined, created_at, updated_at
                ) VALUES (?, ?, ?, ?, '', 1, ?, ?)
                ON CONFLICT(event_uid) DO UPDATE SET
                    retries = excluded.retries,
                    last_error = excluded.last_error,
                    last_error_type = excluded.last_error_type,
                    next_retry_at = '',
                    quarantined = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    suid,
                    retries,
                    str(err_text or ""),
                    str(error_type or "permanent"),
                    now,
                    now,
                ),
            )
            conn.commit()
    except Exception:
        pass


def _event_retry_clear(event_uid: str) -> None:
    suid = str(event_uid or "").strip()
    if not suid:
        return
    try:
        with _db_conn() as conn:
            conn.execute("DELETE FROM event_retry_state WHERE event_uid = ?", (suid,))
            conn.commit()
    except Exception:
        pass


def _event_retry_due_exists() -> bool:
    now_dt = _parse_iso_or_none(_now_iso())
    if now_dt is None:
        return False
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT next_retry_at
                FROM event_retry_state
                WHERE quarantined = 0
                """
            ).fetchall()
    except Exception:
        return False
    for r in rows:
        next_ts = str(r["next_retry_at"] or "").strip()
        if not next_ts:
            return True
        next_dt = _parse_iso_or_none(next_ts)
        if next_dt is None or now_dt >= next_dt:
            return True
    return False


RETRYABLE_MT5_RETCODES = {
    int(getattr(mt5, "TRADE_RETCODE_REQUOTE", -1)),
    int(getattr(mt5, "TRADE_RETCODE_REJECT", -1)),
    int(getattr(mt5, "TRADE_RETCODE_CONNECTION", -1)),
    int(getattr(mt5, "TRADE_RETCODE_TIMEOUT", -1)),
    int(getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", -1)),
    int(getattr(mt5, "TRADE_RETCODE_PRICE_OFF", -1)),
    int(getattr(mt5, "TRADE_RETCODE_TOO_MANY_REQUESTS", -1)),
    int(getattr(mt5, "TRADE_RETCODE_LOCKED", -1)),
    int(getattr(mt5, "TRADE_RETCODE_FROZEN", -1)),
    int(getattr(mt5, "TRADE_RETCODE_NO_CONNECTION", -1)),
}
PERMANENT_MT5_RETCODES = {
    int(getattr(mt5, "TRADE_RETCODE_SERVER_DISABLES_AT", 10026)),
    int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)),
    int(getattr(mt5, "TRADE_RETCODE_TRADE_DISABLED", 10017)),
    int(getattr(mt5, "TRADE_RETCODE_MARKET_CLOSED", 10018)),
    int(getattr(mt5, "TRADE_RETCODE_NO_MONEY", 10019)),
    int(getattr(mt5, "TRADE_RETCODE_INVALID_STOPS", 10016)),
    int(getattr(mt5, "TRADE_RETCODE_INVALID_VOLUME", 10014)),
}


def _mt5_retcode_user_message(retcode, comment="") -> str:
    try:
        code = int(retcode)
    except Exception:
        code = None
    raw_comment = str(comment or "").strip()
    low = raw_comment.lower()
    client_disabled = int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027))
    server_disabled = int(getattr(mt5, "TRADE_RETCODE_SERVER_DISABLES_AT", 10026))
    trade_disabled = int(getattr(mt5, "TRADE_RETCODE_TRADE_DISABLED", 10017))
    market_closed = int(getattr(mt5, "TRADE_RETCODE_MARKET_CLOSED", 10018))
    no_money = int(getattr(mt5, "TRADE_RETCODE_NO_MONEY", 10019))
    invalid_stops = int(getattr(mt5, "TRADE_RETCODE_INVALID_STOPS", 10016))
    invalid_volume = int(getattr(mt5, "TRADE_RETCODE_INVALID_VOLUME", 10014))

    if code == client_disabled or "autotrading disabled" in low or "auto trading disabled" in low:
        return (
            "AutoTrading esta deshabilitado en MT5. "
            "Solucion: abre MetaTrader 5 en Windows y activa el boton 'Algo Trading'/'AutoTrading' "
            "en la barra superior. Tambien revisa Herramientas > Opciones > Expert Advisors y permite trading algoritimico."
        )
    if code == server_disabled:
        return "El servidor/broker deshabilito AutoTrading para esta cuenta o simbolo. Revisa permisos de la cuenta con el broker."
    if code == trade_disabled or "trade disabled" in low:
        return "El trading esta deshabilitado para este simbolo o cuenta. Revisa si el simbolo permite operar y si la cuenta esta habilitada."
    if code == market_closed:
        return "El mercado esta cerrado para este simbolo. Reintenta cuando el mercado este abierto."
    if code == no_money:
        return "Fondos insuficientes o margen insuficiente para abrir la orden. Baja volumen o revisa margen disponible."
    if code == invalid_stops:
        return "SL/TP invalidos para el precio actual. Para BUY el SL debe estar debajo y TP arriba; para SELL al reves."
    if code == invalid_volume:
        return "Volumen invalido para el simbolo. Ajusta TOTAL_VOLUME al minimo/step permitido por el broker."
    return raw_comment or f"MT5 rechazo la orden ret={retcode}"


def _is_retryable_mt5_retcode(retcode) -> bool:
    try:
        code = int(retcode)
    except Exception:
        return False
    if code in PERMANENT_MT5_RETCODES:
        return False
    return code in RETRYABLE_MT5_RETCODES


def _extract_retcode_from_text(text: str):
    m = re.search(r"ret(?:code)?\s*=?\s*(-?\d+)", str(text or ""), flags=re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _is_retryable_error_text(text: str) -> bool:
    raw = str(text or "")
    low = raw.lower()
    if "no positions matched" in low or "no tickets indexed" in low:
        return False
    if "invalid" in low and "price" in low:
        return False
    if "unsupported filling mode" in low:
        return False
    if "autotrading disabled" in low or "auto trading disabled" in low:
        return False
    if "trade disabled" in low or "client disables" in low or "server disables" in low:
        return False
    code = _extract_retcode_from_text(raw)
    if code is not None:
        return _is_retryable_mt5_retcode(code)
    tokens = (
        "timeout",
        "connection",
        "requote",
        "price changed",
        "trade context is busy",
        "temporarily",
        "server busy",
    )
    return any(t in low for t in tokens)


def _queue_error_user_message(error) -> str:
    raw = str(error or "").strip()
    low = raw.lower()
    if "unexpected keyword argument" in low:
        m = re.search(r"unexpected keyword argument ['\"]([^'\"]+)['\"]", raw)
        field = m.group(1) if m else ""
        if field:
            return (
                f"Error interno de compatibilidad: el evento de cola trae el campo '{field}', "
                "pero una funcion del Operador no lo estaba aceptando. "
                "Solucion: actualizar el codigo del Operador y reiniciarlo; el evento queda pendiente para reintento."
            )
        return (
            "Error interno de compatibilidad entre el evento de cola y una funcion del Operador. "
            "Solucion: actualizar el codigo del Operador y reiniciarlo; el evento queda pendiente para reintento."
        )
    if "database is locked" in low:
        return (
            "La base de datos esta ocupada por otro proceso. "
            "Solucion: espera unos segundos o cierra procesos duplicados del bot si quedo mas de uno abierto."
        )
    if "permission denied" in low or "access is denied" in low:
        return (
            "Windows bloqueo el acceso a un archivo que el Operador necesita leer o mover. "
            "Solucion: revisa permisos, antivirus o si el archivo esta abierto en otro programa."
        )
    return raw or "Error desconocido procesando un evento pendiente de la cola."


def normalize_volume(symbol: str, vol: float) -> float:
    info = mt5.symbol_info(symbol)
    if not info:
        return float(f"{vol:.2f}")
    step = info.volume_step or 0.01
    vmin = info.volume_min or 0.01
    vmax = info.volume_max or 100.0
    steps = max(1, int(vol / step + 1e-9))
    v = steps * step
    v = max(vmin, min(v, vmax))
    return float(f"{v:.2f}")

def _parse_float_or_none(value):
    if value in ("", None):
        return None
    if isinstance(value, (int, float, np.floating)):
        if pd.isna(value):
            return None
        return float(value)
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "breakeven", "be"):
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def validate_stops(symbol: str, side: str, entry_price: float, sl, tp):
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.0, 0.0, "No symbol_info"

    point = info.point or 0.0001
    min_dist = (info.trade_stops_level or 0) * point
    warns = []

    s = None if sl in ("", None, np.nan) else float(sl)
    t = None if tp in ("", None, np.nan) else float(tp)

    side_up = side.upper()
    if s is not None:
        if (side_up == "BUY" and not (s < entry_price)) or (side_up == "SELL" and not (s > entry_price)):
            warns.append("SL invalid side; dropped")
            s = None
    if t is not None:
        if (side_up == "BUY" and not (t > entry_price)) or (side_up == "SELL" and not (t < entry_price)):
            warns.append("TP invalid side; dropped")
            t = None

    if s is not None and abs(entry_price - s) < min_dist:
        warns.append(f"SL too close (< {min_dist:.5f}); dropped")
        s = None
    if t is not None and abs(t - entry_price) < min_dist:
        warns.append(f"TP too close (< {min_dist:.5f}); dropped")
        t = None

    s_ok = float(f"{s:.{info.digits}f}") if s is not None else 0.0
    t_ok = float(f"{t:.{info.digits}f}") if t is not None else 0.0
    return s_ok, t_ok, " | ".join(warns)

def _short_id(value, length=6):
    raw = str(value).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:length]

def _mk_comment(channel_index, entry_message_id, style=None):
    base = f"{channel_index}-{entry_message_id}"
    if COMMENT_STYLE_SUFFIX and style:
        base = f"{base}-{style.upper()}"
    if len(base) <= 16:
        return base
    style_code = ""
    if COMMENT_STYLE_SUFFIX and style:
        style_code = style.upper()[0]
    short_id = _short_id(entry_message_id, length=6)
    compact = f"{channel_index}-{short_id}{style_code}"
    return compact if len(compact) <= 16 else compact[:16]

# =============== envío / mod / close ===============
def _deal_request(symbol, volume, side, price, sl=None, tp=None, comment="", filling=None):
    return {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_BUY if side.upper()=="BUY" else mt5.ORDER_TYPE_SELL,
        "price": float(price),
        "sl": float(sl) if sl not in ("", None, np.nan) else 0.0,
        "tp": float(tp) if tp not in ("", None, np.nan) else 0.0,
        "deviation": int(MAX_DEVIATION),
        "magic": int(MAGIC_NUMBER),
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling() if filling is None else int(filling),
    }

def _pending_request(symbol, volume, side, order_type, price, sl=None, tp=None, comment="", filling=None):
    return {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": float(price),
        "sl": float(sl) if sl not in ("", None, np.nan) else 0.0,
        "tp": float(tp) if tp not in ("", None, np.nan) else 0.0,
        "deviation": int(MAX_DEVIATION),
        "magic": int(MAGIC_NUMBER),
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling() if filling is None else int(filling),
    }

def _close_request(symbol, volume, side, price, position, comment="", filling=None):
    return {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_BUY if side.upper()=="BUY" else mt5.ORDER_TYPE_SELL,
        "position": int(position),
        "price": float(price),
        "deviation": int(MAX_DEVIATION),
        "magic": int(MAGIC_NUMBER),
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling() if filling is None else int(filling),
    }

def _log_order_error(event_id, action, symbol, side, volume, comment, result, reason):
    retcode = getattr(result, "retcode", "") if result else ""
    details = _mt5_retcode_user_message(retcode, getattr(result, "comment", "") if result else "") if result else ""
    log_error({
        "timestamp": _now_iso(),
        "event_id": event_id or "",
        "action": action,
        "symbol": symbol,
        "side": side,
        "volume": volume,
        "comment": comment,
        "reason": reason,
        "retcode": retcode,
        "details": details,
    })

def _order_exists_by_comment(symbol: str, comment: str) -> bool:
    positions = mt5.positions_get(symbol=symbol) or []
    for p in positions:
        if p.comment == comment:
            return True
    orders = mt5.orders_get(symbol=symbol) or []
    for o in orders:
        if o.comment == comment:
            return True
    return False


def _track_mt5_result(result) -> None:
    if result is None:
        _mark_mt5_disconnected()
        return
    rc = getattr(result, "retcode", None)
    if _is_retryable_mt5_retcode(rc):
        _mark_mt5_disconnected()


def _post_send_check(result, action, symbol, side, volume, comment, event_id):
    _track_mt5_result(result)
    if result is None:
        _log_order_error(event_id, action, symbol, side, volume, comment, result, "order_send_none")
        return
    if result.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
        _log_order_error(event_id, action, symbol, side, volume, comment, result, "order_send_failed")
        return
    if VERIFY_ORDER_AFTER_SEND:
        found = False
        for _ in range(3):
            if _order_exists_by_comment(symbol, comment):
                found = True
                break
            time.sleep(0.35)
        if not found:
            _log_order_error(event_id, action, symbol, side, volume, comment, result, "not_found_after_send")

def _realized_profit_for_position(position_ticket: int, retries=3):
    for _ in range(max(1, retries)):
        try:
            to_dt = datetime.datetime.now() + datetime.timedelta(minutes=1)
            from_dt = to_dt - datetime.timedelta(days=3)
            deals = mt5.history_deals_get(from_dt, to_dt)
            if deals:
                profit = 0.0
                found = False
                for d in deals:
                    pid = getattr(d, "position_id", None)
                    if pid is None:
                        continue
                    if int(pid) != int(position_ticket):
                        continue
                    found = True
                    profit += float(getattr(d, "profit", 0.0) or 0.0)
                    profit += float(getattr(d, "commission", 0.0) or 0.0)
                    profit += float(getattr(d, "swap", 0.0) or 0.0)
                    profit += float(getattr(d, "fee", 0.0) or 0.0)
                if found:
                    return profit
        except Exception:
            pass
        time.sleep(0.3)
    return None

def send_entry(
    symbol,
    side,
    entry_price,
    sl,
    tp,
    volume,
    comment,
    event_id=None,
    near_entry_pips_min=None,
    near_entry_spread_mult=None,
):
    symbol = resolve_symbol(symbol)
    mt5.symbol_select(symbol, True)

    volume = normalize_volume(symbol, float(volume))
    now_price = _price_now(symbol, side)

    is_market = isinstance(entry_price, str) and entry_price.lower() == "instantly"
    if is_market:
        order_price = now_price
        action = "MARKET"
        sl_ok, tp_ok, warn = validate_stops(symbol, side, order_price, sl, tp)
        if warn:
            print(f"[STOPS] {warn}")

        result = _send_with_fallback(
            _deal_request,
            (symbol, volume, side, order_price, sl_ok, tp_ok, comment),
            symbol,
        )
        if result is None:
            print("❌ order_send devolvió None:", mt5.last_error())
        else:
            print(f"[ORDER] {action} {symbol} {side} vol={volume} price={order_price} "
                  f"-> ret={result.retcode} order={getattr(result,'order',None)} "
                  f"deal={getattr(result,'deal',None)} comment={getattr(result,'comment','')}")
        _post_send_check(result, action, symbol, side, volume, comment, event_id)
        return result, action
    else:
        try:
            ep = float(entry_price)
        except Exception:
            ep = now_price
        spread_pips = _spread_pips(symbol)
        pip = _pip_size(symbol)
        if spread_pips is not None and pip > 0:
            pips_min = float(NEAR_ENTRY_PIPS_MIN if near_entry_pips_min is None else near_entry_pips_min)
            spread_mult = float(NEAR_ENTRY_SPREAD_MULT if near_entry_spread_mult is None else near_entry_spread_mult)
            threshold_pips = max(pips_min, spread_mult * spread_pips)
            if abs(ep - now_price) <= (threshold_pips * pip):
                order_price = now_price
                action = "MARKET"
                sl_ok, tp_ok, warn = validate_stops(symbol, side, order_price, sl, tp)
                if warn:
                    print(f"[STOPS] {warn}")
                result = _send_with_fallback(
                    _deal_request,
                    (symbol, volume, side, order_price, sl_ok, tp_ok, comment),
                    symbol,
                )
                if result is None:
                    print("❌ order_send devolvió None:", mt5.last_error())
                else:
                    print(f"[ORDER] {action} {symbol} {side} vol={volume} price={order_price} "
                          f"-> ret={result.retcode} order={getattr(result,'order',None)} "
                          f"deal={getattr(result,'deal',None)} comment={getattr(result,'comment','')}")
                _post_send_check(result, action, symbol, side, volume, comment, event_id)
                return result, action
        side_up = side.upper()
        order_type = (
            mt5.ORDER_TYPE_BUY_STOP if side_up == "BUY" and ep > now_price else
            mt5.ORDER_TYPE_BUY_LIMIT if side_up == "BUY" else
            mt5.ORDER_TYPE_SELL_STOP if side_up == "SELL" and ep < now_price else
            mt5.ORDER_TYPE_SELL_LIMIT
        )
        order_price = ep
        action = "PENDING"

    sl_ok, tp_ok, warn = validate_stops(symbol, side, order_price, sl, tp)
    if warn:
        print(f"[STOPS] {warn}")

    result = _send_with_fallback(
        _pending_request,
        (symbol, volume, side, order_type, order_price, sl_ok, tp_ok, comment),
        symbol,
    )
    if result is None:
        print("❌ order_send devolvió None:", mt5.last_error())
    else:
        print(f"[ORDER] {action} {symbol} {side} vol={volume} price={order_price} "
              f"-> ret={result.retcode} order={getattr(result,'order',None)} "
              f"deal={getattr(result,'deal',None)} comment={getattr(result,'comment','')}")
    _post_send_check(result, action, symbol, side, volume, comment, event_id)
    return result, action

def modify_position_sl(comments, new_sl, new_tp=None, tickets=None):
    positions = mt5.positions_get() or []
    target = [p for p in positions if p.comment in comments]
    if not target and tickets:
        ticket_set = _ticket_set(tickets)
        target = [p for p in positions if int(p.ticket) in ticket_set]
    sl_val = _parse_float_or_none(new_sl)
    tp_val = _parse_float_or_none(new_tp)
    if sl_val is None and tp_val is None:
        return False, "no valid sl/tp"

    ok = True
    msg = ""
    if target:
        for p in target:
            sl_to_send = sl_val if sl_val is not None else float(p.sl) if p.sl else 0.0
            tp_to_send = tp_val if tp_val is not None else float(p.tp) if p.tp else 0.0
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": p.ticket,
                "sl": float(sl_to_send),
                "tp": float(tp_to_send),
                "symbol": p.symbol,
                "magic": int(MAGIC_NUMBER),
                "comment": f"{p.comment}|MOD_SL",
            }
            r = mt5.order_send(req)
            _track_mt5_result(r)
            if r is None:
                ok = False
                msg += f" ticket {p.ticket} ret=None"
                continue
            if r.retcode != mt5.TRADE_RETCODE_DONE:
                ok = False
                msg += f" ticket {p.ticket} ret={r.retcode}"
        return ok, (msg or "OK")

    # Si no hay posiciones, intentar modificar pendientes por comment/ticket.
    orders = mt5.orders_get() or []
    target_orders = [o for o in orders if o.comment in comments]
    if not target_orders and tickets:
        ticket_set = _ticket_set(tickets)
        target_orders = [o for o in orders if int(o.ticket) in ticket_set]
    if not target_orders:
        return False, "no positions/orders matched"

    for o in target_orders:
        sl_to_send = sl_val if sl_val is not None else float(getattr(o, "sl", 0.0) or 0.0)
        tp_to_send = tp_val if tp_val is not None else float(getattr(o, "tp", 0.0) or 0.0)
        req = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": int(o.ticket),
            "symbol": o.symbol,
            "price": float(getattr(o, "price_open", 0.0) or 0.0),
            "sl": float(sl_to_send),
            "tp": float(tp_to_send),
            "magic": int(MAGIC_NUMBER),
            "comment": f"{o.comment}|MOD_PENDING",
        }
        r = mt5.order_send(req)
        _track_mt5_result(r)
        if r is None:
            ok = False
            msg += f" order {o.ticket} ret=None"
            continue
        if r.retcode != mt5.TRADE_RETCODE_DONE:
            ok = False
            msg += f" order {o.ticket} ret={r.retcode}"
    return ok, (msg or "OK")

def close_positions(comments, tickets=None):
    positions = mt5.positions_get() or []
    target = [p for p in positions if p.comment in comments]
    if not target and tickets:
        ticket_set = _ticket_set(tickets)
        target = [p for p in positions if int(p.ticket) in ticket_set]

    ok = True
    msg = ""
    details = []
    if target:
        for p in target:
            side = "SELL" if p.type == mt5.POSITION_TYPE_BUY else "BUY"
            try:
                price = _price_now(p.symbol, side)
            except Exception as e:
                ok = False
                msg += f" no_price ticket {p.ticket} err={e}"
                continue
            comment = f"{p.comment}|CLOSE"
            r = _send_with_fallback(
                _close_request,
                (p.symbol, p.volume, side, price, p.ticket, comment),
                p.symbol,
            )
            _track_mt5_result(r)
            if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
                ok = False
                msg += f" close ticket {p.ticket} ret={getattr(r,'retcode','NA')}"
                details.append({"ticket": int(p.ticket), "symbol": p.symbol, "status": "ERROR", "profit": None})
                continue
            realized = _realized_profit_for_position(int(p.ticket))
            details.append({"ticket": int(p.ticket), "symbol": p.symbol, "status": "OK", "profit": realized})
        return ok, (msg or "OK"), details

    # Si no hay posiciones, intentar cancelar órdenes pendientes por comment
    orders = mt5.orders_get() or []
    target_orders = [o for o in orders if o.comment in comments]
    if not target_orders and tickets:
        ticket_set = _ticket_set(tickets)
        target_orders = [o for o in orders if int(o.ticket) in ticket_set]
    if not target_orders:
        return False, "no positions matched", details

    for o in target_orders:
        r = mt5.order_delete(o.ticket)
        if isinstance(r, bool):
            if not r:
                ok = False
                msg += f" delete ticket {o.ticket} err={mt5.last_error()}"
        elif r.retcode != mt5.TRADE_RETCODE_DONE:
            ok = False
            msg += f" delete ticket {o.ticket} ret={r.retcode}"
        details.append({"ticket": int(o.ticket), "symbol": o.symbol, "status": "OK" if (isinstance(r, bool) and r) or (hasattr(r, "retcode") and r.retcode == mt5.TRADE_RETCODE_DONE) else "ERROR", "profit": 0.0})
    return ok, (msg or "OK"), details

# =============== índices & tracking ===============
ORDERS_SENT_FIELDS = [
    "timestamp","action","channel","channel_index","entry_message_id","style",
    "symbol","side","volume","sl","tp","entry_price_used","order_type","ticket","comment","status","info"
]
ORDERS_INDEX_FIELDS = ["channel_index","entry_message_id","style","symbol","ticket","comment"]
PROCESSED_FIELDS = ["event_uid"]
ERROR_FIELDS = ["timestamp","event_id","action","symbol","side","volume","comment","reason","retcode","details"]

DEDUP_FIELDS = [
    "message_id", "reply_to", "channel", "channel_index",
    "symbol", "operation", "type", "operator_class",
    "entry_price", "stop_loss", "take_profit", "close_reason",
    "new_stop_loss", "new_take_profit", "move_to_breakeven", "close_pnl_pips",
    "timestamp"
]


def build_event_uid(row, row_index=None):
    event_id = row.get("event_id") or row.get("event_uid")
    if event_id:
        return str(event_id)
    payload = {}
    if row_index is not None:
        payload["row_index"] = int(row_index)
    for f in DEDUP_FIELDS:
        val = row.get(f, "")
        if pd.isna(val):
            val = ""
        payload[f] = val
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def log_sent(row): _append_row(ORDERS_SENT_CSV, row, ORDERS_SENT_FIELDS)
def add_index(mapping_row): _append_row(ORDERS_INDEX_CSV, mapping_row, ORDERS_INDEX_FIELDS)
def log_error(row): _append_row(ERRORES_APERTURAS_CSV, row, ERROR_FIELDS)

def _migrate_processed_events_csv_to_db():
    if not os.path.exists(PROCESSED_EVENTS_CSV):
        return
    df = _load_df(PROCESSED_EVENTS_CSV, PROCESSED_FIELDS)
    if df.empty or "event_uid" not in df.columns:
        return
    now = _now_iso()
    rows = []
    for uid in df["event_uid"].astype(str).tolist():
        suid = str(uid or "").strip()
        if not suid:
            continue
        rows.append((suid, "", "", "", "legacy_csv", "done", now, now))
    if not rows:
        return
    try:
        with _db_conn() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO processed_events (
                    event_uid, event_id, message_id, channel_index, source, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
    except Exception:
        pass


def already_processed(uid) -> bool:
    suid = str(uid or "").strip()
    if not suid:
        return False
    try:
        with _db_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_events WHERE event_uid = ? LIMIT 1",
                (suid,),
            ).fetchone()
            return bool(row)
    except Exception:
        # Fallback legacy si SQLite no esta disponible
        df = _load_df(PROCESSED_EVENTS_CSV, PROCESSED_FIELDS)
        if df.empty:
            return False
        return suid in set(df["event_uid"].astype(str))


def mark_processed(uid, *, event_id="", message_id="", channel_index="", source="signals_csv"):
    suid = str(uid or "").strip()
    if not suid:
        return False
    now = _now_iso()
    try:
        with _db_conn() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO processed_events (
                    event_uid, event_id, message_id, channel_index, source, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'done', ?, ?)
                """,
                (
                    suid,
                    str(event_id or ""),
                    _normalize_id(message_id),
                    _normalize_id(channel_index),
                    str(source or "signals_csv"),
                    now,
                    now,
                ),
            )
            inserted = int(getattr(cur, "rowcount", 0) or 0) > 0
            if not inserted:
                conn.execute(
                    """
                    UPDATE processed_events
                    SET
                        event_id = CASE WHEN COALESCE(event_id,'') = '' THEN ? ELSE event_id END,
                        message_id = CASE WHEN COALESCE(message_id,'') = '' THEN ? ELSE message_id END,
                        channel_index = CASE WHEN COALESCE(channel_index,'') = '' THEN ? ELSE channel_index END,
                        source = CASE WHEN COALESCE(source,'') = '' THEN ? ELSE source END,
                        status = 'done',
                        updated_at = ?
                    WHERE event_uid = ?
                    """,
                    (
                        str(event_id or ""),
                        _normalize_id(message_id),
                        _normalize_id(channel_index),
                        str(source or "signals_csv"),
                        now,
                        suid,
                    ),
                )
            conn.commit()
            return inserted
    except Exception:
        # Fallback legacy (no usado como mecanismo principal)
        _append_row(PROCESSED_EVENTS_CSV, {"event_uid": suid}, PROCESSED_FIELDS)
        return True


def _uniq_int_tickets(values):
    out = []
    seen = set()
    for v in values or []:
        sid = _normalize_id(v)
        if not sid:
            continue
        try:
            tv = int(sid)
        except Exception:
            continue
        if tv in seen:
            continue
        seen.add(tv)
        out.append(tv)
    return out


def _uniq_text(values):
    out = []
    seen = set()
    for v in values or []:
        sv = str(v or "").strip()
        if not sv:
            continue
        if sv in seen:
            continue
        seen.add(sv)
        out.append(sv)
    return out

def find_tickets(channel_index, entry_message_id, style=None):
    df = _load_df(ORDERS_INDEX_CSV, ORDERS_INDEX_FIELDS)
    if df.empty: return ([], pd.DataFrame(columns=ORDERS_INDEX_FIELDS))
    entry_norm = _normalize_id(entry_message_id)
    channel_norm = _normalize_id(channel_index)
    entry_col = df["entry_message_id"].apply(_normalize_id)
    ch_col = df["channel_index"].apply(_normalize_id)
    if channel_norm:
        q = (ch_col == channel_norm) & (entry_col == entry_norm)
    else:
        q = (entry_col == entry_norm)
    if style:
        q &= (df["style"].astype(str).str.upper()==style.upper())
    return df[q]["ticket"].tolist(), df[q]

# =============== Base viva: open_trades.csv ===============
OPEN_TRADES_FIELDS = [
    "channel_index", "entry_message_id", "style", "symbol", "side",
    "ticket", "comment", "volume", "sl", "tp",
    "entry_price_used", "order_type", "status", "opened_at"
]

def _ensure_open_trades():
    with csv_file_lock(OPEN_TRADES_CSV):
        _ensure_open_trades_unlocked()


def _ensure_open_trades_unlocked():
    os.makedirs(os.path.dirname(OPEN_TRADES_CSV), exist_ok=True)
    if not os.path.exists(OPEN_TRADES_CSV):
        with open(OPEN_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=OPEN_TRADES_FIELDS)
            w.writeheader()

def _load_open_trades() -> pd.DataFrame:
    if not os.path.exists(OPEN_TRADES_CSV):
        return pd.DataFrame(columns=OPEN_TRADES_FIELDS)
    with csv_file_lock(OPEN_TRADES_CSV):
        return _load_open_trades_unlocked()


def _load_open_trades_unlocked() -> pd.DataFrame:
    try:
        return pd.read_csv(OPEN_TRADES_CSV)
    except Exception:
        return pd.read_csv(OPEN_TRADES_CSV, on_bad_lines="skip", engine="python")

def _save_open_trades(df: pd.DataFrame):
    with csv_file_lock(OPEN_TRADES_CSV):
        _save_open_trades_unlocked(df)


def _save_open_trades_unlocked(df: pd.DataFrame):
    ordered = df.reindex(columns=OPEN_TRADES_FIELDS)
    atomic_write_dataframe_csv(ordered, OPEN_TRADES_CSV, index=False, encoding="utf-8")


def open_trades_delete_by_tickets(tickets):
    tset = _ticket_set(tickets)
    if not tset:
        return
    with csv_file_lock(OPEN_TRADES_CSV):
        _ensure_open_trades_unlocked()
        df = _load_open_trades_unlocked()
        if df.empty or "ticket" not in df.columns:
            return
        ticket_col = df["ticket"].apply(_normalize_id)
        keep = ~ticket_col.isin({str(t) for t in tset})
        cleaned = df.loc[keep]
        if len(cleaned) != len(df):
            _save_open_trades_unlocked(cleaned)

def _open_key_mask(df, channel_index, entry_message_id, style=None):
    m = (df["channel_index"].astype(str)==str(channel_index)) & (df["entry_message_id"].astype(str)==str(entry_message_id))
    if style is not None:
        m &= (df["style"].astype(str).str.upper()==str(style).upper())
    return m

def open_trades_upsert(row: dict):
    with csv_file_lock(OPEN_TRADES_CSV):
        _ensure_open_trades_unlocked()
        df = _load_open_trades_unlocked()
        mask = _open_key_mask(df, row["channel_index"], row["entry_message_id"], row["style"])
        if df[mask].empty:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df.loc[mask, list(row.keys())] = list(row.values())
        _save_open_trades_unlocked(df)

def open_trades_update_sl_tp(channel_index, entry_message_id, styles, new_sl=None, new_tp=None):
    with csv_file_lock(OPEN_TRADES_CSV):
        _ensure_open_trades_unlocked()
        df = _load_open_trades_unlocked()
        sl_val = _parse_float_or_none(new_sl)
        tp_val = _parse_float_or_none(new_tp)
        changed = False
        for st in styles:
            mask = _open_key_mask(df, channel_index, entry_message_id, st)
            if not df[mask].empty:
                if sl_val is not None:
                    df.loc[mask, "sl"] = float(sl_val)
                    changed = True
                if tp_val is not None:
                    df.loc[mask, "tp"] = float(tp_val)
                    changed = True
        if changed:
            _save_open_trades_unlocked(df)
def open_trades_delete(channel_index, entry_message_id, styles):
    with csv_file_lock(OPEN_TRADES_CSV):
        _ensure_open_trades_unlocked()
        df = _load_open_trades_unlocked()
        for st in styles:
            mask = _open_key_mask(df, channel_index, entry_message_id, st)
            df = df.loc[~mask]
        _save_open_trades_unlocked(df)


def open_trades_has_open_entry(channel_index, entry_message_id):
    _ensure_open_trades()
    df = _load_open_trades()
    if df.empty:
        return False
    if "status" not in df.columns:
        df["status"] = "OPEN"
    ch_norm = _normalize_id(channel_index)
    entry_norm = _normalize_id(entry_message_id)
    ch_col = df["channel_index"].apply(_normalize_id)
    entry_col = df["entry_message_id"].apply(_normalize_id)
    status_col = df["status"].astype(str).str.upper()
    q = (ch_col == ch_norm) & (entry_col == entry_norm) & status_col.isin(["OPEN", "PENDING"])
    return not df[q].empty


def _tickets_comments_from_df(df: pd.DataFrame):
    if df is None or df.empty:
        return [], []
    tickets = _uniq_int_tickets(df["ticket"].tolist()) if "ticket" in df.columns else []
    comments = _uniq_text(df["comment"].tolist()) if "comment" in df.columns else []
    return tickets, comments


def _resolve_from_open_trades(channel_index, entry_id, preferred_style):
    _ensure_open_trades()
    df = _load_open_trades()
    if df.empty:
        return [], [], "open_trades_empty"

    if "status" not in df.columns:
        df["status"] = "OPEN"
    if "style" not in df.columns:
        df["style"] = "SWING"

    entry_norm = _normalize_id(entry_id)
    channel_norm = _normalize_id(channel_index)
    style_norm = _normalize_profile_code(preferred_style, default="SWING")

    entry_col = df["entry_message_id"].apply(_normalize_id)
    ch_col = df["channel_index"].apply(_normalize_id)
    status_col = df["status"].astype(str).str.upper()
    style_col = df["style"].astype(str).str.upper()

    q = (entry_col == entry_norm) & status_col.isin(["OPEN", "PENDING"])
    if channel_norm:
        q &= (ch_col == channel_norm)
    base = df[q]
    if base.empty:
        return [], [], "open_trades_miss"

    exact = base[style_col.loc[base.index] == style_norm]
    if not exact.empty:
        t, c = _tickets_comments_from_df(exact)
        return t, c, "open_trades_style_exact"

    t, c = _tickets_comments_from_df(base)
    return t, c, "open_trades_style_fallback_any"


def _resolve_from_operation_records(channel_index, entry_id, preferred_style):
    entry_norm = _normalize_id(entry_id)
    channel_norm = _normalize_id(channel_index)
    style_norm = _normalize_profile_code(preferred_style, default="SWING")
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT ticket, comment, execution_profile
                FROM operation_records
                WHERE mode = 'real'
                  AND status IN ('OPEN','PENDING')
                  AND COALESCE(entry_message_id,'') = ?
                  AND (? = '' OR COALESCE(channel_index,'') = ?)
                ORDER BY updated_at DESC, id DESC
                """,
                (entry_norm, channel_norm, channel_norm),
            ).fetchall()
    except Exception:
        rows = []

    if not rows:
        return [], [], "operation_records_miss"

    exact_rows = [r for r in rows if _normalize_profile_code(r["execution_profile"], default="SWING") == style_norm]
    target_rows = exact_rows if exact_rows else rows
    tickets = _uniq_int_tickets([r["ticket"] for r in target_rows])
    comments = _uniq_text([r["comment"] for r in target_rows])
    method = "operation_records_style_exact" if exact_rows else "operation_records_style_fallback_any"
    return tickets, comments, method


def _resolve_from_orders_index(channel_index, entry_id, preferred_style):
    style = _normalize_profile_code(preferred_style, default="SWING")
    resolution = "orders_index_style_exact"
    tickets, idx_df = find_tickets(channel_index, entry_id, style=style)
    if not tickets and idx_df.empty:
        resolution = "orders_index_style_fallback_any"
        tickets, idx_df = find_tickets(channel_index, entry_id, style=None)
    comments = []
    if not idx_df.empty and "comment" in idx_df.columns:
        comments = idx_df["comment"].dropna().astype(str).tolist()
    return _uniq_int_tickets(tickets), _uniq_text(comments), resolution


def _resolve_tickets_and_comments(channel_index, entry_id, preferred_style):
    resolvers = [
        _resolve_from_open_trades,
        _resolve_from_operation_records,
        _resolve_from_orders_index,  # fallback legacy
    ]
    last_method = "not_found"
    for resolver in resolvers:
        tickets, comments, method = resolver(channel_index, entry_id, preferred_style)
        last_method = method
        if tickets or comments:
            return tickets, comments, method
    return [], [], last_method


def _live_mt5_ticket_sets():
    pos_tickets = set()
    ord_tickets = set()
    if not _mt5_connection_alive():
        return pos_tickets, ord_tickets
    try:
        for p in (mt5.positions_get() or []):
            try:
                pos_tickets.add(int(getattr(p, "ticket", 0)))
            except Exception:
                continue
    except Exception:
        pass
    try:
        for o in (mt5.orders_get() or []):
            try:
                ord_tickets.add(int(getattr(o, "ticket", 0)))
            except Exception:
                continue
    except Exception:
        pass
    return pos_tickets, ord_tickets


def _live_mt5_comments():
    comments = set()
    if not _mt5_connection_alive():
        return comments
    try:
        for p in (mt5.positions_get() or []):
            c = str(getattr(p, "comment", "") or "").strip()
            if c:
                comments.add(c)
    except Exception:
        pass
    try:
        for o in (mt5.orders_get() or []):
            c = str(getattr(o, "comment", "") or "").strip()
            if c:
                comments.add(c)
    except Exception:
        pass
    return comments


def _prune_open_trades_against_mt5():
    if not _mt5_connection_alive():
        return
    _ensure_open_trades()
    df = _load_open_trades()
    if df.empty or "ticket" not in df.columns:
        return
    pos_tickets, ord_tickets = _live_mt5_ticket_sets()
    live = {str(t) for t in pos_tickets.union(ord_tickets)}
    if not live:
        cleaned = df.iloc[0:0]
    else:
        ticket_col = df["ticket"].apply(_normalize_id)
        cleaned = df.loc[ticket_col.isin(live)]
    if len(cleaned) != len(df):
        _save_open_trades(cleaned)


def _startup_reconcile_stale_real_records():
    if not _mt5_connection_alive():
        return
    live_pos_tickets, live_ord_tickets = _live_mt5_ticket_sets()
    live_tickets = {str(t) for t in live_pos_tickets.union(live_ord_tickets)}
    live_comments = _live_mt5_comments()
    now = _now_iso()
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, ticket, comment, opened_at, status, channel_index, entry_message_id, execution_profile
                FROM operation_records
                WHERE mode = 'real' AND status IN ('OPEN','PENDING')
                ORDER BY id ASC
                """
            ).fetchall()
            for r in rows:
                ticket = _normalize_id(r["ticket"])
                comment = str(r["comment"] or "").strip()
                if ticket and ticket in live_tickets:
                    continue
                if comment and comment in live_comments:
                    continue
                # Fallback robusto por índices de operación.
                channel_index = _normalize_id(r["channel_index"])
                entry_message_id = _normalize_id(r["entry_message_id"])
                expected_style = _normalize_profile_code(r["execution_profile"], default="SWING")
                lookup_method = ""
                if entry_message_id:
                    rtickets, rcomments, lookup_method = _resolve_tickets_and_comments(
                        channel_index,
                        entry_message_id,
                        expected_style,
                    )
                    if any(str(tk) in live_tickets for tk in _ticket_set(rtickets)):
                        continue
                    if any(str(cm or "").strip() in live_comments for cm in (rcomments or [])):
                        continue
                age_sec = _elapsed_seconds(str(r["opened_at"] or ""), now) or 0
                if age_sec < STARTUP_STALE_CLOSE_AGE_SEC:
                    continue
                op_id = int(r["id"])
                details = f"age_sec={age_sec};ticket={ticket or '-'};comment={comment or '-'}"
                if lookup_method:
                    details = f"{details};resolver={lookup_method}"
                if STARTUP_RECONCILE_MODE != "close":
                    conn.execute(
                        """
                        UPDATE operation_records
                        SET last_sync_at = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (now, now, op_id),
                    )
                    _operation_event_add(
                        conn,
                        op_id,
                        event_type="system",
                        status="WARN",
                        error_type="startup_reconcile_warning",
                        details=f"startup_reconcile_warn_only {details}",
                    )
                    continue
                _operation_mark_closed(
                    conn,
                    op_id,
                    status="CLOSED",
                    close_reason="No visible en MT5 al reiniciar: cierre de reconciliación de arranque.",
                    close_source="startup_reconcile",
                    close_details=details,
                )
                _operation_event_add(
                    conn,
                    op_id,
                    event_type="system",
                    status="CLOSED",
                    details=f"startup_reconcile_closed {details}",
                )
                if ticket:
                    open_trades_delete_by_tickets([ticket])
            conn.commit()
    except Exception:
        pass


def _finalize_event_processing(
    uid: str,
    *,
    event_id: str,
    message_id: str,
    channel_index: str,
    source: str,
    retry_error: str = "",
    retry_error_type: str = "runtime",
    permanent_error: str = "",
    permanent_error_type: str = "permanent",
) -> str:
    if retry_error:
        retries = _event_retry_register(uid, retry_error, error_type=retry_error_type)
        log_error({
            "timestamp": _now_iso(),
            "event_id": str(event_id or uid),
            "action": "EVENT_RETRY",
            "symbol": "",
            "side": "",
            "volume": "",
            "comment": "",
            "reason": str(retry_error_type or "runtime"),
            "retcode": "",
            "details": f"{retry_error};retries={retries}",
        })
        if retries >= EVENT_RETRY_MAX:
            mark_processed(uid, event_id=event_id, message_id=message_id, channel_index=channel_index, source=source)
            _event_retry_mark_permanent(uid, retry_error, error_type="retry_limit")
            return "permanent_fail"
        return "retry"

    if permanent_error:
        _event_retry_mark_permanent(uid, permanent_error, error_type=permanent_error_type)
        mark_processed(uid, event_id=event_id, message_id=message_id, channel_index=channel_index, source=source)
        return "permanent_fail"

    mark_processed(uid, event_id=event_id, message_id=message_id, channel_index=channel_index, source=source)
    _event_retry_clear(uid)
    return "done"


def _ticket_hint_map():
    out = {}
    # Prioridad 1: operation_records (persistente en SQLite)
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT ticket, channel_index, entry_message_id, execution_profile, comment
                FROM operation_records
                WHERE mode = 'real'
                  AND status IN ('OPEN','PENDING')
                  AND COALESCE(ticket,'') <> ''
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        for r in rows:
            tk = _normalize_id(r["ticket"])
            if not tk:
                continue
            out[tk] = {
                "channel_index": _normalize_id(r["channel_index"]),
                "entry_message_id": _normalize_id(r["entry_message_id"]),
                "style": _normalize_profile_code(r["execution_profile"], default="SWING"),
                "comment": str(r["comment"] or ""),
            }
    except Exception:
        pass

    # Prioridad 2: open_trades existente (completa huecos si no estaban en SQLite)
    try:
        df = _load_open_trades()
        if not df.empty:
            for _, row in df.iterrows():
                tk = _normalize_id(row.get("ticket", ""))
                if not tk or tk in out:
                    continue
                out[tk] = {
                    "channel_index": _normalize_id(row.get("channel_index", "")),
                    "entry_message_id": _normalize_id(row.get("entry_message_id", "")),
                    "style": _normalize_profile_code(row.get("style", "SWING"), default="SWING"),
                    "comment": str(row.get("comment", "") or ""),
                }
    except Exception:
        pass

    return out


def rebuild_open_trades_from_mt5():
    """Reconstruye la base viva con lo que realmente está abierto en MT5."""
    _ensure_open_trades()
    poss = mt5.positions_get()
    hints = _ticket_hint_map()
    rows = []
    if poss:
        for p in poss:
            style = "SWING"
            ch_idx, entry_id = "", ""
            try:
                parts = str(p.comment).split("-")
                if len(parts) >= 3:
                    style = parts[2].upper()
                if len(parts) >= 2:
                    ch_idx, entry_id = parts[0], parts[1]
            except Exception:
                pass
            hint = hints.get(_normalize_id(p.ticket), {})
            if hint:
                h_ch = _normalize_id(hint.get("channel_index", ""))
                h_entry = _normalize_id(hint.get("entry_message_id", ""))
                h_style = _normalize_profile_code(hint.get("style", "SWING"), default="SWING")
                if h_ch:
                    ch_idx = h_ch
                if h_entry:
                    entry_id = h_entry
                if h_style:
                    style = h_style
            rows.append({
                "channel_index": ch_idx,
                "entry_message_id": entry_id,
                "style": style,
                "symbol": p.symbol,
                "side": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "ticket": p.ticket,
                "comment": p.comment,
                "volume": p.volume,
                "sl": float(p.sl or 0.0),
                "tp": float(p.tp or 0.0),
                "entry_price_used": "",
                "order_type": "",
                "status": "OPEN",
                "opened_at": datetime.datetime.fromtimestamp(p.time, URUGUAY_TZ).isoformat(timespec="seconds"),
            })
    df = pd.DataFrame(rows, columns=OPEN_TRADES_FIELDS)
    _save_open_trades(df)

# =============== procesamiento de eventos ===============
def process_events_df(df: pd.DataFrame, source="signals_csv"):
    needed = [
        "event_id","type","timestamp","message_id","reply_to","channel","channel_index",
        "channel_id",
        "symbol","operation","entry_price","stop_loss","take_profit","operator_class",
        "move_to_breakeven","new_stop_loss","new_take_profit","close_pnl_pips","message_text",
        "operation_id", "close_reason", "close_details",
    ]
    for c in needed:
        if c not in df.columns:
            df[c] = ""

    for idx, r in df.iterrows():
        ev_type = str(r["type"]).lower().strip()
        op_class = str(r.get("operator_class", "") or "").strip().upper()
        if op_class == "STANDARD":
            op_class = "SWING"
        uid = build_event_uid(r, idx)
        event_id = r.get("event_id") or uid
        if not _event_retry_is_due(uid):
            continue

        channel = str(r["channel"])
        channel_index = _normalize_id(r.get("channel_index",""))
        message_id = _normalize_id(r.get("message_id", ""))
        reply_to = _normalize_id(r.get("reply_to", ""))
        message_text = str(r.get("message_text", "") or "")
        symbol_raw = str(r["symbol"]).upper()
        side = str(r["operation"]).upper()
        if ev_type == "entry":
            symbol_hint = _symbol_from_text(message_text)
            side_hint = _side_from_text(message_text)
            if symbol_hint and symbol_hint != symbol_raw:
                if LOG_PARSE_CORRECTIONS:
                    print(
                        f"⚠️ Corrección symbol por texto: event_id={event_id} "
                        f"msg={message_id} parsed={symbol_raw} text={symbol_hint}"
                    )
                symbol_raw = symbol_hint
            if side_hint and side_hint != side:
                if LOG_PARSE_CORRECTIONS:
                    print(
                        f"⚠️ Corrección side por texto: event_id={event_id} "
                        f"msg={message_id} parsed={side} text={side_hint}"
                    )
                side = side_hint
        telegram_row = dict(r)
        telegram_row["symbol"] = symbol_raw
        telegram_row["operation"] = side
        telegram_row["operator_class"] = op_class
        _upsert_telegram_message(telegram_row, str(event_id))
        if already_processed(uid):
            continue
        if ev_type == "panel_close":
            close_retry_error = ""
            op_id = 0
            try:
                op_id = int(str(r.get("operation_id", "") or "0").strip())
            except Exception:
                op_id = 0
            close_reason = str(r.get("close_reason", "") or "").strip() or "Cerrada desde Panel web a mano"
            close_details = str(r.get("close_details", "") or "").strip() or "Cierre solicitado desde panel (MT5)."
            if op_id <= 0:
                _report_log(
                    event_id=event_id,
                    message_id=message_id,
                    channel_name=channel,
                    event_type=ev_type,
                    symbol="",
                    side="",
                    operator_class=op_class,
                    entry_message_id=message_id,
                    reply_to=reply_to,
                    status="ERROR",
                    error_type="invalid_operation_id",
                    details="panel_close sin operation_id válido",
                )
                _finalize_event_processing(
                    uid,
                    event_id=str(event_id),
                    message_id=message_id,
                    channel_index=channel_index,
                    source=source,
                    permanent_error="invalid_operation_id",
                    permanent_error_type="panel_close_invalid",
                )
                continue
            with _db_conn() as conn:
                op = conn.execute(
                    """
                    SELECT *
                    FROM operation_records
                    WHERE id = ?
                    """,
                    (int(op_id),),
                ).fetchone()
                if not op:
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_name=channel,
                        event_type=ev_type,
                        symbol="",
                        side="",
                        operator_class=op_class,
                        entry_message_id="",
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="operation_not_found",
                        details=f"operation_id={op_id}",
                    )
                    _finalize_event_processing(
                        uid,
                        event_id=str(event_id),
                        message_id=message_id,
                        channel_index=channel_index,
                        source=source,
                    )
                    continue
                op_status = str(op["status"] or "").upper()
                op_mode = str(op["mode"] or "")
                op_symbol = str(op["symbol"] or "")
                op_side = str(op["side"] or "")
                op_channel_name = str(op["channel_name"] or channel or "")
                op_channel_index = _normalize_id(op["channel_index"])
                op_entry_message_id = _normalize_id(op["entry_message_id"])
                op_profile = _normalize_profile_code(op["execution_profile"], default="SWING")
                if op_status not in ("OPEN", "PENDING"):
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=int(op["channel_id"]) if op["channel_id"] is not None else None,
                        channel_name=op_channel_name,
                        config_id=int(op["preset_id"]) if op["preset_id"] is not None else None,
                        config_name=str(op["preset_name"] or ""),
                        mode=op_mode,
                        event_type=ev_type,
                        symbol=op_symbol,
                        side=op_side,
                        operator_class=op_profile,
                        entry_message_id=op_entry_message_id,
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="operation_not_open",
                        details=f"operation_id={op_id};status={op_status}",
                    )
                    _finalize_event_processing(
                        uid,
                        event_id=str(event_id),
                        message_id=message_id,
                        channel_index=channel_index,
                        source=source,
                    )
                    continue

                if op_mode == "real":
                    tickets = _uniq_int_tickets([op["ticket"]])
                    comments = _uniq_text([op["comment"]])
                    lookup_method = "operation_ticket_comment"
                    if not tickets and not comments:
                        tickets, comments, lookup_method = _resolve_tickets_and_comments(
                            op_channel_index,
                            op_entry_message_id,
                            op_profile,
                        )
                    ok, info, close_items = close_positions(comments, tickets=tickets)
                    pnl_usd_real = None
                    if close_items:
                        vals = [x.get("profit") for x in close_items if x.get("profit") is not None]
                        if vals:
                            pnl_usd_real = float(sum(vals))
                    info_details = (
                        f"{info};lookup={lookup_method};tickets={len(tickets)};comments={len(comments)};"
                        f"operation_id={op_id}"
                    )
                    if not ok and _is_retryable_error_text(info_details):
                        close_retry_error = f"panel_close_retryable:{info_details}"
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=int(op["channel_id"]) if op["channel_id"] is not None else None,
                        channel_name=op_channel_name,
                        config_id=int(op["preset_id"]) if op["preset_id"] is not None else None,
                        config_name=str(op["preset_name"] or ""),
                        mode=op_mode,
                        event_type="close",
                        symbol=op_symbol,
                        side=op_side,
                        operator_class=op_profile,
                        entry_message_id=op_entry_message_id,
                        reply_to=reply_to,
                        status="OK" if ok else "ERROR",
                        error_type="" if ok else "panel_close_error",
                        pnl_usd=pnl_usd_real,
                        details=f"panel_web_manual_mt5;{info_details}",
                    )
                    _operation_event_add(
                        conn,
                        op_id,
                        event_type="close",
                        event_id=event_id,
                        message_id=message_id,
                        reply_to=reply_to,
                        status="OK" if ok else "ERROR",
                        error_type="" if ok else "panel_close_error",
                        pnl_usd=pnl_usd_real,
                        details=f"panel_web_manual_mt5;{close_details};{info_details}",
                    )
                    if ok:
                        _operation_mark_closed(
                            conn,
                            op_id,
                            status="CLOSED",
                            close_reason=close_reason,
                            close_source="panel_web_manual_mt5",
                            close_details=f"{close_details};{info_details}",
                            close_event_id=str(event_id),
                            close_trigger_message_id=message_id,
                            pnl_usd=pnl_usd_real,
                        )
                        open_trades_delete(op_channel_index, op_entry_message_id, [op_profile, "STANDARD"])
                        if tickets:
                            open_trades_delete_by_tickets(tickets)
                    conn.commit()
                else:
                    vcfg = {
                        "config_id": int(op["preset_id"]) if op["preset_id"] is not None else 0,
                    }
                    close_rows = _virtual_close_positions(
                        int(op["channel_id"]) if op["channel_id"] is not None else 0,
                        vcfg,
                        op_entry_message_id,
                        op_symbol,
                        op_side,
                        close_pnl_pips="",
                    )
                    pnl_usd = None
                    pnl_pips = None
                    if close_rows:
                        pnl_usd = float(sum([float(x.get("pnl_usd") or 0.0) for x in close_rows]))
                        pnl_pips = float(sum([float(x.get("pnl_pips") or 0.0) for x in close_rows]))
                    ok = len(close_rows) > 0
                    detail_v = f"closed_positions={len(close_rows)};operation_id={op_id}"
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=int(op["channel_id"]) if op["channel_id"] is not None else None,
                        channel_name=op_channel_name,
                        config_id=int(op["preset_id"]) if op["preset_id"] is not None else None,
                        config_name=str(op["preset_name"] or ""),
                        mode=op_mode,
                        event_type="close",
                        symbol=op_symbol,
                        side=op_side,
                        operator_class=op_profile,
                        entry_message_id=op_entry_message_id,
                        reply_to=reply_to,
                        status="OK" if ok else "SKIP",
                        error_type="" if ok else "virtual_no_position",
                        pnl_usd=pnl_usd,
                        pnl_pips=pnl_pips,
                        details=f"panel_web_manual_virtual;{detail_v}",
                    )
                    _operation_event_add(
                        conn,
                        op_id,
                        event_type="close",
                        event_id=event_id,
                        message_id=message_id,
                        reply_to=reply_to,
                        status="OK" if ok else "SKIP",
                        error_type="" if ok else "virtual_no_position",
                        pnl_usd=pnl_usd,
                        pnl_pips=pnl_pips,
                        details=f"panel_web_manual_virtual;{close_details};{detail_v}",
                    )
                    if ok:
                        _operation_mark_closed(
                            conn,
                            op_id,
                            status="CLOSED",
                            close_reason=close_reason,
                            close_source="panel_web_manual_virtual",
                            close_details=f"{close_details};{detail_v}",
                            close_event_id=str(event_id),
                            close_trigger_message_id=message_id,
                            pnl_usd=pnl_usd,
                            pnl_pips=pnl_pips,
                        )
                    conn.commit()

            fin = _finalize_event_processing(
                uid,
                event_id=str(event_id),
                message_id=message_id,
                channel_index=channel_index,
                source=source,
                retry_error=close_retry_error,
                retry_error_type="panel_close_retryable",
            )
            if fin == "retry":
                print(f"🔁 PANEL_CLOSE retry programado uid={uid} reason={close_retry_error}")
                continue
            print(f"✅ PANEL_CLOSE operation_id={op_id} event_id={event_id}")
            continue
        if symbol_raw in ("", "UNKNOWN") or side not in ("BUY", "SELL"):
            _finalize_event_processing(
                uid,
                event_id=str(event_id),
                message_id=message_id,
                channel_index=channel_index,
                source=source,
            )
            print(f"⏭️ Evento inválido (symbol/side) uid={uid} symbol={symbol_raw} side={side}")
            _report_log(
                event_id=event_id,
                message_id=message_id,
                channel_name=channel,
                event_type=ev_type,
                symbol=symbol_raw,
                side=side,
                operator_class=op_class,
                entry_message_id=message_id,
                reply_to=reply_to,
                status="SKIP",
                error_type="invalid_symbol_or_side",
                details=f"channel_index={channel_index}",
            )
            continue
        symbol = resolve_symbol(symbol_raw)
        assignments = _load_assignments_for_channel(channel)
        real_assignment = _select_real_assignment(assignments)
        virtual_assignments = _select_virtual_assignments(assignments)

        # ENTRY ------------------------------------------------------
        if ev_type == "entry":
            entry_retry_error = ""
            entry_permanent_error = ""
            execute_real_entry = True
            if assignments and real_assignment is None:
                execute_real_entry = False

            run_profile = _normalize_profile_code(real_assignment["execution_profile"] if real_assignment else EXECUTION_PROFILE)
            run_total_volume = real_assignment["total_volume"] if real_assignment else TOTAL_VOLUME
            run_near_pips = real_assignment["near_entry_pips_min"] if real_assignment else NEAR_ENTRY_PIPS_MIN
            run_near_mult = real_assignment["near_entry_spread_mult"] if real_assignment else NEAR_ENTRY_SPREAD_MULT

            if execute_real_entry:
                style_key = run_profile
                real_operation_key = _operation_key_real(channel_index, message_id, style_key)
                if open_trades_has_open_entry(channel_index, message_id):
                    log_sent({
                        "timestamp": _now_iso(),
                        "action": "ENTRY",
                        "channel": channel, "channel_index": channel_index,
                        "entry_message_id": message_id,
                        "style": style_key,
                        "symbol": symbol, "side": side, "volume": "",
                        "sl": r.get("stop_loss", ""), "tp": r.get("take_profit", ""),
                        "entry_price_used": r.get("entry_price", "instantly"),
                        "order_type": "",
                        "ticket": "", "comment": "",
                        "status": "SKIP", "info": "duplicate_entry_open_exists"
                    })
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=real_assignment["channel_id"] if real_assignment else None,
                        channel_name=channel,
                        config_id=real_assignment["config_id"] if real_assignment else None,
                        config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                        mode="real",
                        event_type="entry",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=message_id,
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="duplicate_entry_open_exists",
                        details=f"style={style_key}",
                    )
                    with _db_conn() as conn:
                        op_id = _operation_id_real(conn, channel_index, message_id, style_key)
                        if op_id:
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="entry",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="SKIP",
                                error_type="duplicate_entry_open_exists",
                                details=f"style={style_key}",
                            )
                            conn.commit()
                else:
                    vol = float(run_total_volume)
                    comment = _mk_comment(channel_index, message_id, style_key)
                    entry_price_used = r.get("entry_price", "instantly")
                    sl, tp = r.get("stop_loss", ""), r.get("take_profit", "")

                    res, action = send_entry(
                        symbol,
                        side,
                        entry_price_used,
                        sl,
                        tp,
                        vol,
                        comment,
                        event_id=event_id,
                        near_entry_pips_min=run_near_pips,
                        near_entry_spread_mult=run_near_mult,
                    )

                    req_obj = getattr(res, "request", None)
                    order_type = getattr(req_obj, "type", "") if req_obj is not None else ""
                    status = "SENT" if (res and res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)) else f"ERROR({res.retcode if res else 'NA'})"
                    ticket = getattr(res, "order", None)
                    if status != "SENT":
                        rc = getattr(res, "retcode", None) if res is not None else None
                        if _is_retryable_mt5_retcode(rc) or res is None:
                            entry_retry_error = f"entry_send_retryable ret={rc}"
                        else:
                            user_message = _mt5_retcode_user_message(rc, getattr(res, "comment", "") if res else "")
                            entry_permanent_error = f"entry_send_error ret={rc}; {user_message}"
                    request_price = _safe_float_or_none(getattr(req_obj, "price", None) if req_obj is not None else None)
                    entry_price_num = request_price
                    if entry_price_num is None:
                        entry_price_num = _safe_float_or_none(entry_price_used)

                    log_sent({
                        "timestamp": _now_iso(),
                        "action": "ENTRY",
                        "channel": channel, "channel_index": channel_index,
                        "entry_message_id": message_id,
                        "style": style_key,
                        "symbol": symbol, "side": side, "volume": float(f"{vol:.2f}"),
                        "sl": sl, "tp": tp,
                        "entry_price_used": entry_price_used,
                        "order_type": order_type,
                        "ticket": ticket, "comment": comment,
                        "status": status, "info": getattr(res, 'comment', '') if res else ''
                    })

                    if ticket and status == "SENT":
                        add_index({
                            "channel_index": channel_index,
                            "entry_message_id": message_id,
                            "style": style_key,
                            "symbol": symbol,
                            "ticket": ticket,
                            "comment": comment
                        })
                        open_row = {
                            "channel_index": channel_index,
                            "entry_message_id": message_id,
                            "style": style_key,
                            "symbol": symbol,
                            "side": side,
                            "ticket": ticket,
                            "comment": comment,
                            "volume": float(f"{vol:.2f}"),
                            "sl": float(sl or 0.0),
                            "tp": float(tp or 0.0),
                            "entry_price_used": entry_price_used,
                            "order_type": order_type,
                            "status": "PENDING" if action == "PENDING" else "OPEN",
                            "opened_at": _now_iso(),
                        }
                        open_trades_upsert(open_row)

                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=real_assignment["channel_id"] if real_assignment else None,
                        channel_name=channel,
                        config_id=real_assignment["config_id"] if real_assignment else None,
                        config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                        mode="real",
                        event_type="entry",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=message_id,
                        reply_to=reply_to,
                        status=status,
                        error_type="" if status == "SENT" else "entry_send_error",
                        details=f"style={style_key};action={action};comment={comment}",
                    )
                    with _db_conn() as conn:
                        status_op = "PENDING" if (status == "SENT" and action == "PENDING") else ("OPEN" if status == "SENT" else "ERROR")
                        op_id = _operation_upsert_entry(
                            conn,
                            operation_key=real_operation_key,
                            mode="real",
                            status=status_op,
                            is_virtual=False,
                            channel_id=real_assignment["channel_id"] if real_assignment else None,
                            channel_name=channel,
                            channel_index=channel_index,
                            preset_id=real_assignment["config_id"] if real_assignment else None,
                            preset_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                            execution_profile=style_key,
                            symbol=symbol,
                            side=side,
                            entry_message_id=message_id,
                            entry_event_id=event_id,
                            entry_trigger_message_id=message_id,
                            entry_ts=str(r.get("timestamp", "") or ""),
                            ticket=ticket or "",
                            comment=comment,
                            volume=vol,
                            entry_price=entry_price_num,
                            sl=sl,
                            tp=tp,
                        )
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="entry",
                            event_id=event_id,
                            message_id=message_id,
                            reply_to=reply_to,
                            status=status_op,
                            error_type="" if status_op in ("OPEN", "PENDING") else "entry_send_error",
                            sl=sl,
                            tp=tp,
                            details=f"action={action};comment={comment}",
                        )
                        if status_op == "ERROR":
                            conn.execute(
                                """
                                UPDATE operation_records
                                SET close_source = 'error',
                                    close_error_id = ?,
                                    close_error_type = 'entry_send_error',
                                    close_details = ?,
                                    updated_at = ?
                                WHERE id = ?
                                """,
                                (
                                    str(event_id),
                                    f"entry_status={status}",
                                    _now_iso(),
                                    int(op_id),
                                ),
                            )
                        conn.commit()
            else:
                _report_log(
                    event_id=event_id,
                    message_id=message_id,
                    channel_name=channel,
                    config_name="unassigned_real",
                    mode="real",
                    event_type="entry",
                    symbol=symbol,
                    side=side,
                    operator_class=op_class,
                    entry_message_id=message_id,
                    reply_to=reply_to,
                    status="SKIP",
                    error_type="no_real_assignment",
                    details="Hay asignaciones activas pero ninguna en modo real para este canal",
                )

            # carteras virtuales (shadow)
            for vcfg in virtual_assignments:
                try:
                    vstyle = _normalize_profile_code(vcfg.get("execution_profile"), default=EXECUTION_PROFILE)
                    vvol = float(vcfg["total_volume"])
                    price_now = _price_now(symbol, side)
                    ep = r.get("entry_price", "instantly")
                    if isinstance(ep, str) and ep.lower() == "instantly":
                        v_entry = price_now
                    else:
                        epf = _parse_float_or_none(ep)
                        if epf is None:
                            v_entry = price_now
                        else:
                            spread_pips = _spread_pips(symbol)
                            pip = _pip_size(symbol)
                            threshold_pips = max(float(vcfg["near_entry_pips_min"]), float(vcfg["near_entry_spread_mult"]) * (spread_pips or 0.0))
                            v_entry = price_now if spread_pips is not None and pip > 0 and abs(epf - price_now) <= (threshold_pips * pip) else epf
                    ok_v = _virtual_open_position(
                        vcfg["channel_id"],
                        channel,
                        vcfg,
                        message_id,
                        symbol,
                        side,
                        float(vvol),
                        float(v_entry),
                        sl=r.get("stop_loss", ""),
                        tp=r.get("take_profit", ""),
                    )
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=vcfg["channel_id"],
                        channel_name=channel,
                        config_id=vcfg["config_id"],
                        config_name=vcfg["config_name"],
                        mode="virtual",
                        event_type="entry",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=message_id,
                        reply_to=reply_to,
                        status="OPENED" if ok_v else "ERROR",
                        error_type="" if ok_v else "virtual_open_error",
                        details=f"entry_price={v_entry};style={vstyle}",
                    )
                    with _db_conn() as conn:
                        op_id = _operation_upsert_entry(
                            conn,
                            operation_key=_operation_key_virtual(vcfg["channel_id"], vcfg["config_id"], message_id),
                            mode="virtual",
                            status="OPEN" if ok_v else "ERROR",
                            is_virtual=True,
                            channel_id=vcfg["channel_id"],
                            channel_name=channel,
                            channel_index=channel_index,
                            preset_id=vcfg["config_id"],
                            preset_name=vcfg["config_name"],
                            execution_profile=vstyle,
                            symbol=symbol,
                            side=side,
                            entry_message_id=message_id,
                            entry_event_id=event_id,
                            entry_trigger_message_id=message_id,
                            entry_ts=str(r.get("timestamp", "") or ""),
                            ticket="",
                            comment="",
                            volume=vvol,
                            entry_price=v_entry,
                            sl=r.get("stop_loss", ""),
                            tp=r.get("take_profit", ""),
                        )
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="entry",
                            event_id=event_id,
                            message_id=message_id,
                            reply_to=reply_to,
                            status="OPEN" if ok_v else "ERROR",
                            error_type="" if ok_v else "virtual_open_error",
                            sl=r.get("stop_loss", ""),
                            tp=r.get("take_profit", ""),
                            details=f"style={vstyle}",
                        )
                        conn.commit()
                except Exception as e:
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=vcfg["channel_id"],
                        channel_name=channel,
                        config_id=vcfg["config_id"],
                        config_name=vcfg["config_name"],
                        mode="virtual",
                        event_type="entry",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=message_id,
                        reply_to=reply_to,
                        status="ERROR",
                        error_type="virtual_open_exception",
                        details=str(e),
                    )

            fin = _finalize_event_processing(
                uid,
                event_id=str(event_id),
                message_id=message_id,
                channel_index=channel_index,
                source=source,
                retry_error=entry_retry_error,
                retry_error_type="entry_retryable",
                permanent_error=entry_permanent_error,
                permanent_error_type="entry_send_error",
            )
            if fin == "retry":
                print(f"🔁 ENTRY retry programado uid={uid} reason={entry_retry_error}")
                continue
            if fin == "permanent_fail":
                print(f"ENTRY fallo permanente {symbol} {side} ({channel}) uid={uid} reason={entry_permanent_error}")
                continue
            print(f"✅ ENTRY {symbol} {side} ({channel}) uid={uid}")
            continue

        # MODIFICATION ----------------------------------------------
        if ev_type == "modification":
            mod_retry_error = ""
            entry_id = reply_to or message_id
            link_method = "reply_to" if reply_to else "message_id"
            expected_style = _normalize_profile_code(real_assignment["execution_profile"] if real_assignment else EXECUTION_PROFILE)
            requested_class = op_class if op_class in KNOWN_PROFILE_CODES else ""
            class_match = requested_class in ("", expected_style)

            if not class_match:
                _report_log(
                    event_id=event_id,
                    message_id=message_id,
                    channel_id=real_assignment["channel_id"] if real_assignment else None,
                    channel_name=channel,
                    config_id=real_assignment["config_id"] if real_assignment else None,
                    config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                    mode="real",
                    event_type="modification",
                    symbol=symbol,
                    side=side,
                    operator_class=op_class,
                    entry_message_id=entry_id,
                    reply_to=reply_to,
                    status="SKIP",
                    error_type="class_mismatch",
                    details=f"expected_style={expected_style};requested_class={requested_class or '-'};class_match=false",
                )
                with _db_conn() as conn:
                    op_id = _operation_id_real(conn, channel_index, entry_id, expected_style)
                    if op_id:
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="modification",
                            event_id=event_id,
                            message_id=message_id,
                            reply_to=reply_to,
                            status="SKIP",
                            error_type="class_mismatch",
                            details=f"expected_style={expected_style};requested_class={requested_class or '-'}",
                        )
                        conn.commit()
            else:
                tickets, comments, lookup_method = _resolve_tickets_and_comments(channel_index, entry_id, expected_style)
                if not tickets and not comments:
                    log_sent({
                        "timestamp": _now_iso(),
                        "action": "MODIFY", "channel": channel, "channel_index": channel_index,
                        "entry_message_id": entry_id, "style": expected_style,
                        "symbol": symbol, "side": "", "volume": "",
                        "sl": r.get("new_stop_loss", ""), "tp": r.get("new_take_profit", ""),
                        "entry_price_used": "", "order_type": "",
                        "ticket": "", "comment": "",
                        "status": "SKIP", "info": "No tickets indexed for this entry/style"
                    })
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=real_assignment["channel_id"] if real_assignment else None,
                        channel_name=channel,
                        config_id=real_assignment["config_id"] if real_assignment else None,
                        config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                        mode="real",
                        event_type="modification",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=entry_id,
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="no_tickets_indexed",
                        details=f"expected_style={expected_style};requested_class={requested_class or '-'};link={link_method};lookup={lookup_method}",
                    )
                    with _db_conn() as conn:
                        op_id = _operation_id_real(conn, channel_index, entry_id, expected_style)
                        if op_id:
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="modification",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="SKIP",
                                error_type="no_tickets_indexed",
                                details=f"expected_style={expected_style};lookup={lookup_method}",
                            )
                            conn.commit()
                    print(f"⏭️ MOD saltada (sin entry indexado) {symbol} {op_class} uid={uid}")
                else:
                    move_be = str(r.get("move_to_breakeven", "")).lower() == "true"
                    new_sl = r.get("new_stop_loss", "")
                    new_tp = r.get("new_take_profit", "")

                    if move_be:
                        pos_list = mt5.positions_get() or []
                        be_price = None
                        for p in pos_list:
                            if p.comment in comments:
                                be_price = p.price_open
                                break
                        if be_price is None and tickets:
                            tset = _ticket_set(tickets)
                            for p in pos_list:
                                if int(p.ticket) in tset:
                                    be_price = p.price_open
                                    break
                        if be_price:
                            new_sl = be_price

                    ok, info = modify_position_sl(comments, new_sl, new_tp=new_tp, tickets=tickets)
                    comment_for_log = comments[0] if comments else ""
                    info_details = (
                        f"{info};expected_style={expected_style};requested_class={requested_class or '-'};"
                        f"class_match={class_match};link={link_method};lookup={lookup_method};tickets={len(tickets)}"
                    )
                    if not ok and _is_retryable_error_text(info_details):
                        mod_retry_error = f"modify_retryable:{info_details}"

                    log_sent({
                        "timestamp": _now_iso(),
                        "action": "MODIFY", "channel": channel, "channel_index": channel_index,
                        "entry_message_id": entry_id, "style": expected_style,
                        "symbol": symbol, "side": "", "volume": "",
                        "sl": new_sl, "tp": new_tp,
                        "entry_price_used": "", "order_type": "",
                        "ticket": "", "comment": comment_for_log,
                        "status": "OK" if ok else "ERROR", "info": info_details
                    })

                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=real_assignment["channel_id"] if real_assignment else None,
                        channel_name=channel,
                        config_id=real_assignment["config_id"] if real_assignment else None,
                        config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                        mode="real",
                        event_type="modification",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=entry_id,
                        reply_to=reply_to,
                        status="OK" if ok else "ERROR",
                        error_type="" if ok else "modify_error",
                        details=info_details,
                    )

                    # actualizar base viva
                    if ok:
                        styles_target = [expected_style, "STANDARD"]
                        open_trades_update_sl_tp(channel_index, entry_id, styles_target, new_sl=new_sl, new_tp=new_tp)
                    with _db_conn() as conn:
                        op_id = _operation_id_real(conn, channel_index, entry_id, expected_style)
                        if op_id:
                            if ok:
                                _operation_apply_modification(
                                    conn,
                                    op_id,
                                    message_id=message_id,
                                    new_sl=new_sl,
                                    new_tp=new_tp,
                                )
                            else:
                                conn.execute(
                                    """
                                    UPDATE operation_records
                                    SET close_source = 'error',
                                        close_error_id = ?,
                                        close_error_type = 'modify_error',
                                        close_details = ?,
                                        updated_at = ?
                                    WHERE id = ?
                                    """,
                                    (str(event_id), info_details, _now_iso(), int(op_id)),
                                )
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="modification",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="OK" if ok else "ERROR",
                                error_type="" if ok else "modify_error",
                                sl=new_sl,
                                tp=new_tp,
                                details=info_details,
                            )
                            conn.commit()

                    print(f"{'✅' if ok else '❌'} MOD {symbol} {op_class} uid={uid} info={info}")

            # virtual modifications
            for vcfg in virtual_assignments:
                vstyle = _normalize_profile_code(vcfg.get("execution_profile"), default=EXECUTION_PROFILE)
                v_requested = op_class if op_class in KNOWN_PROFILE_CODES else ""
                v_class_match = v_requested in ("", vstyle)
                if not v_class_match:
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=vcfg["channel_id"],
                        channel_name=channel,
                        config_id=vcfg["config_id"],
                        config_name=vcfg["config_name"],
                        mode="virtual",
                        event_type="modification",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=entry_id,
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="class_mismatch",
                        details=f"style={vstyle};requested_class={v_requested or '-'};class_match=false",
                    )
                    with _db_conn() as conn:
                        op_id = _operation_id_virtual(conn, vcfg["channel_id"], vcfg["config_id"], entry_id)
                        if op_id:
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="modification",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="SKIP",
                                error_type="class_mismatch",
                                details=f"style={vstyle};requested_class={v_requested or '-'}",
                            )
                            conn.commit()
                    continue
                moved = _virtual_modify_positions(vcfg["channel_id"], vcfg, entry_id, new_sl=r.get("new_stop_loss", ""), new_tp=r.get("new_take_profit", ""))
                _report_log(
                    event_id=event_id,
                    message_id=message_id,
                    channel_id=vcfg["channel_id"],
                    channel_name=channel,
                    config_id=vcfg["config_id"],
                    config_name=vcfg["config_name"],
                    mode="virtual",
                    event_type="modification",
                    symbol=symbol,
                    side=side,
                    operator_class=op_class,
                    entry_message_id=entry_id,
                    reply_to=reply_to,
                    status="OK" if moved > 0 else "SKIP",
                    error_type="" if moved > 0 else "virtual_no_position",
                    details=f"updated={moved};style={vstyle};requested_class={v_requested or '-'};class_match={v_class_match}",
                )
                with _db_conn() as conn:
                    op_id = _operation_id_virtual(conn, vcfg["channel_id"], vcfg["config_id"], entry_id)
                    if op_id:
                        if moved > 0:
                            _operation_apply_modification(
                                conn,
                                op_id,
                                message_id=message_id,
                                new_sl=r.get("new_stop_loss", ""),
                                new_tp=r.get("new_take_profit", ""),
                            )
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="modification",
                            event_id=event_id,
                            message_id=message_id,
                            reply_to=reply_to,
                            status="OK" if moved > 0 else "SKIP",
                            error_type="" if moved > 0 else "virtual_no_position",
                            sl=r.get("new_stop_loss", ""),
                            tp=r.get("new_take_profit", ""),
                            details=f"updated={moved};style={vstyle}",
                        )
                        conn.commit()

            fin = _finalize_event_processing(
                uid,
                event_id=str(event_id),
                message_id=message_id,
                channel_index=channel_index,
                source=source,
                retry_error=mod_retry_error,
                retry_error_type="modification_retryable",
            )
            if fin == "retry":
                print(f"🔁 MOD retry programado uid={uid} reason={mod_retry_error}")
                continue
            continue

        # CLOSE ------------------------------------------------------
        if ev_type == "close":
            close_retry_error = ""
            entry_id = reply_to or message_id
            link_method = "reply_to" if reply_to else "message_id"
            expected_style = _normalize_profile_code(real_assignment["execution_profile"] if real_assignment else EXECUTION_PROFILE)
            requested_class = op_class if op_class in KNOWN_PROFILE_CODES else ""
            class_match = requested_class in ("", expected_style)
            any_ok = True
            infos = []
            if not class_match:
                _report_log(
                    event_id=event_id,
                    message_id=message_id,
                    channel_id=real_assignment["channel_id"] if real_assignment else None,
                    channel_name=channel,
                    config_id=real_assignment["config_id"] if real_assignment else None,
                    config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                    mode="real",
                    event_type="close",
                    symbol=symbol,
                    side=side,
                    operator_class=op_class,
                    entry_message_id=entry_id,
                    reply_to=reply_to,
                    status="SKIP",
                    error_type="class_mismatch",
                    details=f"expected_style={expected_style};requested_class={requested_class or '-'};class_match=false",
                )
                with _db_conn() as conn:
                    op_id = _operation_id_real(conn, channel_index, entry_id, expected_style)
                    if op_id:
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="close",
                            event_id=event_id,
                            message_id=message_id,
                            reply_to=reply_to,
                            status="SKIP",
                            error_type="class_mismatch",
                            details=f"expected_style={expected_style};requested_class={requested_class or '-'}",
                        )
                        conn.commit()
            else:
                tickets, comments, lookup_method = _resolve_tickets_and_comments(channel_index, entry_id, expected_style)
                if not tickets and not comments:
                    any_ok = False
                    infos.append("no_tickets")
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=real_assignment["channel_id"] if real_assignment else None,
                        channel_name=channel,
                        config_id=real_assignment["config_id"] if real_assignment else None,
                        config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                        mode="real",
                        event_type="close",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=entry_id,
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="no_tickets_indexed",
                        details=f"expected_style={expected_style};requested_class={requested_class or '-'};link={link_method};lookup={lookup_method}",
                    )
                    with _db_conn() as conn:
                        op_id = _operation_id_real(conn, channel_index, entry_id, expected_style)
                        if op_id:
                            conn.execute(
                                """
                                UPDATE operation_records
                                SET close_source = 'error',
                                    close_error_id = ?,
                                    close_error_type = 'no_tickets_indexed',
                                    close_details = ?,
                                    updated_at = ?
                                WHERE id = ?
                                """,
                                (
                                    str(event_id),
                                    f"expected_style={expected_style};lookup={lookup_method}",
                                    _now_iso(),
                                    int(op_id),
                                ),
                            )
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="close",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="SKIP",
                                error_type="no_tickets_indexed",
                                details=f"expected_style={expected_style};lookup={lookup_method}",
                            )
                            conn.commit()
                else:
                    ok, info, close_details = close_positions(comments, tickets=tickets)
                    any_ok = ok
                    comment_for_log = comments[0] if comments else ""
                    pnl_usd_real = None
                    if close_details:
                        vals = [d.get("profit") for d in close_details if d.get("profit") is not None]
                        if vals:
                            pnl_usd_real = float(sum(vals))
                    info_details = (
                        f"{info};expected_style={expected_style};requested_class={requested_class or '-'};"
                        f"class_match={class_match};link={link_method};lookup={lookup_method};tickets={len(tickets)}"
                    )
                    if not ok and _is_retryable_error_text(info_details):
                        close_retry_error = f"close_retryable:{info_details}"
                    infos.append(info_details)

                    log_sent({
                        "timestamp": _now_iso(),
                        "action": "CLOSE", "channel": channel, "channel_index": channel_index,
                        "entry_message_id": entry_id, "style": expected_style,
                        "symbol": symbol, "side": "", "volume": "",
                        "sl": "", "tp": "",
                        "entry_price_used": "", "order_type": "",
                        "ticket": "", "comment": comment_for_log,
                        "status": "OK" if ok else "ERROR", "info": info_details
                    })
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=real_assignment["channel_id"] if real_assignment else None,
                        channel_name=channel,
                        config_id=real_assignment["config_id"] if real_assignment else None,
                        config_name=real_assignment["config_name"] if real_assignment else "runtime_default",
                        mode="real",
                        event_type="close",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=entry_id,
                        reply_to=reply_to,
                        status="OK" if ok else "ERROR",
                        error_type="" if ok else "close_error",
                        pnl_usd=pnl_usd_real,
                        details=info_details,
                    )

                    if ok:
                        open_trades_delete(channel_index, entry_id, [expected_style, "STANDARD"])
                    with _db_conn() as conn:
                        op_id = _operation_id_real(conn, channel_index, entry_id, expected_style)
                        if op_id:
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="close",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="OK" if ok else "ERROR",
                                error_type="" if ok else "close_error",
                                pnl_usd=pnl_usd_real,
                                details=info_details,
                            )
                            if ok:
                                _operation_mark_closed(
                                    conn,
                                    op_id,
                                    status="CLOSED",
                                    close_event_id=event_id,
                                    close_message_id=message_id,
                                    close_reason=str(r.get("close_reason", "") or "Cierre por señal"),
                                    close_source="signal",
                                    close_details=info_details,
                                    pnl_usd=pnl_usd_real,
                                )
                            else:
                                conn.execute(
                                    """
                                    UPDATE operation_records
                                    SET close_source = 'error',
                                        close_error_id = ?,
                                        close_error_type = 'close_error',
                                        close_details = ?,
                                        updated_at = ?
                                    WHERE id = ?
                                    """,
                                    (str(event_id), info_details, _now_iso(), int(op_id)),
                                )
                            conn.commit()

            # virtual close for all active virtual assignments
            for vcfg in virtual_assignments:
                vstyle = _normalize_profile_code(vcfg.get("execution_profile"), default=EXECUTION_PROFILE)
                v_requested = op_class if op_class in KNOWN_PROFILE_CODES else ""
                v_class_match = v_requested in ("", vstyle)
                if not v_class_match:
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=vcfg["channel_id"],
                        channel_name=channel,
                        config_id=vcfg["config_id"],
                        config_name=vcfg["config_name"],
                        mode="virtual",
                        event_type="close",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=entry_id,
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="class_mismatch",
                        details=f"style={vstyle};requested_class={v_requested or '-'};class_match=false",
                    )
                    with _db_conn() as conn:
                        op_id = _operation_id_virtual(conn, vcfg["channel_id"], vcfg["config_id"], entry_id)
                        if op_id:
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="close",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="SKIP",
                                error_type="class_mismatch",
                                details=f"style={vstyle};requested_class={v_requested or '-'}",
                            )
                            conn.commit()
                    continue
                close_rows = _virtual_close_positions(
                    vcfg["channel_id"],
                    vcfg,
                    entry_id,
                    symbol,
                    side,
                    close_pnl_pips=r.get("close_pnl_pips", ""),
                )
                if not close_rows:
                    _report_log(
                        event_id=event_id,
                        message_id=message_id,
                        channel_id=vcfg["channel_id"],
                        channel_name=channel,
                        config_id=vcfg["config_id"],
                        config_name=vcfg["config_name"],
                        mode="virtual",
                        event_type="close",
                        symbol=symbol,
                        side=side,
                        operator_class=op_class,
                        entry_message_id=entry_id,
                        reply_to=reply_to,
                        status="SKIP",
                        error_type="virtual_no_position",
                        details=f"no open virtual positions;style={vstyle};requested_class={v_requested or '-'};class_match={v_class_match}",
                    )
                    with _db_conn() as conn:
                        op_id = _operation_id_virtual(conn, vcfg["channel_id"], vcfg["config_id"], entry_id)
                        if op_id:
                            _operation_event_add(
                                conn,
                                op_id,
                                event_type="close",
                                event_id=event_id,
                                message_id=message_id,
                                reply_to=reply_to,
                                status="SKIP",
                                error_type="virtual_no_position",
                                details=f"style={vstyle}",
                            )
                            conn.commit()
                    continue
                pnl_usd = sum([float(x.get("pnl_usd")) for x in close_rows if x.get("pnl_usd") is not None]) if close_rows else None
                pnl_pips = sum([float(x.get("pnl_pips")) for x in close_rows if x.get("pnl_pips") is not None]) if close_rows else None
                _report_log(
                    event_id=event_id,
                    message_id=message_id,
                    channel_id=vcfg["channel_id"],
                    channel_name=channel,
                    config_id=vcfg["config_id"],
                    config_name=vcfg["config_name"],
                    mode="virtual",
                    event_type="close",
                    symbol=symbol,
                    side=side,
                    operator_class=op_class,
                    entry_message_id=entry_id,
                    reply_to=reply_to,
                    status="OK",
                    error_type="",
                    pnl_usd=pnl_usd,
                    pnl_pips=pnl_pips,
                    details=f"closed_positions={len(close_rows)};style={vstyle};requested_class={v_requested or '-'};class_match={v_class_match}",
                )
                with _db_conn() as conn:
                    op_id = _operation_id_virtual(conn, vcfg["channel_id"], vcfg["config_id"], entry_id)
                    if op_id:
                        _operation_event_add(
                            conn,
                            op_id,
                            event_type="close",
                            event_id=event_id,
                            message_id=message_id,
                            reply_to=reply_to,
                            status="OK",
                            pnl_usd=pnl_usd,
                            pnl_pips=pnl_pips,
                            details=f"closed_positions={len(close_rows)};style={vstyle}",
                        )
                        _operation_mark_closed(
                            conn,
                            op_id,
                            status="CLOSED",
                            close_event_id=event_id,
                            close_message_id=message_id,
                            close_reason=str(r.get("close_reason", "") or "Cierre por señal"),
                            close_source="signal",
                            close_details=f"closed_positions={len(close_rows)};style={vstyle}",
                            pnl_usd=pnl_usd,
                            pnl_pips=pnl_pips,
                        )
                        conn.commit()

            fin = _finalize_event_processing(
                uid,
                event_id=str(event_id),
                message_id=message_id,
                channel_index=channel_index,
                source=source,
                retry_error=close_retry_error,
                retry_error_type="close_retryable",
            )
            if fin == "retry":
                print(f"🔁 CLOSE retry programado uid={uid} reason={close_retry_error}")
                continue
            print(f"{'✅' if any_ok else '❌'} CLOSE {symbol} {op_class or 'ALL'} uid={uid} info={' | '.join(infos)}")
            continue

        # otros tipos: marcar procesado y seguir
        _report_log(
            event_id=event_id,
            message_id=message_id,
            channel_name=channel,
            event_type=ev_type,
            symbol=symbol,
            side=side,
            operator_class=op_class,
            entry_message_id=message_id,
            reply_to=reply_to,
            status="SKIP",
            error_type="unknown_event_type",
            details="event marked as processed",
        )
        _finalize_event_processing(
            uid,
            event_id=str(event_id),
            message_id=message_id,
            channel_index=channel_index,
            source=source,
        )

# =============== LOOP PRINCIPAL ===============
def run_loop(poll_seconds=2):
    global _startup_reconcile_done
    _ensure_experiment_tables()
    _migrate_processed_events_csv_to_db()
    try:
        mt5_init()
    except Exception as e:
        _mark_mt5_disconnected()
        print(f"[MT5] inicio diferido, esperando reconexión automática: {e}")
    print("🟢 Operador iniciado. Leyendo:", SIGNALS_CSV)

    _ensure_csv(ORDERS_SENT_CSV, ORDERS_SENT_FIELDS)
    _ensure_csv(ORDERS_INDEX_CSV, ORDERS_INDEX_FIELDS)
    _ensure_csv(ERRORES_APERTURAS_CSV, ERROR_FIELDS)
    _ensure_open_trades()
    if _mt5_connection_alive():
        rebuild_open_trades_from_mt5()
        _prune_open_trades_against_mt5()
        _startup_reconcile_stale_real_records()
        _startup_reconcile_done = True
    else:
        print("[MT5] sin conexión al inicio: se conserva open_trades.csv actual (sin reconstruir).")
    _bootstrap_operation_records()

    last_mtime = 0.0
    last_sync_metrics_at = 0.0

    while True:
        try:
            now_ts = time.time()
            mt5_ok = _ensure_mt5_connection()
            if not mt5_ok:
                time.sleep(1.0)
                continue
            if not _startup_reconcile_done:
                _prune_open_trades_against_mt5()
                _startup_reconcile_stale_real_records()
                _startup_reconcile_done = True

            if (now_ts - last_sync_metrics_at) >= LIVE_SYNC_INTERVAL_SEC:
                _sync_live_operation_metrics()
                last_sync_metrics_at = now_ts

            queue_files = _list_queue_files()
            if queue_files:
                for path in queue_files:
                    event = None
                    try:
                        event = _load_queue_event(path)
                        event_uid = build_event_uid(event, 0)
                        if not _event_retry_is_due(event_uid):
                            continue
                        df = pd.DataFrame([event])
                        process_events_df(df, source="queue")
                        if already_processed(event_uid):
                            _mark_queue_processed(path)
                            _queue_clear_failure(path)
                        else:
                            # Retry controlado por event_retry_state.
                            continue
                    except Exception as e:
                        retries = _queue_register_failure(path, event, str(e))
                        user_error = _queue_error_user_message(e)
                        log_error({
                            "timestamp": _now_iso(),
                            "event_id": _queue_event_id(path, event),
                            "action": "QUEUE",
                            "symbol": "",
                            "side": "",
                            "volume": "",
                            "comment": "",
                            "reason": "queue_event_error",
                            "retcode": "",
                            "details": f"{user_error};raw={e};retries={retries}",
                        })
                        if retries >= QUEUE_MAX_RETRIES:
                            _queue_quarantine_file(path)
                            print(
                                f"⛔ Queue event en cuarentena por errores repetidos: "
                                f"{os.path.basename(path)} retries={retries}. {user_error} raw={e}"
                            )
                        else:
                            print(
                                f"⚠️ Queue event pendiente por error (retry {retries}/{QUEUE_MAX_RETRIES}): "
                                f"{os.path.basename(path)}. {user_error} raw={e}"
                            )
                continue

            if not os.path.exists(SIGNALS_CSV):
                time.sleep(poll_seconds); continue

            mtime = os.path.getmtime(SIGNALS_CSV)
            if mtime == last_mtime and not _event_retry_due_exists():
                time.sleep(poll_seconds); continue
            last_mtime = mtime

            df = _load_df(SIGNALS_CSV)
            process_events_df(df, source="signals_csv")

        except Exception as e:
            print("ERROR en loop:", e)
            time.sleep(poll_seconds)

if __name__ == "__main__":
    run_loop()

