const dbPath = document.getElementById("db-path");
const channelsMsg = document.getElementById("channels-msg");
const profileMsg = document.getElementById("profile-msg");
const presetMsg = document.getElementById("preset-msg");
const assignmentMsg = document.getElementById("assignment-msg");

const channelsBody = document.getElementById("channels-body");
const profilesBody = document.getElementById("profiles-body");
const presetsBody = document.getElementById("presets-body");
const assignmentsBody = document.getElementById("assignments-body");

const assignmentChannel = document.getElementById("assignment_channel");
const assignmentConfig = document.getElementById("assignment_config");
const presetExecutionProfile = document.getElementById("preset_execution_profile_id");
const cpSearchMsg = document.getElementById("cp-search-msg");
const cpSearchResults = document.getElementById("cp-search-results");
const cpSearchId = document.getElementById("cp-search-id");
const cpSearchFrom = document.getElementById("cp-search-from");
const cpSearchTo = document.getElementById("cp-search-to");

let channels = [];
let profiles = [];
let presets = [];
let assignments = [];
let selectedProfileId = null;
let selectedPresetId = null;
let selectedAssignmentId = null;

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

function setChannelForm(channel = null) {
  document.getElementById("channel_id").value = channel ? channel.id : "";
  document.getElementById("channel_name").value = channel ? channel.name : "";
  document.getElementById("channel_chat_id").value = channel ? channel.chat_id : "";
  document.getElementById("channel_external_id").value = channel ? channel.external_id : "";
  document.getElementById("channel_is_active").checked = channel ? !!channel.is_active : true;
}

function channelPayload() {
  return {
    name: document.getElementById("channel_name").value.trim(),
    chat_id: document.getElementById("channel_chat_id").value.trim(),
    external_id: document.getElementById("channel_external_id").value.trim(),
    is_active: document.getElementById("channel_is_active").checked,
  };
}

function renderChannelRows() {
  if (!channelsBody) {
    return;
  }
  channelsBody.innerHTML = "";
  if (!channels.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="empty">No hay canales cargados</td>';
    channelsBody.appendChild(tr);
    return;
  }
  for (const c of channels) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${c.id}</td>
      <td>${c.name}</td>
      <td><code>${c.chat_id}</code></td>
      <td>${c.external_id || "-"}</td>
      <td>${c.is_active ? "si" : "no"}</td>
      <td class="row-actions">
        <button class="mini-btn" data-action="edit-channel" data-id="${c.id}">Editar</button>
        <button class="mini-btn danger" data-action="delete-channel" data-id="${c.id}">Eliminar</button>
      </td>
    `;
    channelsBody.appendChild(tr);
  }
}

function setProfileForm(profile = null) {
  document.getElementById("profile_code").value = profile ? profile.code : "";
  document.getElementById("profile_name").value = profile ? profile.name : "";
  document.getElementById("profile_description").value = profile ? profile.description : "";
  document.getElementById("profile_is_system").checked = profile ? !!profile.is_system : false;
}

function profilePayload() {
  return {
    code: document.getElementById("profile_code").value.trim().toUpperCase(),
    name: document.getElementById("profile_name").value.trim(),
    description: document.getElementById("profile_description").value.trim(),
    is_system: document.getElementById("profile_is_system").checked,
  };
}

function renderProfileRows() {
  profilesBody.innerHTML = "";
  if (!profiles.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="empty">Sin perfiles</td>';
    profilesBody.appendChild(tr);
    return;
  }
  for (const p of profiles) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.id}</td>
      <td>${p.code}</td>
      <td>${p.name}</td>
      <td>${p.description || "-"}</td>
      <td>${p.is_system ? "si" : "no"}</td>
      <td class="row-actions">
        <button class="mini-btn" data-action="edit-profile" data-id="${p.id}">Editar</button>
        <button class="mini-btn danger" data-action="delete-profile" data-id="${p.id}" ${p.is_system ? "disabled" : ""}>Eliminar</button>
      </td>
    `;
    profilesBody.appendChild(tr);
  }
}

