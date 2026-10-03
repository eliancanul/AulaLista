import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { resolve, join, dirname } from 'node:path'
import { pathToFileURL } from 'node:url'
import { tmpdir } from 'node:os'
import { createInterpretationUploader, createReviewSession } from '../src/features/review/review-model.mjs'
import { uncertainInterpretation } from '../src/features/review/review-fixture.mjs'

const clientPath = resolve(process.env.REVIEW_API_CLIENT ?? 'frontend/src/api/client.ts')
const dependencies = createRequire(resolve(process.env.REVIEW_NODE_MODULES ?? 'frontend/node_modules', '../package.json'))
const ts = dependencies('typescript')
const directory = await mkdtemp(join(process.env.AULALISTA_SCRATCH_DIR ?? tmpdir(), 'review-S12-client-'))
for (const [source, target] of [[resolve(dirname(clientPath), '../contracts/interpretation.ts'), 'contract.mjs'], [clientPath, 'client.mjs']]) {
  const result = ts.transpileModule(await readFile(source, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
    .replace("'../contracts/interpretation'", "'./contract.mjs'")
  await writeFile(join(directory, target), result)
}
const { createAPI } = await import(pathToFileURL(join(directory, 'client.mjs')).href)
after(() => rm(directory, { recursive: true, force: true }))

test('actual S11 client sends multipart, session credentials, CSRF and signal into S12 review', async () => {
  let called = 0
  const api = createAPI({ csrf: () => 'test-csrf', fetch: async (path, options) => {
    called++
    assert.equal(path, '/api/v1/interpretations')
    assert.equal(options.method, 'POST')
    assert.equal(options.credentials, 'same-origin')
    assert.equal(options.headers.get('X-CSRFToken'), 'test-csrf')
    assert.equal(options.headers.has('Content-Type'), false)
    assert.equal(options.cache, 'no-store')
    assert.equal(options.redirect, 'error')
    assert.equal(options.signal.aborted, false)
    assert.deepEqual([...options.body.keys()], ['file'])
    assert.equal(options.body.get('file').name, 'material.pdf')
    const response = structuredClone(uncertainInterpretation)
    response.draft.id = 'persisted-fixture-draft'
    return new Response(JSON.stringify(response), { status: 201, headers: { 'Content-Type': 'application/json' } })
  } })
  const session = createReviewSession({ upload: createInterpretationUploader(api) })
  session.selectFile(new File(['%PDF-fixture'], 'material.pdf', { type: 'application/pdf' }))
  assert.equal(await session.submit(), true)
  assert.equal(called, 1)
  assert.equal(session.state.interpretation.draft.id, 'persisted-fixture-draft')
  assert.equal(session.state.interpretation.draft.approval_status, 'pending')
})

test('missing CSRF never sends an upload and exposes session recovery', async () => {
  const api = createAPI({ csrf: () => null, fetch: async () => { assert.fail('Must not send without CSRF') } })
  const session = createReviewSession({ upload: createInterpretationUploader(api) })
  session.selectFile(new File(['%PDF-fixture'], 'material.pdf', { type: 'application/pdf' }))
  assert.equal(await session.submit(), false)
  assert.equal(session.state.error.action, 'sign-in')
  assert.equal(session.state.error.retryable, false)
})
