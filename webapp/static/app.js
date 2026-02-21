const lectorLog = document.getElementById("log-lector");
const operadorLog = document.getElementById("log-operador");
const lectorMsg = document.getElementById("lector-msg");
const operadorMsg = document.getElementById("operador-msg");
const channelsMsg = document.getElementById("channels-msg");
const statusLector = document.getElementById("status-lector");
const statusOperador = document.getElementById("status-operador");
const globalStatus = document.getElementById("global-status");
const dbPath = document.getElementById("db-path");
const channelsBody = document.getElementById("channels-body");
const restartMsg = document.getElementById("restart-msg");
const restartEnabled = document.getElementById("restart-enabled");
const restartInterval = document.getElementById("restart-interval-min");
const restartTarget = document.getElementById("restart-target");
const restartNextAt = document.getElementById("restart-next-at");
const restartCountdown = document.getElementById("restart-countdown");
const controlErrorsMsg = document.getElementById("control-errors-msg");
const controlErrorsBody = document.getElementById("control-errors-body");

const lectorLines = [];
const operadorLines = [];
let restartRemaining = null;

function showSavedToast(message) {
  if (typeof window.showSavedToast === "function") {
    window.showSavedToast(message);
  }
}

function appendLine(el, store, line) {
  store.push(line);
  if (store.length > 800) {
    store.shift();
  }
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 10;
  el.textContent = store.join("\n");
  if (atBottom) {
    el.scrollTop = el.scrollHeight;
  }
}

function setStatus(el, running) {
  el.textContent = running ? "online" : "offline";
  el.classList.toggle("online", running);
}

function fmtTs(value) {
  if (!value) {
    return "-";
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return String(value);
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function fmtCountdown(totalSeconds) {
  if (!Number.isFinite(Number(totalSeconds))) {
    return "-";
  }
  const s = Math.max(0, Number(totalSeconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  const d = days > 0 ? `${days}d ` : "";
  return `${d}${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

async function readJson(res) {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

function setChannelForm(channel = null) {
  document.getElementById("channel_id").value = channel ? channel.id : "";
  document.getElementById("channel_name").value = channel ? channel.name : "";
  document.getElementById("channel_chat_id").value = channel ? channel.chat_id : "";
  document.getElementById("channel_external_id").value = channel ? channel.external_id : "";
  document.getElementById("channel_is_active").checked = channel ? !!channel.is_active : true;
}

function renderChannels(channels) {
  channelsBody.innerHTML = "";
  if (!channels || channels.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="empty">No hay canales cargados</td>';
    channelsBody.appendChild(tr);
    return;
  }

  for (const channel of channels) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${channel.id}</td>
      <td>${channel.name}</td>
      <td><code>${channel.chat_id}</code></td>
      <td>${channel.external_id || "-"}</td>
      <td>${channel.is_active ? "si" : "no"}</td>
      <td class="row-actions">
        <button class="mini-btn" data-action="edit" data-id="${channel.id}">Editar</button>
        <button class="mini-btn danger" data-action="delete" data-id="${channel.id}">Eliminar</button>
      </td>
    `;
    channelsBody.appendChild(tr);
  }
}

async function loadChannels() {
  channelsMsg.textContent = "Cargando canales...";
  const res = await fetch("/api/channels");
  const data = await readJson(res);
  if (!res.ok) {
    channelsMsg.textContent = data.detail || "Error al cargar canales";
    return;
  }
  renderChannels(data.channels || []);
  channelsMsg.textContent = `${(data.channels || []).length} canal(es)`;
}

function channelPayloadFromForm() {
  return {
    name: document.getElementById("channel_name").value.trim(),
    chat_id: document.getElementById("channel_chat_id").value.trim(),
    external_id: document.getElementById("channel_external_id").value.trim(),
    is_active: document.getElementById("channel_is_active").checked,
  };
}

async function saveChannel() {
  const id = document.getElementById("channel_id").value.trim();
  const payload = channelPayloadFromForm();
  if (!payload.name || !payload.chat_id) {
    channelsMsg.textContent = "Nombre y chat ID son obligatorios";
    return;
  }
  channelsMsg.textContent = id ? "Actualizando canal..." : "Creando canal...";

  const endpoint = id ? `/api/channels/${id}` : "/api/channels";
  const method = id ? "PUT" : "POST";
  const res = await fetch(endpoint, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    channelsMsg.textContent = data.detail || "No se pudo guardar";
    return;
  }
  renderChannels(data.channels || []);
  channelsMsg.textContent = id ? "Canal actualizado" : "Canal creado";
  setChannelForm();
}

async function removeChannel(id) {
  if (!window.confirm("Seguro que quieres eliminar este canal?")) {
    return;
  }
  channelsMsg.textContent = "Eliminando canal...";
  const res = await fetch(`/api/channels/${id}`, { method: "DELETE" });
  const data = await readJson(res);
  if (!res.ok) {
    channelsMsg.textContent = data.detail || "No se pudo eliminar";
    return;
  }
  renderChannels(data.channels || []);
  channelsMsg.textContent = "Canal eliminado";
  setChannelForm();
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await readJson(res);
    setStatus(statusLector, !!data.lector?.running);
    setStatus(statusOperador, !!data.operador?.running);
    if (typeof window.applyGlobalHeaderStatus === "function") {
      window.applyGlobalHeaderStatus(data);
    } else {
      const anyRunning = !!(data.lector?.running || data.operador?.running);
      globalStatus.textContent = anyRunning ? "ONLINE" : "OFFLINE";
      globalStatus.classList.toggle("online", anyRunning);
      if (data.db_path) {
        dbPath.textContent = `db: ${data.db_path}`;
      }
    }
    const restart = data.auto_restart || {};
    restartEnabled.checked = !!restart.enabled;
    restartInterval.value = String(restart.interval_minutes || 240);
    restartTarget.value = restart.target || "operador";
    restartNextAt.value = fmtTs(restart.next_restart_at || "");
    restartRemaining = Number.isFinite(Number(restart.seconds_remaining)) ? Number(restart.seconds_remaining) : null;
    restartCountdown.value = restartRemaining == null ? "-" : fmtCountdown(restartRemaining);
    const defaults = data.operador_defaults || {};
    if (!document.getElementById("mt5_terminal_path").value.trim()) {
      document.getElementById("mt5_terminal_path").value = defaults.mt5_terminal_path || data.mt5_terminal_default || "";
    }
    if (!document.getElementById("mt5_login").value.trim() && Number.isFinite(Number(defaults.mt5_login))) {
      document.getElementById("mt5_login").value = String(defaults.mt5_login);
    }
    if (!document.getElementById("mt5_server").value.trim() && defaults.mt5_server) {
      document.getElementById("mt5_server").value = defaults.mt5_server;
    }
  } catch {
    if (typeof window.applyGlobalHeaderStatus === "function") {
      window.applyGlobalHeaderStatus(null);
    } else {
      globalStatus.textContent = "OFFLINE";
      globalStatus.classList.remove("online");
    }
  }
}

async function saveRestartConfig() {
  const payload = {
    enabled: restartEnabled.checked,
    interval_minutes: Number(restartInterval.value || 240),
    target: restartTarget.value,
  };
  if (!Number.isFinite(payload.interval_minutes) || payload.interval_minutes < 5) {
    restartMsg.textContent = "Intervalo mínimo: 5 minutos";
    return;
  }
  restartMsg.textContent = "Guardando programación...";
  const res = await fetch("/api/restart/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    restartMsg.textContent = data.detail || "No se pudo guardar";
    return;
  }
  restartMsg.textContent = "Programación guardada";
  showSavedToast("Configuración guardada correctamente");
  await refreshStatus();
}

async function restartNowQuick() {
  if (!window.confirm("Se ejecutará reinicio controlado ahora. ¿Continuar?")) {
    return;
  }
  restartMsg.textContent = "Ejecutando reinicio rápido...";
  const res = await fetch("/api/restart/now", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target: restartTarget.value }),
  });
  const data = await readJson(res);
  if (!res.ok) {
    restartMsg.textContent = data.detail || "Falló reinicio rápido";
    return;
  }
  const status = data.result?.status || "ok";
  restartMsg.textContent = `Reinicio rápido: ${status}`;
  await refreshStatus();
}

