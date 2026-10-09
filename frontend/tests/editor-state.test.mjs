import test from 'node:test';
import assert from 'node:assert/strict';
import { createActivityEditor } from '../src/features/editor/activityEditor.ts';

const content = () => ({ title: 'Actividad', objective: 'Comparar', materials: ['Papel'], steps: ['Observar'], assessment: 'Explicar', source_ids: ['segmento-1'] });
const initial = () => ({ id: 'draft-1', revision: 1, status: 'draft', content: content(), approved: null });
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
function setup() {
  const requests = [];
  const transport = {
    save: async (id, request) => { requests.push({ id, ...request }); return { ...initial(), revision: request.expected_revision + 1, content: request.content }; },
    approve: async (id, request) => { requests.push({ id, ...request }); return { ...initial(), revision: request.expected_revision + 1, status: 'approved', approved: { revision: request.expected_revision + 1, content: content() } }; },
  };
  return { editor: createActivityEditor(initial(), transport), transport, requests };
}

test('save carries expected revision and exact teacher whitespace without approval', async () => {
  const { editor, requests } = setup();
  editor.edit('title', '  Texto docente\n');
  assert.equal(await editor.save(), true);
  assert.deepEqual(requests, [{ id: 'draft-1', expected_revision: 1, content: { ...content(), title: '  Texto docente\n' } }]);
  assert.equal(editor.snapshot().dirty, false);
  assert.equal(editor.snapshot().isApproved, false);
});

test('typing during save survives its delayed response and is saved on the next revision', async () => {
  const { editor, transport, requests } = setup();
  const wait = deferred();
  const save = transport.save;
  transport.save = () => wait.promise;
  editor.edit('title', 'Texto enviado');
  const saving = editor.save();
  editor.edit('title', 'Texto más reciente');
  assert.equal(editor.snapshot().needsLeaveWarning, true);
  assert.equal(await editor.save(), false);
  wait.resolve({ ...initial(), revision: 2, content: { ...content(), title: 'Texto enviado' } });
  await saving;
  assert.equal(editor.snapshot().draft.title, 'Texto más reciente');
  assert.equal(editor.snapshot().saved.content.title, 'Texto enviado');
  assert.equal(editor.snapshot().dirty, true);
  transport.save = save;
  await editor.save();
  assert.equal(requests[0].expected_revision, 2);
  assert.equal(requests[0].content.title, 'Texto más reciente');
});

test('network failure keeps text, exposes failure, allows revision-guarded retry', async () => {
  const { editor, transport } = setup();
  const save = transport.save;
  transport.save = async () => { throw new Error('offline'); };
  editor.edit('assessment', 'Evaluación de la maestra');
  assert.equal(await editor.save(), false);
  assert.equal(editor.snapshot().draft.assessment, 'Evaluación de la maestra');
  assert.match(editor.snapshot().error, /No se pudo confirmar el guardado/);
  assert.equal(editor.snapshot().dirty, true);
  transport.save = save;
  assert.equal(await editor.save(), true);
});

test('conflict does not overwrite local text or retry until explicit comparison', async () => {
  const { editor, transport, requests } = setup();
  const save = transport.save;
  const other = { ...initial(), revision: 5, content: { ...content(), title: 'Otra pestaña' } };
  transport.save = async () => { throw { status: 409, current: other }; };
  editor.edit('title', 'Mi edición');
  await editor.save();
  assert.equal(editor.snapshot().draft.title, 'Mi edición');
  assert.equal(editor.snapshot().remote.content.title, 'Otra pestaña');
  assert.equal(await editor.save(), false);
  editor.resolveRemote('keep-local');
  transport.save = save;
  await editor.save();
  assert.equal(requests[0].expected_revision, 5);
  assert.equal(requests[0].content.title, 'Mi edición');
});

