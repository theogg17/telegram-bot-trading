import time
import json
import os
import MetaTrader5 as mt5
from datetime import datetime
import pytz

# --- Configuración de MetaTrader 5 ---
credentials = {
    "path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
    "login": 166467033,
    "pass": "Hola2001//",
    "server": "XMGlobal-MT5 2",
    "timeout": 60000,
    "portable": False,
    "volume": 0.01,
    "magic_number": 123456,
    "filling_mode": mt5.ORDER_FILLING_IOC
}

# Es muy importante configurar filling_mode : cada broker admite un tipo distinto. en el caso de XMGlobal se debe usar ORDER_FILLING_IOC

# --- Configuración de la carpeta de señales ---
signal_folder = "new_signal"
signal_file = "new_signal.json"
full_signal_path = os.path.join(signal_folder, signal_file)

# --- Umbral para considerar el precio de entrada como "instantáneo" ---
INSTANT_EXECUTION_THRESHOLD = 0.0001

# --- Registro de señales procesadas ---
processed_signals = set()

def initialize_mt5():
    """Inicializa la conexión con MetaTrader 5."""
    if not mt5.initialize(**credentials):
        print(f"Error al inicializar MetaTrader 5: {mt5.last_error()}")
        return False
    account_info = mt5.account_info()
    terminal_info = mt5.terminal_info()
    if account_info is not None and terminal_info is not None:
        print(f"Conexión a MetaTrader 5 establecida con la cuenta {account_info.login} en el terminal '{terminal_info.name}'")
        return True
    else:
        print("Error al obtener información de la cuenta o del terminal.")
        mt5.shutdown()
        return False

def shutdown_mt5():
    """Cierra la conexión con MetaTrader 5."""
    mt5.shutdown()
    print("Conexión a MetaTrader 5 cerrada.")

def execute_trade(signal_data):
    """Ejecuta una operación en MetaTrader 5 basada en los datos de la señal."""
    symbol = signal_data.get("symbol")
    operation = signal_data.get("operation")
    entry_price_str = signal_data.get("entry_price")
    stop_loss_str = signal_data.get("stop_loss")
    take_profit_str = signal_data.get("take_profit")
    channel = signal_data.get("channel", "N/A")
    channel_index = signal_data.get("channel_index")
    message_id = signal_data.get("message_id", "N/A")
    magic_number = credentials.get("magic_number")
    volume = credentials.get("volume")
    comment = f"{channel_index}-{message_id}"
    signal_identifier = (channel, message_id)

    if signal_identifier in processed_signals:
        print(f"Señal ya procesada: Channel={channel}, Message ID={message_id}. Ignorando.")
        return

    if not all([symbol, operation, stop_loss_str, take_profit_str]):
        print(f"Faltan datos esenciales en la señal: {signal_data}")
        return

