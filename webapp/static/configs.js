const dbPath = document.getElementById("db-path");
const globalStatus = document.getElementById("global-status");
const channelsMsg = document.getElementById("channels-msg");
const profileMsg = document.getElementById("profile-msg");
const presetMsg = document.getElementById("preset-msg");
const assignmentMsg = document.getElementById("assignment-msg");

const channelsBody = document.getElementById("channels-body");
const profilesBody = document.getElementById("profiles-body");
const presetsBody = document.getElementById("presets-body");
const assignmentsBody = document.getElementById("assignments-body");

const channelOpenCreateBtn = document.getElementById("channel-open-create");
const channelModal = document.getElementById("channel-modal");
const channelModalTitle = document.getElementById("channel-modal-title");
const channelModalSaveBtn = document.getElementById("channel-modal-save");
const channelModalCancelBtn = document.getElementById("channel-modal-cancel");
const channelSaveConfirmModal = document.getElementById("channel-save-confirm-modal");
const channelSaveConfirmTitle = document.getElementById("channel-save-confirm-title");
const channelSaveConfirmText = document.getElementById("channel-save-confirm-text");
const channelSaveConfirmAcceptBtn = document.getElementById("channel-save-confirm-accept");
const channelSaveConfirmCancelBtn = document.getElementById("channel-save-confirm-cancel");
const channelSuccessModal = document.getElementById("channel-success-modal");
const channelSuccessTitle = document.getElementById("channel-success-title");
const channelSuccessDetail = document.getElementById("channel-success-detail");
const channelSuccessTime = document.getElementById("channel-success-time");
const channelSuccessCloseBtn = document.getElementById("channel-success-close");
const channelDeleteModal = document.getElementById("channel-delete-modal");
const channelDeleteDetail = document.getElementById("channel-delete-detail");
const channelDeletePassword = document.getElementById("channel-delete-password");
const channelDeleteMsg = document.getElementById("channel-delete-msg");
const channelDeleteConfirmBtn = document.getElementById("channel-delete-confirm");
const channelDeleteCancelBtn = document.getElementById("channel-delete-cancel");

const profilesOpenModalBtn = document.getElementById("profiles-open-modal");
const profilesModal = document.getElementById("profiles-modal");
const profilesModalCloseBtn = document.getElementById("profiles-modal-close");

const presetExecutionProfile = document.getElementById("preset_execution_profile_id");
const presetOpenCreateBtn = document.getElementById("preset-open-create");
const presetRefreshBtn = document.getElementById("preset-refresh");
const presetModal = document.getElementById("preset-modal");
const presetModalTitle = document.getElementById("preset-modal-title");
const presetModalSaveBtn = document.getElementById("preset-modal-save");
const presetModalCancelBtn = document.getElementById("preset-modal-cancel");
const presetSaveConfirmModal = document.getElementById("preset-save-confirm-modal");
const presetSaveConfirmTitle = document.getElementById("preset-save-confirm-title");
const presetSaveConfirmText = document.getElementById("preset-save-confirm-text");
const presetSaveConfirmAcceptBtn = document.getElementById("preset-save-confirm-accept");
const presetSaveConfirmCancelBtn = document.getElementById("preset-save-confirm-cancel");
const presetSuccessModal = document.getElementById("preset-success-modal");
const presetSuccessDetail = document.getElementById("preset-success-detail");
const presetSuccessTime = document.getElementById("preset-success-time");
const presetSuccessCloseBtn = document.getElementById("preset-success-close");
const presetDeleteModal = document.getElementById("preset-delete-modal");
const presetDeleteDetail = document.getElementById("preset-delete-detail");
const presetDeletePassword = document.getElementById("preset-delete-password");
const presetDeleteMsg = document.getElementById("preset-delete-msg");
const presetDeleteConfirmBtn = document.getElementById("preset-delete-confirm");
const presetDeleteCancelBtn = document.getElementById("preset-delete-cancel");

let channels = [];
let profiles = [];
let presets = [];
let assignments = [];
let selectedProfileId = null;
let selectedPresetId = null;
let channelModalMode = "create";
let pendingChannelSaveMode = "";
let pendingDeleteChannelId = null;
let presetModalMode = "create";
let pendingPresetSaveMode = "";
let pendingDeletePresetId = null;

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

