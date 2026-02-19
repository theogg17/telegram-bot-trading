# Operador/config_operador.py
import os
import getpass

# =========================
# RUTAS DE ARCHIVOS
# =========================
BASE = os.path.dirname(__file__)                  # .../Operador
ROOT = os.path.dirname(BASE)                      # raíz del proyecto

# Lector escribe aquí las señales
SIGNALS_CSV          = os.path.join(ROOT, "Lector", "data", "signals.csv")
# --- nuevo: base de posiciones abiertas (viva) ---
OPEN_TRADES_CSV = os.path.join(os.path.dirname(__file__), "open_trades.csv")
OPERACIONES_ABIERTAS_CSV = os.path.join(os.path.dirname(__file__), "operaciones_abiertas.csv")
ERRORES_APERTURAS_CSV = os.path.join(os.path.dirname(__file__), "errores_de_aperturas.csv")

# Cola de eventos (archivos JSON)
EVENTS_QUEUE_DIR = os.path.join(ROOT, "queue", "pending")
EVENTS_QUEUE_PROCESSED_DIR = os.path.join(ROOT, "queue", "processed")



# El Operador escribirá/leerá estos CSV en la carpeta Operador
ORDERS_SENT_CSV      = os.path.join(BASE, "ordenes_enviadas.csv")
ORDERS_INDEX_CSV     = os.path.join(BASE, "orders_index.csv")
PROCESSED_EVENTS_CSV = os.path.join(BASE, "processed_events.csv")

# =========================
# CREDENCIALES / TERMINAL MT5
# =========================
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

def _get_env_cast(name, default, cast):
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    try:
        return cast(value)
    except Exception:
        return default

def _get_env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default

def _get_env_list(name, default):
    value = os.getenv(name)
    if value is None:
        return list(default)
    items = [x.strip() for x in str(value).replace(";", ",").split(",")]
    items = [x for x in items if x]
    return items or list(default)


TERMINAL_PATH = _get_env_or_prompt("MT5_TERMINAL_PATH", "MT5_TERMINAL_PATH: ")
MT5_LOGIN = _get_env_or_prompt("MT5_LOGIN", "MT5_LOGIN: ", cast=int)
MT5_PASSWORD = _get_env_or_prompt("MT5_PASSWORD", "MT5_PASSWORD: ", secret=True)
MT5_SERVER = _get_env_or_prompt("MT5_SERVER", "MT5_SERVER: ")

MT5_TIMEOUT_MS  = 60000
MT5_PORTABLE    = False

# =========================
# PARÁMETROS DE EJECUCIÓN
# =========================
# Modo de ejecución real: siempre una sola orden por señal.
EXECUTION_MODE = "single"
if str(os.getenv("EXECUTION_MODE", "single")).strip().lower() not in ("", "single"):
    print("[CFG] EXECUTION_MODE distinto de 'single' ignorado: el operador usa una orden por señal.")

# Perfil operativo asociado a la configuración (SCALP o SWING).
EXECUTION_PROFILE = str(os.getenv("EXECUTION_PROFILE", "SWING")).strip().upper() or "SWING"

# Volumen total por señal (una orden).
TOTAL_VOLUME    = _get_env_cast("TOTAL_VOLUME", 0.03, float)

# Compatibilidad retroactiva: ya no se usa reparto split en real.
VOLUME_SPLIT    = {"SWING": 1.0}

# Slippage/desvío permitido en puntos
MAX_DEVIATION   = 20

# Comentario con sufijo de estilo para identificar órdenes por operador
# Formato: "<channel_index>-<entry_message_id>-<STYLE>"
COMMENT_STYLE_SUFFIX = True

# Umbral para convertir entradas cercanas a MARKET (en pips)
NEAR_ENTRY_PIPS_MIN = _get_env_cast("NEAR_ENTRY_PIPS_MIN", 1.0, float)
NEAR_ENTRY_SPREAD_MULT = _get_env_cast("NEAR_ENTRY_SPREAD_MULT", 2.0, float)

# Verificación de apertura / consistencia
VERIFY_ORDER_AFTER_SEND = _get_env_bool("VERIFY_ORDER_AFTER_SEND", True)
AUTO_CLOSE_ON_MISMATCH = _get_env_bool("AUTO_CLOSE_ON_MISMATCH", False)
VERIFY_POLL_SECONDS = 10

# Símbolos a forzar en MarketWatch (opcional)
DEFAULT_SYMBOLS_REQUIRED = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURJPY", "GBPJPY", "XAUUSD", "BTCUSD",
]
SYMBOLS_REQUIRED = _get_env_list("SYMBOLS_REQUIRED", DEFAULT_SYMBOLS_REQUIRED)
SYMBOLS_ALWAYS_SELECT = _get_env_list("SYMBOLS_ALWAYS_SELECT", SYMBOLS_REQUIRED)

# =========================
# ORDEN / FILLING / MAGIC
# =========================
# Filling mode: 2=IOC, 3=FOK (usa el que acepte tu broker)
FILLING_MODE    = 2  # IOC

# Magic number para identificar órdenes del bot
MAGIC_NUMBER    = 123456

# =========================
# ALIAS DE SÍMBOLOS (lo que llega del Lector -> variantes en MT5)
# =========================
SYMBOL_ALIASES = {
    "XAUUSD": ["XAUUSD.", "XAUUSDmicro", "GOLD"],
    "EURUSD": ["EURUSD.", "EURUSDmicro"],
    "GBPUSD": ["GBPUSD.", "GBPUSDmicro"],
    "USDJPY": ["USDJPY.", "USDJPYm", "USDJPYmicro"],
    "BTCUSD": ["BTCUSD.", "BTCUSDm", "BTCUSDmicro", "BTCUSDT", "BTCUSD.a"],
    "BTCUDS": ["BTCUSD", "BTCUSD.", "BTCUSDm", "BTCUSDmicro", "BTCUSDT", "BTCUSD.a"],
}
