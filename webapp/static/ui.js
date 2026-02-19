(function () {
  const STACK_ID = "toast-stack";
  const DATETIME_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/;

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

  function normalizeForApi(localValue, isEnd = false) {
    const raw = String(localValue || "").trim();
    if (!raw) {
      return "";
    }
    if (/\b(am|pm)\b/i.test(raw)) {
      return "";
    }
    const match = DATETIME_RE.exec(raw);
    if (match) {
      const year = Number(match[1]);
      const month = Number(match[2]);
      const day = Number(match[3]);
      const hour = Number(match[4]);
      const minute = Number(match[5]);
      const hasSeconds = typeof match[6] === "string";
      let second = hasSeconds ? Number(match[6]) : 0;
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
        return "";
      }
      if (isEnd && !hasSeconds) {
        second = 59;
      }
      const check = new Date(year, month - 1, day, hour, minute, second, 0);
      if (
        Number.isNaN(check.getTime()) ||
        check.getFullYear() !== year ||
        check.getMonth() + 1 !== month ||
        check.getDate() !== day
      ) {
        return "";
      }
      return `${year}-${pad2(month)}-${pad2(day)}T${pad2(hour)}:${pad2(minute)}:${pad2(second)}`;
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
    }
  }

  window.showToast = showToast;
  window.showSavedToast = showSavedToast;
  window.dateTime24 = {
    normalizeForApi,
    enforce24hInputs,
  };

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        enforce24hInputs(document);
      },
      { once: true }
    );
  } else {
    enforce24hInputs(document);
  }
})();
