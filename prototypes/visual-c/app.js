(() => {
  const views = [...document.querySelectorAll(".view")];
  const viewButtons = [...document.querySelectorAll("[data-view]")];
  const stateNodes = [...document.querySelectorAll("[data-state]")];
  const stateButtons = [...document.querySelectorAll("[data-state-target]")];
  const liveChip = document.querySelector("#live-chip");
  const nicknameForm = document.querySelector("#nickname-form");
  const nicknameInput = document.querySelector("#nickname");
  const nicknameList = document.querySelector("#nickname-list");
  const participantCount = document.querySelector("#participant-count");
  const teacherMessage = document.querySelector("#teacher-message");
  const prepareStatus = document.querySelector("#prepare-status");
  const route = "demo-ciencias";
  let currentState = "espera";
  let localAliases = loadAliases();

  function loadAliases() {
    try {
      const saved = JSON.parse(localStorage.getItem("aulalista-demo-apodos") || "[]");
      return Array.isArray(saved) ? saved.filter((alias) => typeof alias === "string").slice(0, 20) : [];
    } catch (error) {
      return [];
    }
  }

  function saveAliases() {
    try {
      localStorage.setItem("aulalista-demo-apodos", JSON.stringify(localAliases));
    } catch (error) {
      return false;
    }
    return true;
  }

  function drawQr(selector) {
    const qr = document.querySelector(selector);
    if (!qr || qr.children.length) return;
    const size = 11;
    const finder = (row, column) => {
      const inTop = row < 3 && column < 3;
      const inBottom = row > 7 && column < 3;
      const inRight = row < 3 && column > 7;
      if (!inTop && !inBottom && !inRight) return null;
      const localRow = row < 3 ? row : row - 8;
      const localColumn = column > 7 ? column - 8 : column;
      return localRow === 0 || localRow === 2 || localColumn === 0 || localColumn === 2;
    };
    for (let row = 0; row < size; row += 1) {
      for (let column = 0; column < size; column += 1) {
        const cell = document.createElement("span");
        const marker = finder(row, column);
        const filled = marker === null ? ((row * 5 + column * 3 + row * column + route.length) % 4 !== 1) : marker;
        cell.className = filled ? "" : "is-empty";
        cell.setAttribute("aria-hidden", "true");
        qr.appendChild(cell);
      }
    }
  }

  function showView(name, updateHash = true) {
    const target = views.some((view) => view.id === name) ? name : "home";
    views.forEach((view) => {
      const visible = view.id === target;
      view.hidden = !visible;
      view.setAttribute("aria-hidden", String(!visible));
    });
    if (updateHash && window.location.hash !== `#${target}`) window.location.hash = target;
    const heading = document.querySelector(`#${target} h1`);
    if (heading) heading.focus({ preventScroll: true });
  }

  function renderRoster() {
    if (participantCount) participantCount.textContent = String(localAliases.length);
    if (!nicknameList) return;
    nicknameList.replaceChildren();
    localAliases.forEach((alias) => {
      const item = document.createElement("li");
      item.textContent = alias;
      nicknameList.appendChild(item);
    });
  }

  function setState(nextState) {
    const allowedStates = ["espera", "activo", "cerrado", "error"];
    currentState = allowedStates.includes(nextState) ? nextState : "error";
    stateNodes.forEach((node) => {
      node.hidden = node.dataset.state !== currentState;
    });
    stateButtons.forEach((button) => {
      const selected = button.dataset.stateTarget === currentState;
      button.classList.toggle("state-button--selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    if (liveChip) {
      const labels = { espera: "EN ESPERA", activo: "ACTIVO", cerrado: "CERRADO", error: "ERROR" };
      liveChip.textContent = labels[currentState];
      liveChip.className = `status-chip status-chip--${currentState === "activo" ? "live" : currentState === "error" ? "error" : "soft"}`;
    }
    if (nicknameForm) nicknameForm.hidden = currentState === "cerrado" || currentState === "error";
    if (currentState === "cerrado") {
      localAliases = [];
      saveAliases();
      renderRoster();
    }
  }

  viewButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      showView(button.dataset.view);
      if (button.dataset.entry === "student") setState("espera");
    });
  });

  stateButtons.forEach((button) => {
    button.addEventListener("click", () => setState(button.dataset.stateTarget));
  });

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.action === "prepare") {
        if (prepareStatus) prepareStatus.textContent = "Preparada por la maestra";
        if (teacherMessage) teacherMessage.textContent = "Sesión preparada. La maestra puede activarla cuando el grupo esté listo.";
      }
      if (button.dataset.action === "activate") {
        showView("active");
        setState("activo");
      }
    });
  });

  if (nicknameForm) {
    nicknameForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (currentState === "cerrado" || currentState === "error") return;
      const typedAlias = nicknameInput.value.trim().replace(/[<>]/g, "").slice(0, 18);
      const alias = typedAlias || "Invitado local";
      if (!localAliases.includes(alias) && localAliases.length < 20) localAliases.push(alias);
      saveAliases();
      renderRoster();
      nicknameInput.value = "";
      nicknameInput.setAttribute("aria-label", `Apodo local ${alias} añadido`);
    });
  }

  drawQr("#qr-student");
  drawQr("#qr-persistent");
  renderRoster();
  setState("espera");
  showView(window.location.hash.slice(1) || "home", false);
  window.addEventListener("hashchange", () => showView(window.location.hash.slice(1), false));
})();
