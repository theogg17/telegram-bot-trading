# main.py (arranque del Lector sin instalación automática de dependencias)

import os
import sys
import subprocess

def run_config_canalesDB():
    """
    Ejecuta el generador de CanalesDB (si existe en el mismo directorio).
    Mantiene el comportamiento que ya tenías de llamar a config_a_canalesDB.py antes de correr el lector.
    """
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_a_canalesDB.py")
    if not os.path.exists(script_path):
        print("ℹ️  config_a_canalesDB.py no encontrado. Saltando este paso.")
        return

    try:
        print("🛠️  Generando CanalesDB (config_a_canalesDB.py)...")
        subprocess.run([sys.executable, script_path], check=True)
        print("✅ CanalesDB generado.\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al ejecutar config_a_canalesDB.py: {e}")

def main():
    # 0) Validar configuración sensible
    from config import validate_config
    validate_config()

    # 1) Generar/actualizar CanalesDB a partir de CHANNELS en config.py (si corresponde)
    run_config_canalesDB()

    # 2) Import del lector (asume dependencias preinstaladas en el entorno)
    from telegram_reader import run

    # 3) Ejecutar el listener de Telegram
    run()

if __name__ == "__main__":
    main()