test('conflict without current response requires host refresh and explicit resolution', async () => {
  const { editor, transport } = setup();
  transport.save = async () => { throw { status: 412 }; };
  editor.edit('title', 'Local');
  await editor.save();
  assert.equal(editor.snapshot().conflict, true);
  assert.equal(editor.resolveRemote('keep-local'), false);
  editor.receive({ ...initial(), revision: 2, content: { ...content(), title: 'Remoto' } });
  assert.equal(editor.snapshot().draft.title, 'Local');
  editor.resolveRemote('use-remote');
  assert.equal(editor.snapshot().draft.title, 'Remoto');
  assert.equal(editor.snapshot().dirty, false);
});

test('refresh never silently replaces even clean teacher text', () => {
  const { editor } = setup();
  editor.receive({ ...initial(), revision: 2, content: { ...content(), objective: 'Cambió' } });
  assert.equal(editor.snapshot().draft.objective, 'Comparar');
  assert.equal(editor.snapshot().conflict, true);
});

test('approved snapshot survives editing and edited draft loses approved status', async () => {
  const { editor } = setup();
  assert.equal(await editor.approve(true), true);
  assert.equal(editor.snapshot().isApproved, true);
  editor.edit('title', 'Nueva propuesta');
  assert.equal(editor.snapshot().isApproved, false);
  assert.equal(editor.snapshot().approved.content.title, 'Actividad');
});

test('approval requires explicit review, saved changes, and sources', async () => {
  const { editor, requests } = setup();
  assert.equal(await editor.approve(false), false);
  editor.edit('title', 'Sin guardar');
  assert.equal(await editor.approve(true), false);
  assert.equal(requests.length, 0);
  const noSources = createActivityEditor({ ...initial(), content: { ...content(), source_ids: [] } }, { approve: () => assert.fail('Approval must not be requested') });
  assert.equal(await noSources.approve(true), false);
});

test('editing during approval preserves text and only approves the reviewed snapshot', async () => {
  const { editor, transport } = setup();
  const wait = deferred();
  transport.approve = () => wait.promise;
  const approving = editor.approve(true);
  editor.edit('steps', ['Cambio posterior']);
  wait.resolve({ ...initial(), revision: 2, status: 'approved', approved: { revision: 2, content: content() } });
  assert.equal(await approving, true);
  assert.deepEqual(editor.snapshot().draft.steps, ['Cambio posterior']);
  assert.deepEqual(editor.snapshot().approved.content.steps, ['Observar']);
  assert.equal(editor.snapshot().isApproved, false);
});

test('failed approval never marks draft approved', async () => {
  const { editor, transport } = setup();
  transport.approve = async () => { throw { status: 403 }; };
  await editor.approve(true);
  assert.equal(editor.snapshot().isApproved, false);
  assert.equal(editor.snapshot().approved, null);
  assert.match(editor.snapshot().error, /No se pudo confirmar la aprobación/);
});

test('invalid server reply preserves the unsaved draft', async () => {
  for (const response of [null, { ...initial(), id: 'someone-else', revision: 2 }, { ...initial(), revision: 2, content: { ...content(), title: 'Servidor reemplazó texto' } }]) {
    const { editor, transport } = setup();
    transport.save = async () => response;
    editor.edit('title', 'Texto docente');
    assert.equal(await editor.save(), false);
    assert.equal(editor.snapshot().draft.title, 'Texto docente');
    assert.equal(editor.snapshot().saved.revision, 1);
  }
});

test('newer remote version arriving during save still requires comparison', async () => {
  const { editor, transport } = setup();
  const wait = deferred();
  transport.save = () => wait.promise;
  editor.edit('title', 'Local');
  const saving = editor.save();
  editor.receive({ ...initial(), revision: 8, content: { ...content(), title: 'Remoto' } });
  wait.resolve({ ...initial(), revision: 2, content: { ...content(), title: 'Local' } });
  await saving;
  assert.equal(editor.snapshot().remote.revision, 8);
  assert.equal(editor.snapshot().draft.title, 'Local');
  assert.equal(editor.snapshot().conflict, true);
});

