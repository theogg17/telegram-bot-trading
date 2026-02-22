const dbPath = document.getElementById("db-path");
const globalStatus = document.getElementById("global-status");
const searchMsg = document.getElementById("search-msg");
const detailMsg = document.getElementById("detail-msg");

const cpIdInput = document.getElementById("cp-id");
const cpFromInput = document.getElementById("cp-from-ts");
const cpToInput = document.getElementById("cp-to-ts");
const cpSearchBtn = document.getElementById("cp-search");
const cpClearBtn = document.getElementById("cp-clear");
const cpToggleActiveBtn = document.getElementById("cp-toggle-active");
const cpToggleMsg = document.getElementById("cp-toggle-msg");
const cpToggleBlockModal = document.getElementById("cp-toggle-block-modal");
const cpToggleBlockText = document.getElementById("cp-toggle-block-text");
const cpToggleBlockOkBtn = document.getElementById("cp-toggle-block-ok");
const cpToggleConfirmModal = document.getElementById("cp-toggle-confirm-modal");
const cpToggleConfirmText = document.getElementById("cp-toggle-confirm-text");
const cpToggleConfirmAcceptBtn = document.getElementById("cp-toggle-confirm-accept");
const cpToggleConfirmCancelBtn = document.getElementById("cp-toggle-confirm-cancel");

const registryBody = document.getElementById("registry-body");
const metaBody = document.getElementById("meta-body");
const periodsBody = document.getElementById("periods-body");
const periodsPrevBtn = document.getElementById("periods-prev-page");
const periodsNextBtn = document.getElementById("periods-next-page");
const periodsPageInfo = document.getElementById("periods-page-info");
const operationsBody = document.getElementById("operations-body");
const operationsPrevBtn = document.getElementById("operations-prev-page");
const operationsNextBtn = document.getElementById("operations-next-page");
const operationsPageInfo = document.getElementById("operations-page-info");
const modsBody = document.getElementById("mods-body");
const modsPrevBtn = document.getElementById("mods-prev-page");
const modsNextBtn = document.getElementById("mods-next-page");
const modsPageInfo = document.getElementById("mods-page-info");

const pnlChart = document.getElementById("cp-pnl-chart");
const pnlCtx = pnlChart ? pnlChart.getContext("2d") : null;
const pipsChart = document.getElementById("cp-pips-chart");
const pipsCtx = pipsChart ? pipsChart.getContext("2d") : null;

