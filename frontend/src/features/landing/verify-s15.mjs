import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire, stripTypeScriptTypes } from 'node:module'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const harness = resolve(process.env.S15_FRONTEND_DIR || 'frontend')
const require = createRequire(resolve(harness, 'package.json'))
const { parse, compileScript, compileStyle } = require('@vue/compiler-sfc')
const { createSSRApp } = require('vue')
const { renderToString } = require('@vue/server-renderer')
const filename = new URL('./LandingPage.vue', import.meta.url)
const source = await readFile(filename, 'utf8')
const { descriptor, errors } = parse(source, { filename: filename.pathname })
assert.deepEqual(errors, [])
const script = compileScript(descriptor, { id: 's15-landing', inlineTemplate: true })
const vueModule = pathToFileURL(require.resolve('vue/dist/vue.runtime.esm-bundler.js')).href
const code = stripTypeScriptTypes(script.content, { mode: 'strip' })
  .replaceAll('from "vue"', `from ${JSON.stringify(vueModule)}`)
const { default: LandingPage } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const css = compileStyle({ source: descriptor.styles[0].content, filename: filename.pathname, id: 'data-v-s15-landing', scoped: true })
assert.deepEqual(css.errors, [])

const defaultHtml = await renderToString(createSSRApp(LandingPage))
assert.match(defaultHtml, /href="\/tutor\/imports\/new\/"/)
assert.equal((defaultHtml.match(/<a /g) || []).length, 1)
assert.match(defaultHtml, /primero iniciarás sesión/)
assert.match(defaultHtml, /aún no está habilitada/)
assert.doesNotMatch(defaultHtml, /Descarga o imprime/)
assert.match(defaultHtml, /debe aprobar y publicar/)
assert.match(defaultHtml, /interpretación asistida puede necesitar conexión/)

const exportHtml = await renderToString(createSSRApp(LandingPage, {
  entryHref: '/teacher/upload', exportsAvailable: true,
}))
assert.match(exportHtml, /href="\/teacher\/upload"/)
assert.match(exportHtml, /Descarga o imprime la actividad revisada/)
assert.doesNotMatch(exportHtml, /aún no está habilitada/)
console.log('S15 PASS: Vue SFC and scoped CSS compile; both export states render; default and supplied entry links render; human review and connection limits remain visible.')