async function seedRecommendedPresets() {
  restartMsg.textContent = "Cargando presets recomendados...";
  const res = await fetch("/api/operator-presets/seed-recommended", { method: "POST" });
  const data = await readJson(res);
  if (!res.ok) {
    restartMsg.textContent = data.detail || "No se pudieron cargar presets";
    return;
  }
  restartMsg.textContent = `Presets recomendados listos (${(data.presets || []).length} total)`;
  showSavedToast("Presets recomendados guardados");
}

function renderControlErrors(items) {
  if (!controlErrorsBody) {
    return;
  }
  controlErrorsBody.innerHTML = "";
  const rows = items || [];
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="empty">Sin errores recientes</td>';
    controlErrorsBody.appendChild(tr);
    return;
  }
  for (const it of rows) {
    const preset = it.preset_name || it.config_name || "-";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtTs(it.ts)}</td>
      <td>${it.channel_name}.${preset}</td>
      <td>${it.mode}</td>
      <td>${it.event_type}</td>
      <td>${it.error_type || it.status}</td>
      <td>${it.details || "-"}</td>
    `;
    controlErrorsBody.appendChild(tr);
  }
}

async function refreshControlErrors() {
  if (!controlErrorsMsg || !controlErrorsBody) {
    return;
  }
  try {
    const res = await fetch("/api/reportes/errors?page=1&page_size=20");
    const data = await readJson(res);
    if (!res.ok) {
      controlErrorsMsg.textContent = data.detail || "Error actualizando errores";
      return;
    }
    renderControlErrors(data.items || []);
    controlErrorsMsg.textContent = `${(data.items || []).length} error(es)`;
  } catch {
    controlErrorsMsg.textContent = "Error actualizando errores";
  }
}

async function startLector() {
  const payload = {
    telegram_api_id: Number(document.getElementById("telegram_api_id").value),
    telegram_api_hash: document.getElementById("telegram_api_hash").value,
    openai_api_key: document.getElementById("openai_api_key").value,
    openai_model: document.getElementById("openai_model").value,
    openai_base_url: document.getElementById("openai_base_url").value,
  };
  if (!Number.isFinite(payload.telegram_api_id) || payload.telegram_api_id <= 0) {
    lectorMsg.textContent = "Telegram API ID inválido";
    return;
  }
  if (!payload.telegram_api_hash || !payload.openai_api_key || !payload.openai_model) {
    lectorMsg.textContent = "Completa API Hash, OpenAI Key y modelo";
    return;
  }
  lectorMsg.textContent = "Iniciando...";
  const res = await fetch("/api/start/lector", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  lectorMsg.textContent = res.ok ? "Lector iniciado" : data.detail || "Fallo al iniciar";
  refreshStatus();
}

async function stopLector() {
  lectorMsg.textContent = "Deteniendo...";
  await fetch("/api/stop/lector", { method: "POST" });
  lectorMsg.textContent = "Lector detenido";
  refreshStatus();
}

async function startOperador() {
  const payload = {
    mt5_terminal_path: document.getElementById("mt5_terminal_path").value.trim(),
    mt5_login: Number(document.getElementById("mt5_login").value),
    mt5_password: document.getElementById("mt5_password").value,
    mt5_server: document.getElementById("mt5_server").value.trim(),
  };
  if (!payload.mt5_terminal_path || !Number.isFinite(payload.mt5_login) || payload.mt5_login <= 0 || !payload.mt5_password || !payload.mt5_server) {
    operadorMsg.textContent = "Completa terminal path, login, password y server";
    return;
  }
  operadorMsg.textContent = "Iniciando...";
  const res = await fetch("/api/start/operador", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  operadorMsg.textContent = res.ok ? "Operador iniciado" : data.detail || "Fallo al iniciar";
  refreshStatus();
}

async function stopOperador() {
  operadorMsg.textContent = "Deteniendo...";
  await fetch("/api/stop/operador", { method: "POST" });
  operadorMsg.textContent = "Operador detenido";
  refreshStatus();
}

function initStreams() {
  const lectorSource = new EventSource("/api/logs/lector");
  lectorSource.onmessage = (event) => appendLine(lectorLog, lectorLines, event.data);

  const operadorSource = new EventSource("/api/logs/operador");
  operadorSource.onmessage = (event) => appendLine(operadorLog, operadorLines, event.data);
}

function initActions() {
  document.getElementById("start-lector").addEventListener("click", startLector);
  document.getElementById("stop-lector").addEventListener("click", stopLector);
  document.getElementById("start-operador").addEventListener("click", startOperador);
  document.getElementById("stop-operador").addEventListener("click", stopOperador);

  const saveChannelBtn = document.getElementById("save-channel");
  const clearChannelBtn = document.getElementById("clear-channel");
  const refreshChannelsBtn = document.getElementById("refresh-channels");
  if (saveChannelBtn && clearChannelBtn && refreshChannelsBtn && channelsMsg) {
    saveChannelBtn.addEventListener("click", saveChannel);
    clearChannelBtn.addEventListener("click", () => {
      setChannelForm();
      channelsMsg.textContent = "Formulario limpio";
    });
    refreshChannelsBtn.addEventListener("click", loadChannels);
  }
  document.getElementById("restart-save").addEventListener("click", saveRestartConfig);
  document.getElementById("restart-now").addEventListener("click", restartNowQuick);
  document.getElementById("seed-recommended-presets").addEventListener("click", seedRecommendedPresets);
  const controlErrorsRefreshBtn = document.getElementById("control-errors-refresh");
  if (controlErrorsRefreshBtn) {
    controlErrorsRefreshBtn.addEventListener("click", refreshControlErrors);
  }

  if (channelsBody && channelsMsg) {
    channelsBody.addEventListener("click", async (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) {
        return;
      }
      const id = Number(btn.dataset.id);
      if (!id) {
        return;
      }

      if (btn.dataset.action === "delete") {
        await removeChannel(id);
        return;
      }
      if (btn.dataset.action === "edit") {
        const res = await fetch("/api/channels");
        const data = await readJson(res);
        const channel = (data.channels || []).find((c) => c.id === id);
        if (channel) {
          setChannelForm(channel);
          channelsMsg.textContent = `Editando canal #${id}`;
        }
      }
    });
  }
}

function initDefaults() {
  document.getElementById("openai_model").value = "gpt-4o-mini";
  restartCountdown.value = "-";
  restartNextAt.value = "-";
}

function startCountdownTicker() {
  setInterval(() => {
    if (restartRemaining == null) {
      restartCountdown.value = "-";
      return;
    }
    restartRemaining = Math.max(0, restartRemaining - 1);
    restartCountdown.value = fmtCountdown(restartRemaining);
  }, 1000);
}

initDefaults();
initStreams();
initActions();
refreshStatus();
refreshControlErrors();
startCountdownTicker();
setInterval(refreshStatus, 1000);
setInterval(refreshControlErrors, 5000);