function nowLabel() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function fmtDateTime(value) {
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
    (!profilesModal || profilesModal.hidden) &&
    (!channelModal || channelModal.hidden) &&
    (!channelSaveConfirmModal || channelSaveConfirmModal.hidden) &&
    (!channelSuccessModal || channelSuccessModal.hidden) &&
    (!channelDeleteModal || channelDeleteModal.hidden) &&
    (!presetModal || presetModal.hidden) &&
    (!presetSaveConfirmModal || presetSaveConfirmModal.hidden) &&
    (!presetSuccessModal || presetSuccessModal.hidden) &&
    (!presetDeleteModal || presetDeleteModal.hidden)
  ) {
    document.body.classList.remove("modal-open");
  }
}

function isModalOpen(modal) {
  return !!modal && !modal.hidden;
}

function openProfilesModal() {
  openModal(profilesModal);
}

function closeProfilesModal() {
  closeModal(profilesModal);
}

function openChannelModal(mode = "create", channel = null) {
  channelModalMode = mode === "edit" ? "edit" : "create";
  if (channelModalMode === "edit" && channel) {
    setChannelForm(channel);
    if (channelModalTitle) {
      channelModalTitle.textContent = "Editar canal";
    }
    if (channelModalSaveBtn) {
      channelModalSaveBtn.textContent = "Actualizar canal";
    }
  } else {
    setChannelForm();
    if (channelModalTitle) {
      channelModalTitle.textContent = "Agregar canal";
    }
    if (channelModalSaveBtn) {
      channelModalSaveBtn.textContent = "Guardar canal";
    }
  }
  openModal(channelModal);
}

function closeChannelModal() {
  channelModalMode = "create";
  setChannelForm();
  if (channelModalTitle) {
    channelModalTitle.textContent = "Agregar canal";
  }
  if (channelModalSaveBtn) {
    channelModalSaveBtn.textContent = "Guardar canal";
  }
  closeModal(channelModal);
}

function openChannelSaveConfirmModal(mode = "edit") {
  pendingChannelSaveMode = mode === "create" ? "create" : "edit";
  if (channelSaveConfirmTitle) {
    channelSaveConfirmTitle.textContent = pendingChannelSaveMode === "edit"
      ? "Confirmar actualización de canal"
      : "Confirmar creación de canal";
  }
  if (channelSaveConfirmText) {
    channelSaveConfirmText.textContent = pendingChannelSaveMode === "edit"
      ? "¿Quieres guardar los cambios de este canal de Telegram?"
      : "¿Quieres guardar este nuevo canal de Telegram?";
  }
  openModal(channelSaveConfirmModal);
}

function closeChannelSaveConfirmModal() {
  pendingChannelSaveMode = "";
  closeModal(channelSaveConfirmModal);
}

function openChannelSuccessModal(detailText, action = "updated") {
  if (channelSuccessTitle) {
    channelSuccessTitle.textContent = action === "deleted"
      ? "Canal eliminado correctamente"
      : "Canal guardado correctamente";
  }
  if (channelSuccessDetail) {
    channelSuccessDetail.textContent = detailText || "Se actualizó el canal.";
  }
  if (channelSuccessTime) {
    channelSuccessTime.textContent = `Hora: ${nowLabel()}`;
  }
  openModal(channelSuccessModal);
}

function closeChannelSuccessModal() {
  closeModal(channelSuccessModal);
}

function openChannelDeleteModal(id) {
  const channel = channels.find((x) => Number(x.id) === Number(id));
  pendingDeleteChannelId = Number(id);
  if (channelDeleteDetail) {
    channelDeleteDetail.textContent = channel
      ? `Canal seleccionado: #${channel.id} ${channel.name} (${channel.chat_id})`
      : `Canal seleccionado: #${id}`;
  }
  if (channelDeletePassword) {
    channelDeletePassword.value = "";
  }
  if (channelDeleteMsg) {
    channelDeleteMsg.textContent = "Confirma tu contraseña para continuar.";
  }
  openModal(channelDeleteModal);
  if (channelDeletePassword) {
    setTimeout(() => {
      try {
        channelDeletePassword.focus();
      } catch {}
    }, 50);
  }
}

