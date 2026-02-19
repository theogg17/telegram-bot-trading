const dbPath = document.getElementById("db-path");
const summaryBody = document.getElementById("summary-body");
const metricsBody = document.getElementById("metrics-body");
const errorsBody = document.getElementById("errors-body");
const seriesMsg = document.getElementById("series-msg");
const summaryMsg = document.getElementById("summary-msg");
const metricsMsg = document.getElementById("metrics-msg");
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
const alertsMsg = document.getElementById("alerts-msg");
const alertsActiveBody = document.getElementById("alerts-active-body");
const alertsHistoryBody = document.getElementById("alerts-history-body");
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
const chart = document.getElementById("pnl-chart");
const ctx = chart.getContext("2d");
const chartFromTs = document.getElementById("chart-from-ts");
const chartToTs = document.getElementById("chart-to-ts");
const chartApplyFilterBtn = document.getElementById("chart-apply-filter");
const chartReset90Btn = document.getElementById("chart-reset-90");
const chartRangeMsg = document.getElementById("chart-range-msg");
const chartTooltip = document.getElementById("pnl-tooltip");
const metricsChart = document.getElementById("metrics-chart");
const metricsCtx = metricsChart ? metricsChart.getContext("2d") : null;

const hasErrorsSection =
  !!errorsBody &&
  !!errorsMsg &&
  !!errorsPageInfo &&
  !!errorsPrevBtn &&
  !!errorsNextBtn &&
  !!errorsFromTs &&
  !!errorsToTs &&
  !!errorsPageSize &&
  !!errorsApplyFilterBtn &&
  !!errorsClearFilterBtn &&
  !!errorsDownloadExcelBtn;

const hasAlertsSection =
  !!alertsMsg &&
  !!alertsActiveBody &&
  !!alertsHistoryBody &&
  !!alertsEnabledInput &&
  !!alertsQueueThresholdInput &&
  !!alertsErrorThresholdInput &&
  !!alertsPendingSecInput &&
  !!alertsDrawdownInput &&
  !!discordEnabledInput &&
  !!discordWebhookInput &&
  !!discordMinSeverityInput &&
  !!alertsSaveConfigBtn &&
  !!alertsTestDiscordBtn;

let errorsPage = 1;
let errorsTotalPages = 1;
let refreshing = false;
let alertsConfigLoaded = false;
let chartHoverPoints = [];

function showSavedToast(message) {
  if (typeof window.showSavedToast === "function") {
    window.showSavedToast(message);
  }
}

function fmtNum(v) {
  return Number.isFinite(Number(v)) ? Number(v).toFixed(2) : "-";
}

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

function fmtDay(value) {
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) {
    return "-";
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
}

