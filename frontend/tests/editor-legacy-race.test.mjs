import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../../templates/curriculum/tutor_import_interpretation.html', import.meta.url), 'utf8');
const script = html.match(/<script id="dirty-guard-script">([\s\S]*?)<\/script>/)[1];
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
const ok = (version = 2) => ({ ok: true, text: async () => JSON.stringify({ status: 'ok', version }) });

function editor({ post = async () => ok(), page = async () => ({ ok: true, text: async () => '<main />' }) } = {}) {
  const requests = [];
  const windowHandlers = {};
  let replaced = false;
  let confirmations = 0;
  function form() {
    const handlers = {};
    const buttons = [{ disabled: false }];
    const version = { value: '1' };
    const field = { value: 'Texto inicial' };
    const element = {
      dataset: {}, version, field, buttons, handlers, alert: null,
      addEventListener(name, fn) { (handlers[name] ??= []).push(fn); },
      querySelectorAll() { return buttons; },
      querySelector(selector) {
        if (selector === '[name="expected_version"]') return version;
        if (selector === '.async-save-error') return this.alert;
        return null;
      },
      getAttribute() { return '/review?item=proyecto'; },
      prepend(alert) { this.alert = alert; },
      edit(text) {
        field.value = text;
        for (const handler of handlers.input) handler({ currentTarget: element, target: field });
      },
      async submit(action = 'save_queue_item') {
        let prevented = false;
        for (const handler of handlers.submit) {
          await handler({ preventDefault() { prevented = true; }, currentTarget: element, submitter: { name: 'action', value: action } });
        }
        return prevented;
      },
    };
    field.form = element;
    return element;
  }
  const queue = form();
  const full = form();
  const approval = form();
  const anchor = { dataset: {}, getAttribute() { return null; }, addEventListener(_, fn) { this.click = fn; } };
  const replacement = { querySelector() { return null; }, querySelectorAll() { return []; } };
  const indicator = { style: {} };
  const document = {
    readyState: 'loading', addEventListener() {},
    getElementById() { return indicator; },
    createElement() { return { setAttribute() {}, focus() {} }; },
    querySelector(selector) {
      if (selector === '#queue-item-form') return queue;
      if (selector === '#interpretation-form') return full;
      if (selector === '#teacher-approval-form') return approval;
      if (selector === 'main.v0-container') return { replaceWith() { replaced = true; queue.field.value = 'Siguiente duda'; } };
      return null;
    },
    querySelectorAll() { return [anchor]; },
  };
  vm.runInNewContext(script, {
    document, URL,
    window: {
      location: { href: 'http://local/review' }, scrollY: 0, scrollTo() {},
      addEventListener(name, fn) { windowHandlers[name] = fn; },
      confirm() { confirmations++; return false; },
    },
    history: { replaceState() {} },
    FormData: class extends Map {
      constructor(source) { super([['proyecto', source.field.value], ['expected_version', source.version.value]]); }
    },
    DOMParser: class { parseFromString() { return { querySelector() { return replacement; } }; } },
    fetch: async (url, options) => {
      requests.push({ url, ...options });
      return options.method === 'POST' ? post() : page();
    },
  });
  return {
    queue, full, approval, requests, indicator,
    get replaced() { return replaced; },
    get confirmations() { return confirmations; },
    unload() {
      let prevented = false;
      windowHandlers.beforeunload({ preventDefault() { prevented = true; } });
      return prevented;
    },
    navigate() {
      let prevented = false;
      anchor.click({ preventDefault() { prevented = true; } });
      return prevented;
    },
  };
}

test('S13 keeps edits typed during POST and retries against the acknowledged version', async () => {
  const pending = deferred();
  const ui = editor({ post: () => pending.promise });
  ui.queue.edit('Texto enviado');
  const saving = ui.queue.submit();
  ui.queue.edit('Edición posterior sin enviar');
  pending.resolve(ok());
  await saving;
  assert.equal(ui.requests[0].body.get('proyecto'), 'Texto enviado');
  assert.equal(ui.replaced, false);
  assert.equal(ui.queue.field.value, 'Edición posterior sin enviar');
  assert.equal(ui.queue.version.value, '2');
  assert.equal(ui.full.version.value, '1', 'unsubmitted full-form snapshot must retain its conflict guard');
  assert.equal(ui.unload(), true);
  assert.equal(ui.queue.buttons[0].disabled, false);
  assert.match(ui.queue.alert.textContent, /cambios sin guardar/);
  await ui.queue.submit();
  assert.equal(ui.requests[1].body.get('proyecto'), 'Edición posterior sin enviar');
  assert.equal(ui.requests[1].body.get('expected_version'), '2');
  assert.equal(ui.replaced, true);
  assert.equal(ui.unload(), false);
});

for (const failedRefresh of [false, true]) {
  test(`S13 retains edits during ${failedRefresh ? 'failed' : 'successful'} GET refresh`, async () => {
    const pending = deferred();
    const started = deferred();
    const ui = editor({ page: () => { started.resolve(); return pending.promise; } });
    ui.queue.edit('Enviado');
    const saving = ui.queue.submit();
    await started.promise;
    ui.queue.edit('Escrito durante la recarga');
    pending.resolve({ ok: !failedRefresh, text: async () => '<main />' });
    await saving;
    assert.equal(ui.replaced, false);
    assert.equal(ui.queue.field.value, 'Escrito durante la recarga');
    assert.equal(ui.queue.buttons[0].disabled, false);
    assert.equal(ui.unload(), true);
    assert.equal(ui.navigate(), true);
  });
}