function fillProfileSelect() {
  const prev = presetExecutionProfile.value;
  presetExecutionProfile.innerHTML = "";
  for (const p of profiles) {
    const opt = document.createElement("option");
    opt.value = String(p.id);
    opt.textContent = `${p.code} - ${p.name}`;
    presetExecutionProfile.appendChild(opt);
  }
  if (prev && profiles.some((p) => String(p.id) === prev)) {
    presetExecutionProfile.value = prev;
  } else {
    const swing = profiles.find((p) => String(p.code || "").toUpperCase() === "SWING");
    if (swing) {
      presetExecutionProfile.value = String(swing.id);
    }
  }
}

function setPresetForm(preset = null) {
  document.getElementById("preset_name").value = preset ? preset.name : "";
  document.getElementById("preset_mt5_terminal_path").value = preset ? preset.mt5_terminal_path : "";
  document.getElementById("preset_mt5_login").value = preset ? String(preset.mt5_login) : "";
  document.getElementById("preset_mt5_server").value = preset ? preset.mt5_server : "";
  document.getElementById("preset_total_volume").value = preset ? String(preset.total_volume) : "0.03";
  document.getElementById("preset_near_entry_pips_min").value = preset ? String(preset.near_entry_pips_min) : "1.0";
  document.getElementById("preset_near_entry_spread_mult").value = preset ? String(preset.near_entry_spread_mult) : "2.0";
  document.getElementById("preset_verify_order_after_send").checked = preset ? !!preset.verify_order_after_send : true;
  document.getElementById("preset_auto_close_on_mismatch").checked = preset ? !!preset.auto_close_on_mismatch : false;
  document.getElementById("preset_is_default").checked = preset ? !!preset.is_default : false;
  if (preset && Number.isFinite(Number(preset.execution_profile_id))) {
    presetExecutionProfile.value = String(preset.execution_profile_id);
  } else {
    fillProfileSelect();
  }
}

function presetPayload() {
  return {
    name: document.getElementById("preset_name").value.trim(),
    mt5_terminal_path: document.getElementById("preset_mt5_terminal_path").value.trim(),
    mt5_login: Number(document.getElementById("preset_mt5_login").value),
    mt5_server: document.getElementById("preset_mt5_server").value.trim(),
    execution_profile_id: Number(presetExecutionProfile.value),
    total_volume: Number(document.getElementById("preset_total_volume").value),
    near_entry_pips_min: Number(document.getElementById("preset_near_entry_pips_min").value),
    near_entry_spread_mult: Number(document.getElementById("preset_near_entry_spread_mult").value),
    verify_order_after_send: document.getElementById("preset_verify_order_after_send").checked,
    auto_close_on_mismatch: document.getElementById("preset_auto_close_on_mismatch").checked,
    is_default: document.getElementById("preset_is_default").checked,
  };
}

function renderPresetRows() {
  presetsBody.innerHTML = "";
  if (!presets.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="8" class="empty">Sin presets</td>';
    presetsBody.appendChild(tr);
    return;
  }
  for (const p of presets) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.id}</td>
      <td>${p.name}</td>
      <td>${p.execution_profile_code || "-"}</td>
      <td>${p.total_volume}</td>
      <td>${p.near_entry_pips_min}</td>
      <td>${p.near_entry_spread_mult}</td>
      <td>${p.is_default ? "si" : "no"}</td>
      <td class="row-actions">
        <button class="mini-btn" data-action="edit-preset" data-id="${p.id}">Editar</button>
        <button class="mini-btn danger" data-action="delete-preset" data-id="${p.id}">Eliminar</button>
      </td>
    `;
    presetsBody.appendChild(tr);
  }
}

function fillAssignmentSelects() {
  assignmentChannel.innerHTML = "";
  assignmentConfig.innerHTML = "";
  for (const c of channels) {
    const opt = document.createElement("option");
    opt.value = String(c.id);
    opt.textContent = `${c.name} (${c.chat_id})`;
    assignmentChannel.appendChild(opt);
  }
  for (const p of presets) {
    const opt = document.createElement("option");
    opt.value = String(p.id);
    opt.textContent = `${p.name} [${p.execution_profile_code || "-"}]`;
    assignmentConfig.appendChild(opt);
  }
}

function renderAssignmentRows() {
  assignmentsBody.innerHTML = "";
  if (!assignments.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="7" class="empty">Sin asignaciones</td>';
    assignmentsBody.appendChild(tr);
    return;
  }
  for (const a of assignments) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${a.id}</td>
      <td>${a.channel_name}</td>
      <td>${a.preset_name || a.config_name}</td>
      <td>${a.execution_profile_code || "-"}</td>
      <td>${a.mode}</td>
      <td>${a.is_active ? "si" : "no"}</td>
      <td class="row-actions">
        <button class="mini-btn" data-action="edit-assignment" data-id="${a.id}">Editar</button>
        <button class="mini-btn danger" data-action="delete-assignment" data-id="${a.id}">Eliminar</button>
      </td>
    `;
    assignmentsBody.appendChild(tr);
  }
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await readJson(res);
  if (data.db_path) {
    dbPath.textContent = `db: ${data.db_path}`;
  }
}

