// Pure fixtures. No installed Pi, credentials, model, DNS, or network calls.
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { IDENTITY, buildRuntime, runRequest, validateModel, validatePayload, validateCatalog, describeFailure } from '../scripts/pi_review_driver.mjs';

const model = { id: IDENTITY.model, provider: IDENTITY.provider, api: IDENTITY.api,
  baseUrl: IDENTITY.base_url, reasoning: true };
const body = { model: IDENTITY.model, tool_choice: 'none', tools: [],
  reasoning: { effort: 'high' }, store: false };
const message = { role: 'assistant', model: IDENTITY.model, provider: IDENTITY.provider,
  api: IDENTITY.api, stopReason: 'stop', content: [{ type: 'text', text: '{}' }],
  usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2 } };
const request = { protocol: IDENTITY.protocol, system: 'fixture system', prompt: 'fixture prompt', timeout_ms: 1000 };

test('model and outgoing body reject routes, tools, reasoning clamps and overrides', () => {
  assert.equal(validateModel(model), model);
  validatePayload(body);
  for (const patch of [{ id: 'gpt-6.1-luna' }, { provider: 'openai' }, { api: 'openai-responses' },
    { baseUrl: 'https://evil.invalid' }, { headers: { Authorization: 'fixture' } },
    { reasoning: false }, { samplingParams: {} }]) {
    assert.throws(() => validateModel({ ...model, ...patch }));
  }
  for (const patch of [{ model: 'other' }, { tool_choice: 'auto' }, { tools: [{}] },
    { reasoning: { effort: 'medium' } }, { store: true }, { background: true },
    { previous_response_id: 'old' }]) assert.throws(() => validatePayload({ ...body, ...patch }));
});

async function fixtureRun(action) {
  const originalFetch = globalThis.fetch;
  const calls = [];
  const events = [];
  let optionsSeen;
  let contextSeen;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(action === 'wire_limit' ? 'x'.repeat(262145) : 'synthetic upstream bytes');
  };
  const runtime = {
    async *streamSimple(given, context, options) {
      optionsSeen = options; contextSeen = context;
      assert.deepEqual(given, model);
      options.onPayload(body);
      const url = action === 'wrong_url' ? 'https://evil.invalid' : IDENTITY.base_url + '/codex/responses';
      const response = await options.fetch(url, { method: action === 'wrong_method' ? 'GET' : 'POST' });
      await response.text();
      if (action === 'second_fetch') await options.fetch(url, { method: 'POST' });
      yield { type: 'start' };
      if (action === 'double_start') yield { type: 'start' };
      if (action === 'tool') yield { type: 'toolcall_start' };
      if (action === 'error') yield { type: 'error' };
      if (action === 'unknown') yield { type: 'unexpected' };
      yield { type: 'text_delta', delta: action === 'generated_limit' ? 'x'.repeat(131073) : '{}' };
      if (action !== 'missing_terminal') yield { type: 'done', message };
    },
  };
  try {
    await runRequest(runtime, model, request, (event) => events.push(event));
    return { calls, events, optionsSeen, contextSeen };
  } finally { globalThis.fetch = originalFetch; }
}

test('one text request: no coding agent, tools, retry, redirect or session cache', async () => {
  const { calls, events, optionsSeen, contextSeen } = await fixtureRun('ok');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.redirect, 'error');
  assert.deepEqual(contextSeen.tools, []);
  assert.equal(contextSeen.messages.length, 1);
  assert.equal(contextSeen.messages[0].content, 'fixture prompt');
  assert.equal(optionsSeen.transport, 'sse');
  assert.equal(optionsSeen.maxRetries, 0);
  assert.equal(optionsSeen.toolChoice, 'none');
  assert.equal(optionsSeen.cacheRetention, 'none');
  assert.equal(optionsSeen.sessionId, undefined);
  assert.equal(optionsSeen.reasoning, 'high');
  assert.deepEqual(events.map((e) => e.type), ['pi.request', 'pi.start', 'pi.result', 'pi.completed']);
});

for (const action of ['wrong_url', 'wrong_method', 'second_fetch', 'double_start', 'tool',
  'error', 'unknown', 'generated_limit', 'wire_limit', 'missing_terminal']) {
  test(`fail closed for ${action}`, async () => { await assert.rejects(fixtureRun(action)); });
}

