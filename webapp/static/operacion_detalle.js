const dbPath = document.getElementById("db-path");
const globalStatus = document.getElementById("global-status");
const titleOp = document.getElementById("title-op");
const subtitleOp = document.getElementById("subtitle-op");
const summaryBody = document.getElementById("summary-body");
const summaryMsg = document.getElementById("summary-msg");
const timelineBody = document.getElementById("timeline-body");
const timelineMsg = document.getElementById("timeline-msg");

function readJson(res) {
  return res.json().catch(() => ({}));
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

function fmtNum(v, digits = 2) {
  return Number.isFinite(Number(v)) ? Number(v).toFixed(digits) : "-";
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

function fmtDur(seconds) {
  if (!Number.isFinite(Number(seconds))) {
    return "-";
  }
  const s = Math.max(0, Number(seconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  const d = days > 0 ? `${days}d ` : "";
  return `${d}${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function operationIdFromPath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (!parts.length) {
    return null;
  }
  const last = parts[parts.length - 1];
  const id = Number(last);
  if (Number.isFinite(id) && id > 0) {
    return id;
  }
  const q = new URLSearchParams(window.location.search).get("id");
  const qn = Number(q);
  if (Number.isFinite(qn) && qn > 0) {
    return qn;
  }
  return null;
}

function renderSummary(op) {
  const closeSignal = op.close_source === "signal" ? `Cerrada por señal (message_id=${op.close_trigger_message_id || "-"})` : "";
  const closeError = op.close_source === "error" ? `Evento de error (error_id=${op.close_error_id || "-"}, tipo=${op.close_error_type || "-"})` : "";
  const closeManual = op.close_source === "manual_mt5" ? "Detectada como cierre/cancelación manual desde MT5 desktop (o externo)." : "";
  const closePanel = op.close_source === "panel_web_manual" ? "Cerrada desde Panel web a mano." : "";
  const closeExplain = closeSignal || closeError || closeManual || closePanel || "-";

  const rows = [
    ["ID", op.id],
    ["Estado", op.status],
    ["Canal.Preset", `${op.channel_name || "-"} . ${op.preset_name || "-"}`],
    ["Modo", `${op.mode} (${op.is_virtual ? "virtual" : "real"})`],
    ["Par/Lado", `${op.symbol || "-"} ${op.side || "-"}`],
    ["entry_message_id", op.entry_message_id || "-"],
    ["entry_event_id", op.entry_event_id || "-"],
    ["Ticket", op.ticket || "-"],
    ["Abierta", fmtTs(op.opened_at)],
    ["Cerrada", fmtTs(op.closed_at)],
    ["Duración", fmtDur(op.duration_seconds ?? op.elapsed_seconds)],
    ["Pips", fmtNum(op.pnl_pips ?? op.last_pips)],
    ["PnL USD", fmtNum(op.pnl_usd ?? op.last_profit_usd)],
    ["SL/TP", `${fmtNum(op.sl, 5)} / ${fmtNum(op.tp, 5)}`],
    ["Modificaciones", `${op.modifications_count || 0}`],
    ["Cierre - explicación", closeExplain],
    ["Detalle cierre", op.close_details || "-"],
  ];
  summaryBody.innerHTML = rows.map((r) => `<tr><th>${r[0]}</th><td>${r[1]}</td></tr>`).join("");
}

function renderTimeline(events) {
  timelineBody.innerHTML = "";
  if (!events || !events.length) {
    timelineBody.innerHTML = '<tr><td colspan="11" class="empty">Sin eventos</td></tr>';
    return;
  }
  for (const ev of events) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtTs(ev.ts)}</td>
      <td>${ev.event_type}</td>
      <td>${ev.status || "-"}</td>
      <td>${ev.message_id || "-"}</td>
      <td>${ev.reply_to || "-"}</td>
      <td>${ev.event_id || "-"}</td>
      <td>${fmtNum(ev.sl, 5)}</td>
      <td>${fmtNum(ev.tp, 5)}</td>
      <td>${fmtNum(ev.pnl_usd)}</td>
      <td>${fmtNum(ev.pnl_pips)}</td>
      <td>${ev.details || "-"}</td>
    `;
    timelineBody.appendChild(tr);
  }
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await readJson(res);
  applyHeaderStatus(data);
}

async function loadDetail(operationId) {
  const res = await fetch(`/api/operations/${operationId}`);
  const data = await readJson(res);
  if (!res.ok) {
    summaryMsg.textContent = data.detail || "No encontrada";
    timelineMsg.textContent = "Sin datos";
    return false;
  }
  const op = data.operation;
  titleOp.textContent = `Descripción de operación #${op.id}`;
  subtitleOp.textContent = `${op.symbol} ${op.side} | ${op.channel_name}.${op.preset_name || "-"}`;
  renderSummary(op);
  renderTimeline(data.events || []);
  summaryMsg.textContent = "Actualizado";
  timelineMsg.textContent = `${(data.events || []).length} evento(s)`;
  return op.status === "OPEN" || op.status === "PENDING";
}

async function init() {
  const operationId = operationIdFromPath();
  if (!operationId) {
    summaryMsg.textContent = "ID inválido";
    return;
  }
  await refreshStatus();
  let keepRefreshing = await loadDetail(operationId);
  if (keepRefreshing) {
    setInterval(async () => {
      keepRefreshing = await loadDetail(operationId);
    }, 5000);
  }
}

init();