async function loadChannels() {
  if (channelsMsg) {
    channelsMsg.textContent = "Cargando canales...";
  }
  const res = await fetch("/api/channels");
  const data = await readJson(res);
  if (!res.ok) {
    const msg = data.detail || "Error canales";
    assignmentMsg.textContent = msg;
    if (channelsMsg) {
      channelsMsg.textContent = msg;
    }
    return;
  }
  channels = data.channels || [];
  renderChannelRows();
  fillAssignmentSelects();
  if (channelsMsg) {
    channelsMsg.textContent = `${channels.length} canal(es)`;
  }
}

async function saveChannel() {
  const id = document.getElementById("channel_id").value.trim();
  const payload = channelPayload();
  if (!payload.name || !payload.chat_id) {
    if (channelsMsg) {
      channelsMsg.textContent = "Nombre y chat ID son obligatorios";
    }
    return;
  }
  if (channelsMsg) {
    channelsMsg.textContent = id ? "Actualizando canal..." : "Creando canal...";
  }
  const endpoint = id ? `/api/channels/${id}` : "/api/channels";
  const method = id ? "PUT" : "POST";
  const res = await fetch(endpoint, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    if (channelsMsg) {
      channelsMsg.textContent = data.detail || "No se pudo guardar";
    }
    return;
  }
  channels = data.channels || [];
  renderChannelRows();
  fillAssignmentSelects();
  setChannelForm();
  if (channelsMsg) {
    channelsMsg.textContent = id ? "Canal actualizado" : "Canal creado";
  }
  showSavedToast(id ? "Canal actualizado correctamente" : "Canal creado correctamente");
}

async function deleteChannel(id) {
  if (!window.confirm("Seguro que quieres eliminar este canal?")) {
    return;
  }
  if (channelsMsg) {
    channelsMsg.textContent = "Eliminando canal...";
  }
  const res = await fetch(`/api/channels/${id}`, { method: "DELETE" });
  const data = await readJson(res);
  if (!res.ok) {
    if (channelsMsg) {
      channelsMsg.textContent = data.detail || "No se pudo eliminar";
    }
    return;
  }
  channels = data.channels || [];
  renderChannelRows();
  fillAssignmentSelects();
  setChannelForm();
  if (channelsMsg) {
    channelsMsg.textContent = "Canal eliminado";
  }
  showSavedToast("Canal eliminado correctamente");
}

async function loadProfiles() {
  profileMsg.textContent = "Cargando perfiles...";
  const res = await fetch("/api/execution-profiles");
  const data = await readJson(res);
  if (!res.ok) {
    profileMsg.textContent = data.detail || "Error perfiles";
    return;
  }
  profiles = data.profiles || [];
  renderProfileRows();
  fillProfileSelect();
  profileMsg.textContent = `${profiles.length} perfil(es)`;
}

async function createProfile() {
  const payload = profilePayload();
  if (!payload.code || !payload.name) {
    profileMsg.textContent = "Completa código y nombre";
    return;
  }
  const res = await fetch("/api/execution-profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    profileMsg.textContent = data.detail || "No se pudo crear";
    return;
  }
  profiles = data.profiles || [];
  renderProfileRows();
  fillProfileSelect();
  profileMsg.textContent = "Perfil creado";
  showSavedToast("Perfil guardado correctamente");
}