function installedFixture({ refresh = 'return { aborted: false, errors: new Map() };',
    checkAuth = "return {type:'oauth'};", getAuth = "return {source:'OAuth'};",
    create = 'return new ModelRuntime();', extra = '' } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'aulalista-pi-stub-'));
  const pkg = path.join(root, 'package');
  const core = path.join(pkg, 'dist/core');
  const ai = path.join(pkg, 'node_modules/@earendil-works/pi-ai');
  fs.mkdirSync(core, { recursive: true });
  fs.mkdirSync(path.join(ai, 'dist'), { recursive: true });
  fs.writeFileSync(path.join(pkg, 'package.json'), JSON.stringify({ name: '@earendil-works/pi-coding-agent', version: '0.84.4', type: 'module' }));
  fs.writeFileSync(path.join(ai, 'package.json'), JSON.stringify({ name: '@earendil-works/pi-ai', version: '0.84.4', type: 'module', exports: { '.': { import: './dist/index.js' } } }));
  fs.writeFileSync(path.join(ai, 'dist/index.js'), 'export {};');
  fs.writeFileSync(path.join(core, 'auth-storage.js'), 'export class ReadOnlyAuthStorage { constructor(path) { this.fixturePath = path; } }');
  fs.writeFileSync(path.join(core, 'model-runtime.js'), `export class ModelRuntime {
    static async create(options) { globalThis.__piFixtureOptions = options; ${create} }
    async refresh(options) { globalThis.__piFixtureRefresh = options; ${refresh} }
    getModel(provider,id) { return ${JSON.stringify(model)}; }
    async checkAuth(provider) { ${checkAuth} }
    async getAuth(model) { ${getAuth} }
    ${extra}
  }`);
  const catalog = path.join(root, 'catalog.json');
  fs.writeFileSync(catalog, JSON.stringify({ 'openai-codex': { lastModified: 1791200000000, models: [model] } }));
  return { root, pkg, core, ai, catalog, args: [pkg, path.join(root, 'agent'), catalog],
    cleanup() { delete globalThis.__piFixtureOptions; delete globalThis.__piFixtureRefresh;
      fs.rmSync(root, { recursive: true, force: true }); } };
}

test('installed package version, read-only auth and cached model are wired without global configuration', async () => {
  const fixture = installedFixture();
  try {
    const result = await buildRuntime(...fixture.args);
    assert.equal(result.model.id, 'gpt-6-luna');
    const options = globalThis.__piFixtureOptions;
    assert.equal(options.modelsPath, null);
    assert.equal(options.allowModelNetwork, false);
    assert.equal(options.refreshOnCreate, false);
    assert.equal(options.credentials.fixturePath, path.join(fixture.args[1], 'auth.json'));
    assert.deepEqual(globalThis.__piFixtureRefresh, { providers: ['openai-codex'], allowNetwork: false });
    assert.equal(await options.modelsStore.read('other'), undefined);
    const cached = await options.modelsStore.read(IDENTITY.provider);
    cached.models[0].id = 'mutation';
    assert.equal((await options.modelsStore.read(IDENTITY.provider)).models[0].id, IDENTITY.model);
    await assert.rejects(options.modelsStore.write('openai-codex', {}));
    await assert.rejects(options.modelsStore.delete('openai-codex'));
    const newer = { name: '@earendil-works/pi-ai', version: '0.84.5', type: 'module', exports: { '.': { import: './dist/index.js' } } };
    fs.writeFileSync(path.join(fixture.ai, 'package.json'), JSON.stringify(newer));
    await assert.rejects(buildRuntime(...fixture.args), /pi_ai_version_unsupported/);
  } finally { fixture.cleanup(); }
});

test('the exact approved model must occur once in the reviewed catalog, not just in built-ins', () => {
  assert.deepEqual(validateCatalog({ [IDENTITY.provider]: { models: [model] } }), { models: [model] });
  for (const catalog of [null, [], {}, { [IDENTITY.provider]: {} },
    { [IDENTITY.provider]: { models: [] } }, { [IDENTITY.provider]: { models: [model, model] } },
    { [IDENTITY.provider]: { models: [{ ...model, provider: 'other' }] } }]) {
    assert.throws(() => validateCatalog(catalog));
  }
});