let currentAssignmentId = null;
const PERIODS_PAGE_SIZE = 15;
const OPERATIONS_PAGE_SIZE = 6;
const MODS_PAGE_SIZE = 6;
let periodsSorted = [];
let periodsPage = 1;
let periodsTotalPages = 1;
let operationsSorted = [];
let operationsPage = 1;
let operationsTotalPages = 1;
let modsSorted = [];
let modsPage = 1;
let modsTotalPages = 1;
let currentAssignmentMeta = null;
let pendingToggleTargetActive = null;

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
  if (window.dateTime24 && typeof window.dateTime24.formatDisplayDateTime === "function") {
    return window.dateTime24.formatDisplayDateTime(value);
  }
  if (!value) {
    return "-";
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return String(value);
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtNum(v) {
  return Number.isFinite(Number(v)) ? Number(v).toFixed(2) : "-";
}

function openModal(modal) {
  if (!modal) {
    return;
  }
  modal.hidden = false;
  modal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeModal(modal) {
  if (!modal) {
    return;
  }
  modal.classList.add("hidden");
  modal.hidden = true;
  if (
    (!cpToggleBlockModal || cpToggleBlockModal.hidden) &&
    (!cpToggleConfirmModal || cpToggleConfirmModal.hidden)
  ) {
    document.body.classList.remove("modal-open");
  }
}

function openToggleBlockedModal(message) {
  if (cpToggleBlockText) {
    cpToggleBlockText.textContent = message || "Canal.Preset tiene operación abierta, por favor ciérrala antes de desactivar este Canal.Preset.";
  }
  openModal(cpToggleBlockModal);
}

function closeToggleBlockedModal() {
  closeModal(cpToggleBlockModal);
}

function openToggleConfirmModal(targetActive) {
  pendingToggleTargetActive = !!targetActive;
  if (cpToggleConfirmText) {
    cpToggleConfirmText.textContent = pendingToggleTargetActive
      ? "¿Confirmas activar este Canal.Preset?"
      : "¿Confirmas desactivar este Canal.Preset?";
  }
  openModal(cpToggleConfirmModal);
}

function closeToggleConfirmModal() {
  pendingToggleTargetActive = null;
  closeModal(cpToggleConfirmModal);
}

function renderToggleControls(meta = null) {
  currentAssignmentMeta = meta || null;
  if (!cpToggleActiveBtn || !cpToggleMsg) {
    return;
  }
  if (!meta || !currentAssignmentId) {
    cpToggleActiveBtn.disabled = true;
    cpToggleActiveBtn.textContent = "activar";
    cpToggleMsg.textContent = "Selecciona un Canal.Preset para gestionar estado.";
    return;
  }
  const isActive = !!meta.current_is_active;
  cpToggleActiveBtn.textContent = isActive ? "desactivar" : "activar";
  if (!meta.current_assignment_exists) {
    cpToggleActiveBtn.disabled = true;
    cpToggleMsg.textContent = "Este Canal.Preset ya no existe en asignaciones activas.";
    return;
  }
  cpToggleActiveBtn.disabled = false;
  cpToggleMsg.textContent = isActive
    ? "Activo: procesa nuevas señales."
    : "Inactivo: ignora nuevas señales.";
}

function periodEventLabel(eventType) {
  const ev = String(eventType || "").toLowerCase();
  if (ev === "activation") {
    return "Activacion";
  }
  if (ev === "deactivation") {
    return "Desactivacion";
  }
  if (ev === "created") {
    return "Creacion";
  }
  if (ev === "deleted") {
    return "Eliminacion";
  }
  if (ev === "updated") {
    return "Actualizacion";
  }
  if (ev === "bootstrap") {
    return "Bootstrap";
  }
  return eventType || "-";
}

function queryFromFilters(withPageId = null) {
  const params = new URLSearchParams();
  const fallbackId = currentAssignmentId || 0;
  const inputId = cpIdInput ? Number(cpIdInput.value || 0) : 0;
  const idVal = withPageId != null ? withPageId : Number(inputId || fallbackId || 0);
  if (Number.isFinite(idVal) && idVal > 0) {
    params.set("assignment_id", String(idVal));
  }
  const fromIso = toIsoForApi(cpFromInput ? cpFromInput.value : "", false);
  const toIso = toIsoForApi(cpToInput ? cpToInput.value : "", true);
  if (fromIso) {
    params.set("from_ts", fromIso);
  }
  if (toIso) {
    params.set("to_ts", toIso);
  }
  return params;
}

function renderRegistry(items) {
  if (!registryBody) {
    return;
  }
  registryBody.innerHTML = "";
  const rows = items || [];
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="8" class="empty">Sin resultados</td>';
    registryBody.appendChild(tr);
    return;
  }
  for (const it of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.assignment_id}</td>
      <td>${it.channel_name}.${it.preset_name}</td>
      <td>${it.current_mode || "-"}</td>
      <td>${it.current_is_active ? "si" : "no"}</td>
      <td>${fmtTs(it.first_seen)}</td>
      <td>${fmtTs(it.last_seen)}</td>
      <td>${it.events_count}</td>
      <td class="row-actions">
        <button class="mini-btn" data-action="open-detail" data-id="${it.assignment_id}">Ver detalle</button>
      </td>
    `;
    registryBody.appendChild(tr);
  }
}

function drawLineSeries(canvas, ctx, series, opts = {}) {
  if (!canvas || !ctx) {
    return;
  }
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "rgba(9,15,26,0.95)";
  ctx.fillRect(0, 0, width, height);
  const points = series || [];
  if (points.length < 1) {
    ctx.fillStyle = "#9fb0cc";
    ctx.font = "16px Trebuchet MS";
    ctx.fillText(String(opts.emptyText || "Sin datos"), 20, 34);
    return;
  }
  const vals = points.map((x) => Number(x.value || 0));
  const minV = Math.min(...vals, 0);
  const maxV = Math.max(...vals, 0);
  const range = Math.max(1e-9, maxV - minV);
  const pad = 36;
  const plotW = width - pad * 2;
  const plotH = height - pad * 2;
  ctx.strokeStyle = "rgba(255,255,255,0.22)";
  ctx.beginPath();
  ctx.moveTo(pad, height - pad);
  ctx.lineTo(width - pad, height - pad);
  ctx.moveTo(pad, pad);
  ctx.lineTo(pad, height - pad);
  ctx.stroke();
  ctx.strokeStyle = String(opts.lineColor || "#46d1bf");
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, idx) => {
    const x = pad + (idx / Math.max(1, points.length - 1)) * plotW;
    const y = pad + (1 - (Number(p.value || 0) - minV) / range) * plotH;
    if (idx === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();
}

function drawPnlSeries(series) {
  drawLineSeries(pnlChart, pnlCtx, series, {
    lineColor: "#46d1bf",
    emptyText: "Sin datos de PnL para este Canal.Preset",
  });
}

function drawPipsSeries(series) {
  drawLineSeries(pipsChart, pipsCtx, series, {
    lineColor: "#f5c542",
    emptyText: "Sin datos de pips acumulados para este Canal.Preset",
  });
}

function renderMeta(detail) {
  const meta = detail.meta || {};
  const st = detail.stats || {};
  metaBody.innerHTML = `
    <tr><th>ID Canal.Preset</th><td>${detail.assignment_id || "-"}</td></tr>
    <tr><th>Canal.Preset</th><td>${meta.channel_name || "-"}.${meta.preset_name || "-"}</td></tr>
    <tr><th>Creado en</th><td>${fmtTs(meta.created_at)}</td></tr>
    <tr><th>Período registrado</th><td>${fmtTs(meta.first_seen)} -> ${fmtTs(meta.last_seen)}</td></tr>
    <tr><th>Eliminado en</th><td>${fmtTs(meta.deleted_at)}</td></tr>
    <tr><th>Modo/estado actual</th><td>${meta.current_mode || "-"} / ${meta.current_is_active ? "activa" : "inactiva"}</td></tr>
    <tr><th>Operaciones abiertas actuales</th><td>${meta.current_open_operations || 0}</td></tr>
    <tr><th>Trades totales</th><td>${st.operations_total || 0}</td></tr>
    <tr><th>Cerradas / abiertas</th><td>${st.operations_closed || 0} / ${st.operations_open_pending || 0}</td></tr>
    <tr><th>Frecuencia trades/día</th><td>${fmtNum(st.frequency_trades_per_day)}</td></tr>
    <tr><th>Largas (>=4h)</th><td>${st.long_duration_count || 0}</td></tr>
    <tr><th>Buy/Sell</th><td>${st.buy_count || 0}/${st.sell_count || 0}</td></tr>
    <tr><th>PnL total USD / pips</th><td>${fmtNum(st.pnl_total_usd)} / ${fmtNum(st.pnl_total_pips)}</td></tr>
  `;
}

function periodTs(value) {
  const t = new Date(value || "").getTime();
  return Number.isNaN(t) ? 0 : t;
}

function operationTs(op) {
  const closeTs = new Date(op?.closed_at || "").getTime();
  if (!Number.isNaN(closeTs) && closeTs > 0) {
    return closeTs;
  }
  const openTs = new Date(op?.opened_at || "").getTime();
  if (!Number.isNaN(openTs) && openTs > 0) {
    return openTs;
  }
  return 0;
}

function modTs(mod) {
  const ts = new Date(mod?.ts || "").getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

function updatePeriodsPager(totalRows = 0) {
  periodsTotalPages = Math.max(1, Math.ceil(totalRows / PERIODS_PAGE_SIZE));
  periodsPage = Math.min(Math.max(1, periodsPage), periodsTotalPages);
  if (periodsPrevBtn) {
    periodsPrevBtn.disabled = periodsPage <= 1 || totalRows <= 0;
  }
  if (periodsNextBtn) {
    periodsNextBtn.disabled = periodsPage >= periodsTotalPages || totalRows <= 0;
  }
  if (periodsPageInfo) {
    periodsPageInfo.textContent = `Página ${periodsPage} de ${periodsTotalPages} | ${totalRows} período(s)`;
  }
}

function renderPeriods(periods) {
  periodsSorted = (periods || []).slice().sort((a, b) => periodTs(b.start_ts) - periodTs(a.start_ts));
  periodsPage = 1;
  renderPeriodsPage();
}

function renderPeriodsPage() {
  periodsBody.innerHTML = "";
  const totalRows = periodsSorted.length;
  updatePeriodsPager(totalRows);
  if (!totalRows) {
    periodsBody.innerHTML = '<tr><td colspan="7" class="empty">Sin períodos</td></tr>';
    return;
  }
  const start = (periodsPage - 1) * PERIODS_PAGE_SIZE;
  const rows = periodsSorted.slice(start, start + PERIODS_PAGE_SIZE);
  if (!rows.length) {
    periodsBody.innerHTML = '<tr><td colspan="7" class="empty">Sin períodos</td></tr>';
    return;
  }
  rows.forEach((p, idx) => {
    const rowNumber = start + idx + 1;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rowNumber}</td>
      <td>${fmtTs(p.start_ts)}</td>
      <td>${fmtTs(p.end_ts)}</td>
      <td>${p.mode || "-"}</td>
      <td>${p.is_active ? "si" : "no"}</td>
      <td>${periodEventLabel(p.event_type)}</td>
      <td>${p.details || "-"}</td>
    `;
    periodsBody.appendChild(tr);
  });
}

