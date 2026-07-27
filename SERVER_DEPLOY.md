# Despliegue 24/7 en Windows VPS

Esta guía deja WebApp, Tailscale y MetaTrader 5 preparados para funcionamiento continuo en una sesión Windows. Lector y Operador se habilitan después de configurar Telegram/OpenAI y validar la cuenta demo.

## 1. Instalación canónica

Usa una sola copia del proyecto. En este servidor la ruta canónica es:

```text
C:\Users\Administrator\telegram-bot-trading
```

Requisitos:

- Python 3.11 o 3.12 x64.
- Git.
- MetaTrader 5 del broker.
- Tailscale con `Run unattended` habilitado.

Preparación inicial:

```powershell
cd C:\Users\Administrator\telegram-bot-trading
powershell -ExecutionPolicy Bypass -File .\scripts\setup_server.ps1
```

`setup_server.ps1` crea `.venv`, instala dependencias y ejecuta `pip check`. Ante cualquier fallo devuelve error y no anuncia una instalación correcta.

## 2. Prueba manual

```powershell
.\scripts\start_webapp.ps1
```

La WebApp debe escuchar solamente en:

```text
http://127.0.0.1:8000
```

No publiques el puerto `8000` ni cambies el bind a `0.0.0.0`. Para acceso remoto privado usa Tailscale Serve hacia `http://127.0.0.1:8000`.

## 3. Tareas de Windows

Abre PowerShell **como administrador** y ejecuta:

```powershell
cd C:\Users\Administrator\telegram-bot-trading

powershell -ExecutionPolicy Bypass -File .\scripts\register_mt5_task.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\register_webapp_task.ps1
```

Registra primero sin iniciar para no duplicar una WebApp o un MT5 abiertos
manualmente. Haz después el traspaso controlado: cierra MT5 con
`Archivo > Salir`, detén con `Ctrl+C` cualquier WebApp manual y comprueba que
ya no exista `terminal64.exe` ni un listener en el puerto 8000. Entonces:

```powershell
Start-ScheduledTask -TaskName TradingBotMT5
Start-ScheduledTask -TaskName TradingBotWebApp

# Espera a que /livez devuelva {"status":"ok"}.
powershell -ExecutionPolicy Bypass -File .\scripts\register_webapp_watchdog_task.ps1 -RunNow
```

Se crean:

- `TradingBotMT5`: abre MetaTrader 5 al iniciar sesión.
- `TradingBotWebApp`: WebApp sin límite de 72 horas, una sola instancia y recuperación ante salida.
- `TradingBotWebAppWatchdog`: consulta `/livez` y MT5 cada minuto; exige dos fallos consecutivos y hace `stop -> start` con cooldown si la WebApp no responde, y reinicia la tarea de MT5 si el terminal desaparece.

La WebApp se ejecuta con token limitado. Solo el watchdog usa elevación para recuperar una tarea colgada.

## 4. Sesión de Windows y RDP

MT5 necesita la sesión interactiva del mismo usuario. Desconecta RDP cerrando la ventana; **no elijas Cerrar sesión/Sign out**.

Las tareas arrancan al iniciar sesión. Después de un reinicio completo de Windows debes volver a iniciar sesión una vez. Automatizar también ese punto exige una cuenta Windows dedicada y una decisión explícita sobre autologon; no se habilita por defecto porque reduce la seguridad del VPS.

## 5. Salud y diagnóstico

Endpoints:

```text
http://127.0.0.1:8000/livez
http://127.0.0.1:8000/healthz
http://127.0.0.1:8000/api/health/24x7
http://127.0.0.1:8000/api/backup/status
```

- `/livez`: liveness mínimo usado por el watchdog.
- `/healthz`: DB, disco, cola, backup y procesos esperados.
- Los endpoints `/api/*` requieren login.

Chequeo integral, desde PowerShell como administrador:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_server_24x7.ps1
```

Cuando Lector y Operador deban estar activos:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_server_24x7.ps1 -RequireLector -RequireOperador
```

Códigos: `0` correcto, `1` advertencias, `2` fallo. El chequeo valida tareas, puerto loopback, duplicados, MT5 interactivo, Tailscale Serve, autenticación, antigüedad del backup, CRC del ZIP y `PRAGMA integrity_check` de SQLite.

## 6. Seguridad de ejecución MT5

El Operador arranca **desarmado** por defecto:

- `TRADING_BOT_EXECUTION_ARMED=false`: bloquea aperturas, modificaciones, cierres y cancelaciones MT5; las carteras virtuales continúan.
- `TRADING_BOT_REQUIRE_DEMO_ACCOUNT=true`: rechaza una cuenta que no sea demo.
- `ENTRY_EVENT_TTL_SEC=300`: una entrada con más de cinco minutos, sin timestamp o inválida no puede abrir una orden tardía.

El panel muestra una casilla separada para armar envíos a MT5 y pide confirmación. La ruta del panel fuerza siempre cuenta demo. El cambio futuro a dinero real requiere una modificación deliberada del servidor.

Las asignaciones creadas o promovidas automáticamente al modo `real` nacen inactivas y deben habilitarse de forma explícita desde el panel.

Lector y Operador tienen lock de instancia única para impedir duplicados después de una caída.

## 7. Backups y logs

- Logs persistentes y rotados en `logs/`.
- Backups locales diarios en `backups/`.
- Retención de backups: 14 días al ejecutar mediante la tarea de producción.
- Cada backup nuevo valida SQLite, CRC del ZIP, manifiesto SHA-256 interno y sidecar `.sha256`.
- Si un backup falla, reintenta aproximadamente un minuto después.

El ZIP incluye snapshot consistente de SQLite, datos del Lector, CSV del Operador y colas pending/failed. No incluye secretos de recuperación como `config/runtime_env.key` o la sesión Telegram: deben copiarse por separado a almacenamiento externo cifrado.

Un backup local no protege ante pérdida completa de la VPS. Activa snapshots del proveedor o define posteriormente un destino externo.

## 8. Orden seguro de activación

1. Mantener WebApp, Tailscale y MT5 encendidos.
2. Vincular Telegram desde el panel.
3. Configurar API key/modelo de OpenAI.
4. Mantener todas las asignaciones MT5 reales inactivas y probar carteras virtuales.
5. Iniciar Operador desarmado y revisar logs/health.
6. Seleccionar un solo canal, cuenta demo y volumen mínimo.
7. Armar el Operador y realizar una prueba controlada.
8. Ejecutar el chequeo 24/7 y observar durante al menos 24 horas antes de ampliar canales.