function closeChannelDeleteModal() {
  pendingDeleteChannelId = null;
  if (channelDeletePassword) {
    channelDeletePassword.value = "";
  }
  if (channelDeleteMsg) {
    channelDeleteMsg.textContent = "Confirma tu contraseña para continuar.";
  }
  closeModal(channelDeleteModal);
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

function summarizeChannelChanges(beforeChannel, afterChannel, action = "created") {
  if (action === "deleted") {
    if (beforeChannel) {
      return `Se eliminó canal #${beforeChannel.id} (${beforeChannel.name}) chat_id=${beforeChannel.chat_id}.`;
    }
    return "Se eliminó un canal de Telegram.";
  }
  if (action === "created") {
    return `Se agregó canal #${afterChannel.id} (${afterChannel.name}) chat_id=${afterChannel.chat_id}.`;
  }
  if (!beforeChannel || !afterChannel) {
    return "Se actualizó un canal.";
  }
  const changes = [];
  if (String(beforeChannel.name || "") !== String(afterChannel.name || "")) {
    changes.push(`nombre: "${beforeChannel.name}" -> "${afterChannel.name}"`);
  }
  if (String(beforeChannel.chat_id || "") !== String(afterChannel.chat_id || "")) {
    changes.push(`chat_id: ${beforeChannel.chat_id} -> ${afterChannel.chat_id}`);
  }
  if (String(beforeChannel.external_id || "") !== String(afterChannel.external_id || "")) {
    changes.push(`identificador: "${beforeChannel.external_id || "-"}" -> "${afterChannel.external_id || "-"}"`);
  }
  if (!!beforeChannel.is_active !== !!afterChannel.is_active) {
    changes.push(`activo: ${beforeChannel.is_active ? "si" : "no"} -> ${afterChannel.is_active ? "si" : "no"}`);
  }
  if (!changes.length) {
    return `Se actualizó canal #${afterChannel.id} (${afterChannel.name}) sin cambios visibles.`;
  }
  return `Se actualizó canal #${afterChannel.id} (${afterChannel.name}): ${changes.join("; ")}.`;
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

function openPresetModal(mode = "create", preset = null) {
  if (!presetModal) {
    return;
  }
  presetModalMode = mode === "edit" ? "edit" : "create";
  if (presetModalMode === "edit" && preset) {
    selectedPresetId = Number(preset.id);
    setPresetForm(preset);
    if (presetModalTitle) {
      presetModalTitle.textContent = "Editar preset";
    }
    if (presetModalSaveBtn) {
      presetModalSaveBtn.textContent = "Actualizar preset";
    }
  } else {
    selectedPresetId = null;
    setPresetForm();
    if (presetModalTitle) {
      presetModalTitle.textContent = "Agregar preset";
    }
    if (presetModalSaveBtn) {
      presetModalSaveBtn.textContent = "Guardar preset";
    }
  }
  openModal(presetModal);
}

function closePresetModal() {
  if (!presetModal) {
    return;
  }
  closeModal(presetModal);
  presetModalMode = "create";
  selectedPresetId = null;
  setPresetForm();
  if (presetModalTitle) {
    presetModalTitle.textContent = "Agregar preset";
  }
  if (presetModalSaveBtn) {
    presetModalSaveBtn.textContent = "Guardar preset";
  }
}

function openPresetSaveConfirmModal(mode = "create") {
  pendingPresetSaveMode = mode === "edit" ? "edit" : "create";
  if (presetSaveConfirmTitle) {
    presetSaveConfirmTitle.textContent = pendingPresetSaveMode === "edit" ? "Confirmar actualización" : "Confirmar guardado";
  }
  if (presetSaveConfirmText) {
    presetSaveConfirmText.textContent = pendingPresetSaveMode === "edit"
      ? "¿Quieres actualizar este preset del Operador?"
      : "¿Quieres guardar este nuevo preset del Operador?";
  }
  openModal(presetSaveConfirmModal);
}

function closePresetSaveConfirmModal() {
  pendingPresetSaveMode = "";
  closeModal(presetSaveConfirmModal);
}

function openPresetSuccessModal(detailText) {
  if (presetSuccessDetail) {
    presetSuccessDetail.textContent = detailText || "Se guardó la configuración.";
  }
  if (presetSuccessTime) {
    presetSuccessTime.textContent = `Hora: ${nowLabel()}`;
  }
  openModal(presetSuccessModal);
}

function closePresetSuccessModal() {
  closeModal(presetSuccessModal);
}

function openPresetDeleteModal(id) {
  const preset = presets.find((x) => Number(x.id) === Number(id));
  pendingDeletePresetId = Number(id);
  if (presetDeleteDetail) {
    presetDeleteDetail.textContent = preset
      ? `Preset seleccionado: #${preset.id} ${preset.name} (${preset.execution_profile_code || "-"})`
      : `Preset seleccionado: #${id}`;
  }
  if (presetDeletePassword) {
    presetDeletePassword.value = "";
  }
  if (presetDeleteMsg) {
    presetDeleteMsg.textContent = "Confirma tu contraseña para continuar.";
  }
  openModal(presetDeleteModal);
  if (presetDeletePassword) {
    setTimeout(() => {
      try {
        presetDeletePassword.focus();
      } catch {}
    }, 50);
  }
}

function closePresetDeleteModal() {
  pendingDeletePresetId = null;
  if (presetDeletePassword) {
    presetDeletePassword.value = "";
  }
  if (presetDeleteMsg) {
    presetDeleteMsg.textContent = "Confirma tu contraseña para continuar.";
  }
  closeModal(presetDeleteModal);
}

function summarizePresetChanges(beforePreset, afterPreset, action = "created") {
  if (!afterPreset) {
    return action === "updated" ? "Se actualizó un preset." : "Se agregó un preset.";
  }
  if (action !== "updated" || !beforePreset) {
    return `Se agregó preset #${afterPreset.id} (${afterPreset.name}) con perfil ${afterPreset.execution_profile_code || "-"}.`;
  }
  const changes = [];
  if (String(beforePreset.name || "") !== String(afterPreset.name || "")) {
    changes.push(`nombre: "${beforePreset.name}" -> "${afterPreset.name}"`);
  }
  if (Number(beforePreset.execution_profile_id || 0) !== Number(afterPreset.execution_profile_id || 0)) {
    changes.push(`perfil: ${beforePreset.execution_profile_code || "-"} -> ${afterPreset.execution_profile_code || "-"}`);
  }
  if (Number(beforePreset.total_volume || 0) !== Number(afterPreset.total_volume || 0)) {
    changes.push(`volumen: ${beforePreset.total_volume} -> ${afterPreset.total_volume}`);
  }
  if (Number(beforePreset.near_entry_pips_min || 0) !== Number(afterPreset.near_entry_pips_min || 0)) {
    changes.push(`near min: ${beforePreset.near_entry_pips_min} -> ${afterPreset.near_entry_pips_min}`);
  }
  if (Number(beforePreset.near_entry_spread_mult || 0) !== Number(afterPreset.near_entry_spread_mult || 0)) {
    changes.push(`near mult: ${beforePreset.near_entry_spread_mult} -> ${afterPreset.near_entry_spread_mult}`);
  }
  if (!!beforePreset.verify_order_after_send !== !!afterPreset.verify_order_after_send) {
    changes.push(`verificar orden: ${beforePreset.verify_order_after_send ? "si" : "no"} -> ${afterPreset.verify_order_after_send ? "si" : "no"}`);
  }
  if (!!beforePreset.auto_close_on_mismatch !== !!afterPreset.auto_close_on_mismatch) {
    changes.push(`auto mismatch: ${beforePreset.auto_close_on_mismatch ? "si" : "no"} -> ${afterPreset.auto_close_on_mismatch ? "si" : "no"}`);
  }
  if (!!beforePreset.is_default !== !!afterPreset.is_default) {
    changes.push(`default: ${beforePreset.is_default ? "si" : "no"} -> ${afterPreset.is_default ? "si" : "no"}`);
  }
  if (!changes.length) {
    return `Se actualizó preset #${afterPreset.id} (${afterPreset.name}) sin cambios visibles en campos principales.`;
  }
  return `Se actualizó preset #${afterPreset.id} (${afterPreset.name}): ${changes.join("; ")}.`;
}

async function verifyWebPassword(password) {
  const res = await fetch("/api/web-auth/verify-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: String(password || "") }),
  });
  const data = await readJson(res);
  if (!res.ok) {
    return { ok: false, error: data.detail || "Contraseña inválida" };
  }
  return { ok: !!data.valid };
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
  // La UI ya no tiene asignador manual, se mantiene no-op por compatibilidad.
}

function renderAssignmentRows() {
  assignmentsBody.innerHTML = "";
  if (!assignments.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="8" class="empty">Sin asignaciones</td>';
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
        <button class="mini-btn" data-action="details-assignment" data-id="${a.id}">Detalles</button>
      </td>
      <td>${fmtDateTime(a.created_at)}</td>
    `;
    assignmentsBody.appendChild(tr);
  }
}

function activeRealPreset(excludePresetId = null) {
  const excluded = excludePresetId == null ? null : Number(excludePresetId);
  return presets.find((p) => !!p.is_default && (excluded == null || Number(p.id) !== excluded)) || null;
}

function validateRealPresetSelection(payload, editingPresetId = null) {
  if (!payload || !payload.is_default) {
    return { ok: true };
  }
  const selectedProfile = profiles.find((p) => Number(p.id) === Number(payload.execution_profile_id));
  const selectedCode = String(selectedProfile?.code || "").toUpperCase();
  if (selectedCode && selectedCode !== "SWING") {
    return { ok: false, message: "El único preset real debe usar perfil SWING." };
  }
  const existingReal = activeRealPreset(editingPresetId);
  if (existingReal) {
    return {
      ok: false,
      message: `No se puede marcar otro preset como real. Ya existe #${existingReal.id} (${existingReal.name}).`,
    };
  }
  return { ok: true };
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await readJson(res);
  applyHeaderStatus(data);
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
  openChannelSaveConfirmModal(channelModalMode);
}