function renderOperations(ops) {
  operationsSorted = (ops || [])
    .filter((op) => String(op?.status || "").toUpperCase() === "CLOSED")
    .slice()
    .sort((a, b) => {
      const byTs = operationTs(b) - operationTs(a);
      if (byTs !== 0) {
        return byTs;
      }
      return Number(b?.id || 0) - Number(a?.id || 0);
    });
  operationsPage = 1;
  renderOperationsPage();
}

function updateOperationsPager(totalRows = 0) {
  operationsTotalPages = Math.max(1, Math.ceil(totalRows / OPERATIONS_PAGE_SIZE));
  operationsPage = Math.min(Math.max(1, operationsPage), operationsTotalPages);
  if (operationsPrevBtn) {
    operationsPrevBtn.disabled = operationsPage <= 1 || totalRows <= 0;
  }
  if (operationsNextBtn) {
    operationsNextBtn.disabled = operationsPage >= operationsTotalPages || totalRows <= 0;
  }
  if (operationsPageInfo) {
    operationsPageInfo.textContent = `Página ${operationsPage} de ${operationsTotalPages} | ${totalRows} operación(es)`;
  }
}

function renderOperationsPage() {
  operationsBody.innerHTML = "";
  const totalRows = operationsSorted.length;
  updateOperationsPager(totalRows);
  if (!totalRows) {
    operationsBody.innerHTML = '<tr><td colspan="10" class="empty">Sin operaciones cerradas</td></tr>';
    return;
  }
  const start = (operationsPage - 1) * OPERATIONS_PAGE_SIZE;
  const rows = operationsSorted.slice(start, start + OPERATIONS_PAGE_SIZE);
  for (const op of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${op.id}</td>
      <td>${op.status}</td>
      <td>${op.mode}${op.is_virtual ? " (virtual)" : ""}</td>
      <td>${op.symbol} ${op.side}</td>
      <td>${fmtTs(op.opened_at)}</td>
      <td>${fmtTs(op.closed_at)}</td>
      <td>${op.modifications_count || 0}</td>
      <td>${op.duration_seconds ?? "-"}</td>
      <td>${fmtNum(op.pnl_usd)}</td>
      <td>${fmtNum(op.pnl_pips)}</td>
    `;
    operationsBody.appendChild(tr);
  }
}

function renderMods(mods) {
  modsSorted = (mods || [])
    .slice()
    .sort((a, b) => {
      const byTs = modTs(b) - modTs(a);
      if (byTs !== 0) {
        return byTs;
      }
      return Number(b?.operation_id || 0) - Number(a?.operation_id || 0);
    });
  modsPage = 1;
  renderModsPage();
}

function updateModsPager(totalRows = 0) {
  modsTotalPages = Math.max(1, Math.ceil(totalRows / MODS_PAGE_SIZE));
  modsPage = Math.min(Math.max(1, modsPage), modsTotalPages);
  if (modsPrevBtn) {
    modsPrevBtn.disabled = modsPage <= 1 || totalRows <= 0;
  }
  if (modsNextBtn) {
    modsNextBtn.disabled = modsPage >= modsTotalPages || totalRows <= 0;
  }
  if (modsPageInfo) {
    modsPageInfo.textContent = `Página ${modsPage} de ${modsTotalPages} | ${totalRows} modificación(es)`;
  }
}

function renderModsPage() {
  modsBody.innerHTML = "";
  const totalRows = modsSorted.length;
  updateModsPager(totalRows);
  if (!totalRows) {
    modsBody.innerHTML = '<tr><td colspan="8" class="empty">Sin modificaciones</td></tr>';
    return;
  }
  const start = (modsPage - 1) * MODS_PAGE_SIZE;
  const rows = modsSorted.slice(start, start + MODS_PAGE_SIZE);
  for (const m of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${m.operation_id}</td>
      <td>${fmtTs(m.ts)}</td>
      <td>${m.message_id || "-"}</td>
      <td>${m.event_id || "-"}</td>
      <td>${fmtNum(m.sl)}</td>
      <td>${fmtNum(m.tp)}</td>
      <td>${m.status || "-"}</td>
      <td>${m.details || "-"}</td>
    `;
    modsBody.appendChild(tr);
  }
}

