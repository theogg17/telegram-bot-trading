import MetaTrader5 as mt5
import pandas as pd
import time
import os

# --- Configuración ---
CSV_FILE = 'ordenes_enviadas.csv'


def _get_env_or_prompt_int(name, prompt):
    value = str(os.getenv(name, "") or "").strip()
    while not value:
        value = str(input(prompt) or "").strip()
    while True:
        try:
            return int(value)
        except Exception:
            value = str(input(f"{prompt} (valor inválido, intenta de nuevo): ") or "").strip()


ACCOUNT_NUMBER = _get_env_or_prompt_int("MT5_LOGIN", "MT5_LOGIN: ")

def verificar_orden():
    """Verifica si la última orden ENVIADA desde el script coincide con alguna entrada en el CSV."""
    if not mt5.initialize():
        print(f"Error al inicializar MetaTrader 5: {mt5.last_error()}")
        return

    logged_in = mt5.login(ACCOUNT_NUMBER)
    if not logged_in:
        print(f"Error al conectar a la cuenta {ACCOUNT_NUMBER}: {mt5.last_error()}")
        mt5.shutdown()
        return
    else:
        print(f"Conectado a la cuenta {ACCOUNT_NUMBER} para verificar la orden.")

    # 1. Obtener todas las órdenes activas en la cuenta
    orders = mt5.orders_get()
    if not orders:
        print("No se encontraron órdenes activas en MetaTrader 5.")
        mt5.shutdown()
        return

    # Vamos a intentar obtener la información de la última orden *enviada* desde el script principal
    # Para esto, necesitamos el 'comment' que generamos.
    # Asumimos que el script principal pasa el 'comment' de alguna manera o lo podemos reconstruir.
    # Como no tenemos esa información directa aquí, vamos a intentar buscar
    # órdenes que coincidan con la última entrada del CSV (esto es una aproximación).

    try:
        df_csv = pd.read_csv(CSV_FILE)
        if not df_csv.empty:
            ultima_fila_csv = df_csv.iloc[-1]
            csv_symbol = ultima_fila_csv['symbol']
            csv_message_id = str(int(ultima_fila_csv['message_id'])) # Asegurarse de que sea string para la comparación
            csv_channel = ultima_fila_csv['channel']
            comment_esperado_mt5 = f"{csv_channel}-{csv_message_id}"

            encontrada = False
            for orden in orders:
                if orden.comment == comment_esperado_mt5 and orden.symbol == csv_symbol:
                    mt5_symbol = orden.symbol
                    mt5_sl = orden.sl
                    mt5_tp = orden.tp
                    mt5_comment_completo = orden.comment
                    mt5_ticket = orden.ticket

                    csv_stop_loss = ultima_fila_csv['stop_loss']
                    csv_take_profit = ultima_fila_csv['take_profit']

                    if (mt5_symbol == csv_symbol and
                        abs(mt5_sl - csv_stop_loss) < 1e-5 and # Usar tolerancia para comparar floats
                        abs(mt5_tp - csv_take_profit) < 1e-5): # Usar tolerancia para comparar floats
                        print(f"Verificación exitosa para {mt5_comment_completo} (Ticket: {mt5_ticket})")
                        encontrada = True
                        break

            if not encontrada:
                print(f"No se encontró en MT5 una orden activa con el comentario esperado: '{comment_esperado_mt5}' y símbolo '{csv_symbol}'.")
        else:
            print("El archivo CSV está vacío.")

    except FileNotFoundError:
        print(f"Error: El archivo CSV '{CSV_FILE}' no fue encontrado.")
    except Exception as e:
        print(f"Ocurrió un error al leer el CSV o comparar las órdenes: {e}")

    mt5.shutdown()

if __name__ == "__main__":
    time.sleep(5)  # Aumentamos la pausa antes de verificar
    verificar_orden()
