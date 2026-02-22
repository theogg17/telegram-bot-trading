(function () {
  const STACK_ID = "toast-stack";
  const DATETIME_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/;
  const TIMESTAMP_TEXT_RE = /(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)/g;
  const WEB_AUTH_ME_PATH = "/api/web-auth/me";
  const WEB_AUTH_LOGIN_PATH = "/api/web-auth/login";
  const WEB_AUTH_LOGOUT_PATH = "/api/web-auth/logout";

  let datePickerEnhancerHandle = null;
  let globalHeaderStatusPollHandle = null;
  let tableTimestampObserver = null;
  const nativeFetch = typeof window.fetch === "function" ? window.fetch.bind(window) : null;
  let webAuthReady = false;
  let webAuthReadyResolver = null;
  const webAuthReadyPromise = new Promise((resolve) => {
    webAuthReadyResolver = resolve;
  });

  function ensureStack() {
    let stack = document.getElementById(STACK_ID);
    if (!stack) {
      stack = document.createElement("div");
      stack.id = STACK_ID;
      stack.className = "toast-stack";
      document.body.appendChild(stack);
    }
    return stack;
  }

  function showToast(message, type = "success", durationMs = 4000) {
    const stack = ensureStack();
    const toast = document.createElement("div");
    toast.className = `toast toast-${String(type || "success")}`;
    toast.textContent = String(message || "Guardado");
    stack.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => {
        if (toast.parentElement) {
          toast.parentElement.removeChild(toast);
        }
      }, 220);
    }, Math.max(800, Number(durationMs) || 4000));
  }

  function showSavedToast(message = "Configuración guardada correctamente") {
    showToast(message, "success", 4000);
  }

  function pad2(n) {
    return String(Number(n) || 0).padStart(2, "0");
  }

  function toLocalIso(dateObj) {
    if (!(dateObj instanceof Date) || Number.isNaN(dateObj.getTime())) {
      return "";
    }
    return `${dateObj.getFullYear()}-${pad2(dateObj.getMonth() + 1)}-${pad2(dateObj.getDate())}T${pad2(dateObj.getHours())}:${pad2(dateObj.getMinutes())}:${pad2(dateObj.getSeconds())}`;
  }

  function parseDateTimeLocal(rawValue) {
    const raw = String(rawValue || "").trim();
    if (!raw) {
      return null;
    }
    const match = DATETIME_RE.exec(raw);
    if (!match) {
      return null;
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const hour = Number(match[4]);
    const minute = Number(match[5]);
    const hasSeconds = typeof match[6] === "string";
    const second = hasSeconds ? Number(match[6]) : 0;
    if (
      !Number.isFinite(year) ||
      !Number.isFinite(month) ||
      !Number.isFinite(day) ||
      !Number.isFinite(hour) ||
      !Number.isFinite(minute) ||
      !Number.isFinite(second) ||
      month < 1 ||
      month > 12 ||
      day < 1 ||
      day > 31 ||
      hour < 0 ||
      hour > 23 ||
      minute < 0 ||
      minute > 59 ||
      second < 0 ||
      second > 59
    ) {
      return null;
    }
    const check = new Date(year, month - 1, day, hour, minute, second, 0);
    if (
      Number.isNaN(check.getTime()) ||
      check.getFullYear() !== year ||
      check.getMonth() + 1 !== month ||
      check.getDate() !== day
    ) {
      return null;
    }
    return {
      year,
      month,
      day,
      hour,
      minute,
      second,
      hasSeconds,
      dateObj: check,
    };
  }

  function parseDateValue(value) {
    if (value instanceof Date) {
      return Number.isNaN(value.getTime()) ? null : value;
    }
    if (Number.isFinite(Number(value)) && typeof value !== "string") {
      const n = Number(value);
      const ms = Math.abs(n) < 1000000000000 ? n * 1000 : n;
      const d = new Date(ms);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const raw = String(value || "").trim();
    if (!raw) {
      return null;
    }
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?(?:\.(\d{1,3}))?(Z|[+-]\d{2}:?\d{2})?$/.exec(raw);
    if (m) {
      const year = Number(m[1]);
      const month = Number(m[2]);
      const day = Number(m[3]);
      const hour = Number(m[4] || 0);
      const minute = Number(m[5] || 0);
      const second = Number(m[6] || 0);
      const ms = Number(String(m[7] || "0").padEnd(3, "0"));
      const zone = String(m[8] || "");
      if (zone) {
        const zoneNorm =
          zone === "Z"
            ? "Z"
            : zone.includes(":")
              ? zone
              : `${zone.slice(0, 3)}:${zone.slice(3)}`;
        const iso = `${year}-${pad2(month)}-${pad2(day)}T${pad2(hour)}:${pad2(minute)}:${pad2(second)}.${String(ms).padStart(3, "0")}${zoneNorm}`;
        const dZone = new Date(iso);
        if (!Number.isNaN(dZone.getTime())) {
          return dZone;
        }
      } else {
        const dLocal = new Date(year, month - 1, day, hour, minute, second, ms);
        if (
          !Number.isNaN(dLocal.getTime()) &&
          dLocal.getFullYear() === year &&
          dLocal.getMonth() + 1 === month &&
          dLocal.getDate() === day
        ) {
          return dLocal;
        }
      }
    }
    const normalized = raw.includes(" ") && !raw.includes("T") ? raw.replace(" ", "T") : raw;
    const d = new Date(normalized);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function normalizeForApi(localValue, isEnd = false) {
    const raw = String(localValue || "").trim();
    if (!raw) {
      return "";
    }
    if (/\b(am|pm)\b/i.test(raw)) {
      return "";
    }
    const parsed = parseDateTimeLocal(raw);
    if (parsed) {
      const second = isEnd && !parsed.hasSeconds ? 59 : parsed.second;
      return `${parsed.year}-${pad2(parsed.month)}-${pad2(parsed.day)}T${pad2(parsed.hour)}:${pad2(parsed.minute)}:${pad2(second)}`;
    }
    const fallback = new Date(raw);
    if (Number.isNaN(fallback.getTime())) {
      return "";
    }
    if (isEnd) {
      fallback.setSeconds(59, 999);
    }
    return toLocalIso(fallback);
  }

  function formatDisplayDateTime(value) {
    if (!value) {
      return "-";
    }
    const d = parseDateValue(value);
    if (!d) {
      return String(value);
    }
    return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }

  function formatTableTimestamps(root = document) {
    const cells = root.querySelectorAll("table td, table th");
    for (const cell of cells) {
      if (!(cell instanceof HTMLElement)) {
        continue;
      }
      if (cell.childElementCount > 0) {
        continue;
      }
      const raw = String(cell.textContent || "").trim();
      if (!raw) {
        continue;
      }
      const replaced = raw.replace(TIMESTAMP_TEXT_RE, (match) => {
        const fmt = formatDisplayDateTime(match);
        return fmt === "-" ? match : fmt;
      });
      if (replaced !== raw) {
        cell.textContent = replaced;
      }
    }
  }

  function startAutoTableTimestampFormatting() {
    formatTableTimestamps(document);
    if (tableTimestampObserver != null || !document.body) {
      return;
    }
    let rafId = 0;
    const schedule = () => {
      if (rafId) {
        return;
      }
      rafId = window.requestAnimationFrame(() => {
        rafId = 0;
        formatTableTimestamps(document);
      });
    };
    tableTimestampObserver = new MutationObserver(schedule);
    tableTimestampObserver.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  function enhanceSimpleDatePickers(root = document) {
    const inputs = root.querySelectorAll("input[type='datetime-local']");
    for (const input of inputs) {
      if (!(input instanceof HTMLInputElement)) {
        continue;
      }
      input.classList.add("dp-simple-hidden");
      input.removeAttribute("aria-hidden");
      input.dataset.dpSimpleMounted = "1";
    }
  }

  function enforce24hInputs(root = document) {
    const inputs = root.querySelectorAll("input[type='datetime-local'], input[type='time']");
    for (const input of inputs) {
      input.setAttribute("lang", "en-GB");
      if (input.type === "datetime-local" && !input.getAttribute("step")) {
        input.setAttribute("step", "1");
      }
      if (!input.title) {
        input.title = "Formato 24h (HH:mm)";
      }
      const validateValue = () => {
        const value = String(input.value || "");
        if (/\b(am|pm)\b/i.test(value)) {
          input.setCustomValidity("Usa formato de 24 horas (HH:mm)");
        } else {
          input.setCustomValidity("");
        }
      };
      input.addEventListener("input", validateValue);
      input.addEventListener("blur", validateValue);
      validateValue();
    }
  }

  function startSimpleDatePickerEnhancer(intervalMs = 1200) {
    enhanceSimpleDatePickers(document);
    if (datePickerEnhancerHandle != null) {
      return;
    }
    datePickerEnhancerHandle = window.setInterval(() => enhanceSimpleDatePickers(document), intervalMs);
  }

  function resolveWebAuthReady() {
    if (webAuthReady) {
      return;
    }
    webAuthReady = true;
    if (typeof webAuthReadyResolver === "function") {
      webAuthReadyResolver();
    }
  }

  function extractFetchPathname(input) {
    let rawUrl = "";
    if (typeof input === "string") {
      rawUrl = input;
    } else if (input && typeof input.url === "string") {
      rawUrl = input.url;
    }
    if (!rawUrl) {
      return "";
    }
    try {
      return new URL(rawUrl, window.location.origin).pathname || "";
    } catch {
      return "";
    }
  }

  function isProtectedApiPath(pathname) {
    const path = String(pathname || "");
    if (!path.startsWith("/api/")) {
      return false;
    }
    if (path === WEB_AUTH_ME_PATH || path === WEB_AUTH_LOGIN_PATH || path === WEB_AUTH_LOGOUT_PATH) {
      return false;
    }
    return true;
  }

  function installWebAuthFetchGate() {
    if (!nativeFetch || typeof window.fetch !== "function") {
      resolveWebAuthReady();
      return;
    }
    if (window.fetch.__webAuthGateInstalled) {
      return;
    }
    const gatedFetch = async (input, init) => {
      const pathname = extractFetchPathname(input);
      if (isProtectedApiPath(pathname)) {
        await webAuthReadyPromise;
      }
      return nativeFetch(input, init);
    };
    gatedFetch.__webAuthGateInstalled = true;
    window.fetch = gatedFetch;
  }

  function ensureHeaderUserMeta() {
    const statusWrap = document.querySelector(".status-wrap");
    if (!statusWrap) {
      return null;
    }
    let userNode = document.getElementById("session-user");
    if (!userNode) {
      userNode = document.createElement("span");
      userNode.id = "session-user";
      userNode.className = "meta";
      userNode.textContent = "user: --";
      const dbPath = document.getElementById("db-path");
      if (dbPath && dbPath.parentElement === statusWrap) {
        statusWrap.insertBefore(userNode, dbPath);
      } else {
        statusWrap.appendChild(userNode);
      }
    }
    return userNode;
  }

  function setHeaderUser(username) {
    const userNode = ensureHeaderUserMeta();
    if (!userNode) {
      return;
    }
    const cleanUser = String(username || "").trim();
    userNode.textContent = `user: ${cleanUser || "--"}`;
  }

  function ensureWebAuthModal() {
    let overlay = document.getElementById("web-auth-overlay");
    if (overlay) {
      return overlay;
    }
    overlay = document.createElement("div");
    overlay.id = "web-auth-overlay";
    overlay.className = "modal-overlay hidden web-auth-overlay";
    overlay.innerHTML = `
      <div class="panel modal-panel modal-panel-mini web-auth-panel">
        <header class="panel-header">
          <div>
            <h2>Acceso web</h2>
            <p>Ingresa usuario y contraseña para continuar.</p>
          </div>
        </header>
        <form id="web-auth-form" class="form-grid" autocomplete="on">
          <label>
            Usuario
            <input id="web-auth-username" type="text" autocomplete="username" required />
          </label>
          <label>
            Contraseña
            <input id="web-auth-password" type="password" autocomplete="current-password" required />
          </label>
          <p id="web-auth-error" class="hint-inline web-auth-error"></p>
          <div class="actions web-auth-actions">
            <button class="btn primary" id="web-auth-submit" type="submit">Ingresar</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(overlay);
    const form = overlay.querySelector("#web-auth-form");
    if (form) {
      form.addEventListener("submit", onWebAuthSubmit);
    }
    return overlay;
  }

  function showWebAuthModal(message = "") {
    const overlay = ensureWebAuthModal();
    if (!overlay) {
      return;
    }
    const userInput = overlay.querySelector("#web-auth-username");
    const passInput = overlay.querySelector("#web-auth-password");
    const errorNode = overlay.querySelector("#web-auth-error");
    if (errorNode) {
      errorNode.textContent = String(message || "");
    }
    if (userInput && !String(userInput.value || "").trim()) {
      userInput.value = "admin";
    }
    if (passInput) {
      passInput.value = "";
    }
    overlay.classList.remove("hidden");
    document.body.classList.add("modal-open");
    if (passInput) {
      window.setTimeout(() => passInput.focus(), 40);
    }
  }

  function hideWebAuthModal() {
    const overlay = document.getElementById("web-auth-overlay");
    if (!overlay) {
      return;
    }
    overlay.classList.add("hidden");
    document.body.classList.remove("modal-open");
  }

  async function onWebAuthSubmit(event) {
    event.preventDefault();
    if (!nativeFetch) {
      resolveWebAuthReady();
      hideWebAuthModal();
      return;
    }
    const overlay = ensureWebAuthModal();
    const userInput = overlay.querySelector("#web-auth-username");
    const passInput = overlay.querySelector("#web-auth-password");
    const errorNode = overlay.querySelector("#web-auth-error");
    const submitBtn = overlay.querySelector("#web-auth-submit");

    const username = String(userInput?.value || "").trim();
    const password = String(passInput?.value || "");
    if (errorNode) {
      errorNode.textContent = "";
    }
    if (!username || !password) {
      if (errorNode) {
        errorNode.textContent = "Completa usuario y contraseña";
      }
      return;
    }
    if (submitBtn) {
      submitBtn.disabled = true;
    }
    try {
      const res = await nativeFetch(WEB_AUTH_LOGIN_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data?.authenticated) {
        const detail = String(data?.detail || "Usuario o contraseña incorrectos");
        throw new Error(detail);
      }
      setHeaderUser(data.username || username);
      hideWebAuthModal();
      resolveWebAuthReady();
    } catch (err) {
      if (errorNode) {
        errorNode.textContent = String(err?.message || "No se pudo iniciar sesión");
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
      }
    }
  }

  async function initializeWebAuthSession() {
    ensureHeaderUserMeta();
    if (!nativeFetch) {
      setHeaderUser("admin");
      resolveWebAuthReady();
      return;
    }
    try {
      const res = await nativeFetch(WEB_AUTH_ME_PATH);
      const data = await res.json().catch(() => ({}));
      if (res.ok && data?.authenticated) {
        setHeaderUser(data.username || "admin");
        hideWebAuthModal();
        resolveWebAuthReady();
        return;
      }
    } catch {}
    setHeaderUser("");
    showWebAuthModal("");
  }

  function setupLogoutButton() {
    const btn = document.getElementById("logout-btn");
    if (!btn || btn.dataset.logoutReady === "1") {
      return;
    }
    btn.dataset.logoutReady = "1";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        if (nativeFetch) {
          await nativeFetch(WEB_AUTH_LOGOUT_PATH, { method: "POST" });
        }
      } catch {
        // incluso si falla, forzamos volver a inicio para pedir login
      }
      window.location.href = "/";
    });
  }

  function isAnyServiceRunning(statusData) {
    return !!(statusData?.lector?.running || statusData?.operador?.running);
  }

  function applyGlobalHeaderStatus(statusData = null) {
    const globalStatus = document.getElementById("global-status");
    if (!globalStatus) {
      return;
    }
    const online = isAnyServiceRunning(statusData);
    globalStatus.textContent = online ? "ONLINE" : "OFFLINE";
    globalStatus.classList.toggle("online", online);
    const dbPath = document.getElementById("db-path");
    if (dbPath && statusData?.db_path) {
      dbPath.textContent = `db: ${statusData.db_path}`;
    }
  }

  async function refreshGlobalHeaderStatus() {
    if (!document.getElementById("global-status")) {
      return null;
    }
    try {
      const res = await fetch("/api/status");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error("status_fetch_failed");
      }
      applyGlobalHeaderStatus(data);
      return data;
    } catch {
      applyGlobalHeaderStatus(null);
      return null;
    }
  }

  function startGlobalHeaderStatusPolling(intervalMs = 1000) {
    if (!document.getElementById("global-status")) {
      return;
    }
    if (document.body?.classList.contains("control-page")) {
      return;
    }
    refreshGlobalHeaderStatus();
    if (globalHeaderStatusPollHandle != null) {
      return;
    }
    globalHeaderStatusPollHandle = window.setInterval(refreshGlobalHeaderStatus, intervalMs);
  }

  installWebAuthFetchGate();

  window.showToast = showToast;
  window.showSavedToast = showSavedToast;
  window.applyGlobalHeaderStatus = applyGlobalHeaderStatus;
  window.refreshGlobalHeaderStatus = refreshGlobalHeaderStatus;
  window.setHeaderUser = setHeaderUser;
  window.dateTime24 = {
    normalizeForApi,
    formatDisplayDateTime,
    enforce24hInputs,
    enhanceSimpleDatePickers,
  };

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        initializeWebAuthSession();
        setupLogoutButton();
        enforce24hInputs(document);
        startSimpleDatePickerEnhancer(1200);
        startAutoTableTimestampFormatting();
        startGlobalHeaderStatusPolling(1000);
      },
      { once: true }
    );
  } else {
    initializeWebAuthSession();
    setupLogoutButton();
    enforce24hInputs(document);
    startSimpleDatePickerEnhancer(1200);
    startAutoTableTimestampFormatting();
    startGlobalHeaderStatusPolling(1000);
  }
})();
