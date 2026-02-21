const dbPath = document.getElementById("db-path");
const globalStatus = document.getElementById("global-status");
const alertsMsg = document.getElementById("alerts-msg");
const alertsActiveBody = document.getElementById("alerts-active-body");
const alertsHistoryBody = document.getElementById("alerts-history-body");
const alertsHistoryInfo = document.getElementById("alerts-history-info");
const alertsHistoryPageInfo = document.getElementById("alerts-history-page-info");
const alertsHistoryFromTs = document.getElementById("alerts-history-from-ts");
const alertsHistoryToTs = document.getElementById("alerts-history-to-ts");
const alertsHistoryApplyBtn = document.getElementById("alerts-history-apply");
const alertsHistoryClearBtn = document.getElementById("alerts-history-clear");
const alertsHistoryPrevBtn = document.getElementById("alerts-history-prev");
const alertsHistoryNextBtn = document.getElementById("alerts-history-next");

const alertsEnabledInput = document.getElementById("alerts-enabled");
const alertsQueueThresholdInput = document.getElementById("alerts-queue-threshold");
const alertsErrorThresholdInput = document.getElementById("alerts-error-threshold");
const alertsPendingSecInput = document.getElementById("alerts-pending-sec");
const alertsDrawdownInput = document.getElementById("alerts-drawdown");
const discordEnabledInput = document.getElementById("discord-enabled");
const discordWebhookInput = document.getElementById("discord-webhook");
const discordMinSeverityInput = document.getElementById("discord-min-severity");
const alertsSaveConfigBtn = document.getElementById("alerts-save-config");
const alertsTestDiscordBtn = document.getElementById("alerts-test-discord");

const errorsBody = document.getElementById("errors-body");
const errorsMsg = document.getElementById("errors-msg");
const errorsPageInfo = document.getElementById("errors-page-info");
const errorsPrevBtn = document.getElementById("errors-prev-page");
const errorsNextBtn = document.getElementById("errors-next-page");
const errorsFromTs = document.getElementById("errors-from-ts");
const errorsToTs = document.getElementById("errors-to-ts");
const errorsPageSize = document.getElementById("errors-page-size");
const errorsApplyFilterBtn = document.getElementById("errors-apply-filter");
const errorsClearFilterBtn = document.getElementById("errors-clear-filter");
const errorsDownloadExcelBtn = document.getElementById("errors-download-excel");

let errorsPage = 1;
let errorsTotalPages = 1;
let refreshing = false;
let alertsHistoryPage = 1;
let alertsHistoryTotalPages = 1;

function showSavedToast(message) {
  if (typeof window.showSavedToast === "function") {
    window.showSavedToast(message);
  }
}

