import json
import csv
import os
import time

def registrar_datos_csv(ruta_json, ruta_csv):
    """
    Lee datos de un archivo JSON y los registra en un archivo CSV, evitando duplicados.

    Args:
        ruta_json (str): La ruta al archivo JSON.
        ruta_csv (str): La ruta al archivo CSV.
    """
    try:
        with open(ruta_json, 'r') as archivo_json:
            datos_json = json.load(archivo_json)

        if not datos_json:
            print(f"El archivo JSON '{ruta_json}' está vacío.")
            return

        encabezados = list(datos_json.keys())

        # Verificar si el archivo CSV existe y leer los datos existentes
        datos_existentes = []
        existe_csv = os.path.exists(ruta_csv)
        if existe_csv:
            with open(ruta_csv, 'r', newline='') as archivo_csv:
                lector_csv = csv.DictReader(archivo_csv)
                datos_existentes = list(lector_csv)

        # Verificar si el registro ya existe
        if datos_json not in datos_existentes:
            with open(ruta_csv, 'a', newline='') as archivo_csv:
                escritor_csv = csv.DictWriter(archivo_csv, fieldnames=encabezados)

                # Escribir encabezados si el archivo es nuevo
                if not existe_csv:
                    escritor_csv.writeheader()

                escritor_csv.writerow(datos_json)
            print(f"Datos del archivo '{ruta_json}' registrados en '{ruta_csv}'.")
        else:
            print(f"Los datos del archivo '{ruta_json}' ya existen en '{ruta_csv}'. No se registraron duplicados.")

    except FileNotFoundError:
        print(f"Error: No se encontró el archivo JSON en la ruta '{ruta_json}'.")
    except json.JSONDecodeError:
        print(f"Error: El archivo '{ruta_json}' no contiene un JSON válido.")
    except Exception as e:
        print(f"Ocurrió un error: {e}")

def monitorear_ubicacion(ubicacion_json, ruta_csv, intervalo=5):
    """
    Monitorea una ubicación en busca de archivos JSON para registrar.

    Args:
        ubicacion_json (str): La ruta al directorio donde se buscarán los archivos JSON.
        ruta_csv (str): La ruta al archivo CSV donde se registrarán los datos.
        intervalo (int): El intervalo de tiempo en segundos para verificar la ubicación.
    """
    while True:
        try:
            archivos_encontrados = [f for f in os.listdir(ubicacion_json) if f.endswith(".json")]

            if archivos_encontrados:
                for archivo in archivos_encontrados:
                    ruta_completa_json = os.path.join(ubicacion_json, archivo)
                    registrar_datos_csv(ruta_completa_json, ruta_csv)
                    # Opcional: Puedes mover o eliminar el archivo JSON después de procesarlo
                    # os.remove(ruta_completa_json)
            else:
                print(f"Esperando archivos JSON en '{ubicacion_json}'...")
        except FileNotFoundError:
            print(f"Error: No se encontró el directorio '{ubicacion_json}'.")
        except NotADirectoryError:
            print(f"Error: '{ubicacion_json}' no es un directorio válido.")
        except Exception as e:
            print(f"Ocurrió un error al listar archivos: {e}")

        time.sleep(intervalo)

if __name__ == "__main__":
    ubicacion_json = "new_signal"
    carpeta_csv = "ordenes_registradas"
    nombre_archivo_csv = "ordenes_registradas.csv"
    ruta_csv = os.path.join(carpeta_csv, nombre_archivo_csv)

    # Asegúrate de que el directorio de los archivos JSON exista
    if not os.path.exists(ubicacion_json):
        print(f"Error: El directorio '{ubicacion_json}' no existe.")
    elif not os.path.isdir(ubicacion_json):
        print(f"Error: '{ubicacion_json}' no es un directorio.")
    else:
        # Crear la carpeta para el archivo CSV si no existe
        if not os.path.exists(carpeta_csv):
            try:
                os.makedirs(carpeta_csv)
                print(f"Se creó la carpeta para el CSV: '{carpeta_csv}'.")
            except OSError as e:
                print(f"Error al crear la carpeta '{carpeta_csv}': {e}")

        monitorear_ubicacion(ubicacion_json, ruta_csv)