async function persistChannel() {
  const id = document.getElementById("channel_id").value.trim();
  const payload = channelPayload();
  if (!payload.name || !payload.chat_id) {
    if (channelsMsg) {
      channelsMsg.textContent = "Nombre y chat ID son obligatorios";
    }
    return { ok: false, error: "Datos incompletos" };
  }
  const before = id ? channels.find((c) => Number(c.id) === Number(id)) || null : null;
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
    return { ok: false, error: data.detail || "No se pudo guardar" };
  }
  channels = data.channels || [];
  renderChannelRows();
  fillAssignmentSelects();
  const created = !id ? channels.find((c) => c.chat_id === payload.chat_id && c.name === payload.name) || null : null;
  const updated = id ? channels.find((c) => Number(c.id) === Number(id)) || null : null;
  setChannelForm();
  if (channelsMsg) {
    channelsMsg.textContent = id ? "Canal actualizado" : "Canal creado";
  }
  showSavedToast(id ? "Canal actualizado correctamente" : "Canal creado correctamente");
  return {
    ok: true,
    action: id ? "updated" : "created",
    channel: id ? updated : created,
    detail: id
      ? summarizeChannelChanges(before, updated, "updated")
      : summarizeChannelChanges(null, created || { id: "-", name: payload.name, chat_id: payload.chat_id }, "created"),
  };
}

