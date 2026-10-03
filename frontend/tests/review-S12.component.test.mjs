import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { uncertainInterpretation } from '../src/features/review/review-fixture.mjs'

const dependencyRoot = resolve(process.env.REVIEW_NODE_MODULES ?? 'frontend/node_modules')
const dependencies = createRequire(join(dependencyRoot, '../package.json'))
const { Window } = await import(pathToFileURL(dependencies.resolve('happy-dom')).href)
const window = new Window()
for (const key of ['window', 'document', 'Node', 'Element', 'HTMLElement', 'SVGElement']) globalThis[key] = key === 'window' ? window : window[key]
const vuePath = dependencies.resolve('vue')
const vue = await import(pathToFileURL(vuePath).href)
const { parse, compileScript } = dependencies('@vue/compiler-sfc')
const directory = await mkdtemp(join(process.env.AULALISTA_SCRATCH_DIR ?? tmpdir(), 'review-S12-'))
const filename = fileURLToPath(new URL('../src/features/review/UploadReview.vue', import.meta.url))
const { descriptor, errors } = parse(await readFile(filename, 'utf8'), { filename })
assert.deepEqual(errors, [])
const compiled = compileScript(descriptor, { id: 's12-test', inlineTemplate: true }).content
  .replaceAll(/(['"])vue\1/g, JSON.stringify(pathToFileURL(vuePath).href))
  .replace("'./review-model.mjs'", JSON.stringify(new URL('../src/features/review/review-model.mjs', import.meta.url).href))
await writeFile(join(directory, 'component.mjs'), compiled)
const Component = (await import(pathToFileURL(join(directory, 'component.mjs')).href)).default
const mount = props => {
  const host = document.createElement('div')
  document.body.append(host)
  const app = vue.createApp(Component, props)
  app.mount(host)
  return { host, close() { app.unmount(); host.remove() } }
}
after(async () => { await rm(directory, { recursive: true, force: true }); await window.happyDOM.close() })

test('renders actual Vue source links, explicit uncertainty and fixture label; hands off typed corrections', async () => {
  let result
  const { host, close } = mount({ initialInterpretation: structuredClone(uncertainInterpretation), fixture: true, onContinue: value => { result = value } })
  try {
    assert.match(host.textContent, /Demostración con datos de ejemplo/)
    assert.match(host.textContent, /Propuesta por confirmar/)
    assert.match(host.textContent, /No se pudo determinar/)
    assert.match(host.textContent, /no aprueba ni publica/)
    for (const anchor of host.querySelectorAll('a')) {
      const target = document.getElementById(anchor.hash.slice(1))
      assert.ok(target)
      assert.match(target.textContent, /Cuidamos el agua/)
    }
    const questions = [...host.querySelectorAll('.question')]
    assert.equal(questions.length, 3)
    const level = questions.find(el => el.textContent.includes('nivel educativo')).querySelector('input')
    level.value = 'Secundaria'
    level.dispatchEvent(new window.Event('input', { bubbles: true }))
    await vue.nextTick()
    host.querySelector('button').click()
    assert.equal(result.answers.nivel_educativo, 'Secundaria')
    assert.equal(result.interpretation.fields.find(f => f.key === 'nivel_educativo').value, null)
    assert.equal(result.interpretation.draft.approval_status, 'pending')
    assert.equal(host.querySelectorAll('input[required]').length, 0)
  } finally { close() }
})

test('escapes source text instead of injecting document HTML', () => {
  const data = structuredClone(uncertainInterpretation)
  data.source_segments[0].text = '<img src=x onerror="alert(1)">'
  const { host, close } = mount({ initialInterpretation: data })
  try {
    assert.equal(host.querySelector('img'), null)
    assert.match(host.querySelector('blockquote').textContent, /<img/)
    assert.doesNotMatch(host.textContent, /Demostración con datos/)
  } finally { close() }
})

test('upload failure renders recovery and leaves the selected PDF visible', async () => {
  const { host, close } = mount({ upload: async () => { throw new Error('private network text') } })
  try {
    const input = host.querySelector('input[type=file]')
    Object.defineProperty(input, 'files', { configurable: true, value: [new File(['%PDF'], 'clase.pdf', { type: 'application/pdf' })] })
    input.dispatchEvent(new window.Event('change', { bubbles: true }))
    await vue.nextTick()
    host.querySelector('button').click()
    await new Promise(resolve => setImmediate(resolve))
    await vue.nextTick()
    assert.match(host.querySelector('[role=alert]').textContent, /otra copia/)
    assert.match(host.textContent, /clase.pdf/)
    assert.doesNotMatch(host.textContent, /private network/)
    assert.equal(host.querySelector('button').textContent.trim(), 'Volver a intentar')
    assert.equal(host.querySelector('button').disabled, false)
  } finally { close() }
})
