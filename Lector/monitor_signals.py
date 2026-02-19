# monitor_signals.py

import shutil
import time
import os

# Configuración
SOURCE_FILE = "data/signals.csv"  # Ruta al archivo original
MONITOR_FOLDER = "../signals_monitor"  # Carpeta de monitoreo fuera del directorio actual
MONITOR_FILE = os.path.join(MONITOR_FOLDER, "signals_monitor.csv")
COPY_INTERVAL_SECONDS = 5  # Intervalo de copia en segundos

def create_monitor_folder():
    """Crea la carpeta de monitoreo si no existe."""
    os.makedirs(MONITOR_FOLDER, exist_ok=True)
    print(f"Carpeta de monitoreo creada en: {MONITOR_FOLDER}")

def copy_signals_file():
    """Copia el archivo signals.csv a la carpeta de monitoreo."""
    try:
        shutil.copy2(SOURCE_FILE, MONITOR_FILE)  # copy2 preserva los metadatos
        print(f"Archivo '{SOURCE_FILE}' copiado a '{MONITOR_FILE}'")
    except FileNotFoundError:
        print(f"Error: Archivo fuente '{SOURCE_FILE}' no encontrado.")
    except Exception as e:
        print(f"Error al copiar el archivo: {e}")

if __name__ == "__main__":
    create_monitor_folder()
    while True:
        copy_signals_file()
        time.sleep(COPY_INTERVAL_SECONDS)