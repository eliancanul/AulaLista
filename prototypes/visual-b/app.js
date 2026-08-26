const screens = Array.from(document.querySelectorAll('.screen'));
const announcement = document.getElementById('announcement');
const storageKey = 'aulalista-visual-b';
const fallbackSession = { joinCode: 'AULA-B7Q2', nicknames: ['Luz', 'Nube'] };

function getSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (saved && saved.joinCode && Array.isArray(saved.nicknames)) return saved;
  } catch (error) {
    return { ...fallbackSession, storageError: true };
  }
  return { ...fallbackSession };
}

function saveSession(session) {
  try {
    localStorage.setItem(storageKey, JSON.stringify({ joinCode: session.joinCode, nicknames: session.nicknames.slice(0, 12) }));
  } catch (error) {
    document.getElementById('session-error').hidden = false;
  }
}

const session = getSession();

function announce(message) {
  announcement.textContent = message;
}

function navigate(screenName, shouldFocus = true) {
  const destination = document.getElementById(`screen-${screenName}`);
  if (!destination) return;
  screens.forEach((screen) => {
    const isVisible = screen === destination;
    screen.hidden = !isVisible;
    screen.classList.toggle('active-screen', isVisible);
  });
  if (shouldFocus) {
    const heading = destination.querySelector('h1');
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      heading.focus({ preventScroll: true });
    }
  }
  announce(`Vista ${screenName} abierta.`);
  window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

document.querySelectorAll('[data-screen]').forEach((control) => {
  control.addEventListener('click', () => navigate(control.dataset.screen));
});

function renderQr(element) {
  if (!element) return;
  const pattern = [
    '11110101111', '10010001001', '10110111011', '10010001001', '11110101111',
    '00001101000', '11010111101', '01001100100', '11111010111', '10000101001', '11101111111'
  ];
  element.replaceChildren();
  pattern.forEach((row) => row.split('').forEach((cell) => {
    const square = document.createElement('span');
    square.setAttribute('aria-hidden', 'true');
    if (cell === '0') square.style.opacity = '0';
    element.appendChild(square);
  }));
}

function renderSession() {
  document.querySelectorAll('.join-code').forEach((element) => { element.textContent = session.joinCode; });
  document.querySelectorAll('[data-demo="synthetic"] .code-chip').forEach((element) => { element.textContent = session.joinCode; });
  const list = document.getElementById('nickname-list');
  const count = document.getElementById('participant-count');
  if (!list || !count) return;
  list.replaceChildren();
  session.nicknames.forEach((nickname) => {
    const chip = document.createElement('span');
    chip.className = 'nickname-chip';
    chip.append(document.createTextNode(nickname));
    const label = document.createElement('i');
    label.textContent = 'demo';
    chip.append(label);
    list.append(chip);
  });
  count.textContent = String(session.nicknames.length);
}

renderQr(document.getElementById('student-qr'));
renderQr(document.getElementById('active-qr'));
renderSession();

const nicknameForm = document.getElementById('nickname-form');
if (nicknameForm) {
  nicknameForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = document.getElementById('nickname');
    const nickname = input.value.trim().replace(/[^\p{L}\p{N} _-]/gu, '').slice(0, 14);
    if (!nickname) {
      input.setCustomValidity('Escribe un apodo local para continuar.');
      input.reportValidity();
      return;
    }
    input.setCustomValidity('');
    if (!session.nicknames.includes(nickname)) session.nicknames.push(nickname);
    saveSession(session);
    renderSession();
    navigate('roadmap');
    announce(`Apodo local ${nickname} agregado a la demostración sintética.`);
  });
}

document.querySelectorAll('[data-action="start-activity"]').forEach((control) => {
  control.addEventListener('click', () => {
    const panel = document.getElementById('activity-panel');
    panel.hidden = false;
    panel.querySelector('h2').focus({ preventScroll: true });
    announce('Actividad abierta. Elige una opción.');
  });
});

document.querySelectorAll('.option-button').forEach((option) => {
  option.addEventListener('click', () => {
    const feedback = document.getElementById('activity-feedback');
    feedback.textContent = option.dataset.option === 'calle'
      ? 'Respuesta registrada en la demo sintética. La maestra decide cuándo marcar el siguiente tema.'
      : 'Opción registrada en la demo sintética. Puedes volver a intentarlo con la misma regla local.';
    announce(feedback.textContent);
  });
});

document.querySelectorAll('[data-action="activate-session"]').forEach((control) => {
  control.addEventListener('click', () => {
    navigate('active');
    setSessionState('activo');
    announce('La maestra activó la sesión sintética.');
  });
});

function setSessionState(state) {
  const container = document.getElementById('active-state');
  const label = document.getElementById('active-state-label');
  const errorBanner = document.getElementById('session-error');
  if (!container || !label || !errorBanner) return;
  const labels = { espera: 'Espera', activo: 'Activo', cerrado: 'Cerrado', error: 'Error' };
  container.dataset.state = labels[state] ? state : 'error';
  label.textContent = labels[state] || 'Error';
  errorBanner.hidden = state !== 'error';
  announce(`Estado de sesión: ${label.textContent}.`);
}

document.querySelectorAll('[data-state]').forEach((control) => {
  control.addEventListener('click', () => setSessionState(control.dataset.state));
});

document.querySelector('[data-action="copy-code"]')?.addEventListener('click', async () => {
  const code = session.joinCode;
  try {
    await navigator.clipboard.writeText(code);
    announce(`Código local ${code} copiado.`);
  } catch (error) {
    announce(`Código local: ${code}. La copia automática no está disponible.`);
  }
});

if (session.storageError) document.getElementById('session-error').hidden = false;