async function updateProfile() {
  if (!selectedProfileId) {
    profileMsg.textContent = "Selecciona un perfil";
    return;
  }
  const payload = profilePayload();
  const res = await fetch(`/api/execution-profiles/${selectedProfileId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    profileMsg.textContent = data.detail || "No se pudo actualizar";
    return;
  }
  profiles = data.profiles || [];
  renderProfileRows();
  fillProfileSelect();
  profileMsg.textContent = "Perfil actualizado";
  showSavedToast("Perfil actualizado correctamente");
}

async function deleteProfile(id) {
  if (!window.confirm("Seguro que quieres eliminar este canal/preset de operador?")) {
    return;
  }
  const res = await fetch(`/api/execution-profiles/${id}`, { method: "DELETE" });
  const data = await readJson(res);
  if (!res.ok) {
    profileMsg.textContent = data.detail || "No se pudo eliminar";
    return;
  }
  profiles = data.profiles || [];
  selectedProfileId = null;
  setProfileForm();
  renderProfileRows();
  fillProfileSelect();
  profileMsg.textContent = "Perfil eliminado";
  showSavedToast("Perfil eliminado correctamente");
}

async function loadPresets() {
  presetMsg.textContent = "Cargando presets...";
  const res = await fetch("/api/operator-presets");
  const data = await readJson(res);
  if (!res.ok) {
    presetMsg.textContent = data.detail || "Error presets";
    return;
  }
  presets = data.presets || [];
  renderPresetRows();
  fillAssignmentSelects();
  presetMsg.textContent = `${presets.length} preset(s)`;
}

async function createPreset() {
  const payload = presetPayload();
  if (!payload.name || !payload.mt5_terminal_path || !Number.isFinite(payload.mt5_login) || payload.mt5_login <= 0 || !payload.mt5_server || !Number.isFinite(payload.execution_profile_id) || payload.execution_profile_id <= 0) {
    presetMsg.textContent = "Completa nombre/path/login/server/perfil";
    return;
  }
  const res = await fetch("/api/operator-presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    presetMsg.textContent = data.detail || "No se pudo crear";
    return;
  }
  presets = data.presets || [];
  renderPresetRows();
  fillAssignmentSelects();
  presetMsg.textContent = "Preset creado";
  showSavedToast("Preset guardado correctamente");
}

async function updatePreset() {
  if (!selectedPresetId) {
    presetMsg.textContent = "Selecciona un preset";
    return;
  }
  const payload = presetPayload();
  const res = await fetch(`/api/operator-presets/${selectedPresetId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    presetMsg.textContent = data.detail || "No se pudo actualizar";
    return;
  }
  presets = data.presets || [];
  renderPresetRows();
  fillAssignmentSelects();
  presetMsg.textContent = "Preset actualizado";
  showSavedToast("Preset actualizado correctamente");
}

async function deletePreset(id) {
  if (!window.confirm("Seguro que quieres eliminar este canal/preset de operador?")) {
    return;
  }
  const res = await fetch(`/api/operator-presets/${id}`, { method: "DELETE" });
  const data = await readJson(res);
  if (!res.ok) {
    presetMsg.textContent = data.detail || "No se pudo eliminar";
    return;
  }
  presets = data.presets || [];
  selectedPresetId = null;
  setPresetForm();
  renderPresetRows();
  fillAssignmentSelects();
  await loadAssignments();
  presetMsg.textContent = "Preset eliminado";
  showSavedToast("Preset eliminado correctamente");
}

function assignmentPayload() {
  return {
    channel_id: Number(assignmentChannel.value),
    config_id: Number(assignmentConfig.value),
    mode: document.getElementById("assignment_mode").value,
    is_active: document.getElementById("assignment_is_active").checked,
  };
}

function findRealAssignmentForChannel(channelId, ignoreAssignmentId = null) {
  const cid = Number(channelId);
  const ignoreId = ignoreAssignmentId == null ? null : Number(ignoreAssignmentId);
  return assignments.find(
    (a) =>
      Number(a.channel_id) === cid &&
      String(a.mode).toLowerCase() === "real" &&
      (ignoreId == null || Number(a.id) !== ignoreId),
  );
}

function findPresetById(id) {
  const pid = Number(id);
  return presets.find((p) => Number(p.id) === pid) || null;
}

function presetIsSwing(id) {
  const p = findPresetById(id);
  return !!p && String(p.execution_profile_code || "").toUpperCase() === "SWING";
}

async function createAssignment() {
  const payload = assignmentPayload();
  if (!Number.isFinite(payload.channel_id) || !Number.isFinite(payload.config_id)) {
    assignmentMsg.textContent = "Selecciona canal y preset";
    return;
  }
  if (String(payload.mode).toLowerCase() === "real") {
    if (!presetIsSwing(payload.config_id)) {
      assignmentMsg.textContent = "Modo real solo permitido con presets de perfil SWING.";
      return;
    }
    const existing = findRealAssignmentForChannel(payload.channel_id);
    if (existing) {
      assignmentMsg.textContent = `No permitido: ya existe 1 modo real para este canal (#${existing.id}, ${existing.preset_name || existing.config_name}).`;
      return;
    }
  }
  const res = await fetch("/api/assignments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    assignmentMsg.textContent = data.detail || "No se pudo crear asignación";
    return;
  }
  assignments = data.assignments || [];
  renderAssignmentRows();
  assignmentMsg.textContent = "Asignación creada";
  showSavedToast("Asignación guardada correctamente");
}

async function updateAssignment() {
  if (!selectedAssignmentId) {
    assignmentMsg.textContent = "Selecciona una asignación";
    return;
  }
  const nextMode = document.getElementById("assignment_mode").value;
  const current = assignments.find((x) => x.id === selectedAssignmentId);
  if (!current) {
    assignmentMsg.textContent = "Asignación seleccionada no encontrada";
    return;
  }
  if (String(nextMode).toLowerCase() === "real") {
    if (!presetIsSwing(current.config_id)) {
      assignmentMsg.textContent = "Modo real solo permitido con presets de perfil SWING.";
      return;
    }
    const existing = findRealAssignmentForChannel(current.channel_id, selectedAssignmentId);
    if (existing) {
      assignmentMsg.textContent = `No permitido: ya existe 1 modo real para este canal (#${existing.id}, ${existing.preset_name || existing.config_name}).`;
      return;
    }
  }
  const payload = {
    mode: nextMode,
    is_active: document.getElementById("assignment_is_active").checked,
  };
  const res = await fetch(`/api/assignments/${selectedAssignmentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    assignmentMsg.textContent = data.detail || "No se pudo actualizar";
    return;
  }
  assignments = data.assignments || [];
  renderAssignmentRows();
  assignmentMsg.textContent = "Asignación actualizada";
  showSavedToast("Asignación actualizada correctamente");
}

async function deleteAssignment(id) {
  if (!window.confirm("Seguro que quieres eliminar este canal/preset de operador?")) {
    return;
  }
  const res = await fetch(`/api/assignments/${id}`, { method: "DELETE" });
  const data = await readJson(res);
  if (!res.ok) {
    assignmentMsg.textContent = data.detail || "No se pudo eliminar";
    return;
  }
  assignments = data.assignments || [];
  selectedAssignmentId = null;
  renderAssignmentRows();
  assignmentMsg.textContent = "Asignación eliminada";
  showSavedToast("Asignación eliminada correctamente");
}

async function loadAssignments() {
  assignmentMsg.textContent = "Cargando asignaciones...";
  const res = await fetch("/api/assignments");
  const data = await readJson(res);
  if (!res.ok) {
    assignmentMsg.textContent = data.detail || "Error asignaciones";
    return;
  }
  assignments = data.assignments || [];
  renderAssignmentRows();
  assignmentMsg.textContent = `${assignments.length} asignación(es)`;
}

async function seedCrossAssignments() {
  if (!window.confirm("Esto creará el cruce completo Canal x Preset y ajustará 1 real activo por canal. ¿Continuar?")) {
    return;
  }
  assignmentMsg.textContent = "Generando cruce Canal x Preset...";
  const res = await fetch("/api/assignments/seed-cross-product", { method: "POST" });
  const data = await readJson(res);
  if (!res.ok) {
    assignmentMsg.textContent = data.detail || "No se pudo generar el cruce";
    return;
  }
  assignments = data.assignments || [];
  renderAssignmentRows();
  const r = data.result || {};
  assignmentMsg.textContent = `Cruce generado: ${r.expected_pairs || 0} pares (creadas ${r.created || 0}, actualizadas ${r.updated || 0})`;
  showSavedToast("Cruce Canal x Preset guardado");
}

function renderChannelPresetSearchRows(items) {
  if (!cpSearchResults) {
    return;
  }
  cpSearchResults.innerHTML = "";
  const rows = items || [];
  if (!rows.length) {
    cpSearchResults.innerHTML = '<tr><td colspan="8" class="empty">Sin resultados</td></tr>';
    return;
  }
  for (const it of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.assignment_id}</td>
      <td>${it.channel_name}.${it.preset_name}</td>
      <td>${it.current_mode || "-"}</td>
      <td>${it.current_is_active ? "si" : "no"}</td>
      <td>${it.first_seen || "-"}</td>
      <td>${it.last_seen || "-"}</td>
      <td>${it.events_count || 0}</td>
      <td><a href="/canal-presets?id=${it.assignment_id}" target="_blank" rel="noopener">Abrir</a></td>
    `;
    cpSearchResults.appendChild(tr);
  }
}

function buildChannelPresetRegistryQuery() {
  const params = new URLSearchParams();
  const id = Number(cpSearchId ? cpSearchId.value : 0);
  if (Number.isFinite(id) && id > 0) {
    params.set("assignment_id", String(id));
  }
  const fromIso = toIsoForApi(cpSearchFrom ? cpSearchFrom.value : "", false);
  const toIso = toIsoForApi(cpSearchTo ? cpSearchTo.value : "", true);
  if (fromIso) {
    params.set("from_ts", fromIso);
  }
  if (toIso) {
    params.set("to_ts", toIso);
  }
  return params;
}

async function runChannelPresetSearch(openFirst = false) {
  if (!cpSearchMsg) {
    return;
  }
  cpSearchMsg.textContent = "Buscando...";
  const params = buildChannelPresetRegistryQuery();
  const res = await fetch(`/api/channel-presets/registry?${params.toString()}`);
  const data = await readJson(res);
  if (!res.ok) {
    cpSearchMsg.textContent = data.detail || "Error de búsqueda";
    return;
  }
  const items = data.items || [];
  renderChannelPresetSearchRows(items);
  cpSearchMsg.textContent = `${items.length} resultado(s)`;
  if (openFirst && items.length > 0) {
    const firstId = Number(items[0].assignment_id || 0);
    if (firstId > 0) {
      const detailParams = new URLSearchParams();
      detailParams.set("id", String(firstId));
      const fromIso = toIsoForApi(cpSearchFrom ? cpSearchFrom.value : "", false);
      const toIso = toIsoForApi(cpSearchTo ? cpSearchTo.value : "", true);
      if (fromIso) {
        detailParams.set("from_ts", fromIso);
      }
      if (toIso) {
        detailParams.set("to_ts", toIso);
      }
      window.open(`/canal-presets?${detailParams.toString()}`, "_blank");
    }
  }
}

function initActions() {
  const saveChannelBtn = document.getElementById("save-channel");
  const clearChannelBtn = document.getElementById("clear-channel");
  const refreshChannelsBtn = document.getElementById("refresh-channels");
  if (saveChannelBtn && clearChannelBtn && refreshChannelsBtn && channelsBody) {
    saveChannelBtn.addEventListener("click", saveChannel);
    clearChannelBtn.addEventListener("click", () => {
      setChannelForm();
      if (channelsMsg) {
        channelsMsg.textContent = "Formulario limpio";
      }
    });
    refreshChannelsBtn.addEventListener("click", loadChannels);

    channelsBody.addEventListener("click", async (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) {
        return;
      }
      const id = Number(btn.dataset.id);
      if (!id) {
        return;
      }
      if (btn.dataset.action === "delete-channel") {
        await deleteChannel(id);
        return;
      }
      if (btn.dataset.action === "edit-channel") {
        const channel = channels.find((c) => c.id === id);
        if (channel) {
          setChannelForm(channel);
          if (channelsMsg) {
            channelsMsg.textContent = `Editando canal #${id}`;
          }
        }
      }
    });
  }

  const cpSearchBtn = document.getElementById("cp-search-btn");
  const cpSearchClearBtn = document.getElementById("cp-search-clear");
  if (cpSearchBtn && cpSearchClearBtn) {
    cpSearchBtn.addEventListener("click", () => runChannelPresetSearch(true));
    cpSearchClearBtn.addEventListener("click", () => {
      if (cpSearchId) {
        cpSearchId.value = "";
      }
      if (cpSearchFrom) {
        cpSearchFrom.value = "";
      }
      if (cpSearchTo) {
        cpSearchTo.value = "";
      }
      runChannelPresetSearch(false);
    });
  }

  document.getElementById("profile-create").addEventListener("click", createProfile);
  document.getElementById("profile-update").addEventListener("click", updateProfile);
  document.getElementById("profile-delete").addEventListener("click", () => {
    if (!selectedProfileId) {
      profileMsg.textContent = "Selecciona un perfil";
      return;
    }
    deleteProfile(selectedProfileId);
  });
  document.getElementById("profile-refresh").addEventListener("click", loadProfiles);

  profilesBody.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) {
      return;
    }
    const id = Number(btn.dataset.id);
    if (!id) {
      return;
    }
    if (btn.dataset.action === "delete-profile") {
      deleteProfile(id);
      return;
    }
    if (btn.dataset.action === "edit-profile") {
      const profile = profiles.find((x) => x.id === id);
      if (profile) {
        selectedProfileId = id;
        setProfileForm(profile);
        profileMsg.textContent = `Editando perfil #${id}`;
      }
    }
  });

  document.getElementById("preset-create").addEventListener("click", createPreset);
  document.getElementById("preset-update").addEventListener("click", updatePreset);
  document.getElementById("preset-delete").addEventListener("click", () => {
    if (!selectedPresetId) {
      presetMsg.textContent = "Selecciona un preset";
      return;
    }
    deletePreset(selectedPresetId);
  });
  document.getElementById("preset-refresh").addEventListener("click", loadPresets);

  presetsBody.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) {
      return;
    }
    const id = Number(btn.dataset.id);
    if (!id) {
      return;
    }
    if (btn.dataset.action === "delete-preset") {
      deletePreset(id);
      return;
    }
    if (btn.dataset.action === "edit-preset") {
      const preset = presets.find((x) => x.id === id);
      if (preset) {
        selectedPresetId = id;
        setPresetForm(preset);
        presetMsg.textContent = `Editando preset #${id}`;
      }
    }
  });

  document.getElementById("assignment-create").addEventListener("click", createAssignment);
  document.getElementById("assignment-seed-cross").addEventListener("click", seedCrossAssignments);
  document.getElementById("assignment-update").addEventListener("click", updateAssignment);
  document.getElementById("assignment-delete").addEventListener("click", () => {
    if (!selectedAssignmentId) {
      assignmentMsg.textContent = "Selecciona una asignación";
      return;
    }
    deleteAssignment(selectedAssignmentId);
  });
  document.getElementById("assignment-refresh").addEventListener("click", loadAssignments);
  document.getElementById("assignment_mode").addEventListener("change", () => {
    const mode = document.getElementById("assignment_mode").value;
    if (String(mode).toLowerCase() === "real") {
      assignmentMsg.textContent = "Advertencia: solo se permite 1 asignación real por canal y debe ser preset SWING.";
    }
  });

  assignmentsBody.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) {
      return;
    }
    const id = Number(btn.dataset.id);
    if (!id) {
      return;
    }
    if (btn.dataset.action === "delete-assignment") {
      deleteAssignment(id);
      return;
    }
    if (btn.dataset.action === "edit-assignment") {
      const a = assignments.find((x) => x.id === id);
      if (a) {
        selectedAssignmentId = id;
        assignmentChannel.value = String(a.channel_id);
        assignmentConfig.value = String(a.config_id);
        document.getElementById("assignment_mode").value = a.mode;
        document.getElementById("assignment_is_active").checked = !!a.is_active;
        assignmentMsg.textContent = `Editando asignación #${id}`;
      }
    }
  });
}

async function init() {
  initActions();
  setChannelForm();
  await refreshStatus();
  await loadChannels();
  await loadProfiles();
  await loadPresets();
  await loadAssignments();
  await runChannelPresetSearch(false);
}

init();