async function readJson(res) {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

function applyHeaderStatus(data = null) {
  if (typeof window.applyGlobalHeaderStatus === "function") {
    window.applyGlobalHeaderStatus(data);
    return;
  }
  if (!globalStatus) {
    return;
  }
  const online = !!(data?.lector?.running || data?.operador?.running);
  globalStatus.textContent = online ? "ONLINE" : "OFFLINE";
  globalStatus.classList.toggle("online", online);
  if (dbPath && data?.db_path) {
    dbPath.textContent = `db: ${data.db_path}`;
  }
}

function toIsoForApi(localValue, isEnd = false) {
  if (window.dateTime24 && typeof window.dateTime24.normalizeForApi === "function") {
    return window.dateTime24.normalizeForApi(localValue, isEnd);
  }
  if (!localValue) {
    return "";
  }
  const d = new Date(localValue);
  if (Number.isNaN(d.getTime())) {
    return localValue;
  }
  if (isEnd && localValue.length <= 16) {
    d.setSeconds(59, 999);
  }
  return d.toISOString();
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

function renderAlertRows(tbodyEl, items) {
  tbodyEl.innerHTML = "";
  if (!items || !items.length) {
    tbodyEl.innerHTML = '<tr><td colspan="8" class="empty">Sin datos</td></tr>';
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtTs(it.timestamp)}</td>
      <td>${it.estado}</td>
      <td>${it.severity || "-"}</td>
      <td>${it.code || "-"}</td>
      <td>${it.title || "-"}</td>
      <td>${it.details || "-"}</td>
      <td>${Number.isFinite(Number(it.occurrences)) ? Number(it.occurrences) : "-"}</td>
      <td>${fmtTs(it.last_seen)}</td>
    `;
    tbodyEl.appendChild(tr);
  }
}

function renderActiveAlerts(items) {
  const rows = (items || []).map((it) => ({
    timestamp: it.first_seen || it.ts,
    estado: "ACTIVA",
    severity: it.severity,
    code: it.code,
    title: it.title,
    details: it.details,
    occurrences: it.occurrences,
    last_seen: it.last_seen || it.ts,
  }));
  renderAlertRows(alertsActiveBody, rows);
}

function renderAlertsHistory(items) {
  const rows = (items || []).map((it) => ({
    timestamp: it.ts,
    estado: it.status || (it.is_active ? "ACTIVA" : "RESUELTA"),
    severity: it.severity,
    code: it.code,
    title: it.title,
    details: it.details,
    occurrences: it.occurrences,
    last_seen: it.last_seen || it.resolved_at || it.ts,
  }));
  renderAlertRows(alertsHistoryBody, rows);
}

function applyAlertsConfigToForm(cfg) {
  alertsEnabledInput.checked = !!cfg.alerts_enabled;
  alertsQueueThresholdInput.value = String(cfg.alerts_queue_pending_threshold ?? 50);
  alertsErrorThresholdInput.value = String(cfg.alerts_error_count_threshold ?? 8);
  alertsPendingSecInput.value = String(cfg.alerts_pending_order_sec ?? 1200);
  alertsDrawdownInput.value = String(cfg.alerts_drawdown_daily_usd ?? -150);
  discordEnabledInput.checked = !!cfg.discord_enabled;
  discordWebhookInput.value = cfg.discord_webhook_url || "";
  discordMinSeverityInput.value = cfg.discord_min_severity || "warning";
}

function alertsPayloadFromForm() {
  return {
    alerts_enabled: alertsEnabledInput.checked,
    alerts_check_interval_sec: 10,
    alerts_queue_pending_threshold: Number(alertsQueueThresholdInput.value || 50),
    alerts_queue_oldest_sec: 180,
    alerts_pending_order_sec: Number(alertsPendingSecInput.value || 1200),
    alerts_error_window_min: 15,
    alerts_error_count_threshold: Number(alertsErrorThresholdInput.value || 8),
    alerts_no_tickets_threshold: 3,
    alerts_drawdown_daily_usd: Number(alertsDrawdownInput.value || -150),
    alerts_stale_sync_sec: 60,
    discord_enabled: discordEnabledInput.checked,
    discord_webhook_url: discordWebhookInput.value.trim(),
    discord_min_severity: discordMinSeverityInput.value,
  };
}

function buildAlertHistoryQuery(pageOverride = null) {
  const params = new URLSearchParams();
  const targetPage = Number.isFinite(Number(pageOverride)) ? Number(pageOverride) : alertsHistoryPage;
  params.set("page", String(Math.max(1, targetPage)));
  params.set("page_size", "20");
  const fromIso = toIsoForApi(alertsHistoryFromTs.value, false);
  const toIso = toIsoForApi(alertsHistoryToTs.value, true);
  if (fromIso) {
    params.set("from_ts", fromIso);
  }
  if (toIso) {
    params.set("to_ts", toIso);
  }
  return params.toString();
}

async function loadAlertsConfig() {
  const res = await fetch("/api/alerts/config");
  const data = await readJson(res);
  if (!res.ok) {
    alertsMsg.textContent = data.detail || "Error cargando configuración de alertas";
    return;
  }
  applyAlertsConfigToForm(data.config || {});
}

async function refreshActiveAlertsOnly() {
  const res = await fetch("/api/alerts/active");
  const data = await readJson(res);
  if (!res.ok) {
    alertsMsg.textContent = data.detail || "Error cargando alertas activas";
    return;
  }
  const items = data.items || [];
  renderActiveAlerts(items);
  alertsMsg.textContent = `${items.length} alerta(s) activa(s)`;
}

async function refreshAlertHistoryOnly() {
  const qs = buildAlertHistoryQuery();
  const res = await fetch(`/api/alerts/history?${qs}`);
  const data = await readJson(res);
  if (!res.ok) {
    alertsHistoryInfo.textContent = data.detail || "Error cargando historial";
    return;
  }
  const items = data.items || [];
  renderAlertsHistory(items);
  alertsHistoryPage = Number(data.page || 1);
  alertsHistoryTotalPages = Number(data.total_pages || 1);
  if (alertsHistoryPrevBtn) {
    alertsHistoryPrevBtn.disabled = !data.has_prev;
  }
  if (alertsHistoryNextBtn) {
    alertsHistoryNextBtn.disabled = !data.has_next;
  }
  if (alertsHistoryPageInfo) {
    alertsHistoryPageInfo.textContent = `Página ${alertsHistoryPage} de ${alertsHistoryTotalPages}`;
  }
  alertsHistoryInfo.textContent = `Mostrando ${items.length} de ${data.total || items.length} (20 por página)`;
}

async function saveAlertsConfig() {
  const payload = alertsPayloadFromForm();
  alertsMsg.textContent = "Guardando configuración...";
  const res = await fetch("/api/alerts/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    alertsMsg.textContent = data.detail || "No se pudo guardar configuración";
    return;
  }
  applyAlertsConfigToForm(data.config || {});
  alertsMsg.textContent = "Configuración de alertas guardada";
  showSavedToast("Configuración de alertas guardada");
}

async function testDiscord() {
  alertsMsg.textContent = "Enviando test a Discord...";
  const res = await fetch("/api/alerts/discord-test", { method: "POST" });
  const data = await readJson(res);
  if (!res.ok) {
    alertsMsg.textContent = data.detail || "No se pudo enviar test";
    return;
  }
  alertsMsg.textContent = "Test enviado a Discord";
  if (typeof window.showToast === "function") {
    window.showToast("Test enviado a Discord", "success", 3000);
  }
}

function buildErrorsQuery(pageOverride = null) {
  const page = Number.isFinite(Number(pageOverride)) ? Number(pageOverride) : errorsPage;
  const pageSize = Number(errorsPageSize.value || 100);
  const params = new URLSearchParams();
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(Math.max(1, pageSize)));
  const fromIso = toIsoForApi(errorsFromTs.value, false);
  const toIso = toIsoForApi(errorsToTs.value, true);
  if (fromIso) {
    params.set("from_ts", fromIso);
  }
  if (toIso) {
    params.set("to_ts", toIso);
  }
  return params.toString();
}

function renderErrors(items) {
  errorsBody.innerHTML = "";
  if (!items || !items.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="empty">Sin errores recientes</td>';
    errorsBody.appendChild(tr);
    return;
  }
  for (const it of items) {
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
    errorsBody.appendChild(tr);
  }
}

function updateErrorPager(meta) {
  errorsPage = meta.page || 1;
  errorsTotalPages = meta.total_pages || 1;
  errorsPageInfo.textContent = `Página ${errorsPage} de ${errorsTotalPages} | Total errores: ${meta.total || 0}`;
  errorsPrevBtn.disabled = !meta.has_prev;
  errorsNextBtn.disabled = !meta.has_next;
}

async function refreshErrorsOnly(pageOverride = null) {
  try {
    const qs = buildErrorsQuery(pageOverride);
    const res = await fetch(`/api/reportes/errors?${qs}`);
    const data = await readJson(res);
    if (!res.ok) {
      errorsMsg.textContent = data.detail || "Error actualizando errores";
      return;
    }
    renderErrors(data.items || []);
    updateErrorPager(data);
    errorsMsg.textContent = `${(data.items || []).length} error(es) en página`;
  } catch {
    errorsMsg.textContent = "Error actualizando errores";
  }
}

function downloadErrorsExcel() {
  const params = new URLSearchParams();
  const fromIso = toIsoForApi(errorsFromTs.value, false);
  const toIso = toIsoForApi(errorsToTs.value, true);
  if (fromIso) {
    params.set("from_ts", fromIso);
  }
  if (toIso) {
    params.set("to_ts", toIso);
  }
  const url = `/api/reportes/errors/excel?${params.toString()}`;
  window.open(url, "_blank");
}

async function refreshAll() {
  if (refreshing) {
    return;
  }
  refreshing = true;
  try {
    const statusRes = await fetch("/api/status");
    const statusData = await readJson(statusRes);
    applyHeaderStatus(statusData);
    await refreshActiveAlertsOnly();
    await refreshAlertHistoryOnly();
    await refreshErrorsOnly(errorsPage);
  } finally {
    refreshing = false;
  }
}

function initActions() {
  alertsSaveConfigBtn.addEventListener("click", saveAlertsConfig);
  alertsTestDiscordBtn.addEventListener("click", testDiscord);
  alertsHistoryApplyBtn.addEventListener("click", () => {
    alertsHistoryPage = 1;
    refreshAlertHistoryOnly();
  });
  alertsHistoryClearBtn.addEventListener("click", () => {
    alertsHistoryFromTs.value = "";
    alertsHistoryToTs.value = "";
    alertsHistoryPage = 1;
    refreshAlertHistoryOnly();
  });
  if (alertsHistoryPrevBtn) {
    alertsHistoryPrevBtn.addEventListener("click", () => {
      if (alertsHistoryPage > 1) {
        alertsHistoryPage -= 1;
        refreshAlertHistoryOnly();
      }
    });
  }
  if (alertsHistoryNextBtn) {
    alertsHistoryNextBtn.addEventListener("click", () => {
      if (alertsHistoryPage < alertsHistoryTotalPages) {
        alertsHistoryPage += 1;
        refreshAlertHistoryOnly();
      }
    });
  }
  errorsPrevBtn.addEventListener("click", () => {
    if (errorsPage > 1) {
      refreshErrorsOnly(errorsPage - 1);
    }
  });
  errorsNextBtn.addEventListener("click", () => {
    if (errorsPage < errorsTotalPages) {
      refreshErrorsOnly(errorsPage + 1);
    }
  });
  errorsApplyFilterBtn.addEventListener("click", () => {
    refreshErrorsOnly(1);
  });
  errorsClearFilterBtn.addEventListener("click", () => {
    errorsFromTs.value = "";
    errorsToTs.value = "";
    refreshErrorsOnly(1);
  });
  errorsPageSize.addEventListener("change", () => {
    refreshErrorsOnly(1);
  });
  errorsDownloadExcelBtn.addEventListener("click", downloadErrorsExcel);
}

initActions();
loadAlertsConfig().then(refreshAll);
setInterval(refreshAll, 5000);
