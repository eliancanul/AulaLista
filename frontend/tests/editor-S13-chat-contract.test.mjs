import test from 'node:test';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createActivityEditor } from '../src/features/editor/activityEditor.ts';

const chatRoot = process.env.S13_CHAT_DIR
  ? pathToFileURL(`${resolve(process.env.S13_CHAT_DIR)}/`)
  : new URL('../src/features/chat/', import.meta.url);
const { createTeacherChat } = await import(new URL('chat.ts', chatRoot));
const { createEditPreview } = await import(new URL('editPreview.ts', chatRoot));
const content = () => ({ title: 'Actividad', objective: 'Comparar', materials: ['Papel'],
  steps: ['Observar'], assessment: 'Explicar', source_ids: ['fuente-1'] });
const saved = () => ({ id: 'documento-1', revision: 3, status: 'draft', content: content(), approved: null });
const sources = [{ id: 'fuente-1', text: 'Materiales: papel y lápiz.', page: 1 }];
const context = editor => ({ id: editor.snapshot().saved.id,
  revision: editor.snapshot().saved.revision, content: editor.snapshot().draft });
const proposal = editor => ({ id: 'propuesta-fixture', base: context(editor),
  changes: { materials: ['papel y lápiz'] }, source_ids: ['fuente-1'] });
const s16ProposalFixture = () => ({ draft_id: 'documento-1', expected_revision: 3,
  changes: { materials: ['papel y lápiz'] }, source_ids: ['fuente-1'], requires_acceptance: true,
  label: 'Propuesta basada en fragmentos. Revisa y acepta los cambios antes de guardarlos.' });
const reply = proposals => ({ interpretation_id: 'documento-1', message: 'Revisa estos fragmentos.',
  source_ids: ['fuente-1'], proposals, mode: 'source_lookup', applies_changes: false,
  citations: [{ source_id: 'fuente-1', page: 1, quote: sources[0].text }], provider_status: 'not_used' });
const editor = initial => createActivityEditor(initial ?? saved(), {
  save: async () => assert.fail('La revisión de propuesta no debe guardar'),
  approve: async () => assert.fail('La revisión de propuesta no debe aprobar'),
});

test('S13/S17: una consulta sin propuestas conserva el borrador', async () => {
  const state = editor();
  const before = state.snapshot();
  const chat = createTeacherChat('documento-1', sources, async () => reply([]));
  chat.setInput('¿Qué materiales indica la fuente?');
  assert.equal(await chat.send(), true);
  assert.equal(chat.snapshot().turns[0].answer, 'Revisa estos fragmentos.');
  assert.deepEqual(state.snapshot(), before);
});

test('brecha S16/S17: una propuesta con la forma publicada se rechaza en chat', async () => {
  const chat = createTeacherChat('documento-1', sources, async () => ({
    ...reply([s16ProposalFixture()]), provider_status: 'validated_extractive',
  }));
  chat.setInput('¿Qué materiales indica la fuente?');
  assert.equal(await chat.send(), false);
  assert.equal(chat.snapshot().status, 'failed');
  assert.equal(chat.snapshot().retryable, false);
  assert.deepEqual(chat.snapshot().turns, []);
  assert.equal(chat.snapshot().input, '¿Qué materiales indica la fuente?');
});

test('brecha S16/S17: la propuesta HTTP no es un EditProposal con base', () => {
  assert.throws(() => createEditPreview(s16ProposalFixture(), ['fuente-1']), /propuesta no es válida/);
});

test('S13/S17: aceptar emite intención una sola vez sin mutar; rechazar no edita', () => {
  const state = editor();
  const before = state.snapshot();
  const preview = createEditPreview(proposal(state), ['fuente-1']);
  const intent = preview.accept(context(state));
  assert.deepEqual(intent.changes, { materials: ['papel y lápiz'] });
  assert.equal(preview.accept(context(state)), null);
  assert.deepEqual(state.snapshot(), before);
  const rejected = createEditPreview(proposal(state), ['fuente-1']);
  assert.equal(rejected.reject(), true);
  assert.equal(rejected.accept(context(state)), null);
  assert.deepEqual(state.snapshot(), before);
});

test('S13/S17: otra revisión, otro documento y edición local bloquean aceptación', () => {
  const state = editor();
  const base = context(state);
  for (const current of [{ ...base, revision: 4 }, { ...base, id: 'otro' },
    { ...base, content: { ...base.content, title: 'Texto nuevo sin guardar' } }]) {
    const preview = createEditPreview(proposal(state), ['fuente-1']);
    assert.equal(preview.isCurrent(current), false);
    assert.equal(preview.accept(current), null);
  }
  assert.equal(state.snapshot().draft.title, 'Actividad');
});

test('S13/S17: aplicar campos explícitos invalida aprobación y conserva copia aprobada', () => {
  const state = editor({ ...saved(), status: 'approved', approved: { revision: 3, content: content() } });
  const preview = createEditPreview(proposal(state), ['fuente-1']);
  const intent = preview.accept(context(state));
  assert.ok(intent);
  for (const [key, value] of Object.entries(intent.changes)) state.edit(key, value);
  assert.equal(state.snapshot().dirty, true);
  assert.equal(state.snapshot().isApproved, false);
  assert.deepEqual(state.snapshot().draft.materials, ['papel y lápiz']);
  assert.deepEqual(state.snapshot().approved.content.materials, ['Papel']);
  assert.deepEqual(JSON.parse(state.recoveryJSON()).content.materials, ['papel y lápiz']);
  assert.equal(JSON.parse(state.recoveryJSON()).status, 'draft');
});

test('S13/S17: aplicar una intención vuelve obsoleta otra con la misma base', () => {
  const state = editor();
  const first = createEditPreview(proposal(state), ['fuente-1']);
  const second = createEditPreview({ ...proposal(state), id: 'segunda-fixture' }, ['fuente-1']);
  const intent = first.accept(context(state));
  state.edit('materials', intent.changes.materials);
  assert.equal(second.accept(context(state)), null);
  assert.deepEqual(state.snapshot().draft.materials, ['papel y lápiz']);
});

test('brecha de host: preview no conoce el conflicto remoto de S13', () => {
  const state = editor();
  const preview = createEditPreview(proposal(state), ['fuente-1']);
  state.receive({ ...saved(), revision: 4, content: { ...content(), title: 'Otra pestaña' } });
  assert.equal(state.snapshot().conflict, true);
  assert.equal(preview.isCurrent(context(state)), true);
  assert.ok(preview.accept(context(state)));
  assert.equal(state.snapshot().draft.title, 'Actividad');
});

test('brecha de host: preview no conoce una aprobación pendiente de S13', async () => {
  let finish;
  const state = createActivityEditor(saved(), {
    approve: () => new Promise(resolve => { finish = resolve; }),
  });
  const preview = createEditPreview(proposal(state), ['fuente-1']);
  const approval = state.approve(true);
  assert.equal(state.snapshot().pending, 'approve');
  assert.ok(preview.accept(context(state)));
  finish({ ...saved(), status: 'approved', approved: { revision: 3, content: content() } });
  assert.equal(await approval, true);
  assert.deepEqual(state.snapshot().draft.materials, ['Papel']);
});

test('brecha de host: comparar cinco campos no verifica cambios de fuentes', () => {
  const state = editor();
  const preview = createEditPreview(proposal(state), ['fuente-1']);
  state.edit('source_ids', ['otra-fuente']);
  assert.equal(preview.isCurrent(context(state)), true);
  assert.ok(preview.accept(context(state)));
  assert.deepEqual(state.snapshot().draft.source_ids, ['otra-fuente']);
});
