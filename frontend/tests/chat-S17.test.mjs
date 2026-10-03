import assert from 'node:assert/strict';
import test from 'node:test';
import { createTeacherChat } from '../src/features/chat/chat.ts';
import { createEditPreview } from '../src/features/chat/editPreview.ts';

const sources = [{ id: 's1', text: 'Leer un cuento en equipo.', page: 2 }];
const response = (changes = {}) => ({ interpretation_id: 'doc1', message: 'Leer un cuento en equipo.',
  source_ids: ['s1'], proposals: [], mode: 'source_lookup', applies_changes: false, ...changes });
const current = () => ({ id: 'draft1', revision: 1, content: {
  title: 'Mi actividad', objective: 'Leer', materials: ['Un cuento'], steps: ['Leer'], assessment: 'Conversar',
} });
const proposal = (changes = {}) => ({ id: 'p1', base: current(), changes: { title: 'Lectura en equipo' }, source_ids: ['s1'], ...changes });
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

test('S17 sends the published request, preserves exact text and resolves source excerpts', async () => {
  let sent;
  const chat = createTeacherChat('doc1', sources, async value => { sent = value; return response(); });
  chat.setInput(' ¿Qué leo? ');
  assert.equal(await chat.send(), true);
  assert.deepEqual(sent, { interpretation_id: 'doc1', message: ' ¿Qué leo? ' });
  assert.deepEqual(chat.snapshot(), { input: '', status: 'idle', error: null, retryable: false,
    turns: [{ question: ' ¿Qué leo? ', answer: 'Leer un cuento en equipo.', sources }] });
});

test('S17 loading prevents duplicate requests and does not clear text typed while waiting', async () => {
  const pending = deferred();
  let calls = 0;
  const chat = createTeacherChat('doc1', sources, () => { calls++; return pending.promise; });
  chat.setInput('Pregunta inicial');
  const sent = chat.send();
  assert.equal(chat.snapshot().status, 'loading');
  chat.setInput('Pregunta siguiente');
  assert.equal(await chat.send(), false);
  pending.resolve(response());
  assert.equal(await sent, true);
  assert.equal(calls, 1);
  assert.equal(chat.snapshot().input, 'Pregunta siguiente');
});

test('S17 failure retains work and retry repeats failed question without overwriting new input', async () => {
  const requests = [];
  const chat = createTeacherChat('doc1', sources, async value => {
    requests.push(value.message);
    if (requests.length === 1) throw new Error('private server content');
    return response();
  });
  chat.setInput('Primera');
  assert.equal(await chat.send(), false);
  assert.equal(chat.snapshot().input, 'Primera');
  assert.equal(chat.snapshot().status, 'failed');
  assert.equal(chat.snapshot().retryable, true);
  assert.doesNotMatch(chat.snapshot().error, /private/);
  chat.setInput('Segunda');
  assert.equal(await chat.retry(), true);
  assert.deepEqual(requests, ['Primera', 'Primera']);
  assert.equal(chat.snapshot().input, 'Segunda');
});

for (const status of [401, 403, 404, 422]) {
  test(`S17 does not offer blind retry for HTTP ${status}`, async () => {
    const chat = createTeacherChat('doc1', sources, async () => { throw { status }; });
    chat.setInput('Pregunta');
    await chat.send();
    assert.equal(chat.snapshot().retryable, false);
    assert.equal(await chat.retry(), false);
    assert.equal(chat.snapshot().input, 'Pregunta');
  });
}

for (const invalid of [null, response({ interpretation_id: 'other' }), response({ source_ids: ['missing'] }),
  response({ applies_changes: true }), response({ proposals: [{ changes: { title: 'No' } }] })]) {
  test(`S17 rejects unsupported or ungrounded replies ${JSON.stringify(invalid)}`, async () => {
    const chat = createTeacherChat('doc1', sources, async () => invalid);
    chat.setInput('Mi pregunta');
    assert.equal(await chat.send(), false);
    assert.equal(chat.snapshot().retryable, false);
    assert.deepEqual(chat.snapshot().turns, []);
    assert.equal(chat.snapshot().input, 'Mi pregunta');
  });
}

test('S17 missing evidence is explicit and history survives later failure', async () => {
  let calls = 0;
  const chat = createTeacherChat('doc1', sources, async () => {
    if (calls++) throw { status: 503 };
    return response({ source_ids: [], message: 'No hay suficiente fuente local.' });
  });
  chat.setInput('Pregunta');
  await chat.send();
  chat.setInput('Otra');
  await chat.send();
  assert.equal(chat.snapshot().turns[0].answer, 'No hay suficiente fuente local.');
  assert.deepEqual(chat.snapshot().turns[0].sources, []);
  assert.equal(chat.snapshot().retryable, true);
});

test('S17 disposed chat ignores late replies and detached snapshots cannot mutate state', async () => {
  const pending = deferred();
  const chat = createTeacherChat('doc1', sources, () => pending.promise);
  chat.setInput('Pregunta');
  const sent = chat.send();
  chat.snapshot().input = 'Alterado';
  chat.dispose();
  pending.resolve(response());
  assert.equal(await sent, false);
  assert.equal(chat.snapshot().input, 'Pregunta');
  assert.deepEqual(chat.snapshot().turns, []);
});

test('S17 rejects empty and oversized input without transport', async () => {
  const chat = createTeacherChat('doc1', sources, async () => assert.fail('must not send'));
  for (const input of ['', '   ', 'x'.repeat(4001)]) {
    chat.setInput(input);
    assert.equal(await chat.send(), false);
  }
});

test('S17 preview never mutates activity and acceptance produces one detached edit intent', () => {
  const draft = current();
  const raw = proposal();
  const preview = createEditPreview(raw, ['s1']);
  raw.changes.title = 'Changed upstream';
  assert.deepEqual(preview.rows(), [{ key: 'title', label: 'Título', before: 'Mi actividad', after: 'Lectura en equipo' }]);
  assert.deepEqual(draft, current());
  assert.deepEqual(preview.accept(draft), { proposal_id: 'p1', base: current(), changes: { title: 'Lectura en equipo' } });
  assert.deepEqual(draft, current());
  assert.equal(preview.accept(draft), null);
  assert.equal(preview.reject(), false);
});

test('S17 rejection permanently discards proposal without activity changes', () => {
  const draft = current();
  const preview = createEditPreview(proposal(), ['s1']);
  assert.equal(preview.reject(), true);
  assert.equal(preview.accept(draft), null);
  assert.deepEqual(draft, current());
});

test('S17 unsaved edits, new revision and different activity each block acceptance', () => {
  for (const draft of [{ ...current(), id: 'other' }, { ...current(), revision: 2 },
    { ...current(), content: { ...current().content, objective: 'Mi edición sin guardar' } }]) {
    const preview = createEditPreview(proposal(), ['s1']);
    assert.equal(preview.isCurrent(draft), false);
    assert.equal(preview.accept(draft), null);
  }
});

test('S17 proposals cannot change authority or sources and require known evidence', () => {
  for (const changes of [{ status: 'approved' }, { source_ids: ['s1'] }, { title: null }, {},
    { materials: 'Una lista incorrecta' }, { title: 'Mi actividad' }]) {
    assert.throws(() => createEditPreview(proposal({ changes }), ['s1']));
  }
  assert.throws(() => createEditPreview(proposal({ source_ids: [] }), ['s1']));
  assert.throws(() => createEditPreview(proposal({ source_ids: ['unknown'] }), ['s1']));
});
