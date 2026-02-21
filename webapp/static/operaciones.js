const dbPath = document.getElementById("db-path");
const globalStatus = document.getElementById("global-status");
const searchMsg = document.getElementById("search-msg");
const openMsg = document.getElementById("open-msg");
const openCards = document.getElementById("open-cards");
const closedMsg = document.getElementById("closed-msg");
const closedBody = document.getElementById("closed-body");
const closedPageInfo = document.getElementById("closed-page-info");
const closedPrevBtn = document.getElementById("closed-prev");
const closedNextBtn = document.getElementById("closed-next");
const manualCloseMode = document.getElementById("manual-close-mode");
const manualCloseIncludePending = document.getElementById("manual-close-include-pending");
const manualCloseInMt5 = document.getElementById("manual-close-in-mt5");
const manualCloseAllBtn = document.getElementById("manual-close-all-btn");
const manualCloseMsg = document.getElementById("manual-close-msg");

let openItems = [];
let closedPage = 1;
let closedTotalPages = 1;
let openLoadInFlight = false;

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

function showToastMsg(message, type = "success") {
  if (typeof window.showToast === "function") {
    window.showToast(message, type, 4000);
  }
}

function fmtNum(v, digits = 2) {
  return Number.isFinite(Number(v)) ? Number(v).toFixed(digits) : "-";
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

function renderOpenCards(items) {
  openCards.innerHTML = "";
  if (!items || !items.length) {
    openCards.innerHTML = '<article class="operation-card pending"><p class="empty">No hay operaciones abiertas/pending.</p></article>';
    return;
  }
  for (const it of items) {
    const status = String(it.status || "").toUpperCase();
    const style = status === "PENDING" ? "pending" : "open";
    const card = document.createElement("article");
    card.className = `operation-card ${style}`;
    card.dataset.openedAt = it.opened_at || "";
    card.dataset.closedAt = it.closed_at || "";
    card.dataset.id = String(it.id);
    card.innerHTML = `
      <header>
        <strong>#${it.id} ${it.symbol} ${it.side}</strong>
        <span class="pill-small">${status || "-"}</span>
      </header>
      <p><b>Canal.Preset:</b> ${it.channel_name || "-"} . ${it.preset_name || "-"}</p>
      <p><b>Modo:</b> ${it.mode} (${it.is_virtual ? "virtual" : "real"})</p>
      <p><b>Abierta desde:</b> ${fmtTs(it.opened_at)}</p>
      <p><b>Tiempo activo:</b> <span class="live-elapsed">${fmtDur(it.elapsed_seconds)}</span></p>
      <p><b>Pips acumulados:</b> ${fmtNum(it.last_pips ?? it.pnl_pips)}</p>
      <p><b>SL/TP:</b> ${fmtNum(it.sl, 5)} / ${fmtNum(it.tp, 5)}</p>
      <p><b>Modificaciones:</b> ${it.modifications_count || 0}</p>
      <div class="actions">
        <button class="btn ghost" data-action="close-open-op" data-id="${it.id}" type="button">Cerrar manual</button>
        <a class="btn ghost" target="_blank" href="/operaciones/${it.id}">Descripción de la operación</a>
      </div>
    `;
    openCards.appendChild(card);
  }
}

function renderClosedRows(items) {
  closedBody.innerHTML = "";
  if (!items || !items.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="11" class="empty">Sin operaciones registradas</td>';
    closedBody.appendChild(tr);
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.id}</td>
      <td>${it.status}</td>
      <td>${it.channel_name}.${it.preset_name || "-"}</td>
      <td>${it.symbol} ${it.side}</td>
      <td>${fmtTs(it.opened_at)}</td>
      <td>${fmtTs(it.closed_at)}</td>
      <td>${fmtDur(it.duration_seconds)}</td>
      <td>${fmtNum(it.pnl_pips ?? it.last_pips)}</td>
      <td>${fmtNum(it.pnl_usd ?? it.last_profit_usd)}</td>
      <td>${it.close_source || "-"}</td>
      <td><a class="mini-btn" target="_blank" href="/operaciones/${it.id}">Ver</a></td>
    `;
    closedBody.appendChild(tr);
  }
}

function updateClosedPager(meta) {
  closedPage = meta.page || 1;
  closedTotalPages = meta.total_pages || 1;
  closedPrevBtn.disabled = !meta.has_prev;
  closedNextBtn.disabled = !meta.has_next;
  closedPageInfo.textContent = `Página ${closedPage} de ${closedTotalPages} | Total: ${meta.total || 0}`;
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await readJson(res);
  applyHeaderStatus(data);
}

async function loadOpenOperations() {
  if (openLoadInFlight) {
    return;
  }
  openLoadInFlight = true;
  try {
    const res = await fetch("/api/operations/open");
    const data = await readJson(res);
    if (!res.ok) {
      openMsg.textContent = data.detail || "Error cargando abiertas";
      return;
    }
    openItems = data.items || [];
    renderOpenCards(openItems);
    openMsg.textContent = `${openItems.length} abierta(s)/pending`;
  } finally {
    openLoadInFlight = false;
  }
}

async function loadClosedOperations(page = 1) {
  const res = await fetch(`/api/operations/closed?page=${Math.max(1, page)}&page_size=20`);
  const data = await readJson(res);
  if (!res.ok) {
    closedMsg.textContent = data.detail || "Error cargando cerradas";
    return;
  }
  renderClosedRows(data.items || []);
  updateClosedPager(data);
  closedMsg.textContent = `${(data.items || []).length} operación(es) en página`;
}

async function closeOperationManual(operationId) {
  const idNum = Number(operationId);
  if (!Number.isFinite(idNum) || idNum <= 0) {
    return;
  }
  if (!window.confirm(`Seguro que quieres cerrar manualmente la operación #${idNum}?`)) {
    return;
  }
  if (manualCloseMsg) {
    manualCloseMsg.textContent = `Cerrando #${idNum}...`;
  }
  const payload = {
    reason: "Cerrada desde Panel web a mano",
    details: "Cierre manual solicitado desde Operaciones (UI).",
    close_in_mt5: manualCloseInMt5 ? !!manualCloseInMt5.checked : false,
  };
  const res = await fetch(`/api/operations/${idNum}/close-manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    if (manualCloseMsg) {
      manualCloseMsg.textContent = data.detail || "No se pudo cerrar la operación";
    }
    showToastMsg(data.detail || "No se pudo cerrar la operación", "error");
    return;
  }
  const queued = Number(data.queued_count || 0) > 0;
  const msg = queued
    ? `Operación #${idNum} enviada a cola para cierre en MT5`
    : `Operación #${idNum} cerrada manualmente`;
  if (manualCloseMsg) {
    manualCloseMsg.textContent = msg;
  }
  showToastMsg(msg, "success");
  await refreshAll();
}

async function closeAllOperationsManual() {
  const mode = manualCloseMode ? manualCloseMode.value : "all";
  const includePending = manualCloseIncludePending ? !!manualCloseIncludePending.checked : true;
  const closeInMt5 = manualCloseInMt5 ? !!manualCloseInMt5.checked : false;
  const modeLabel = mode === "real" ? "solo real" : mode === "virtual" ? "solo virtual" : "real + virtual";
  const pendingLabel = includePending ? "incluyendo pending" : "solo abiertas";
  const mt5Label = closeInMt5 ? ", cierre real en MT5" : ", solo registro";
  if (!window.confirm(`Seguro que quieres cerrar en masa (${modeLabel}, ${pendingLabel}${mt5Label})?`)) {
    return;
  }
  if (manualCloseMsg) {
    manualCloseMsg.textContent = "Cerrando operaciones por filtro...";
  }
  const payload = {
    mode,
    include_pending: includePending,
    reason: "Cerrada desde Panel web a mano",
    details: `Cierre masivo desde Operaciones (UI). mode=${mode};include_pending=${includePending ? "1" : "0"}`,
    close_in_mt5: closeInMt5,
  };
  const res = await fetch("/api/operations/close-manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    if (manualCloseMsg) {
      manualCloseMsg.textContent = data.detail || "No se pudo ejecutar cierre masivo";
    }
    showToastMsg(data.detail || "No se pudo ejecutar cierre masivo", "error");
    return;
  }
  const msg = `Cierre masivo: ${data.closed_count || 0} cerrada(s), ${data.queued_count || 0} en cola MT5`;
  if (manualCloseMsg) {
    manualCloseMsg.textContent = msg;
  }
  showToastMsg(msg, "success");
  await refreshAll();
}

