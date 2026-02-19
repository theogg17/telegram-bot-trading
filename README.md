# Trading Bot (Lector + Operador)

Este proyecto lee senales de trading desde canales de Telegram y las ejecuta en MetaTrader 5.
Ahora incluye un dashboard web para configurar y ejecutar todo sin editar codigo.

Se divide en tres bloques:

- Lector: escucha Telegram, parsea mensajes y guarda eventos en CSV.
- Operador: lee el CSV y ejecuta ordenes en MT5, registrando el historial.
- WebApp: administra canales en SQLite, inicia/detiene procesos y muestra logs en vivo.

## Estructura

- Lector/main.py: arranca el lector (sin instalar dependencias en runtime).
- Lector/telegram_reader.py: escucha mensajes y los escribe en Lector/data/signals.csv.
- Lector/message_parser_chatgpt.py: parsea senales usando OpenAI.
- Lector/config.py: credenciales de Telegram/OpenAI y carga canales activos desde SQLite.
- Operador/daemon.py: bucle que lee signals.csv y envia ordenes a MT5.
- Operador/config_operador.py: credenciales MT5 y parametros de ejecucion.
- Operador/verificador_apertura.py: verifica aperturas y genera snapshots de MT5.
- webapp/app.py: API + control de procesos + CRUD de canales.
- webapp/static/configs.html: perfiles de ejecución + presets del operador + asignaciones Canal.Preset.
- webapp/static/operaciones.html: monitoreo de operaciones abiertas/pending e historial de cerradas.
- webapp/static/mensajes.html: buscador por `message_id`/`event_id`.
- webapp/static/reportes.html: monitoreo/analytics en tiempo real por Canal.Preset.
- webapp/static/tutorial.html: guía funcional de cada configuración.

## Requisitos

- Windows con MetaTrader 5 instalado.
- Python 3.10+ recomendado.
- Paquetes en `requirements.txt` (agrega webapp + Lector + Operador).
- Acceso a Telegram (API ID / API HASH).
- API key de OpenAI (o un proxy compatible con OpenAI).

Instalacion en entorno nuevo (obligatoria):

```powershell
pip install -r requirements.txt
```

## Configuracion

### Opcion recomendada: dashboard web

1) Iniciar la web:

```powershell
pip install -r requirements.txt
python webapp\app.py
```

Autenticacion web (obligatoria):
- Si defines `TRADING_BOT_WEB_USER` y `TRADING_BOT_WEB_PASSWORD`, esas credenciales se usan en todas las rutas.
- Si no defines variables, el sistema genera credenciales y las guarda en `config/web_auth.json`.

2) Abrir `http://127.0.0.1:8000`

3) Navegación:
- `/` Control: iniciar/detener Lector/Operador + canales.
- `/operaciones` Operaciones: abiertas/pending, historial cerrado y detalle por ID.
- `/reportes` Reportes: PnL, ranking, errores y alertas 24/7.
- `/presets` Presets: perfiles de ejecución, presets y asignaciones Canal.Preset.
- `/mensajes` Mensajes: búsqueda por `message_id`/`event_id`.
- `/tutorial` Tutorial: explicación clara de cada ajuste.

4) Configurar en la web:
- Canales de Telegram (nombre + `chat_id` + id externo opcional + activo/no activo).
- Perfiles de ejecución en `/presets`: `SCALP` y `SWING`.
- Presets del Operador en `/presets`: `TOTAL_VOLUME`, `NEAR_ENTRY_PIPS_MIN`, `NEAR_ENTRY_SPREAD_MULT`, `VERIFY_ORDER_AFTER_SEND`, `AUTO_CLOSE_ON_MISMATCH`, perfil de ejecución y credenciales base MT5 (sin password).
- Presets del Operador: guardar configuraciones reutilizables del formulario y marcar una como default.
  - El password de MT5 no se persiste en presets por seguridad; se ingresa al iniciar.
- Asignaciones `Canal.Preset`: activar en modo `real` (1 por canal) o `virtual` (N por canal).
- Eliminaciones de canal/preset/asignación piden confirmación previa en la UI.
- En `Control` puedes programar reinicio automático (recomendado: solo Operador), ver cuenta regresiva y ejecutar un reinicio rápido de prueba.

5) Iniciar/detener Lector y Operador desde el dashboard.

Notas:
- Los canales se guardan en `config/trading_bot.db` (SQLite).
- Los presets del Operador tambien se guardan en `config/trading_bot.db` (tabla `operator_presets`).
- Los perfiles de ejecución se guardan en `config/trading_bot.db` (tabla `execution_profiles`).
- Las asignaciones Canal.Preset se guardan en `config/trading_bot.db` (tabla `channel_config_assignments`).
- Los eventos/beneficios/errores por Canal.Preset se registran en `strategy_event_log`.
- Las operaciones persistidas y su timeline se guardan en `operation_records` + `operation_events`.
- El índice de mensajes Telegram se guarda en `telegram_messages`.
- El Lector solo escucha canales activos.
- Si agregas/eliminas canales con el Lector ya corriendo, reinicialo para aplicar cambios.

