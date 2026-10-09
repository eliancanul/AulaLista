import test from 'node:test'
import assert from 'node:assert/strict'
import { createInterpretationUploader, createReviewSession, MAX_PDF_BYTES, questionsFor, readInterpretation, uploadError, validateFile } from '../src/features/review/review-model.mjs'
import { uncertainInterpretation } from '../src/features/review/review-fixture.mjs'

const fixture = () => structuredClone(uncertainInterpretation)
const pdf = () => new File(['%PDF-demo'], 'material.pdf', { type: 'application/pdf' })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('canonical fixture keeps grade suggested and level unknown', () => {
  const result = readInterpretation(fixture())
  assert.equal(result.fields.find(f => f.key === 'grado').status, 'suggested')
  assert.equal(result.fields.find(f => f.key === 'nivel_educativo').value, null)
  assert.equal(result.draft.approval_status, 'pending')
  assert.deepEqual(questionsFor(result).map(q => q.key), ['grado', 'nivel_educativo', 'evaluacion'])
})

test('detaches source data and rejects dangling references, missing fields and false known values', () => {
  const input = fixture()
  const result = readInterpretation(input)
  result.source_segments[0].text = 'Changed'
  assert.notEqual(input.source_segments[0].text, 'Changed')
  for (const mutate of [
    v => { v.fields[0].evidence_ids = ['missing'] },
    v => { v.fields[0].evidence_ids = [] },
    v => { v.fields[0].value = null },
    v => { v.fields.pop() },
    v => { v.fields[1].value = 'Unsupported' },
    v => { v.source_segments.push(v.source_segments[0]) },
    v => { v.fields[1] = v.fields[0] },
    v => { v.source_segments[0].page = 0 },
    v => { v.draft.source_ids = ['missing'] },
    v => { v.diagnostics.source_warnings = null },
  ]) {
    const invalid = fixture()
    mutate(invalid)
    assert.throws(() => readInterpretation(invalid), { code: 'invalid_response' })
  }
})

test('validates file type, emptiness, configured size and a missing browser MIME', () => {
  assert.equal(validateFile(pdf()), null)
  assert.equal(validateFile({ name: 'MATERIAL.PDF', size: 1, type: '' }), null)
  assert.match(validateFile({ name: 'x.pdf', size: 0, type: '' }), /vacío/)
  assert.match(validateFile({ name: 'x.txt', size: 1, type: '' }), /PDF/)
  assert.match(validateFile({ name: 'x.pdf', size: MAX_PDF_BYTES + 1, type: '' }), /25 MB/)
  assert.match(validateFile({ name: 'x.pdf', size: 3 * 1024 * 1024, type: '' }, 2 * 1024 * 1024), /2 MB/)
})

test('upload transitions idle to ready to submitting to review without fabricating intermediate progress', async () => {
  const response = deferred()
  const phases = []
  let calls = 0
  const session = createReviewSession({ upload: async file => { calls++; assert.equal(file.name, 'material.pdf'); return response.promise }, onChange: state => phases.push(state.phase) })
  assert.equal(session.state.phase, 'idle')
  assert.equal(session.selectFile(pdf()), true)
  const submit = session.submit()
  assert.equal(await session.submit(), false)
  assert.equal(session.selectFile(pdf()), false)
  response.resolve(fixture())
  assert.equal(await submit, true)
  assert.equal(calls, 1)
  assert.deepEqual(phases, ['ready', 'submitting', 'review'])
  assert.equal(session.state.interpretation.document_id, 'demostracion-s12')
})

test('manual retry retains the selected file after a connection error', async () => {
  let calls = 0
  const file = pdf()
  const session = createReviewSession({ upload: async () => { if (++calls === 1) throw new TypeError('secret transport detail'); return fixture() } })
  session.selectFile(file)
  assert.equal(await session.submit(), false)
  assert.equal(calls, 1)
  assert.equal(session.state.file, file)
  assert.equal(session.state.error.retryable, true)
  assert.doesNotMatch(session.state.error.message, /secret/)
  assert.match(session.state.error.message, /otra copia/)
  assert.equal(await session.submit(), true)
})

test('stopping does not accept a late response or override the next upload', async () => {
  const old = deferred()
  let calls = 0
  let oldSignal
  const session = createReviewSession({ upload: async (_, { signal }) => { if (++calls === 1) { oldSignal = signal; return old.promise } const next = fixture(); next.document_id = 'next'; return next } })
  session.selectFile(pdf())
  const first = session.submit()
  session.stopWaiting()
  assert.equal(oldSignal.aborted, true)
  assert.equal(session.state.phase, 'stopped')
  assert.equal(await session.submit(), true)
  old.resolve(fixture())
  assert.equal(await first, false)
  assert.equal(session.state.interpretation.document_id, 'next')
})

test('unmount discards asynchronous results', async () => {
  const response = deferred()
  const session = createReviewSession({ upload: () => response.promise })
  session.selectFile(pdf())
  const pending = session.submit()
  session.dispose()
  response.resolve(fixture())
  assert.equal(await pending, false)
  assert.equal(session.state.interpretation, null)
})

test('invalid response stays an error without exposing fabricated review data', async () => {
  const session = createReviewSession({ upload: async () => ({ document_id: 'x' }) })
  session.selectFile(pdf())
  assert.equal(await session.submit(), false)
  assert.equal(session.state.phase, 'error')
  assert.equal(session.state.interpretation, null)
  assert.equal(session.state.error.retryable, false)
})

test('teacher answers remain separate from source and handoff never approves', () => {
  const original = fixture()
  const session = createReviewSession({ initialInterpretation: original })
  session.answer('nivel_educativo', 'Secundaria')
  session.answer('grado', '3ro')
  session.answer('proposito', 'Mi propósito revisado')
  assert.equal(session.selectFile(pdf()), false)
  const handoff = session.handoff()
  assert.equal(handoff.answers.nivel_educativo, 'Secundaria')
  assert.equal(handoff.interpretation.fields.find(f => f.key === 'nivel_educativo').value, null)
  assert.equal(handoff.interpretation.draft.approval_status, 'pending')
  assert.deepEqual(handoff.interpretation, original)
  handoff.answers.grado = 'Changed'
  assert.equal(session.state.answers.grado, '3ro')
})

test('missing adapter never substitutes fixture behavior', async () => {
  const session = createReviewSession()
  session.selectFile(pdf())
  assert.equal(await session.submit(), false)
  assert.equal(session.state.interpretation, null)
  assert.match(session.state.error.message, /todavía no está disponible/)
})

test('authentication and malformed files are not blindly retried', async () => {
  for (const status of [401, 403, 413, 415, 422]) {
    let calls = 0
    const session = createReviewSession({ upload: async () => { calls++; throw { status } } })
    session.selectFile(pdf())
    await session.submit()
    assert.equal(session.state.error.retryable, false)
    assert.equal(await session.submit(), false)
    assert.equal(calls, 1)
  }
  assert.equal(uploadError({ status: 503 }).retryable, true)
  assert.equal(uploadError({ status: 504 }).retryable, true)
})

test('adapter forwards the file and abort signal to S11 without bypassing identity or CSRF', async () => {
  const file = pdf()
  const signal = new AbortController().signal
  const upload = createInterpretationUploader({ createInterpretation: async (actualFile, actualSignal) => {
    assert.equal(actualFile, file)
    assert.equal(actualSignal, signal)
    return fixture()
  } })
  assert.equal((await upload(file, { signal })).document_id, 'demostracion-s12')
})
