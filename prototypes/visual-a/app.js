(() => {
  "use strict";

  const DEMO_CODE = "DEMO-7K4";
  const STORAGE_KEY = "aulalista-visual-a-demo-nicknames";
  const DEFAULT_NICKNAMES = ["Río", "Luna", "Pino"];
  const validRoutes = new Set(["inicio", "estudiante", "docente", "actividad"]);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  // Todo lo que vive aquí es demostración sintética y solo permanece en este navegador.
  const state = {
    session: "activa",
    nicknames: loadNicknames(),
    reducedMotion: reducedMotion.matches,
  };

  function loadNicknames() {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (Array.isArray(stored) && stored.every((name) => typeof name === "string")) {
        return stored.slice(0, 12);
      }
    } catch (_error) {
      // La interfaz funciona también cuando el navegador no permite almacenamiento local.
    }
    return DEFAULT_NICKNAMES.slice();
  }

  function saveNicknames() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.nicknames.slice(0, 12)));
    } catch (_error) {
      // El apodo sigue siendo visible durante esta visita aunque no pueda persistirse.
    }
  }

  function escapeHTML(value) {
    return value.replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[character]));
  }

  function initials(name) {
    return name.trim().slice(0, 2).toUpperCase();
  }

  function renderParticipants() {
    const list = document.querySelector("#participant-list");
    const count = document.querySelector("#participant-count");
    if (!list || !count) return;
    count.textContent = String(state.nicknames.length);
    list.innerHTML = state.nicknames.map((name) => `
      <div class="participant">
        <span class="participant-bubble" aria-hidden="true">${escapeHTML(initials(name))}</span>
        <span class="participant-name">${escapeHTML(name)}</span>
      </div>
    `).join("");
  }

  function renderQR() {
    const qr = document.querySelector("#demo-qr");
    if (!qr) return;
    const size = 15;
    const cells = [];
    const inFinder = (row, column, startRow, startColumn) => {
      const r = row - startRow;
      const c = column - startColumn;
      if (r < 0 || r > 6 || c < 0 || c > 6) return false;
      return r === 0 || r === 6 || c === 0 || c === 6 || (r >= 2 && r <= 4 && c >= 2 && c <= 4);
    };
    for (let row = 0; row < size; row += 1) {
      for (let column = 0; column < size; column += 1) {
        const finder = inFinder(row, column, 0, 0) || inFinder(row, column, 0, 8) || inFinder(row, column, 8, 0);
        const quietFinderSpace = (row < 8 && column < 8) || (row < 8 && column > 7) || (row > 7 && column < 8);
        const patterned = ((row * 7 + column * 11 + row * column) % 5) < 2;
        cells.push(`<span class="qr-cell${finder || (!quietFinderSpace && patterned) ? " is-on" : ""}" aria-hidden="true"></span>`);
      }
    }
    qr.innerHTML = cells.join("");
  }

  function setRoute(route) {
    const nextRoute = validRoutes.has(route) ? route : "inicio";
    document.querySelectorAll("[data-view]").forEach((view) => {
      view.hidden = view.dataset.view !== nextRoute;
    });
    document.querySelectorAll("[data-route]").forEach((link) => {
      link.classList.toggle("is-active", link.dataset.route === nextRoute);
    });
    document.title = nextRoute === "inicio" ? "AulaLista — prototipo A" : `AulaLista — ${nextRoute}`;
    if (nextRoute === "actividad") {
      renderParticipants();
      renderQR();
      renderSessionState();
    }
    document.querySelector("#contenido")?.focus({ preventScroll: true });
  }

  function renderSessionState() {
    document.querySelectorAll("[data-state-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.statePanel !== state.session;
    });
    document.querySelectorAll("[data-session-state]").forEach((button) => {
      button.classList.toggle("is-selected", button.dataset.sessionState === state.session);
      button.setAttribute("aria-pressed", String(button.dataset.sessionState === state.session));
    });
    const descriptions = {
      espera: "La actividad está lista y espera la activación de la maestra.",
      activa: "La actividad está activa para el grupo.",
      cerrada: "La actividad está cerrada; el acceso está detenido.",
      error: "Hay un error local simulado; ningún dato salió de este dispositivo.",
    };
    const description = document.querySelector("#state-description");
    if (description) description.textContent = descriptions[state.session];
    const closeButton = document.querySelector("#session-close");
    if (closeButton) closeButton.disabled = state.session === "cerrada";
  }

  function setFeedback(message, kind) {
    const feedback = document.querySelector("#entry-feedback");
    if (!feedback) return;
    feedback.textContent = message;
    feedback.className = `form-feedback${kind ? ` is-${kind}` : ""}`;
  }

  function bindNavigation() {
    document.addEventListener("click", (event) => {
      const link = event.target.closest("[data-route]");
      if (!link) return;
      const route = link.dataset.route;
      if (!validRoutes.has(route)) return;
      event.preventDefault();
      window.location.hash = route;
    });
    window.addEventListener("hashchange", () => setRoute(window.location.hash.slice(1)));
  }

  function bindStudentEntry() {
    document.querySelector("#student-entry-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const code = document.querySelector("#session-code").value.trim().toUpperCase();
      if (code !== DEMO_CODE) {
        setFeedback("No encontramos ese enlace de demostración. Revisa el código e inténtalo de nuevo.", "error");
        return;
      }
      const nicknameInput = document.querySelector("#local-nickname");
      const nickname = nicknameInput.value.trim().replace(/\s+/g, " ");
      if (nickname && !state.nicknames.includes(nickname)) {
        state.nicknames.push(nickname.slice(0, 18));
        saveNicknames();
      }
      setFeedback("Entrada lista. El apodo queda solo en este dispositivo.", "success");
      window.setTimeout(() => { window.location.hash = "actividad"; }, state.reducedMotion ? 0 : 220);
    });
  }

  function bindNicknameForm() {
    document.querySelector("#nickname-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = document.querySelector("#new-nickname");
      const feedback = document.querySelector("#nickname-feedback");
      const nickname = input.value.trim().replace(/\s+/g, " ");
      if (!nickname) {
        feedback.textContent = "Escribe un apodo local para sumarlo a la demostración.";
        feedback.className = "field-help";
        input.focus();
        return;
      }
      if (state.nicknames.length >= 12) {
        feedback.textContent = "La demostración muestra hasta 12 apodos locales.";
        return;
      }
      if (state.nicknames.includes(nickname)) {
        feedback.textContent = "Ese apodo ya está en esta pantalla.";
        return;
      }
      state.nicknames.push(nickname.slice(0, 18));
      saveNicknames();
      input.value = "";
      feedback.textContent = "Apodo local agregado. No es una cuenta estudiantil.";
      renderParticipants();
    });
  }

  function bindActivityControls() {
    document.querySelectorAll("[data-session-state]").forEach((button) => {
      button.addEventListener("click", () => {
        state.session = button.dataset.sessionState;
        renderSessionState();
      });
    });
    document.querySelector("#session-close")?.addEventListener("click", () => {
      state.session = "cerrada";
      renderSessionState();
    });
    document.querySelector("#projection-toggle")?.addEventListener("click", (event) => {
      document.body.classList.toggle("projection-mode");
      const projection = document.body.classList.contains("projection-mode");
      event.currentTarget.textContent = projection ? "Salir de proyección" : "Modo proyección";
      event.currentTarget.setAttribute("aria-pressed", String(projection));
    });
  }

  reducedMotion.addEventListener?.("change", (event) => { state.reducedMotion = event.matches; });
  renderParticipants();
  renderQR();
  bindNavigation();
  bindStudentEntry();
  bindNicknameForm();
  bindActivityControls();
  setRoute(window.location.hash.slice(1));
})();
