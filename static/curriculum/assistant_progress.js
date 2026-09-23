(() => {
  const indicator = document.querySelector("[data-status-url]");
  if (!indicator) return;

  const statusLabel = document.querySelector("#assistant-status-label");
  const counter = document.querySelector("#assistant-progress-counter");
  const activeNotice = document.querySelector("#assistant-active-notice");
  const failedGuide = document.querySelector("#assistant-failed-guide");
  const errorContainer = document.querySelector("#assistant-error-container");
  const error = document.querySelector("#assistant-live-error");
  const retryForm = document.querySelector("#assistant-retry-form");
  const retryBtn = document.querySelector("#retry-organization-btn");
  const reextractForm = document.querySelector("#assistant-reextract-form");
  const reextractBtn = document.querySelector("#reextract-organization-btn");

  const poll = async () => {
    try {
      const response = await fetch(indicator.dataset.statusUrl, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("status-unavailable");
      const data = await response.json();
      indicator.dataset.assistantState = data.state;
      if (data.label && statusLabel) {
        statusLabel.textContent = data.label;
      }
      const statusDesc = document.querySelector("#assistant-status-description");
      if (statusDesc && data.description !== undefined) {
        statusDesc.textContent = data.description;
      }

      if (data.total && counter) {
        counter.hidden = false;
        counter.textContent = `${data.done} de ${data.total}`;
      }
      if (data.state === "finished") {
        window.location.assign(data.redirect_url);
        return;
      }
      if (data.state === "error" || data.interpretation_state === "failed") {
        const errorMsg = data.error || "Ocurrió un problema al organizar tu planeación. Puedes volver a intentarlo.";
        if (error) {
          error.textContent = errorMsg;
        }
        if (activeNotice) {
          activeNotice.hidden = true;
          activeNotice.textContent = "";
        }
        if (counter) {
          counter.hidden = true;
        }
        if (errorContainer) {
          errorContainer.hidden = false;
        }
        if (data.needs_reextract) {
          if (failedGuide) {
            failedGuide.textContent = "El archivo original cambió o requiere volver a extraerse. Pulsa Reextraer planeación para continuar.";
            failedGuide.hidden = false;
          }
          if (retryForm) {
            retryForm.hidden = true;
          }
          if (retryBtn) {
            retryBtn.disabled = true;
          }
          if (reextractForm) {
            reextractForm.hidden = false;
            if (reextractBtn) {
              reextractBtn.disabled = false;
              reextractBtn.focus();
            } else if (errorContainer) {
              errorContainer.focus();
            }
          } else {
            window.location.reload();
            return;
          }
        } else {
          if (failedGuide) {
            failedGuide.textContent = "El proceso se detuvo. Pulsa Volver a intentar para iniciar un nuevo intento.";
            failedGuide.hidden = false;
          }
          if (reextractForm) {
            reextractForm.hidden = true;
          }
          if (reextractBtn) {
            reextractBtn.disabled = true;
          }
          if (retryForm) {
            retryForm.hidden = false;
            if (retryBtn) {
              retryBtn.disabled = false;
              retryBtn.focus();
            } else if (errorContainer) {
              errorContainer.focus();
            }
          } else {
            window.location.reload();
            return;
          }
        }
        return;
      } else {
        if (reextractForm) {
          reextractForm.hidden = true;
        }
        if (reextractBtn) {
          reextractBtn.disabled = true;
        }
        if (retryForm) {
          retryForm.hidden = true;
        }
        if (retryBtn) {
          retryBtn.disabled = true;
        }
        if (activeNotice) {
          activeNotice.textContent = "Esto puede tardar varios minutos con currículas grandes. Puedes dejar esta página abierta: al terminar continuarás automáticamente.";
          activeNotice.hidden = false;
        }
        if (failedGuide) {
          failedGuide.textContent = "";
          failedGuide.hidden = true;
        }
        if (errorContainer) {
          errorContainer.hidden = true;
        }
      }
    } catch (_pollingError) {
      if (error) {
        error.textContent = "No se pudo actualizar el estado del asistente. Reintentando automáticamente sin duplicar la generación.";
      }
      if (errorContainer) {
        errorContainer.hidden = false;
      }
    }
    window.setTimeout(poll, 2000);
  };

  window.setTimeout(poll, 250);
})();