# VERIFICAR QUE SYMBOL ESTÉ EN MARKET WATCH, SI NO ESTÁ: INTENTAR AGREGARLO
    symbol_info = mt5.symbol_info(symbol)

    if symbol_info is not None:
        print(f"El símbolo '{symbol}' se encuentra en el MarketWatch.")
        
        # Verificar filling modes disponibles
        filling_modes = symbol_info.filling_mode
        print(f"Modos de llenado soportados para {symbol}: {filling_modes}")
        
    else:
        print(f"El símbolo '{symbol}' NO se encuentra en MarketWatch.")
        print("Agregando símbolo a MarketWatch...")
        agregado = mt5.symbol_select(symbol, True)
        time.sleep(2)  # Espera 2 segundos para que se agregue el símbolo

        symbol_info_despues_agregar = mt5.symbol_info(symbol)

        if symbol_info_despues_agregar is None:
            print(f"¡Error al agregar el símbolo '{symbol}' a MarketWatch!")
                
        else:
            print(f"El símbolo '{symbol}' se agregó a MarketWatch exitosamente.")

    sl = float(stop_loss_str)
    tp = float(take_profit_str)

    point = symbol_info.point

    if entry_price_str == "instantly":
        if operation == "BUY":
            trade_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask
        elif operation == "SELL":
            trade_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
        else:
            print(f"Operación no válida: {operation}")
            return
    else:
        try:
            entry_price = float(entry_price_str)
            current_ask = mt5.symbol_info_tick(symbol).ask
            current_bid = mt5.symbol_info_tick(symbol).bid

            if operation == "BUY":
                if abs(entry_price - current_ask) <= INSTANT_EXECUTION_THRESHOLD:
                    trade_type = mt5.ORDER_TYPE_BUY
                    price = current_ask
                elif entry_price > current_ask:
                    trade_type = mt5.ORDER_TYPE_BUY_STOP
                    price = entry_price
                elif entry_price < current_bid:
                    trade_type = mt5.ORDER_TYPE_BUY_LIMIT
                    price = entry_price
                else:
                    print(f"Condición de entrada BUY no clara para {symbol} con precio {entry_price}")
                    return
            elif operation == "SELL":
                if abs(entry_price - current_bid) <= INSTANT_EXECUTION_THRESHOLD:
                    trade_type = mt5.ORDER_TYPE_SELL
                    price = current_bid
                elif entry_price < current_bid:
                    trade_type = mt5.ORDER_TYPE_SELL_STOP
                    price = entry_price
                elif entry_price > current_ask:
                    trade_type = mt5.ORDER_TYPE_SELL_LIMIT
                    price = entry_price
                else:
                    print(f"Condición de entrada SELL no clara para {symbol} con precio {entry_price}")
                    return
            else:
                print(f"Operación no válida: {operation}")
                return
        except ValueError:
            print(f"Error al convertir el precio de entrada: {entry_price_str}")
            return
    request = {
        "action": mt5.TRADE_ACTION_DEAL if entry_price_str == "instantly" else mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": trade_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": magic_number,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": credentials.get("filling_mode"),
    }
     
    result = mt5.order_send(request)
    if result is None:
        print("Error: No se recibió respuesta del servidor")
    else:
        print(f"Código de retorno: {result.retcode}, Descripción: {mt5.last_error()}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Error al enviar la orden: {result}")
        else:
            print(f"Orden {operation} para {symbol} colocada exitosamente...")
            print(f"Ticket: {result.order}, Precio: {price}, SL: {sl}, TP: {tp}, Comentario: {comment}")
            processed_signals.add(signal_identifier)
    
########### verificación de correcta apertura(contrastando con csv de ordenes_registradas) (punto de cruce del flujo del dato en esquema)
            time.sleep(2)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"Orden enviada exitosamente con ticket: {result.order}")
                import verificador_apertura  # Importa el script de verificación
                verificador_apertura.verificar_orden() # Llama a la función de verificación
            else:
                print(f"Error al enviar la orden: {result}")
                
###################################################################
            
            
            
            
def process_signal_file():
    """Procesa el archivo de señal JSON si existe."""
    if os.path.exists(full_signal_path):
        try:
            with open(full_signal_path, 'r') as f:
                signal_data = json.load(f)
            print(f"Archivo de señal leído: {signal_data}")
            execute_trade(signal_data)
            # El archivo JSON NO se elimina en esta versión
        except json.JSONDecodeError:
            print(f"Error al decodificar el archivo JSON: {full_signal_path}")
        except Exception as e:
            print(f"Ocurrió un error al procesar el archivo: {e}")

def main():
    """Función principal del script."""
    if not os.path.exists(signal_folder):
        os.makedirs(signal_folder)
        print(f"Carpeta de señales '{signal_folder}' creada.")

    if initialize_mt5():
        try:
            while True:
                process_signal_file()
                time.sleep(1)  # Revisa cada segundo por nuevos archivos
        except KeyboardInterrupt:
            print("Script detenido por el usuario.")
        finally:
            shutdown_mt5()

if __name__ == "__main__":
    main()
    
