# Despliegue 24/7 en Windows VPS

Guia corta para dejar el bot ejecutandose en una VPS Windows con RDP.

## 1. Instalar base

En la VPS instala:

- Python 3.11 o 3.12 x64.
- Git.
- MetaTrader 5 del broker.
- Tailscale para acceso privado por RDP.
- Opcional: Cloudflare Tunnel si vas a publicar la web con dominio.

Clona el repo y entra a la carpeta:

```powershell
git clone https://github.com/theogg17/telegram-bot-trading.git
cd telegram-bot-trading
```

Prepara el entorno:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_server.ps1
```

## 2. Probar manualmente

Antes de registrar tareas, prueba la WebApp:

```powershell
.\scripts\start_webapp.ps1
```

Abre:

```text
http://127.0.0.1:8000
```

Desde el panel configura:

- Sesion Telegram del Lector.
- OpenAI API key/modelo.
- Presets MT5.
- Canales y Canal.Preset.
- MT5 password al iniciar el Operador.

## 3. Registrar arranque automatico

Con PowerShell como administrador:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_webapp_task.ps1 -RunNow
```

Esto crea una tarea llamada `TradingBotWebApp` que arranca la WebApp cuando el usuario de Windows inicia sesion.

Para MT5 es preferible mantener la sesion de Windows iniciada y desconectar RDP sin cerrar sesion.

## 4. Registrar watchdog externo

Con PowerShell como administrador:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_webapp_watchdog_task.ps1
```

Esto crea una tarea que revisa `http://127.0.0.1:8000/healthz` cada minuto y vuelve a arrancar la WebApp si no responde.

## 5. Estado 24/7

Endpoints utiles:

```text
http://127.0.0.1:8000/healthz
http://127.0.0.1:8000/api/health/24x7
http://127.0.0.1:8000/api/backup/status
```

`/api/health/24x7` requiere login web.

## 6. Backups y logs

La WebApp genera:

- Logs persistentes en `logs/`.
- Backups ZIP en `backups/`.

El backup local incluye:

- Snapshot consistente de `config/trading_bot.db`.
- `Lector/data`.
- `Operador/*.csv`.
- `queue/pending`.
- `queue/failed`.

El backup local no reemplaza un backup externo. Para produccion conviene copiar `backups/` a un storage externo o activar Auto Backup del proveedor.

## 7. Acceso seguro

No abras publicamente estos puertos:

- RDP `3389`.
- WebApp `8000`.

Opciones recomendadas:

- Privado: Tailscale y entrar por IP Tailscale.
- Web segura: Cloudflare Tunnel + Access hacia `http://127.0.0.1:8000`.
