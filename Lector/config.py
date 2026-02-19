# Lector/config.py
# ===============================
# Configuración del BLOQUE LECTOR
# ===============================

import os
import getpass
import sqlite3
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # type: ignore

URUGUAY_TZ = ZoneInfo("America/Montevideo") if ZoneInfo is not None else timezone(timedelta(hours=-3))

def _get_env_or_prompt(name, prompt, cast=None, secret=False):
    value = os.getenv(name)
    while not value:
        value = getpass.getpass(prompt) if secret else input(prompt)
        value = value.strip()
    if cast:
        while True:
            try:
                return cast(value)
            except ValueError:
                value = input(f"{prompt} (valor inválido, intente otra vez): ").strip()
    return value


# --- Credenciales de Telegram (de tu app en my.telegram.org) ---
# Primero se leen desde variables de entorno, si faltan se piden en runtime.
API_ID = _get_env_or_prompt("TELEGRAM_API_ID", "TELEGRAM_API_ID: ", cast=int)
API_HASH = _get_env_or_prompt("TELEGRAM_API_HASH", "TELEGRAM_API_HASH: ", secret=True)

# ===============================
# Rutas y archivos del Lector
# ===============================
BASE_DIR       = os.path.dirname(__file__)                 # .../Lector
ROOT_DIR       = os.path.dirname(BASE_DIR)                 # raíz del proyecto
DATA_DIR       = os.path.join(BASE_DIR, "data")
CANALESDB_DIR  = os.path.join(BASE_DIR, "CanalesDB")
EVENTS_QUEUE_DIR = os.path.join(ROOT_DIR, "queue", "pending")
EVENTS_QUEUE_PROCESSED_DIR = os.path.join(ROOT_DIR, "queue", "processed")

# Crear carpetas si no existen
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CANALESDB_DIR, exist_ok=True)
os.makedirs(EVENTS_QUEUE_DIR, exist_ok=True)
os.makedirs(EVENTS_QUEUE_PROCESSED_DIR, exist_ok=True)

# Archivo MAESTRO donde el Lector escribe TODAS las señales parseadas
# (El Operador leerá este archivo desde su propio config)
SIGNALS_CSV    = os.path.join(DATA_DIR, "signals.csv")
NON_SIGNALS_CSV = os.path.join(DATA_DIR, "non_signals.csv")

# CSV con índice de canales (lo genera el Lector al arrancar)
CANALES_DB_CSV = os.path.join(CANALESDB_DIR, "canalesDB.csv")
TRADING_BOT_DB_PATH = os.getenv(
    "TRADING_BOT_DB_PATH",
    os.path.join(ROOT_DIR, "config", "trading_bot.db"),
)


# --- Canales a escuchar (nombre visible -> chat_id) ---
DEFAULT_CHANNELS = {
    "TechnicalPips":  -1001287502434,
    "Metabear_Forex": -1001422733304,
    "MiCanalPrueba":  -1002509518709,
}


def _load_channels_from_sqlite() -> dict[str, int]:
    path = TRADING_BOT_DB_PATH
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                chat_id TEXT NOT NULL UNIQUE,
                external_id TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        count = conn.execute("SELECT COUNT(1) FROM telegram_channels").fetchone()[0]
        if int(count) == 0:
            now = datetime.now(URUGUAY_TZ).isoformat(timespec="seconds")
            conn.executemany(
                """
                INSERT INTO telegram_channels (name, chat_id, external_id, is_active, created_at, updated_at)
                VALUES (?, ?, '', 1, ?, ?)
                """,
                [(name, str(chat_id), now, now) for name, chat_id in DEFAULT_CHANNELS.items()],
            )
            conn.commit()

        cur = conn.cursor()
        cur.execute(
            """
            SELECT name, chat_id
            FROM telegram_channels
            WHERE is_active = 1
            ORDER BY id ASC
            """
        )
        rows = cur.fetchall()
    except Exception as e:
        print(f"Warning: no se pudieron cargar canales desde SQLite ({path}): {e}")
        rows = []
    finally:
        if conn is not None:
            conn.close()

    channels = {}
    for name, chat_id in rows:
        clean_name = str(name or "").strip()
        if not clean_name:
            continue
        try:
            channels[clean_name] = int(str(chat_id).strip())
        except Exception:
            print(f"Warning: chat_id inválido para canal '{clean_name}': {chat_id}")
    return channels


def load_channels() -> dict[str, int]:
    channels = _load_channels_from_sqlite()
    if channels:
        return channels
    return dict(DEFAULT_CHANNELS)


CHANNELS = load_channels()

# ===============================
# Parser con ChatGPT (OpenAI)
# ===============================
# Usa variables de entorno si existen, si no se piden por pantalla.
OPENAI_API_KEY = _get_env_or_prompt("OPENAI_API_KEY", "OPENAI_API_KEY: ", secret=True)
OPENAI_MODEL = _get_env_or_prompt(
    "OPENAI_MODEL",
    "OPENAI_MODEL (rápido recomendado: gpt-4o-mini): ",
)
# Opcional: para proxies/routers compatibles (solo si lo necesitás).
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")


def validate_config():
    errors = []
    if not CHANNELS:
        errors.append("CHANNELS está vacío (sin canales activos)")
    if errors:
        raise ValueError("Config inválida: " + " | ".join(errors))
