import csv
import time
import json
import os
from datetime import datetime
import pytz

def monitorear_csv(nombre_archivo):
    """
    Lee continuamente un archivo CSV, notifica nuevas entradas ("entry") imprimiendo la hora de Uruguay,
    guarda la última entrada en un archivo JSON solo si el tipo es "entry",
    y notifica las señales de cierre ("close") por pantalla.

    Args:
        nombre_archivo (str): La ruta del archivo CSV a monitorear.
    """
    lineas_leidas = set()
    ruta_carpeta_json = "new_signal"
    nombre_archivo_json = "new_signal.json"
    ruta_completa_json = os.path.join(ruta_carpeta_json, nombre_archivo_json)

    # Crear la carpeta si no existe
    if not os.path.exists(ruta_carpeta_json):
        os.makedirs(ruta_carpeta_json)

    while True:
        try:
            with open(nombre_archivo, 'r', newline='', encoding='utf-8') as archivo_csv:
                lector_csv = csv.reader(archivo_csv)
                encabezado = next(lector_csv)  # Leer la primera línea como encabezado
                nuevas_entradas = False
                ultima_fila = None
                lineas_actuales = set()
                # Obtener la hora actual en Uruguay
                zona_uruguay = pytz.timezone('America/Montevideo')
                hora_uruguay = datetime.now(zona_uruguay).strftime("%H:%M:%S")

                for fila in lector_csv:
                    linea_tupla = tuple(fila)
                    lineas_actuales.add(linea_tupla)
                    if linea_tupla not in lineas_leidas:
                        if lineas_leidas:  # Evitar el mensaje y JSON en la primera lectura
                            
                            ultima_fila = fila
                            
                        elif not lineas_leidas and fila: # Capturar la primera fila en la primera lectura
                            ultima_fila = fila
                            

                if  ultima_fila:
                    # Crear el diccionario JSON
                    nueva_senal_json = dict(zip(encabezado, ultima_fila))
                    if nueva_senal_json["type"] == "entry":
                        print(f"Nueva entrada a las {hora_uruguay}")
                        # Guardar en archivo JSON
                        with open(ruta_completa_json, 'w', encoding='utf-8') as archivo_json:
                            json.dump(nueva_senal_json, archivo_json, indent=4)  # indent para formato legible
                    else:
                        print("Señal de cierre (close)")
                        

                elif not nuevas_entradas and lineas_leidas:
                    print(".")

                lineas_leidas = lineas_actuales

            time.sleep(1)  # Esperar 1 segundo antes de volver a leer el archivo

        except FileNotFoundError:
            print(f"Error: El archivo '{nombre_archivo}' no fue encontrado.")
            break
        except StopIteration:
            # Esto ocurre si el archivo está vacío después del encabezado
            pass
        except Exception as e:
            print(f"Ocurrió un error: {e}")
            break

if __name__ == "__main__":
    nombre_del_archivo_csv = "../Lector/data/signals.csv"
    monitorear_csv(nombre_del_archivo_csv)
