const dbPath = document.getElementById("db-path");
const searchMsg = document.getElementById("search-msg");
const detailMsg = document.getElementById("detail-msg");

const cpIdInput = document.getElementById("cp-id");
const cpFromInput = document.getElementById("cp-from-ts");
const cpToInput = document.getElementById("cp-to-ts");
const cpSearchBtn = document.getElementById("cp-search");
const cpClearBtn = document.getElementById("cp-clear");

const registryBody = document.getElementById("registry-body");
const metaBody = document.getElementById("meta-body");
const periodsBody = document.getElementById("periods-body");
const periodsPrevBtn = document.getElementById("periods-prev-page");
const periodsNextBtn = document.getElementById("periods-next-page");
const periodsPageInfo = document.getElementById("periods-page-info");
const operationsBody = document.getElementById("operations-body");
const modsBody = document.getElementById("mods-body");

const pnlChart = document.getElementById("cp-pnl-chart");
const pnlCtx = pnlChart.getContext("2d");

let currentAssignmentId = null;
const PERIODS_PAGE_SIZE = 3;
let periodsSorted = [];
let periodsPage = 1;
let periodsTotalPages = 1;

async function readJson(res) {
  try {
    return await res.json();
  } catch {
    return {};
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

function fmtNum(v) {
  return Number.isFinite(Number(v)) ? Number(v).toFixed(2) : "-";
}

function queryFromFilters(withPageId = null) {
  const params = new URLSearchParams();
  const idVal = withPageId != null ? withPageId : Number(cpIdInput.value || 0);
  if (Number.isFinite(idVal) && idVal > 0) {
    params.set("assignment_id", String(idVal));
  }
  const fromIso = toIsoForApi(cpFromInput.value, false);
  const toIso = toIsoForApi(cpToInput.value, true);
  if (fromIso) {
    params.set("from_ts", fromIso);
  }
  if (toIso) {
    params.set("to_ts", toIso);
  }
  return params;
}

function renderRegistry(items) {
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

function drawPnlSeries(series) {
  const width = pnlChart.width;
  const height = pnlChart.height;
  pnlCtx.clearRect(0, 0, width, height);
  pnlCtx.fillStyle = "rgba(9,15,26,0.95)";
  pnlCtx.fillRect(0, 0, width, height);
  const points = series || [];
  if (points.length < 1) {
    pnlCtx.fillStyle = "#9fb0cc";
    pnlCtx.font = "16px Trebuchet MS";
    pnlCtx.fillText("Sin datos de PnL para este Canal.Preset", 20, 34);
    return;
  }
  const vals = points.map((x) => Number(x.value || 0));
  const minV = Math.min(...vals, 0);
  const maxV = Math.max(...vals, 0);
  const range = Math.max(1e-9, maxV - minV);
  const pad = 36;
  const plotW = width - pad * 2;
  const plotH = height - pad * 2;
  pnlCtx.strokeStyle = "rgba(255,255,255,0.22)";
  pnlCtx.beginPath();
  pnlCtx.moveTo(pad, height - pad);
  pnlCtx.lineTo(width - pad, height - pad);
  pnlCtx.moveTo(pad, pad);
  pnlCtx.lineTo(pad, height - pad);
  pnlCtx.stroke();
  pnlCtx.strokeStyle = "#46d1bf";
  pnlCtx.lineWidth = 2;
  pnlCtx.beginPath();
  points.forEach((p, idx) => {
    const x = pad + (idx / Math.max(1, points.length - 1)) * plotW;
    const y = pad + (1 - (Number(p.value || 0) - minV) / range) * plotH;
    if (idx === 0) {
      pnlCtx.moveTo(x, y);
    } else {
      pnlCtx.lineTo(x, y);
    }
  });
  pnlCtx.stroke();
}

function renderMeta(detail) {
  const meta = detail.meta || {};
  const st = detail.stats || {};
  metaBody.innerHTML = `
    <tr><th>ID Canal.Preset</th><td>${detail.assignment_id || "-"}</td></tr>
    <tr><th>Canal.Preset</th><td>${meta.channel_name || "-"}.${meta.preset_name || "-"}</td></tr>
    <tr><th>Período registrado</th><td>${fmtTs(meta.first_seen)} -> ${fmtTs(meta.last_seen)}</td></tr>
    <tr><th>Eliminado en</th><td>${fmtTs(meta.deleted_at)}</td></tr>
    <tr><th>Modo/estado actual</th><td>${meta.current_mode || "-"} / ${meta.current_is_active ? "activa" : "inactiva"}</td></tr>
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
      <td>${p.event_type || "-"}</td>
      <td>${p.details || "-"}</td>
    `;
    periodsBody.appendChild(tr);
  });
}

function renderOperations(ops) {
  operationsBody.innerHTML = "";
  const rows = ops || [];
  if (!rows.length) {
    operationsBody.innerHTML = '<tr><td colspan="10" class="empty">Sin operaciones</td></tr>';
    return;
  }
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
  modsBody.innerHTML = "";
  const rows = mods || [];
  if (!rows.length) {
    modsBody.innerHTML = '<tr><td colspan="8" class="empty">Sin modificaciones</td></tr>';
    return;
  }
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
  const qs = queryFromFilters();
  searchMsg.textContent = "Buscando...";
  const res = await fetch(`/api/channel-presets/registry?${qs.toString()}`);
  const data = await readJson(res);
  if (!res.ok) {
    searchMsg.textContent = data.detail || "Error de búsqueda";
    return;
  }
  renderRegistry(data.items || []);
  searchMsg.textContent = `${data.count || 0} resultado(s)`;
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
  renderPeriods(data.periods || []);
  renderOperations(data.operations || []);
  renderMods(data.modifications || []);
  drawPnlSeries(data.pnl_series || []);
  detailMsg.textContent = `Detalle cargado #${idNum}`;
}

function initActions() {
  cpSearchBtn.addEventListener("click", () => {
    loadRegistry();
    const idNum = Number(cpIdInput.value || 0);
    if (idNum > 0) {
      loadDetail(idNum);
    }
  });
  cpClearBtn.addEventListener("click", () => {
    cpIdInput.value = "";
    cpFromInput.value = "";
    cpToInput.value = "";
    currentAssignmentId = null;
    loadRegistry();
    detailMsg.textContent = "Sin selección";
    metaBody.innerHTML = "";
    renderPeriods([]);
    operationsBody.innerHTML = "";
    modsBody.innerHTML = "";
    drawPnlSeries([]);
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
  registryBody.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action='open-detail']");
    if (!btn) {
      return;
    }
    const id = Number(btn.dataset.id || 0);
    if (id > 0) {
      cpIdInput.value = String(id);
      loadDetail(id);
    }
  });
}

async function init() {
  initActions();
  try {
    const statusRes = await fetch("/api/status");
    const statusData = await readJson(statusRes);
    if (statusData.db_path) {
      dbPath.textContent = `db: ${statusData.db_path}`;
    }
  } catch {
    dbPath.textContent = "db: --";
  }

  const params = new URLSearchParams(window.location.search);
  const pId = Number(params.get("id") || 0);
  const pFrom = params.get("from_ts") || "";
  const pTo = params.get("to_ts") || "";
  if (pFrom) {
    const dt = new Date(pFrom);
    if (!Number.isNaN(dt.getTime())) {
      cpFromInput.value = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}T${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}:${String(dt.getSeconds()).padStart(2, "0")}`;
    }
  }
  if (pTo) {
    const dt = new Date(pTo);
    if (!Number.isNaN(dt.getTime())) {
      cpToInput.value = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}T${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}:${String(dt.getSeconds()).padStart(2, "0")}`;
    }
  }
  if (pId > 0) {
    cpIdInput.value = String(pId);
  }
  await loadRegistry();
  if (pId > 0) {
    await loadDetail(pId);
  } else {
    drawPnlSeries([]);
  }
}

init();