test('caller mutations cannot alter internal drafts or approval snapshots', () => {
  const source = initial();
  const editor = createActivityEditor(source, {});
  source.content.steps.push('Mutation');
  editor.snapshot().draft.steps.push('Mutation');
  assert.deepEqual(editor.snapshot().draft.steps, ['Observar']);
});

test('recovery download contains exact local text and is always labeled draft', () => {
  const { editor } = setup();
  editor.edit('title', 'Sin conexión');
  const recovery = JSON.parse(editor.recoveryJSON());
  assert.equal(recovery.content.title, 'Sin conexión');
  assert.equal(recovery.base_revision, 1);
  assert.equal(recovery.status, 'draft');
});

test('switching documents cannot replace an unsaved draft', () => {
  const { editor } = setup();
  editor.edit('title', 'Mi texto');
  assert.equal(editor.receive({ ...initial(), id: 'another' }), false);
  assert.equal(editor.snapshot().draft.title, 'Mi texto');
  assert.equal(editor.snapshot().saved.id, 'draft-1');
});

test('stale refresh cannot roll back the server revision', async () => {
  const { editor } = setup();
  editor.edit('title', 'Guardado');
  await editor.save();
  assert.equal(editor.receive(initial()), false);
  assert.equal(editor.snapshot().saved.revision, 2);
  assert.equal(editor.snapshot().conflict, false);
});

test('save response cannot grant approval', async () => {
  const { editor, transport } = setup();
  const edited = { ...content(), title: 'Mi texto' };
  transport.save = async () => ({ ...initial(), revision: 2, content: edited, status: 'approved', approved: { revision: 2, content: edited } });
  editor.edit('title', 'Mi texto');
  assert.equal(await editor.save(), false);
  assert.equal(editor.snapshot().isApproved, false);
  assert.equal(editor.snapshot().approved, null);
});

test('out-of-order refresh keeps the newest comparison candidate', () => {
  const { editor } = setup();
  editor.receive({ ...initial(), revision: 8 });
  assert.equal(editor.receive({ ...initial(), revision: 3 }), false);
  assert.equal(editor.snapshot().remote.revision, 8);
});

test('approval may confirm the current content revision without incrementing it', async () => {
  const { editor, transport } = setup();
  transport.approve = async () => ({ ...initial(), status: 'approved', approved: { revision: 1, content: content() } });
  assert.equal(await editor.approve(true), true);
  assert.equal(editor.snapshot().isApproved, true);
});

test('non-Error network rejection still produces a visible failure', async () => {
  const { editor, transport } = setup();
  transport.save = async () => { throw null; };
  editor.edit('title', 'Texto protegido');
  assert.equal(await editor.save(), false);
  assert.match(editor.snapshot().error, /Tu texto sigue aquí/);
  assert.equal(editor.snapshot().draft.title, 'Texto protegido');
});

test('matching refresh during save clears comparison and its stale error after confirmation', async () => {
  const { editor, transport } = setup();
  const wait = deferred();
  transport.save = () => wait.promise;
  editor.edit('title', 'Enviado');
  const saving = editor.save();
  const result = { ...initial(), revision: 2, content: { ...content(), title: 'Enviado' } };
  editor.receive(result);
  wait.resolve(result);
  await saving;
  assert.equal(editor.snapshot().conflict, false);
  assert.equal(editor.snapshot().error, null);
});

test('reactive-style Proxy props can initialize and refresh without losing text', () => {
  const original = initial();
  const proxy = new Proxy(original, {});
  const editor = createActivityEditor(proxy, {});
  editor.edit('title', 'Texto local');
  editor.receive(new Proxy({ ...initial(), revision: 2 }, {}));
  assert.equal(editor.snapshot().draft.title, 'Texto local');
  assert.equal(original.content.title, 'Actividad');
});