for (const [name, options, stage, code] of [
  ['refresh errors', { refresh: "return { aborted: false, errors: new Map([['openai-codex', new Error('PRIVATE_SENTINEL')]]) };" }, 'catalog_refresh', 'pi_catalog_refresh_failed'],
  ['refresh aborted', { refresh: 'return { aborted: true, errors: new Map() };' }, 'catalog_refresh', 'pi_catalog_refresh_aborted'],
  ['refresh missing result', { refresh: 'return undefined;' }, 'catalog_refresh', 'pi_refresh_contract_mismatch'],
  ['refresh malformed result', { refresh: 'return { aborted: false, errors: {} };' }, 'catalog_refresh', 'pi_refresh_contract_mismatch'],
  ['refresh exception', { refresh: "throw new Error('PRIVATE_SENTINEL');" }, 'catalog_refresh', 'pi_stage_failed'],
  ['create exception', { create: "throw new Error('PRIVATE_SENTINEL');" }, 'runtime_create', 'pi_stage_failed'],
  ['missing auth', { checkAuth: 'return undefined;' }, 'auth_check', 'pi_oauth_required'],
  ['auth read exception', { checkAuth: "throw new Error('PRIVATE_SENTINEL');" }, 'auth_check', 'pi_stage_failed'],
  ['resolution read-only refusal', { getAuth: "throw new Error('PRIVATE_SENTINEL');" }, 'auth_resolution', 'pi_stage_failed'],
  ['resolution not OAuth', { getAuth: "return {source:'environment'};" }, 'auth_resolution', 'pi_oauth_required'],
]) {
  test(`sanitized diagnostic for ${name}`, async () => {
    const fixture = installedFixture(options);
    try {
      await assert.rejects(buildRuntime(...fixture.args), (error) => {
        assert.deepEqual(describeFailure(error), { type: 'pi.error', stage, code });
        assert.ok(!String(error).includes('PRIVATE_SENTINEL'));
        return true;
      });
    } finally { fixture.cleanup(); }
  });
}

test('invalid reviewed catalog blocks before creating the runtime', async () => {
  const fixture = installedFixture();
  try {
    fs.writeFileSync(fixture.catalog, '{}');
    await assert.rejects(buildRuntime(...fixture.args), (error) => {
      assert.deepEqual(describeFailure(error), { type: 'pi.error', stage: 'catalog_read', code: 'pi_catalog_contract_mismatch' });
      return true;
    });
    assert.equal(globalThis.__piFixtureOptions, undefined);
  } finally { fixture.cleanup(); }
});

test('untrusted errors cannot supply diagnostic fields, even with look-alike code and stage', async () => {
  const forged = Object.assign(new Error('PRIVATE_SENTINEL'), { code: 'PRIVATE_SENTINEL', stage: 'PRIVATE_SENTINEL' });
  const unreadable = new Proxy({}, { get() { throw new Error('must not inspect provider exception'); } });
  for (const error of [forged, unreadable, 'PRIVATE_SENTINEL', null, undefined]) {
    assert.deepEqual(describeFailure(error), { type: 'pi.error', stage: 'driver', code: 'pi_driver_failed' });
    const runtime = { streamSimple() { throw error; } };
    await assert.rejects(runRequest(runtime, model, request, () => {}), (safe) => {
      assert.deepEqual(describeFailure(safe), { type: 'pi.error', stage: 'provider_stream', code: 'pi_stage_failed' });
      return true;
    });
  }
});

test('CLI failure emits one bounded diagnostic only on stderr and never prints upstream details', () => {
  const fixture = installedFixture({ getAuth: "throw new Error('PRIVATE_SENTINEL');" });
  try {
    const result = spawnSync(process.execPath, [fileURLToPath(new URL('../scripts/pi_review_driver.mjs', import.meta.url)), '--preflight', ...fixture.args],
      { env: { PATH: process.env.PATH, PI_OFFLINE: '1', PI_TELEMETRY: '0' }, encoding: 'utf8', timeout: 5000 });
    assert.equal(result.status, 1);
    assert.equal(result.stdout, '');
    assert.deepEqual(JSON.parse(result.stderr), { type: 'pi.error', stage: 'auth_resolution', code: 'pi_stage_failed' });
    assert.ok(result.stderr.length < 256);
    assert.ok(!result.stderr.includes('PRIVATE_SENTINEL'));
  } finally { fixture.cleanup(); }
});

test('a launcher that drops the required offline flags fails before runtime or auth loading', () => {
  const driver = fileURLToPath(new URL('../scripts/pi_review_driver.mjs', import.meta.url));
  for (const flags of [{}, { PI_OFFLINE: '1' }, { PI_TELEMETRY: '0' },
    { PI_OFFLINE: '0', PI_TELEMETRY: '0' }, { PI_OFFLINE: '1', PI_TELEMETRY: '1' }]) {
    const result = spawnSync(process.execPath,
      [driver, '--preflight', '/never-open-package', '/never-open-agent', '/never-open-catalog'],
      { env: { PATH: process.env.PATH, ...flags }, encoding: 'utf8', timeout: 5000 });
    assert.equal(result.status, 1);
    assert.equal(result.stdout, '');
    assert.deepEqual(JSON.parse(result.stderr), { type: 'pi.error', stage: 'invocation', code: 'invalid_invocation' });
  }
});
