const dbPath = document.getElementById("db-path");
const globalStatus = document.getElementById("global-status");
const searchMsg = document.getElementById("search-msg");
const resultsMsg = document.getElementById("results-msg");
const resultsBody = document.getElementById("results-body");
const queryInput = document.getElementById("message-query");

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

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await readJson(res);
  applyHeaderStatus(data);
}

function renderRows(items) {
  resultsBody.innerHTML = "";
  if (!items || !items.length) {
    resultsBody.innerHTML = '<tr><td colspan="9" class="empty">Sin resultados</td></tr>';
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.message_uid || "-"}</td>
      <td>${it.message_id || "-"}</td>
      <td>${it.event_id || "-"}</td>
      <td>${it.channel_name || "-"}</td>
      <td>${fmtTs(it.ts)}</td>
      <td>${it.event_type || "-"}</td>
      <td>${it.symbol || "-"} ${it.operation || "-"}</td>
      <td>${it.operator_class || "-"}</td>
      <td>${(it.message_text || it.raw_payload || "-").slice(0, 400)}</td>
    `;
    resultsBody.appendChild(tr);
  }
}

async function search() {
  const q = queryInput.value.trim();
  if (!q) {
    searchMsg.textContent = "Ingresa un ID";
    return;
  }
  searchMsg.textContent = "Buscando...";
  const res = await fetch(`/api/messages/search?message_id=${encodeURIComponent(q)}&limit=100`);
  const data = await readJson(res);
  if (!res.ok) {
    searchMsg.textContent = data.detail || "Error de búsqueda";
    return;
  }
  renderRows(data.items || []);
  searchMsg.textContent = "Búsqueda completada";
  resultsMsg.textContent = `${data.count || 0} resultado(s)`;
}

document.getElementById("message-search-btn").addEventListener("click", search);
queryInput.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    ev.preventDefault();
    search();
  }
});

refreshStatus();
