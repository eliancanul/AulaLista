import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { createActivityFile, downloadActivityFile } from '../src/features/export/activityExport.ts';

const fixture = () => JSON.parse(readFileSync(new URL('../src/features/export/fixtures/activity.json', import.meta.url), 'utf8'));

test('S14 exports exact current teacher edits and referenced source context as a draft', () => {
  const { state, source } = fixture();
  state.draft.objective = '  Mi objetivo editado\ncon dos líneas  ';
  const before = structuredClone({ state, source });
  const file = createActivityFile(state, source);
  assert.equal(file.filename, 'aulalista-actividad-borrador-base-3.html');
  assert.equal(file.mime, 'text/html;charset=utf-8');
  assert.ok(file.content.includes('<p>  Mi objetivo editado\ncon dos líneas  </p>'));
  for (const value of [state.draft.title, state.draft.assessment, ...state.draft.steps, ...state.draft.materials, source.document_id, source.source_segments[0].text]) {
    assert.ok(file.content.includes(value), `missing ${value}`);
  }
  assert.match(file.content, /Borrador para revisión humana/);
  assert.match(file.content, /aunque no esté guardado/);
  assert.match(file.content, /Página 1/);
  assert.deepEqual({ state, source }, before);
});

test('S14 explicit approved export selects the old snapshot, never concurrent draft edits', () => {
  const { state, source } = fixture();
  state.approved = { revision: 2, content: structuredClone(state.draft) };
  state.approved.content.title = 'Texto aprobado anteriormente';
  state.draft.title = 'CAMBIO AÚN NO APROBADO';
  const approved = createActivityFile(state, source, 'approved');
  assert.match(approved.content, /Texto aprobado anteriormente/);
  assert.doesNotMatch(approved.content, /CAMBIO AÚN NO APROBADO/);
  assert.match(approved.content, /Revisión aprobada 2/);
  assert.match(approved.content, /La aprobación no implica publicación/);
  assert.equal(approved.filename, 'aulalista-actividad-aprobada-2.html');
  const draft = createActivityFile(state, source);
  assert.match(draft.content, /CAMBIO AÚN NO APROBADO/);
  assert.match(draft.content, /Borrador para revisión humana/);
});

test('S14 approval cannot be fabricated from a missing snapshot', () => {
  const { state, source } = fixture();
  assert.throws(() => createActivityFile(state, source, 'approved'), /Todavía no hay una versión aprobada/);
  assert.throws(() => createActivityFile(state, source, 'published'), /Elige una copia/);
});

test('S14 missing evidence is visible in a draft and blocks an approved copy', () => {
  const { state, source } = fixture();
  state.draft.source_ids.push('referencia-ausente');
  state.approved = { revision: 3, content: structuredClone(state.draft) };
  assert.match(createActivityFile(state, source).content, /No hay suficiente fuente local/);
  assert.match(createActivityFile(state, source).content, /Falta el fragmento de la referencia referencia-ausente/);
  assert.throws(() => createActivityFile(state, source, 'approved'), /Falta contenido esencial o una fuente/);
  state.draft.source_ids = [];
  assert.match(createActivityFile(state, source).content, /No se indicaron referencias/);
});

test('S14 blanks stay pending without inventing content or school level', () => {
  const { state, source } = fixture();
  state.draft.title = '1ro / 3ro';
  state.draft.objective = '';
  state.draft.steps = [];
  state.draft.materials = [];
  state.draft.assessment = '';
  const { content } = createActivityFile(state, source);
  assert.match(content, /Falta contenido esencial/);
  assert.match(content, /Pendiente de completar/);
  assert.match(content, /Pendiente de confirmar/);
  assert.doesNotMatch(content, /primaria|secundaria/i);
});

test('S14 all user text is escaped and cannot create remote assets or executable markup', () => {
  const { state, source } = fixture();
  const attack = '<img src="https://example.invalid/x" onerror="alert(1)"><script>x()</script>&\'';
  state.draft.title = attack;
  state.draft.objective = attack;
  state.draft.assessment = attack;
  state.draft.materials = [attack];
  state.draft.steps = [attack];
  state.draft.source_ids = [attack];
  source.document_id = attack;
  source.source_segments = [{ id: attack, text: attack, page: 7 }];
  const { content } = createActivityFile(state, source);
  assert.equal(content.split('&lt;img src=&quot;https://example.invalid/x&quot;').length - 1, 9);
  assert.doesNotMatch(content, /<script|<img|<iframe|<link|<a\s|@import|url\(/i);
  assert.match(content, /default-src 'none'/);
});

test('S14 boundary rejects malformed content, pages, duplicate references and revision', () => {
  const invalid = [
    ({ state }) => { state.draft.steps = 'not an array'; },
    ({ state }) => { state.draft.materials = [null]; },
    ({ state }) => { state.saved.revision = -1; },
    ({ source }) => { source.document_id = ''; },
    ({ source }) => { source.source_segments[0].page = 0; },
    ({ source }) => { source.source_segments[0].text = ' '; },
    ({ source }) => { source.source_segments.push(source.source_segments[0]); },
  ];
  for (const mutate of invalid) {
    const input = fixture();
    mutate(input);
    assert.throws(() => createActivityFile(input.state, input.source), Error);
  }
});

test('S14 fixture is generated by the real exporter and declares synthetic origin', () => {
  const { state, source } = fixture();
  const expected = readFileSync(new URL('../src/features/export/fixtures/activity.html', import.meta.url), 'utf8');
  assert.equal(createActivityFile(state, source, 'draft', true).content, expected);
  assert.match(expected, /Ejemplo sintético para probar el software/);
  assert.match(expected, /no genera actividades, no guarda cambios en AulaLista y no sincroniza/);
  assert.match(expected, /imágenes, videos, anexos, enlaces y el PDF original no se incluyen/);
  assert.match(expected, /@media print/);
});

test('S14 export works with network calls unavailable', () => {
  const { state, source } = fixture();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = () => { throw new Error('Network disabled'); };
  try {
    assert.match(createActivityFile(state, source).content, /Compartimos una hoja/);
  } finally { globalThis.fetch = originalFetch; }
});

test('S14 download uses local Blob, releases its URL, and reports browser failure without throwing', async () => {
  const original = { document: globalThis.document, create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  const seen = [];
  let anchor;
  let fail = false;
  URL.createObjectURL = blob => { assert.equal(blob.type, 'text/html;charset=utf-8'); seen.push('blob'); return 'blob:local'; };
  URL.revokeObjectURL = url => { seen.push(url); };
  globalThis.document = {
    createElement() { anchor = { click() { if (fail) throw new Error('blocked'); seen.push('click'); }, remove() { seen.push('remove'); } }; return anchor; },
    body: { append() { seen.push('append'); } },
  };
  try {
    const { state, source } = fixture();
    const file = createActivityFile(state, source);
    assert.equal(downloadActivityFile(file).ok, true);
    assert.equal(anchor.href, 'blob:local');
    assert.equal(anchor.download, file.filename);
    fail = true;
    const result = downloadActivityFile(file);
    assert.equal(result.ok, false);
    assert.match(result.message, /Tu actividad sigue en el editor/);
    await new Promise(resolve => setTimeout(resolve, 1100));
    assert.deepEqual(seen, ['blob', 'append', 'click', 'remove', 'blob', 'append', 'remove', 'blob:local', 'blob:local']);
  } finally {
    globalThis.document = original.document;
    URL.createObjectURL = original.create;
    URL.revokeObjectURL = original.revoke;
  }
});