function toLocalInputValue(dateObj) {
  const d = dateObj instanceof Date ? dateObj : new Date(dateObj);
  if (Number.isNaN(d.getTime())) {
    return "";
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function applyDefaultChartRange(days = 90) {
  if (!chartFromTs || !chartToTs) {
    return;
  }
  const now = new Date();
  const from = new Date(now.getTime() - Math.max(1, Number(days)) * 86400000);
  chartFromTs.value = toLocalInputValue(from);
  chartToTs.value = toLocalInputValue(now);
  if (chartRangeMsg) {
    chartRangeMsg.textContent = `Período: últimos ${Math.max(1, Number(days))} días`;
  }
}

function buildSeriesQuery() {
  const params = new URLSearchParams();
  const fromIso = toIsoForApi(chartFromTs ? chartFromTs.value : "", false);
  const toIso = toIsoForApi(chartToTs ? chartToTs.value : "", true);
  if (fromIso) {
    params.set("from_ts", fromIso);
  }
  if (toIso) {
    params.set("to_ts", toIso);
  }
  return params.toString();
}

function buildErrorsQuery(pageOverride = null) {
  if (!hasErrorsSection) {
    return "page=1&page_size=100";
  }
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

function renderSummary(items) {
  summaryBody.innerHTML = "";
  if (!items || !items.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="9" class="empty">Sin datos</td>';
    summaryBody.appendChild(tr);
    return;
  }
  for (const it of items) {
    const preset = it.preset_name || it.config_name || "-";
    const comboText = `${it.channel_name}.${preset}`;
    const comboCell =
      Number.isFinite(Number(it.assignment_id)) && Number(it.assignment_id) > 0
        ? `<a href="/canal-presets?id=${Number(it.assignment_id)}">${comboText}</a>`
        : comboText;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${comboCell}</td>
      <td>${it.mode}</td>
      <td>${it.events}</td>
      <td>${it.entries}</td>
      <td>${it.modifications}</td>
      <td>${it.closes}</td>
      <td>${it.errors}</td>
      <td>${fmtNum(it.pnl_usd)}</td>
      <td>${fmtNum(it.pnl_pips)}</td>
    `;
    summaryBody.appendChild(tr);
  }
}

function drawMetricsChart(items) {
  if (!metricsCtx || !metricsChart) {
    return;
  }
  const width = metricsChart.width;
  const height = metricsChart.height;
  metricsCtx.clearRect(0, 0, width, height);
  metricsCtx.fillStyle = "rgba(9,15,26,0.95)";
  metricsCtx.fillRect(0, 0, width, height);
  const rows = items || [];
  if (!rows.length) {
    metricsCtx.fillStyle = "#9fb0cc";
    metricsCtx.font = "16px Trebuchet MS";
    metricsCtx.fillText("Sin métricas disponibles", 24, 36);
    return;
  }
  const top = rows.slice(0, 8);
  const maxFreq = Math.max(1, ...top.map((x) => Number(x.frequency_trades_per_day || 0)));
  const barH = Math.max(16, Math.floor((height - 30) / top.length) - 8);
  top.forEach((it, idx) => {
    const y = 20 + idx * (barH + 8);
    const freq = Number(it.frequency_trades_per_day || 0);
    const longCount = Number(it.long_duration_count || 0);
    const barW = Math.max(0, Math.floor((width - 260) * (freq / maxFreq)));
    metricsCtx.fillStyle = "rgba(70, 209, 191, 0.85)";
    metricsCtx.fillRect(230, y, barW, barH);
    metricsCtx.fillStyle = "#d7e5ff";
    metricsCtx.font = "12px Trebuchet MS";
    const name = `${it.channel_name}.${it.preset_name}`;
    metricsCtx.fillText(name.slice(0, 30), 12, y + 12);
    metricsCtx.fillText(`freq ${fmtNum(freq)}/d | largas ${longCount}`, 230 + barW + 8, y + 12);
  });
}

function renderMetrics(items) {
  if (!metricsBody) {
    return;
  }
  metricsBody.innerHTML = "";
  const rows = items || [];
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="7" class="empty">Sin métricas</td>';
    metricsBody.appendChild(tr);
    drawMetricsChart([]);
    return;
  }
  for (const it of rows) {
    const assignmentId = Number(it.assignment_id || 0);
    const detailLink = assignmentId > 0 ? `<a href="/canal-presets?id=${assignmentId}">Ver detalle</a>` : "-";
    const avgMin = Number(it.avg_duration_sec || 0) / 60;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.channel_name}.${it.preset_name}</td>
      <td>${Number(it.entries || 0)}</td>
      <td>${fmtNum(it.frequency_trades_per_day || 0)}</td>
      <td>${fmtNum(avgMin)}</td>
      <td>${Number(it.long_duration_count || 0)}</td>
      <td>${Number(it.buy_count || 0)}/${Number(it.sell_count || 0)}</td>
      <td>${detailLink}</td>
    `;
    metricsBody.appendChild(tr);
  }
  drawMetricsChart(rows);
}

function renderErrors(items) {
  if (!errorsBody) {
    return;
  }
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

function renderActiveAlerts(items) {
  if (!alertsActiveBody) {
    return;
  }
  alertsActiveBody.innerHTML = "";
  if (!items || !items.length) {
    alertsActiveBody.innerHTML = '<tr><td colspan="8" class="empty">Sin alertas activas</td></tr>';
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtTs(it.first_seen || it.ts)}</td>
      <td>ACTIVA</td>
      <td>${it.severity}</td>
      <td>${it.code}</td>
      <td>${it.title}</td>
      <td>${it.details}</td>
      <td>${it.occurrences}</td>
      <td>${fmtTs(it.last_seen || it.ts)}</td>
    `;
    alertsActiveBody.appendChild(tr);
  }
}

function renderAlertsHistory(items) {
  if (!alertsHistoryBody) {
    return;
  }
  alertsHistoryBody.innerHTML = "";
  if (!items || !items.length) {
    alertsHistoryBody.innerHTML = '<tr><td colspan="8" class="empty">Sin historial de alertas</td></tr>';
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtTs(it.ts)}</td>
      <td>${it.status || (it.is_active ? "ACTIVA" : "RESUELTA")}</td>
      <td>${it.severity}</td>
      <td>${it.code}</td>
      <td>${it.title}</td>
      <td>${it.details}</td>
      <td>${it.occurrences}</td>
      <td>${fmtTs(it.last_seen || it.resolved_at || it.ts)}</td>
    `;
    alertsHistoryBody.appendChild(tr);
  }
}

function drawSeries(series) {
  chartHoverPoints = [];
  const width = chart.width;
  const height = chart.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "rgba(9,15,26,0.95)";
  ctx.fillRect(0, 0, width, height);

  const palette = ["#46d1bf", "#ffb86a", "#79b8ff", "#ff7aa2", "#b5ff7a", "#f7d65d", "#f78cff", "#67e8f9", "#f472b6"];
  const keys = Object.keys(series || {});
  if (!keys.length) {
    ctx.fillStyle = "#9fb0cc";
    ctx.font = "16px Trebuchet MS";
    ctx.fillText("Sin series disponibles", 24, 36);
    hideChartTooltip();
    return;
  }

  const datasets = [];
  for (let i = 0; i < keys.length; i += 1) {
    const combo = keys[i];
    const raw = Array.isArray(series[combo]) ? series[combo] : [];
    const points = raw
      .map((p) => {
        const ts = new Date(p.ts);
        const value = Number(p.value);
        if (Number.isNaN(ts.getTime()) || !Number.isFinite(value)) {
          return null;
        }
        return {
          tsRaw: String(p.ts || ""),
          tsMs: ts.getTime(),
          value,
        };
      })
      .filter(Boolean)
      .sort((a, b) => a.tsMs - b.tsMs);
    datasets.push({ combo, color: palette[i % palette.length], points });
  }

  const allPoints = datasets.flatMap((d) => d.points);
  if (!allPoints.length) {
    ctx.fillStyle = "#9fb0cc";
    ctx.font = "16px Trebuchet MS";
    ctx.fillText("Sin datos en el período seleccionado", 24, 36);
    hideChartTooltip();
    return;
  }

  const left = 72;
  const right = 22;
  const top = 18;
  const bottom = 96;
  const plotW = Math.max(40, width - left - right);
  const plotH = Math.max(40, height - top - bottom);

  let xMin = Math.min(...allPoints.map((p) => p.tsMs));
  let xMax = Math.max(...allPoints.map((p) => p.tsMs));
  if (xMax <= xMin) {
    xMax = xMin + 86400000;
  }

  let yMin = Math.min(...allPoints.map((p) => p.value), 0);
  let yMax = Math.max(...allPoints.map((p) => p.value), 0);
  if (Math.abs(yMax - yMin) < 1e-9) {
    yMin -= 1;
    yMax += 1;
  }

  const xToPx = (tsMs) => left + ((tsMs - xMin) / Math.max(1, xMax - xMin)) * plotW;
  const yToPx = (value) => top + (1 - (value - yMin) / Math.max(1e-9, yMax - yMin)) * plotH;

  ctx.strokeStyle = "rgba(255,255,255,0.2)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, top + plotH);
  ctx.lineTo(left + plotW, top + plotH);
  ctx.stroke();

  const yTicks = 6;
  ctx.font = "12px Trebuchet MS";
  for (let i = 0; i <= yTicks; i += 1) {
    const t = i / yTicks;
    const val = yMax - t * (yMax - yMin);
    const y = yToPx(val);
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
    ctx.fillStyle = "#aebfd8";
    ctx.textAlign = "right";
    ctx.fillText(fmtNum(val), left - 8, y + 4);
  }

  const xTicks = 7;
  for (let i = 0; i <= xTicks; i += 1) {
    const t = i / xTicks;
    const tsMs = xMin + t * (xMax - xMin);
    const x = xToPx(tsMs);
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, top + plotH);
    ctx.stroke();
    ctx.fillStyle = "#aebfd8";
    ctx.textAlign = "center";
    ctx.fillText(fmtDay(tsMs), x, top + plotH + 18);
  }

  if (yMin <= 0 && yMax >= 0) {
    const yZero = yToPx(0);
    ctx.save();
    ctx.setLineDash([6, 6]);
    ctx.strokeStyle = "rgba(255,255,255,0.8)";
    ctx.beginPath();
    ctx.moveTo(left, yZero);
    ctx.lineTo(left + plotW, yZero);
    ctx.stroke();
    ctx.restore();
  }

  ctx.fillStyle = "#cfe0ff";
  ctx.textAlign = "center";
  ctx.fillText("Días", left + plotW / 2, height - 10);
  ctx.save();
  ctx.translate(16, top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillText("PnL (USD)", 0, 0);
  ctx.restore();

  datasets.forEach((ds) => {
    if (!ds.points.length) {
      return;
    }
    ctx.strokeStyle = ds.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ds.points.forEach((p, idx) => {
      const x = xToPx(p.tsMs);
      const y = yToPx(p.value);
      if (idx === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      chartHoverPoints.push({
        x,
        y,
        combo: ds.combo,
        ts: p.tsRaw,
        value: p.value,
      });
    });
    ctx.stroke();
    if (ds.points.length === 1) {
      const p = ds.points[0];
      ctx.fillStyle = ds.color;
      ctx.beginPath();
      ctx.arc(xToPx(p.tsMs), yToPx(p.value), 3, 0, Math.PI * 2);
      ctx.fill();
    }
  });

  let lx = left + 4;
  let ly = top + plotH + 40;
  const legendLineH = 16;
  datasets.forEach((ds) => {
    if (!ds.points.length) {
      return;
    }
    const label = ds.combo;
    ctx.font = "12px Trebuchet MS";
    const blockW = 16 + 6 + ctx.measureText(label).width + 12;
    if (lx + blockW > width - right) {
      lx = left + 4;
      ly += legendLineH;
    }
    ctx.fillStyle = ds.color;
    ctx.fillRect(lx, ly - 8, 10, 10);
    ctx.fillStyle = "#d7e5ff";
    ctx.textAlign = "left";
    ctx.fillText(label, lx + 16, ly);
    lx += blockW;
  });
}

function escapeHtml(v) {
  return String(v || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function hideChartTooltip() {
  if (!chartTooltip) {
    return;
  }
  chartTooltip.hidden = true;
}

function showChartTooltip(point, localX, localY) {
  if (!chartTooltip || !point) {
    return;
  }
  chartTooltip.innerHTML = `${escapeHtml(point.combo)}<br>${escapeHtml(fmtTs(point.ts))}<br>PnL: ${escapeHtml(fmtNum(point.value))} USD`;
  chartTooltip.hidden = false;
  const wrap = chartTooltip.parentElement;
  if (!wrap) {
    return;
  }
  const wrapW = wrap.clientWidth || chart.width;
  const wrapH = wrap.clientHeight || chart.height;
  const ttW = chartTooltip.offsetWidth || 200;
  const ttH = chartTooltip.offsetHeight || 64;
  const x = Math.max(8, Math.min(localX + 12, wrapW - ttW - 8));
  const y = Math.max(8, Math.min(localY + 12, wrapH - ttH - 8));
  chartTooltip.style.left = `${x}px`;
  chartTooltip.style.top = `${y}px`;
}

function onChartMouseMove(event) {
  if (!chart || !chartHoverPoints.length) {
    hideChartTooltip();
    return;
  }
  const rect = chart.getBoundingClientRect();
  const scaleX = chart.width / Math.max(1, rect.width);
  const scaleY = chart.height / Math.max(1, rect.height);
  const mx = (event.clientX - rect.left) * scaleX;
  const my = (event.clientY - rect.top) * scaleY;
  let nearest = null;
  let bestD2 = Infinity;
  for (const p of chartHoverPoints) {
    const dx = p.x - mx;
    const dy = p.y - my;
    const d2 = dx * dx + dy * dy;
    if (d2 < bestD2) {
      bestD2 = d2;
      nearest = p;
    }
  }
  const maxD2 = 14 * 14;
  if (!nearest || bestD2 > maxD2) {
    hideChartTooltip();
    return;
  }
  showChartTooltip(nearest, event.clientX - rect.left, event.clientY - rect.top);
}

function updatePager(meta) {
  if (!hasErrorsSection) {
    return;
  }
  errorsPage = meta.page || 1;
  errorsTotalPages = meta.total_pages || 1;
  errorsPageInfo.textContent = `Página ${errorsPage} de ${errorsTotalPages} | Total errores: ${meta.total || 0}`;
  errorsPrevBtn.disabled = !meta.has_prev;
  errorsNextBtn.disabled = !meta.has_next;
}

async function refreshErrorsOnly(pageOverride = null) {
  if (!hasErrorsSection) {
    return;
  }
  try {
    const qs = buildErrorsQuery(pageOverride);
    const res = await fetch(`/api/reportes/errors?${qs}`);
    const data = await readJson(res);
    if (!res.ok) {
      errorsMsg.textContent = data.detail || "Error actualizando errores";
      return;
    }
    renderErrors(data.items || []);
    updatePager(data);
    errorsMsg.textContent = `${(data.items || []).length} error(es) en página`;
  } catch {
    if (errorsMsg) {
      errorsMsg.textContent = "Error actualizando errores";
    }
  }
}

function applyAlertsConfigToForm(cfg) {
  if (!hasAlertsSection) {
    return;
  }
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

async function loadAlertsConfig() {
  if (!hasAlertsSection) {
    return;
  }
  const res = await fetch("/api/alerts/config");
  const data = await readJson(res);
  if (!res.ok) {
    alertsMsg.textContent = data.detail || "Error cargando configuración de alertas";
    return;
  }
  applyAlertsConfigToForm(data.config || {});
  alertsConfigLoaded = true;
}

async function refreshAlerts() {
  if (!hasAlertsSection) {
    return;
  }
  try {
    const [activeRes, histRes] = await Promise.all([
      fetch("/api/alerts/active"),
      fetch("/api/alerts/history?page=1&page_size=20"),
    ]);
    const activeData = await readJson(activeRes);
    const histData = await readJson(histRes);
    if (activeRes.ok) {
      renderActiveAlerts(activeData.items || []);
      alertsMsg.textContent = `${(activeData.items || []).length} alerta(s) activa(s)`;
    }
    if (histRes.ok) {
      renderAlertsHistory(histData.items || []);
    }
  } catch {
    alertsMsg.textContent = "Error actualizando alertas";
  }
}

async function saveAlertsConfig() {
  if (!hasAlertsSection) {
    return;
  }
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
  if (!hasAlertsSection) {
    return;
  }
  alertsMsg.textContent = "Enviando test a Discord...";
  const res = await fetch("/api/alerts/discord-test", { method: "POST" });
  const data = await readJson(res);
  if (!res.ok) {
    alertsMsg.textContent = data.detail || "No se pudo enviar test";
    return;
  }
  alertsMsg.textContent = "Test enviado a Discord";
}

async function refreshAll() {
  if (refreshing) {
    return;
  }
  refreshing = true;
  try {
    const seriesQs = buildSeriesQuery();
    const [statusRes, summaryRes, seriesRes, metricsRes] = await Promise.all([
      fetch("/api/status"),
      fetch("/api/reportes/summary"),
      fetch(`/api/reportes/timeseries?${seriesQs}`),
      fetch("/api/reportes/channel-preset-metrics"),
    ]);
    const statusData = await readJson(statusRes);
    const summaryData = await readJson(summaryRes);
    const seriesData = await readJson(seriesRes);
    const metricsData = await readJson(metricsRes);

    if (statusData.db_path) {
      dbPath.textContent = `db: ${statusData.db_path}`;
    }
    renderSummary(summaryData.items || []);
    drawSeries(seriesData.series || {});
    renderMetrics(metricsData.items || []);
    summaryMsg.textContent = `${(summaryData.items || []).length} combinación(es)`;
    seriesMsg.textContent = `${Object.keys(seriesData.series || {}).length} serie(s)`;
    if (chartRangeMsg) {
      const allPoints = Object.values(seriesData.series || {}).flatMap((arr) =>
        (Array.isArray(arr) ? arr : []).map((p) => new Date(p.ts)).filter((d) => !Number.isNaN(d.getTime())),
      );
      if (allPoints.length) {
        allPoints.sort((a, b) => a.getTime() - b.getTime());
        chartRangeMsg.textContent = `Rango visible: ${fmtTs(allPoints[0])} -> ${fmtTs(allPoints[allPoints.length - 1])}`;
      } else {
        chartRangeMsg.textContent = "Sin datos en el período seleccionado";
      }
    }
    if (metricsMsg) {
      metricsMsg.textContent = `${(metricsData.items || []).length} combinación(es)`;
    }

    await refreshErrorsOnly(errorsPage);
    await refreshAlerts();
  } catch {
    seriesMsg.textContent = "Error actualizando series";
    summaryMsg.textContent = "Error actualizando resumen";
    if (errorsMsg) {
      errorsMsg.textContent = "Error actualizando errores";
    }
  } finally {
    refreshing = false;
  }
}

function downloadErrorsExcel() {
  if (!hasErrorsSection) {
    return;
  }
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

function initActions() {
  if (chart) {
    chart.addEventListener("mousemove", onChartMouseMove);
    chart.addEventListener("mouseleave", hideChartTooltip);
  }
  if (chartApplyFilterBtn) {
    chartApplyFilterBtn.addEventListener("click", () => {
      refreshAll();
    });
  }
  if (chartReset90Btn) {
    chartReset90Btn.addEventListener("click", () => {
      applyDefaultChartRange(90);
      refreshAll();
    });
  }
  if (hasErrorsSection) {
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
  if (hasAlertsSection) {
    alertsSaveConfigBtn.addEventListener("click", saveAlertsConfig);
    alertsTestDiscordBtn.addEventListener("click", testDiscord);
  }
}

initActions();
applyDefaultChartRange(90);
if (hasAlertsSection) {
  loadAlertsConfig().then(refreshAll);
} else {
  refreshAll();
}
setInterval(refreshAll, 5000);
