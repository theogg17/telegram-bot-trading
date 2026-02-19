import csv
import os
import sqlite3


def crear_csv_canales():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    db_path = os.getenv(
        "TRADING_BOT_DB_PATH",
        os.path.join(root_dir, "config", "trading_bot.db"),
    )
    canales_db_dir = os.path.join(script_dir, "CanalesDB")
    nombre_archivo_salida = os.path.join(canales_db_dir, "canalesDB.csv")
    os.makedirs(canales_db_dir, exist_ok=True)

    rows = []
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
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
        rows = conn.execute(
            """
            SELECT id, name, chat_id
            FROM telegram_channels
            WHERE is_active = 1
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        if conn is not None:
            conn.close()

    datos = []
    for r in rows:
        datos.append(
            {
                "canal": str(r["name"]),
                "id_canal": str(r["chat_id"]),
                "indice": int(r["id"]),  # índice estable (ID SQLite)
            }
        )

    with open(nombre_archivo_salida, "w", newline="", encoding="utf-8") as archivo_csv:
        columnas = ["canal", "id_canal", "indice"]
        writer = csv.DictWriter(archivo_csv, fieldnames=columnas)
        writer.writeheader()
        for fila in datos:
            writer.writerow(fila)

    print(f"Archivo '{nombre_archivo_salida}' creado exitosamente.")
    print("\nContenido del archivo:")
    for fila in datos:
        print(f"{fila['canal']}, {fila['id_canal']}, {fila['indice']}")


if __name__ == "__main__":
    crear_csv_canales()