for (const timing of ['before', 'during']) {
  test(`S13 retains full-form edits made ${timing} a queue save`, async () => {
    const pending = deferred();
    const ui = editor({ post: () => pending.promise });
    if (timing === 'before') ui.full.edit('Otra corrección docente');
    const saving = ui.queue.submit();
    if (timing === 'during') ui.full.edit('Otra corrección docente');
    pending.resolve(ok());
    await saving;
    assert.equal(ui.replaced, false);
    assert.equal(ui.full.field.value, 'Otra corrección docente');
    assert.equal(ui.full.version.value, '1');
    assert.equal(ui.unload(), true);
  });
}

test('S13 protects reload/navigation and prevents competing saves or approval while pending', async () => {
  const pending = deferred();
  const ui = editor({ post: () => pending.promise });
  ui.queue.buttons.push({ disabled: true });
  const saving = ui.queue.submit('confirm_queue_item');
  assert.equal(ui.unload(), true);
  assert.equal(ui.navigate(), true);
  assert.equal(ui.confirmations, 1);
  await ui.queue.submit();
  assert.equal(await ui.full.submit('approve'), true);
  assert.equal(ui.requests.length, 1);
  pending.resolve(ok());
  await saving;
  assert.equal(ui.replaced, true);
  assert.equal(ui.unload(), false);
  assert.equal(ui.queue.buttons[1].disabled, true);
});

for (const failure of ['network', 'conflict']) {
  test(`S13 keeps text and version after ${failure}, then allows explicit retry`, async () => {
    let attempt = 0;
    const ui = editor({ post: async () => {
      if (++attempt > 1) return ok();
      if (failure === 'network') throw new Error('Failed to fetch');
      return { ok: false, text: async () => JSON.stringify({ status: 'error', message: 'Versión en conflicto' }) };
    } });
    ui.queue.edit('  Texto docente exacto\n');
    await ui.queue.submit();
    assert.equal(ui.queue.field.value, '  Texto docente exacto\n');
    assert.equal(ui.queue.version.value, '1');
    assert.equal(ui.unload(), true);
    assert.equal(ui.queue.buttons[0].disabled, false);
    assert.equal(ui.replaced, false);
    await ui.queue.submit();
    assert.equal(ui.requests[1].body.get('proyecto'), '  Texto docente exacto\n');
    assert.equal(ui.requests[1].body.get('action'), 'save_queue_item');
    assert.equal(ui.replaced, true);
  });
}

test('S13 saved POST with failed refresh keeps version and permits retry without marking edits saved', async () => {
  const ui = editor({ page: async () => ({ ok: false }) });
  ui.queue.edit('Texto guardado');
  await ui.queue.submit();
  assert.equal(ui.queue.version.value, '2');
  assert.equal(ui.unload(), false);
  assert.match(ui.queue.alert.textContent, /se guardó/);
  ui.queue.edit('Texto nuevo');
  assert.equal(ui.unload(), true);
  await ui.queue.submit();
  assert.equal(ui.requests[2].body.get('proyecto'), 'Texto nuevo');
  assert.equal(ui.requests[2].body.get('expected_version'), '2');
});

test('S13 never confirms or approves unsaved queue text implicitly', async () => {
  const ui = editor();
  ui.queue.edit('Pendiente de guardar');
  await ui.queue.submit('confirm_queue_item');
  await ui.queue.submit('postpone_queue_item');
  assert.equal(await ui.full.submit('approve'), true);
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.queue.field.value, 'Pendiente de guardar');
  await ui.queue.submit();
  assert.equal(ui.requests[0].body.get('action'), 'save_queue_item');
  assert.equal(ui.requests[0].body.has('confirm_approval'), false);
});


test('separate approval form ignores confirmation controls as edits but blocks unsaved text', async () => {
  const ui = editor();
  for (const handler of ui.full.handlers.input) handler({ currentTarget: ui.full, target: { form: ui.approval } });
  assert.equal(ui.unload(), false, 'external confirmation is not an edit');
  assert.equal(await ui.approval.submit('approve'), false);
  ui.full.edit('Edición todavía no guardada');
  assert.equal(await ui.approval.submit('approve'), true);
  assert.match(ui.full.alert.textContent, /Guarda tus cambios/);
});

test('separate approval form blocks while a guided save is unresolved', async () => {
  const pending = deferred();
  const ui = editor({ post: () => pending.promise });
  const saving = ui.queue.submit();
  assert.equal(await ui.approval.submit('approve'), true);
  pending.resolve(ok());
  await saving;
});


test('guided save blocks stale full-form submission without raising its version or losing text', async () => {
  const ui = editor();
  ui.full.edit('Objetivo docente sin guardar');
  ui.queue.edit('Proyecto guardado aparte');
  await ui.queue.submit();
  assert.equal(ui.queue.version.value, '2');
  assert.equal(ui.full.version.value, '1');
  assert.equal(await ui.full.submit('save_corrections'), true);
  assert.equal(ui.requests.length, 1);
  assert.equal(ui.full.field.value, 'Objetivo docente sin guardar');
  assert.equal(ui.unload(), true);
  assert.match(ui.full.alert.textContent, /versión más reciente/);
});
