(() => {
  const indicator = document.querySelector("[data-status-url]");
  if (!indicator) return;

  const statusLabel = document.querySelector("#assistant-status-label");
  const counter = document.querySelector("#assistant-progress-counter");
  const error = document.querySelector("#assistant-live-error");
  const retry = document.querySelector("#assistant-retry-link");

  const poll = async () => {
    try {
      const response = await fetch(indicator.dataset.statusUrl, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("status-unavailable");
      const data = await response.json();
      indicator.dataset.assistantState = data.state;
      statusLabel.textContent = data.label;
      error.hidden = true;
      retry.hidden = true;

      if (data.total) {
        counter.hidden = false;
        counter.textContent = `${data.done} de ${data.total}`;
      }
      if (data.state === "finished") {
        window.location.assign(data.redirect_url);
        return;
      }
      if (data.state === "error") {
        error.textContent = data.error || "La generación se interrumpió.";
        error.hidden = false;
        retry.hidden = false;
        return;
      }
    } catch (_pollingError) {
      error.textContent = "No se pudo actualizar el estado del asistente. Reintentando automáticamente sin duplicar la generación.";
      error.hidden = false;
      retry.hidden = false;
    }
    window.setTimeout(poll, 2000);
  };

  window.setTimeout(poll, 250);
})();