async function deleteChannel(id) {
  const before = channels.find((c) => Number(c.id) === Number(id)) || null;
  if (channelsMsg) {
    channelsMsg.textContent = "Eliminando canal...";
  }
  const res = await fetch(`/api/channels/${id}`, { method: "DELETE" });
  const data = await readJson(res);
  if (!res.ok) {
    if (channelsMsg) {
      channelsMsg.textContent = data.detail || "No se pudo eliminar";
    }
    return { ok: false, error: data.detail || "No se pudo eliminar" };
  }
  channels = data.channels || [];
  renderChannelRows();
  fillAssignmentSelects();
  setChannelForm();
  if (channelsMsg) {
    channelsMsg.textContent = "Canal eliminado";
  }
  showSavedToast("Canal eliminado correctamente");
  return {
    ok: true,
    action: "deleted",
    detail: summarizeChannelChanges(before, null, "deleted"),
  };
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
  const previousPresets = (presets || []).slice();
  const prevIds = new Set(previousPresets.map((x) => Number(x.id)));
  if (!payload.name || !payload.mt5_terminal_path || !Number.isFinite(payload.mt5_login) || payload.mt5_login <= 0 || !payload.mt5_server || !Number.isFinite(payload.execution_profile_id) || payload.execution_profile_id <= 0) {
    presetMsg.textContent = "Completa nombre/path/login/server/perfil";
    return { ok: false, error: "Datos incompletos" };
  }
  const realValidation = validateRealPresetSelection(payload, null);
  if (!realValidation.ok) {
    presetMsg.textContent = realValidation.message;
    return { ok: false, error: realValidation.message };
  }
  const res = await fetch("/api/operator-presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    presetMsg.textContent = data.detail || "No se pudo crear";
    return { ok: false, error: data.detail || "No se pudo crear" };
  }
  presets = data.presets || [];
  renderPresetRows();
  fillAssignmentSelects();
  const created = presets.find((p) => !prevIds.has(Number(p.id)))
    || presets.find((p) => String(p.name || "").trim() === payload.name);
  if (!created) {
    presetMsg.textContent = "Guardado parcial: no se pudo verificar el preset recién creado";
    return { ok: false, error: "No se pudo verificar el preset creado" };
  }
  presetMsg.textContent = "Preset creado";
  return {
    ok: true,
    action: "created",
    preset: created,
    detail: summarizePresetChanges(null, created, "created"),
  };
}