async function loadRegistry() {
  if (!registryBody) {
    return;
  }
  const qs = queryFromFilters();
  if (searchMsg) {
    searchMsg.textContent = "Buscando...";
  }
  const res = await fetch(`/api/channel-presets/registry?${qs.toString()}`);
  const data = await readJson(res);
  if (!res.ok) {
    if (searchMsg) {
      searchMsg.textContent = data.detail || "Error de búsqueda";
    }
    return;
  }
  renderRegistry(data.items || []);
  if (searchMsg) {
    searchMsg.textContent = `${data.count || 0} resultado(s)`;
  }
}

async function loadDetail(assignmentId) {
  const idNum = Number(assignmentId || 0);
  if (!Number.isFinite(idNum) || idNum <= 0) {
    detailMsg.textContent = "ID inválido";
    return;
  }
  const qs = queryFromFilters(idNum);
  detailMsg.textContent = `Cargando detalle #${idNum}...`;
  const res = await fetch(`/api/channel-presets/${idNum}/detail?${qs.toString()}`);
  const data = await readJson(res);
  if (!res.ok) {
    detailMsg.textContent = data.detail || "No se pudo cargar detalle";
    return;
  }
  currentAssignmentId = idNum;
  renderMeta(data);
  renderToggleControls(data.meta || null);
  renderPeriods(data.periods || []);
  renderOperations(data.operations || []);
  renderMods(data.modifications || []);
  drawPnlSeries(data.pnl_series || []);
  drawPipsSeries(data.pips_series || []);
  detailMsg.textContent = `Detalle cargado #${idNum}`;
}