### Opcion CLI (fallback)

Tambien puedes seguir ejecutando por consola:

```powershell
python Lector\main.py
python Operador\daemon.py
```

Opcional: copiar signals.csv para monitoreo externo:

```powershell
python Lector\monitor_signals.py
```

Opcional: verificador de aperturas (genera snapshot y errores):

```powershell
python Operador\verificador_apertura.py
```

Para ejecutar una sola verificacion:

```powershell
python Operador\verificador_apertura.py --once
```

## Archivos generados

- config/trading_bot.db: base SQLite con canales.
- Lector/data/signals.csv: eventos de senales parseadas.
- Lector/data/signals.csv incluye event_id para deduplicacion.
- Lector/data/non_signals.csv: mensajes sin señal (reportes, comentarios, etc.).
- Lector/CanalesDB/canalesDB.csv: indice de canales.
- queue/pending/*.json: cola de eventos generada por el Lector.
- queue/processed/*.json: eventos ya procesados por el Operador.
- Operador/ordenes_enviadas.csv: log de ordenes enviadas.
- Operador/orders_index.csv: mapeo entry -> ticket (legacy/fallback).
- Operador/processed_events.csv: deduplicacion legacy (solo migracion/fallback).
- Operador/open_trades.csv: base viva de operaciones abiertas.
- Operador/operaciones_abiertas.csv: snapshot de posiciones y pendientes en MT5.
- Operador/errores_de_aperturas.csv: registro de inconsistencias y fallos.
- SQLite `strategy_event_log`: bitácora de eventos por `Canal.Preset` para reportes.
- SQLite `virtual_positions`: posiciones shadow/virtuales para backtesting en vivo.
- SQLite `operation_records`: operaciones abiertas/cerradas con estado y métricas.
- SQLite `operation_events`: timeline por operación (entry/mod/close/system).
- SQLite `telegram_messages`: índice de mensajes/eventos para búsqueda por ID.
- SQLite `processed_events`: deduplicación principal por `event_uid`.

## Notas y consideraciones

- El parser actual es OpenAI (message_parser_chatgpt.py).
- Modificaciones y cierres funcionan mejor cuando el mensaje es reply al entry original (usa reply_to para enlazar).
- El comentario de orden usa el formato: <channel_index>-<entry_message_id>-<STYLE>. Si se cambia, ajustar Operador/daemon.py.
- El dashboard no guarda credenciales sensibles en SQLite; las inyecta por variables de entorno al iniciar cada proceso.
- Lector/main.py no instala paquetes: requiere entorno con dependencias preinstaladas.
- Entradas muy cercanas al precio actual pueden ejecutarse como MARKET si estan dentro del umbral en pips (configurable).
- El filling mode se selecciona automaticamente por simbolo y tiene fallback si el broker no acepta el modo inicial.
- El comentario de MT5 se compacta si supera 16 caracteres, para evitar rechazos por longitud.
- El Operador prioriza la cola JSON si hay eventos pendientes; si no, usa signals.csv como fallback.
- El operador real abre una sola orden por señal y por asignación real activa.
- Restricción estructural: máximo 1 asignación `real` por canal (`Canal.Preset`).
- SCALP/SWING se gestionan como perfiles independientes en `/presets`.
- El reinicio 24/7 ahora persiste la configuración de arranque cifrada en SQLite (clave local en `config/runtime_env.key`).
- Si `cryptography` no está disponible, se usa fallback funcional no cifrado (recomendado instalar dependencias completas).
- La API web está protegida con Basic Auth.
- Eventos problemáticos en `queue/pending` se mueven a `queue/failed` tras varios reintentos.

## Seguridad operacional del Operador

- `VERIFY_ORDER_AFTER_SEND`:
  - Si esta en `true`, despues de enviar una orden el bot valida que exista en MT5 (por `comment`) con reintentos cortos.
  - Si no la encuentra, registra error `not_found_after_send` en `Operador/errores_de_aperturas.csv`.
  - No cierra nada automaticamente; es una verificacion de consistencia post-envio.

- `AUTO_CLOSE_ON_MISMATCH`:
  - Lo usa `Operador/verificador_apertura.py` al auditar `open_trades.csv` contra MT5.
  - Si detecta inconsistencias (ejemplo: symbol mismatch), y esta en `true`, intenta cerrar/cancelar la operacion inconsistente.
  - Si esta en `false`, solo registra el error y no toma accion correctiva automatica.

## Watchlist y símbolos requeridos

- Al iniciar, el Operador intenta seleccionar y validar simbolos requeridos en Market Watch.
- Incluye por defecto principales pares FX, `XAUUSD` y `BTCUSD`.
- Muestra en logs:
  - simbolos listos para operar (`ready`)
  - simbolos no listos y motivo (`not_found`, `trade_disabled`, `not_visible`, `no_tick`)
- Variables opcionales:
  - `SYMBOLS_REQUIRED`: lista separada por comas con simbolos requeridos.
  - `SYMBOLS_ALWAYS_SELECT`: lista separada por comas para forzar seleccion en watchlist.

## Experimentos Canal.Preset (Opción A)

- El Operador ejecuta una vía real por canal (si existe asignación `real`) y múltiples vías virtuales (`virtual`) en paralelo.
- En vía real: 1 señal => 1 operación (sin split de órdenes).
- Cada nueva asignación o cambio de config comienza a registrar automáticamente en reportes.
- El dashboard `/reportes` muestra:
  - curva principal acumulada por `Canal.Preset`
  - resumen/ranking por combinación
  - tabla de errores en tiempo real con paginación y scroll
  - exportación Excel (`.xlsx`) de errores por rango fecha/hora

## Operaciones y Mensajes

- `/operaciones`:
  - tarjetas de operaciones `OPEN` (azul) y `PENDING` (gris)
  - cronómetro en vivo (días/horas/min/seg)
  - pips actualizados cada ~5s
  - botón a descripción completa por operación
  - historial paginado de operaciones cerradas
- `/operaciones/{id}`:
  - detalle completo con apertura, modificaciones, cierre y IDs de mensaje/evento
  - discriminación de cierre por señal, por error o detección manual MT5
- `/mensajes`:
  - búsqueda por `message_id`, `event_id` o `channel:message_id`
  - muestra canal, hora, tipo de evento y texto/payload asociado

## Alertas 24/7 y Discord

- `/reportes` incluye sección dedicada `Alertas 24/7` (no mezclada con errores).
- Las alertas se registran en SQLite (`alerts_log`) con severidad, ocurrencias, timestamps y estado activa/resuelta.
- Soporta envío proactivo a Discord por webhook:
  - configurar `discord_enabled`, `discord_webhook_url`, `discord_min_severity`
  - botón de prueba desde la UI para validar conectividad.

## Resolución De Cierres/Mods

- Para `modification` y `close`, el operador resuelve la operación en este orden:
  - `reply_to` (si existe) como referencia al `entry_message_id`.
  - `message_id` como fallback.
  - búsqueda en `open_trades.csv` por `channel_index + entry_message_id + perfil esperado`.
  - fallback en `operation_records` (SQLite) por `channel_index + entry_message_id`.
  - fallback final legacy en `orders_index.csv`.
- El log deja trazabilidad con:
  - método de enlace (`reply_to` o `message_id`)
  - método de lookup (exacto por perfil o fallback)
  - clase pedida por señal vs perfil activo (`class_match=true/false`)

## Robustez 24/7 (nuevo)

- SQLite:
  - conexiones con `WAL`, `busy_timeout` y `timeout` para reducir `database is locked`.
- MT5:
  - no se marca cierre manual por una sola ausencia temporal.
  - se exige confirmación en chequeos consecutivos (`MANUAL_CLOSE_CONFIRM_CHECKS`, default `3`).
- Queue:
  - reintentos por evento (`QUEUE_MAX_RETRIES`, default `5`).
  - cuarentena automática en `queue/failed` para no bloquear el loop.
- ACK de eventos:
  - el Operador marca `processed` solo cuando el evento termina en éxito o fallo permanente.
  - errores transitorios quedan en reintento con backoff (`EVENT_RETRY_MAX`, `EVENT_RETRY_BASE_SEC`, `EVENT_RETRY_MAX_SEC`).
- Reconexión MT5:
  - si la sesión MT5 cae, el Operador reintenta `initialize/login` en backoff automático (`MT5_RECONNECT_BASE_SEC`, `MT5_RECONNECT_MAX_SEC`).
  - mientras no hay sesión, no consume eventos operativos para evitar pérdidas.
- Virtual:
  - cierre automático por toque de SL/TP en carteras virtuales (`VIRTUAL_AUTOCLOSE_SLTP=true` por defecto).
- Parser:
  - parseo OpenAI fuera del loop principal de Telegram (`asyncio.to_thread`).
  - timeout configurable (`PARSER_TIMEOUT_SEC`, default `35`).
- Mensajes Telegram:
  - `telegram_messages` ahora guarda 1 fila por evento (no se sobrescriben eventos del mismo `message_id`).
  - búsqueda compatible por `channel:message_id` y por `event_id`.
- Reconcile de arranque:
  - modo seguro por defecto `STARTUP_RECONCILE_MODE=warn` (no autocierra al arrancar, solo advierte).
  - para autocierre explícito: `STARTUP_RECONCILE_MODE=close`.
- Cierre manual desde panel:
  - modo `solo registro` (cierra en DB).
  - modo `cerrar en MT5` (encola evento `panel_close` para que lo ejecute el Operador).
- Retención 24/7:
  - worker de retención con archivo JSON en SQLite (`retention_archive`) y purga por antigüedad configurable.

## Seguridad

- No compartas credenciales reales de Telegram/OpenAI/MT5.
- Si decides persistir credenciales en archivos, usa un metodo seguro (vault o variables de entorno del sistema).