async function updatePreset() {
  if (!selectedPresetId) {
    presetMsg.textContent = "Selecciona un preset";
    return { ok: false, error: "Sin preset seleccionado" };
  }
  const before = presets.find((p) => Number(p.id) === Number(selectedPresetId)) || null;
  const payload = presetPayload();
  const realValidation = validateRealPresetSelection(payload, selectedPresetId);
  if (!realValidation.ok) {
    presetMsg.textContent = realValidation.message;
    return { ok: false, error: realValidation.message };
  }
  const res = await fetch(`/api/operator-presets/${selectedPresetId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok) {
    presetMsg.textContent = data.detail || "No se pudo actualizar";
    return { ok: false, error: data.detail || "No se pudo actualizar" };
  }
  presets = data.presets || [];
  renderPresetRows();
  fillAssignmentSelects();
  const updated = presets.find((p) => Number(p.id) === Number(selectedPresetId)) || null;
  if (!updated) {
    presetMsg.textContent = "Actualizado parcial: no se pudo verificar el preset";
    return { ok: false, error: "No se pudo verificar el preset actualizado" };
  }
  presetMsg.textContent = "Preset actualizado";
  return {
    ok: true,
    action: "updated",
    preset: updated,
    detail: summarizePresetChanges(before, updated, "updated"),
  };
}

async function deletePreset(id) {
  const before = presets.find((p) => Number(p.id) === Number(id)) || null;
  const res = await fetch(`/api/operator-presets/${id}`, { method: "DELETE" });
  const data = await readJson(res);
  if (!res.ok) {
    presetMsg.textContent = data.detail || "No se pudo eliminar";
    return { ok: false, error: data.detail || "No se pudo eliminar" };
  }
  presets = data.presets || [];
  selectedPresetId = null;
  setPresetForm();
  renderPresetRows();
  fillAssignmentSelects();
  await loadAssignments();
  presetMsg.textContent = "Preset eliminado";
  return {
    ok: true,
    action: "deleted",
    preset: before,
    detail: before
      ? `Se eliminó preset #${before.id} (${before.name}) con perfil ${before.execution_profile_code || "-"}.`
      : `Se eliminó preset #${id}.`,
  };
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

function openAssignmentDetails(assignmentId) {
  const id = Number(assignmentId || 0);
  if (id <= 0) {
    return;
  }
  window.open(`/canal-presets?id=${id}`, "_blank");
}

function initActions() {
  const refreshChannelsBtn = document.getElementById("refresh-channels");
  if (channelSaveConfirmAcceptBtn) {
    channelSaveConfirmAcceptBtn.addEventListener("click", async () => {
      const result = await persistChannel();
      closeChannelSaveConfirmModal();
      if (!result || !result.ok) {
        return;
      }
      closeChannelModal();
      openChannelSuccessModal(result.detail, result.action);
    });
  }
  if (channelSaveConfirmCancelBtn) {
    channelSaveConfirmCancelBtn.addEventListener("click", () => {
      closeChannelSaveConfirmModal();
    });
  }
  if (channelSuccessCloseBtn) {
    channelSuccessCloseBtn.addEventListener("click", () => {
      closeChannelSuccessModal();
    });
  }
  if (channelDeleteCancelBtn) {
    channelDeleteCancelBtn.addEventListener("click", () => {
      closeChannelDeleteModal();
    });
  }
  if (channelDeleteConfirmBtn) {
    channelDeleteConfirmBtn.addEventListener("click", async () => {
      const id = Number(pendingDeleteChannelId || 0);
      if (id <= 0) {
        if (channelDeleteMsg) {
          channelDeleteMsg.textContent = "Canal inválido para eliminar.";
        }
        return;
      }
      const pwd = channelDeletePassword ? String(channelDeletePassword.value || "").trim() : "";
      if (!pwd) {
        if (channelDeleteMsg) {
          channelDeleteMsg.textContent = "Ingresa la contraseña para confirmar.";
        }
        return;
      }
      if (channelDeleteMsg) {
        channelDeleteMsg.textContent = "Verificando contraseña...";
      }
      const authCheck = await verifyWebPassword(pwd);
      if (!authCheck.ok) {
        if (channelDeleteMsg) {
          channelDeleteMsg.textContent = authCheck.error || "Contraseña incorrecta";
        }
        return;
      }
      if (channelDeleteMsg) {
        channelDeleteMsg.textContent = "Eliminando canal...";
      }
      const result = await deleteChannel(id);
      if (!result || !result.ok) {
        if (channelDeleteMsg) {
          channelDeleteMsg.textContent = result?.error || "No se pudo eliminar";
        }
        return;
      }
      closeChannelDeleteModal();
      openChannelSuccessModal(result.detail, "deleted");
    });
  }
  if (channelSaveConfirmModal) {
    channelSaveConfirmModal.addEventListener("click", (event) => {
      if (event.target === channelSaveConfirmModal) {
        closeChannelSaveConfirmModal();
      }
    });
  }
  if (channelSuccessModal) {
    channelSuccessModal.addEventListener("click", (event) => {
      if (event.target === channelSuccessModal) {
        closeChannelSuccessModal();
      }
    });
  }
  if (channelDeleteModal) {
    channelDeleteModal.addEventListener("click", (event) => {
      if (event.target === channelDeleteModal) {
        closeChannelDeleteModal();
      }
    });
  }

  if (profilesOpenModalBtn) {
    profilesOpenModalBtn.addEventListener("click", async () => {
      openProfilesModal();
      await loadProfiles();
    });
  }
  if (profilesModalCloseBtn) {
    profilesModalCloseBtn.addEventListener("click", () => {
      closeProfilesModal();
    });
  }
  if (profilesModal) {
    profilesModal.addEventListener("click", (event) => {
      if (event.target === profilesModal) {
        closeProfilesModal();
      }
    });
  }

  if (channelOpenCreateBtn) {
    channelOpenCreateBtn.addEventListener("click", () => {
      openChannelModal("create");
    });
  }
  if (channelModalSaveBtn) {
    channelModalSaveBtn.addEventListener("click", saveChannel);
  }
  if (channelModalCancelBtn) {
    channelModalCancelBtn.addEventListener("click", () => {
      closeChannelModal();
    });
  }
  if (channelModal) {
    channelModal.addEventListener("click", (event) => {
      if (event.target === channelModal) {
        closeChannelModal();
      }
    });
  }
  if (refreshChannelsBtn) {
    refreshChannelsBtn.addEventListener("click", loadChannels);
  }
  if (channelsBody) {
    channelsBody.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) {
        return;
      }
      const id = Number(btn.dataset.id);
      if (!id) {
        return;
      }
      if (btn.dataset.action === "delete-channel") {
        openChannelDeleteModal(id);
        return;
      }
      if (btn.dataset.action === "edit-channel") {
        const channel = channels.find((c) => Number(c.id) === id);
        if (channel) {
          openChannelModal("edit", channel);
          if (channelsMsg) {
            channelsMsg.textContent = `Editando canal #${id}`;
          }
        }
      }
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

  if (presetOpenCreateBtn) {
    presetOpenCreateBtn.addEventListener("click", () => {
      openPresetModal("create");
    });
  }
  if (presetRefreshBtn) {
    presetRefreshBtn.addEventListener("click", loadPresets);
  }
  if (presetModalSaveBtn) {
    presetModalSaveBtn.addEventListener("click", () => {
      openPresetSaveConfirmModal(presetModalMode);
    });
  }
  if (presetModalCancelBtn) {
    presetModalCancelBtn.addEventListener("click", () => {
      closePresetModal();
    });
  }
  if (presetSaveConfirmAcceptBtn) {
    presetSaveConfirmAcceptBtn.addEventListener("click", async () => {
      const result = pendingPresetSaveMode === "edit" ? await updatePreset() : await createPreset();
      closePresetSaveConfirmModal();
      if (!result || !result.ok) {
        return;
      }
      closePresetModal();
      openPresetSuccessModal(result.detail);
    });
  }
  if (presetSaveConfirmCancelBtn) {
    presetSaveConfirmCancelBtn.addEventListener("click", () => {
      closePresetSaveConfirmModal();
    });
  }
  if (presetSuccessCloseBtn) {
    presetSuccessCloseBtn.addEventListener("click", () => {
      closePresetSuccessModal();
    });
  }
  if (presetDeleteCancelBtn) {
    presetDeleteCancelBtn.addEventListener("click", () => {
      closePresetDeleteModal();
    });
  }
  if (presetDeleteConfirmBtn) {
    presetDeleteConfirmBtn.addEventListener("click", async () => {
      const id = Number(pendingDeletePresetId || 0);
      if (id <= 0) {
        if (presetDeleteMsg) {
          presetDeleteMsg.textContent = "Preset inválido para eliminar.";
        }
        return;
      }
      const pwd = presetDeletePassword ? String(presetDeletePassword.value || "").trim() : "";
      if (!pwd) {
        if (presetDeleteMsg) {
          presetDeleteMsg.textContent = "Ingresa la contraseña para confirmar.";
        }
        return;
      }
      if (presetDeleteMsg) {
        presetDeleteMsg.textContent = "Verificando contraseña...";
      }
      const authCheck = await verifyWebPassword(pwd);
      if (!authCheck.ok) {
        if (presetDeleteMsg) {
          presetDeleteMsg.textContent = authCheck.error || "Contraseña incorrecta";
        }
        return;
      }
      if (presetDeleteMsg) {
        presetDeleteMsg.textContent = "Eliminando preset...";
      }
      const result = await deletePreset(id);
      if (!result || !result.ok) {
        if (presetDeleteMsg) {
          presetDeleteMsg.textContent = result?.error || "No se pudo eliminar";
        }
        return;
      }
      closePresetDeleteModal();
      openPresetSuccessModal(result.detail);
    });
  }
  if (presetModal) {
    presetModal.addEventListener("click", (event) => {
      if (event.target === presetModal) {
        closePresetModal();
      }
    });
  }
  if (presetSaveConfirmModal) {
    presetSaveConfirmModal.addEventListener("click", (event) => {
      if (event.target === presetSaveConfirmModal) {
        closePresetSaveConfirmModal();
      }
    });
  }
  if (presetSuccessModal) {
    presetSuccessModal.addEventListener("click", (event) => {
      if (event.target === presetSuccessModal) {
        closePresetSuccessModal();
      }
    });
  }
  if (presetDeleteModal) {
    presetDeleteModal.addEventListener("click", (event) => {
      if (event.target === presetDeleteModal) {
        closePresetDeleteModal();
      }
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (isModalOpen(profilesModal)) {
      closeProfilesModal();
      return;
    }
    if (isModalOpen(channelDeleteModal)) {
      closeChannelDeleteModal();
      return;
    }
    if (isModalOpen(channelSuccessModal)) {
      closeChannelSuccessModal();
      return;
    }
    if (isModalOpen(channelSaveConfirmModal)) {
      closeChannelSaveConfirmModal();
      return;
    }
    if (isModalOpen(channelModal)) {
      closeChannelModal();
      return;
    }
    if (isModalOpen(presetDeleteModal)) {
      closePresetDeleteModal();
      return;
    }
    if (isModalOpen(presetSuccessModal)) {
      closePresetSuccessModal();
      return;
    }
    if (isModalOpen(presetSaveConfirmModal)) {
      closePresetSaveConfirmModal();
      return;
    }
    if (isModalOpen(presetModal)) {
      closePresetModal();
    }
  });

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
      openPresetDeleteModal(id);
      return;
    }
    if (btn.dataset.action === "edit-preset") {
      const preset = presets.find((x) => x.id === id);
      if (preset) {
        openPresetModal("edit", preset);
        presetMsg.textContent = `Editando preset #${id}`;
      }
    }
  });

  const assignmentRefreshBtn = document.getElementById("assignment-refresh");
  if (assignmentRefreshBtn) {
    assignmentRefreshBtn.addEventListener("click", loadAssignments);
  }

  assignmentsBody.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) {
      return;
    }
    const id = Number(btn.dataset.id);
    if (!id) {
      return;
    }
    if (btn.dataset.action === "details-assignment") {
      openAssignmentDetails(id);
    }
  });

  const presetIsDefaultInput = document.getElementById("preset_is_default");
  if (presetIsDefaultInput) {
    presetIsDefaultInput.addEventListener("change", () => {
      if (!presetIsDefaultInput.checked) {
        return;
      }
      const validation = validateRealPresetSelection(
        {
          execution_profile_id: Number(presetExecutionProfile.value),
          is_default: true,
        },
        presetModalMode === "edit" ? selectedPresetId : null,
      );
      if (!validation.ok) {
        presetIsDefaultInput.checked = false;
        presetMsg.textContent = validation.message;
      }
    });
  }
}

async function init() {
  initActions();
  setChannelForm();
  await refreshStatus();
  await loadChannels();
  await loadProfiles();
  await loadPresets();
  await loadAssignments();
}

init();
