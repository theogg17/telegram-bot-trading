const dbPath = document.getElementById("db-path");
const searchMsg = document.getElementById("search-msg");
const resultsMsg = document.getElementById("results-msg");
const resultsBody = document.getElementById("results-body");
const pageInfo = document.getElementById("page-info");
const prevPageBtn = document.getElementById("prev-page");
const nextPageBtn = document.getElementById("next-page");

const fOpenFrom = document.getElementById("f-open-from");
const fOpenTo = document.getElementById("f-open-to");
const fCloseFrom = document.getElementById("f-close-from");
const fCloseTo = document.getElementById("f-close-to");
const fSymbol = document.getElementById("f-symbol");
const fSide = document.getElementById("f-side");
const fId = document.getElementById("f-id");
const fChannelPreset = document.getElementById("f-channel-preset");
const fCloseSource = document.getElementById("f-close-source");
const fCloseMessageId = document.getElementById("f-close-message-id");
const fErrorId = document.getElementById("f-error-id");
const btnSearch = document.getElementById("btn-search");
const btnClear = document.getElementById("btn-clear");

let page = 1;
let totalPages = 1;

function readJson(res) {
  return res.json().catch(() => ({}));
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

function toIsoForApi(localValue, isEnd = false) {
  if (window.dateTime24 && typeof window.dateTime24.normalizeForApi === "function") {
    return window.dateTime24.normalizeForApi(localValue, isEnd);
  }
  if (!localValue) {
    return "";
  }
  const d = new Date(localValue);
  if (Number.isNaN(d.getTime())) {
    return "";
  }
  if (isEnd && localValue.length <= 16) {
    d.setSeconds(59, 999);
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function filters() {
  return {
    opened_from_ts: toIsoForApi((fOpenFrom.value || "").trim(), false),
    opened_to_ts: toIsoForApi((fOpenTo.value || "").trim(), true),
    closed_from_ts: toIsoForApi((fCloseFrom.value || "").trim(), false),
    closed_to_ts: toIsoForApi((fCloseTo.value || "").trim(), true),
    symbol: (fSymbol.value || "").trim(),
    side: (fSide.value || "").trim(),
    operation_id: (fId.value || "").trim(),
    channel_preset: (fChannelPreset.value || "").trim(),
    close_source: (fCloseSource.value || "").trim(),
    close_message_id: (fCloseMessageId.value || "").trim(),
    error_id: (fErrorId.value || "").trim(),
  };
}

function renderRows(items) {
  resultsBody.innerHTML = "";
  if (!items || !items.length) {
    resultsBody.innerHTML = '<tr><td colspan="13" class="empty">Sin resultados</td></tr>';
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.id}</td>
      <td>${it.status || "-"}</td>
      <td>${it.channel_name || "-"}.${it.preset_name || "-"}</td>
      <td>${it.symbol || "-"} ${it.side || "-"}</td>
      <td>${fmtTs(it.opened_at)}</td>
      <td>${fmtTs(it.closed_at)}</td>
      <td>${fmtDur(it.duration_seconds)}</td>
      <td>${fmtNum(it.pnl_pips ?? it.last_pips)}</td>
      <td>${fmtNum(it.pnl_usd ?? it.last_profit_usd)}</td>
      <td>${it.close_source || "-"}</td>
      <td>${it.close_trigger_message_id || "-"}</td>
      <td>${it.close_error_id || "-"}</td>
      <td><a class="mini-btn" target="_blank" href="/operaciones/${it.id}">Ver</a></td>
    `;
    resultsBody.appendChild(tr);
  }
}

function updatePager(meta) {
  page = Number(meta.page || 1);
  totalPages = Number(meta.total_pages || 1);
  prevPageBtn.disabled = !(meta.has_prev);
  nextPageBtn.disabled = !(meta.has_next);
  pageInfo.textContent = `Página ${page} de ${totalPages} | Total: ${meta.total || 0}`;
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await readJson(res);
  if (data.db_path) {
    dbPath.textContent = `db: ${data.db_path}`;
  }
}

async function loadData(goToPage = 1) {
  page = Math.max(1, Number(goToPage || 1));
  const f = filters();
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", "50");
  Object.entries(f).forEach(([k, v]) => {
    if (v !== "") {
      params.set(k, v);
    }
  });
  searchMsg.textContent = "Buscando...";
  const res = await fetch(`/api/operations/closed?${params.toString()}`);
  const data = await readJson(res);
  if (!res.ok) {
    searchMsg.textContent = data.detail || "Error de búsqueda";
    return;
  }
  renderRows(data.items || []);
  updatePager(data);
  resultsMsg.textContent = `${(data.items || []).length} resultado(s) en página`;
  searchMsg.textContent = "Búsqueda completada";
}

function clearFilters() {
  fOpenFrom.value = "";
  fOpenTo.value = "";
  fCloseFrom.value = "";
  fCloseTo.value = "";
  fSymbol.value = "";
  fSide.value = "";
  fId.value = "";
  fChannelPreset.value = "";
  fCloseSource.value = "";
  fCloseMessageId.value = "";
  fErrorId.value = "";
}

btnSearch.addEventListener("click", () => loadData(1));
btnClear.addEventListener("click", () => {
  clearFilters();
  loadData(1);
});
prevPageBtn.addEventListener("click", () => {
  if (page > 1) {
    loadData(page - 1);
  }
});
nextPageBtn.addEventListener("click", () => {
  if (page < totalPages) {
    loadData(page + 1);
  }
});

[fOpenFrom, fOpenTo, fCloseFrom, fCloseTo, fSymbol, fSide, fId, fChannelPreset, fCloseSource, fCloseMessageId, fErrorId].forEach((el) => {
  el.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      loadData(1);
    }
  });
});

refreshStatus();
loadData(1);
