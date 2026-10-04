(() => {
  const form = document.querySelector('#teacher-answer-form');
  const status = document.querySelector('#draft-status');
  let timer;
  let resumeTimer;
  let submissionGeneration = 0;
  let pending = Promise.resolve();
  let unsaved = false;
  let inputVersion = 0;
  let leavingForSubmit = false;
  if (form && status) {
    const input = form.querySelector('textarea');
    const epoch = form.querySelector('[name="draft_epoch"]');
    input.addEventListener('input', () => {
      clearTimeout(timer);
      unsaved = true;
      const version = ++inputVersion;
      status.textContent = 'Guardando borrador…';
      const text = input.value;
      timer = setTimeout(() => {
        // Serialize writes. Read the epoch only when dispatching, after the
        // previous response. The server CAS rejects reordered/obsolete requests.
        pending = pending.catch(() => {}).then(async () => {
          const data = new FormData(form);
          data.set('answer', text);
          data.set('action', 'save_draft');
          const response = await fetch(window.location.href, {method: 'POST', body: data, credentials: 'same-origin'});
          const result = await response.json();
          if (!response.ok || !result.saved) throw new Error('draft_conflict');
          epoch.value = String(result.draft_epoch);
          if (inputVersion === version) {
            unsaved = false;
            status.textContent = 'Borrador guardado en esta sesión.';
          }
        }).catch(() => {status.textContent = 'No se pudo guardar este borrador; sigue en la caja y no se ha sobrescrito el más reciente.';});
      }, 600);
    });
    window.addEventListener('beforeunload', event => {
      if (unsaved && !leavingForSubmit) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
  }
  document.querySelectorAll('form').forEach(current => current.addEventListener('submit', event => {
    clearTimeout(timer);
    // Finish already-dispatched local saves before the answer/discard. Server
    // revision/epoch checks independently reject a request that arrives later.
    if (current === form && !current.dataset.prepared) {
      event.preventDefault();
      if (current.dataset.submitting) return;
      current.dataset.submitting = 'true';
      const submitter = event.submitter;
      const generation = ++submissionGeneration;
      pending.finally(() => {
        // Native submit listeners can run microtasks before the form releases
        // its submission-event guard. A new task avoids ignored reentrant
        // requestSubmit calls, while still waiting for the latest saved epoch.
        resumeTimer = setTimeout(() => {
          if (generation !== submissionGeneration || !current.dataset.submitting) return;
          current.dataset.prepared = 'true';
          current.requestSubmit(submitter);
        }, 0);
      });
      return;
    }
    if (current === form) leavingForSubmit = true;
    current.setAttribute('aria-busy', 'true');
    if (status) status.textContent = 'Guardando y preparando el siguiente paso…';
    const generation = submissionGeneration;
    setTimeout(() => {
      if (generation !== submissionGeneration) return;
      current.querySelectorAll('button').forEach(button => {button.disabled = true;});
    }, 0);
  }));
  window.addEventListener('pageshow', () => {
    ++submissionGeneration;
    clearTimeout(resumeTimer);
    leavingForSubmit = false;
    document.querySelectorAll('form').forEach(current => {
      current.removeAttribute('aria-busy');
      delete current.dataset.prepared;
      delete current.dataset.submitting;
      current.querySelectorAll('button').forEach(button => {
        if (!button.dataset.domainDisabled) button.disabled = false;
      });
    });
  });
})();