async function toggleCurrentChannelPreset() {
  if (!currentAssignmentId || !currentAssignmentMeta || !currentAssignmentMeta.current_assignment_exists) {
    return;
  }
  const targetActive = pendingToggleTargetActive === null
    ? !currentAssignmentMeta.current_is_active
    : !!pendingToggleTargetActive;
  if (cpToggleMsg) {
    cpToggleMsg.textContent = targetActive ? "Activando Canal.Preset..." : "Desactivando Canal.Preset...";
  }
  const res = await fetch(`/api/channel-presets/${currentAssignmentId}/set-active`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active: !!targetActive }),
  });
  const data = await readJson(res);
  if (!res.ok) {
    const msg = data.detail || "No se pudo actualizar estado de Canal.Preset";
    if (res.status === 409 && !targetActive) {
      openToggleBlockedModal(msg);
    }
    if (cpToggleMsg) {
      cpToggleMsg.textContent = msg;
    }
    return;
  }
  if (cpToggleMsg) {
    cpToggleMsg.textContent = targetActive
      ? "Canal.Preset activado correctamente."
      : "Canal.Preset desactivado correctamente.";
  }
  await loadDetail(currentAssignmentId);
}

function initActions() {
  if (cpSearchBtn) {
    cpSearchBtn.addEventListener("click", () => {
      loadRegistry();
      const idNum = Number((cpIdInput && cpIdInput.value) || 0);
      if (idNum > 0) {
        loadDetail(idNum);
      }
    });
  }
  if (cpClearBtn) {
    cpClearBtn.addEventListener("click", () => {
      if (cpIdInput) {
        cpIdInput.value = "";
      }
      if (cpFromInput) {
        cpFromInput.value = "";
      }
      if (cpToInput) {
        cpToInput.value = "";
      }
      currentAssignmentId = null;
      loadRegistry();
      detailMsg.textContent = "Sin selección";
      metaBody.innerHTML = "";
      renderPeriods([]);
      renderOperations([]);
      renderMods([]);
      drawPnlSeries([]);
      drawPipsSeries([]);
      renderToggleControls(null);
    });
  }
  if (cpToggleActiveBtn) {
    cpToggleActiveBtn.addEventListener("click", () => {
      if (!currentAssignmentMeta || !currentAssignmentMeta.current_assignment_exists) {
        return;
      }
      const targetActive = !currentAssignmentMeta.current_is_active;
      openToggleConfirmModal(targetActive);
    });
  }
  if (cpToggleBlockOkBtn) {
    cpToggleBlockOkBtn.addEventListener("click", closeToggleBlockedModal);
  }
  if (cpToggleBlockModal) {
    cpToggleBlockModal.addEventListener("click", (event) => {
      if (event.target === cpToggleBlockModal) {
        closeToggleBlockedModal();
      }
    });
  }
  if (cpToggleConfirmAcceptBtn) {
    cpToggleConfirmAcceptBtn.addEventListener("click", async () => {
      await toggleCurrentChannelPreset();
      closeToggleConfirmModal();
    });
  }
  if (cpToggleConfirmCancelBtn) {
    cpToggleConfirmCancelBtn.addEventListener("click", closeToggleConfirmModal);
  }
  if (cpToggleConfirmModal) {
    cpToggleConfirmModal.addEventListener("click", (event) => {
      if (event.target === cpToggleConfirmModal) {
        closeToggleConfirmModal();
      }
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (cpToggleConfirmModal && !cpToggleConfirmModal.hidden) {
      closeToggleConfirmModal();
      return;
    }
    if (cpToggleBlockModal && !cpToggleBlockModal.hidden) {
      closeToggleBlockedModal();
    }
  });
  if (periodsPrevBtn) {
    periodsPrevBtn.addEventListener("click", () => {
      if (periodsPage > 1) {
        periodsPage -= 1;
        renderPeriodsPage();
      }
    });
  }
  if (periodsNextBtn) {
    periodsNextBtn.addEventListener("click", () => {
      if (periodsPage < periodsTotalPages) {
        periodsPage += 1;
        renderPeriodsPage();
      }
    });
  }
  if (operationsPrevBtn) {
    operationsPrevBtn.addEventListener("click", () => {
      if (operationsPage > 1) {
        operationsPage -= 1;
        renderOperationsPage();
      }
    });
  }
  if (operationsNextBtn) {
    operationsNextBtn.addEventListener("click", () => {
      if (operationsPage < operationsTotalPages) {
        operationsPage += 1;
        renderOperationsPage();
      }
    });
  }
  if (modsPrevBtn) {
    modsPrevBtn.addEventListener("click", () => {
      if (modsPage > 1) {
        modsPage -= 1;
        renderModsPage();
      }
    });
  }
  if (modsNextBtn) {
    modsNextBtn.addEventListener("click", () => {
      if (modsPage < modsTotalPages) {
        modsPage += 1;
        renderModsPage();
      }
    });
  }
  if (registryBody) {
    registryBody.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-action='open-detail']");
      if (!btn) {
        return;
      }
      const id = Number(btn.dataset.id || 0);
      if (id > 0) {
        if (cpIdInput) {
          cpIdInput.value = String(id);
        }
        loadDetail(id);
      }
    });
  }
}

