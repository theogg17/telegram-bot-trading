import MetaTrader5 as mt5
import time
import os
import getpass


def _get_env_or_prompt(name, prompt, cast=None, secret=False):
    value = str(os.getenv(name, "") or "").strip()
    while not value:
        value = getpass.getpass(prompt) if secret else input(prompt)
        value = str(value or "").strip()
    if cast is not None:
        while True:
            try:
                return cast(value)
            except Exception:
                value = str(input(f"{prompt} (valor inválido, intenta de nuevo): ") or "").strip()
    return value

# Introduce tus credenciales
login = _get_env_or_prompt("MT5_LOGIN", "MT5_LOGIN: ", cast=int)
password = _get_env_or_prompt("MT5_PASSWORD", "MT5_PASSWORD: ", secret=True)
server = _get_env_or_prompt("MT5_SERVER", "MT5_SERVER: ")  # Ejemplo: "ICMarkets-Live"

# Inicializar la conexión a MetaTrader 5
if not mt5.initialize():
    print(f"¡Error al inicializar MetaTrader 5! Código de error = {mt5.last_error()}")
    mt5.shutdown()
else:
    print("MetaTrader 5 inicializado correctamente.")

    # Intentar conectar con las credenciales
    if mt5.login(login, password, server):
        print(f"¡Conexión exitosa a la cuenta {login} en el servidor {server}!")

        # Aquí puedes agregar cualquier otra lógica que necesites mantener la conexión activa

        # Consultar y mostrar información sobre trades activos
        try:
            while True:
                # Consultar posiciones abiertas
                positions = mt5.positions_get()
                print("\n=== POSICIONES ABIERTAS ===")
                if positions:
                    for position in positions:
                        print(f"Ticket: {position.ticket}, Símbolo: {position.symbol}, Tipo: {'COMPRA' if position.type == 0 else 'VENTA'}, Volumen: {position.volume}")
                        print(f"  Precio de apertura: {position.price_open}, Precio actual: {position.price_current}")
                        print(f"  Beneficio: {position.profit} USD, Swap: {position.swap}")
                        print(f"  Comentario: {position.comment}")
                        print("------------------------------")
                else:
                    print("No hay posiciones abiertas actualmente.")

                # Consultar órdenes pendientes
                orders = mt5.orders_get()
                print("\n=== ÓRDENES PENDIENTES ===")
                if orders:
                    for order in orders:
                        order_type = {0: "BUY", 1: "SELL", 2: "BUY LIMIT", 3: "SELL LIMIT", 4: "BUY STOP", 5: "SELL STOP"}
                        print(f"Ticket: {order.ticket}, Símbolo: {order.symbol}, Tipo: {order_type.get(order.type, 'DESCONOCIDO')}")
                        print(f"  Volumen: {order.volume_initial}, Precio: {order.price_open}")
                        print(f"  Comentario: {order.comment}")
                        print("------------------------------")
                else:
                    print("No hay órdenes pendientes actualmente.")

                print(f"\nVerificación completada: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(2)  # Esperar 2 segundos antes de la siguiente ejecución

        except KeyboardInterrupt:
            print("\nDesconectando de MetaTrader 5...")
        finally:
            # Cerrar la conexión al finalizar
            mt5.shutdown()
            print("Conexión a MetaTrader 5 cerrada.")
    else:
        print(f"¡Error al conectar! Código de error = {mt5.last_error()}")
        mt5.shutdown()