function tickElapsed() {
  const cards = openCards.querySelectorAll(".operation-card");
  const now = new Date();
  cards.forEach((card) => {
    const openedAt = card.dataset.openedAt;
    const label = card.querySelector(".live-elapsed");
    if (!openedAt || !label) {
      return;
    }
    const od = new Date(openedAt);
    if (Number.isNaN(od.getTime())) {
      return;
    }
    const secs = Math.max(0, Math.floor((now.getTime() - od.getTime()) / 1000));
    label.textContent = fmtDur(secs);
  });
}

async function searchOperation() {
  const raw = document.getElementById("search-operation-id").value.trim();
  if (!raw) {
    searchMsg.textContent = "Ingresa un ID";
    return;
  }
  const res = await fetch(`/api/operations/search?operation_id=${encodeURIComponent(raw)}`);
  const data = await readJson(res);
  if (!res.ok) {
    searchMsg.textContent = data.detail || "No encontrada";
    return;
  }
  window.location.href = data.url;
}

function initActions() {
  document.getElementById("search-operation-btn").addEventListener("click", searchOperation);
  if (manualCloseAllBtn) {
    manualCloseAllBtn.addEventListener("click", closeAllOperationsManual);
  }
  openCards.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action='close-open-op']");
    if (!btn) {
      return;
    }
    const id = Number(btn.dataset.id || 0);
    if (id > 0) {
      closeOperationManual(id);
    }
  });
  closedPrevBtn.addEventListener("click", () => {
    if (closedPage > 1) {
      loadClosedOperations(closedPage - 1);
    }
  });
  closedNextBtn.addEventListener("click", () => {
    if (closedPage < closedTotalPages) {
      loadClosedOperations(closedPage + 1);
    }
  });
}

async function refreshAll() {
  await Promise.all([refreshStatus(), loadOpenOperations(), loadClosedOperations(closedPage)]);
}

initActions();
refreshAll();
setInterval(loadOpenOperations, 1000);
setInterval(() => loadClosedOperations(closedPage), 15000);
setInterval(tickElapsed, 1000);