async function init() {
  initActions();
  renderToggleControls(null);
  try {
    const statusRes = await fetch("/api/status");
    const statusData = await readJson(statusRes);
    applyHeaderStatus(statusData);
  } catch {
    applyHeaderStatus(null);
  }

  const params = new URLSearchParams(window.location.search);
  const pId = Number(params.get("id") || 0);
  const pFrom = params.get("from_ts") || "";
  const pTo = params.get("to_ts") || "";
  if (pFrom && cpFromInput) {
    const dt = new Date(pFrom);
    if (!Number.isNaN(dt.getTime())) {
      cpFromInput.value = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}T${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}:${String(dt.getSeconds()).padStart(2, "0")}`;
    }
  }
  if (pTo && cpToInput) {
    const dt = new Date(pTo);
    if (!Number.isNaN(dt.getTime())) {
      cpToInput.value = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}T${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}:${String(dt.getSeconds()).padStart(2, "0")}`;
    }
  }
  if (pId > 0 && cpIdInput) {
    cpIdInput.value = String(pId);
  }
  await loadRegistry();
  if (pId > 0) {
    await loadDetail(pId);
  } else {
    detailMsg.textContent = "Abre esta vista desde Asignaciones Canal.Preset > Detalles.";
    metaBody.innerHTML = '<tr><td class="empty">Sin Canal.Preset seleccionado.</td></tr>';
    drawPnlSeries([]);
    drawPipsSeries([]);
  }
}

init();
