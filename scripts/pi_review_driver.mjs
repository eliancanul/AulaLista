/** One text request through installed Pi 0.84.4. Never creates a coding agent.
 * Invoke only inside a separately reviewed OS isolation boundary. No auth export,
 * login, credential copy, global settings, extension discovery, or model fallback.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { findPackageJSON } from 'node:module';

export const IDENTITY = Object.freeze({
  protocol: 'aulalista.pi-text.v1', pi_version: '0.84.4', provider: 'openai-codex',
  model: 'gpt-6-luna', api: 'openai-codex-responses',
  base_url: 'https://chatgpt.com/backend-api', effort: 'high',
});
const LIMIT = 4 * 1024 * 1024;
// Only errors made here may supply a diagnostic code. Never inspect an upstream
// exception's message, stack, cause, name or arbitrary properties.
const failures = new WeakMap();
function fail(code) {
  const error = new Error(code);
  failures.set(error, { code });
  return error;
}
async function stage(name, action) {
  try { return await action(); }
  catch (error) {
    const known = failures.get(error);
    const safe = fail(known?.code ?? 'pi_stage_failed');
    failures.set(safe, { code: known?.code ?? 'pi_stage_failed', stage: known?.stage ?? name });
    throw safe;
  }
}
export function describeFailure(error) {
  const known = failures.get(error);
  return { type: 'pi.error', stage: known?.stage ?? 'driver', code: known?.code ?? 'pi_driver_failed' };
}

function boundedJson(file, limit) {
  const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.size > limit) throw fail('invalid_file');
    const raw = fs.readFileSync(fd);
    if (raw.length > limit) throw fail('invalid_file');
    return JSON.parse(raw.toString('utf8'));
  } finally { fs.closeSync(fd); }
}

export function validateModel(model) {
  if (!model || model.id !== IDENTITY.model || model.provider !== IDENTITY.provider
      || model.api !== IDENTITY.api || model.baseUrl !== IDENTITY.base_url
      || model.reasoning !== true || Object.keys(model.headers ?? {}).length
      || model.samplingParams || model.samplingParamsByThinkingLevel) {
    throw fail('pi_model_contract_mismatch');
  }
  return model;
}

export function validatePayload(body) {
  if (!body || body.model !== IDENTITY.model || body.tool_choice !== 'none'
      || (body.tools !== undefined && (!Array.isArray(body.tools) || body.tools.length))
      || body.reasoning?.effort !== IDENTITY.effort || body.previous_response_id
      || body.background || body.store !== false) throw fail('pi_payload_contract_mismatch');
}

export function validateCatalog(catalog) {
  if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog)) {
    throw fail('pi_catalog_contract_mismatch');
  }
  const entry = catalog[IDENTITY.provider];
  if (!entry || !Array.isArray(entry.models)) throw fail('pi_catalog_contract_mismatch');
  const matches = entry.models.filter((model) => model?.id === IDENTITY.model);
  if (matches.length !== 1) throw fail('pi_catalog_model_missing_or_duplicate');
  validateModel(matches[0]);
  return entry;
}

export async function buildRuntime(packageDir, agentDir, catalogPath) {
  await stage('package_manifest', () => {
    const manifest = boundedJson(path.join(packageDir, 'package.json'), 32768);
    if (manifest.name !== '@earendil-works/pi-coding-agent' || manifest.version !== IDENTITY.pi_version) {
      throw fail('pi_version_unsupported');
    }
  });
  await stage('ai_manifest', () => {
    const aiManifestPath = findPackageJSON('@earendil-works/pi-ai',
      pathToFileURL(path.join(packageDir, 'dist/core/model-runtime.js')));
    const aiManifest = boundedJson(aiManifestPath, 32768);
    if (aiManifest.name !== '@earendil-works/pi-ai' || aiManifest.version !== IDENTITY.pi_version) {
      throw fail('pi_ai_version_unsupported');
    }
  });
  // These internal exports are deliberately pinned to 0.84.4, not assumed stable.
  const [{ ModelRuntime }, { ReadOnlyAuthStorage }] = await stage('runtime_import', () => Promise.all([
    import(pathToFileURL(path.join(packageDir, 'dist/core/model-runtime.js'))),
    import(pathToFileURL(path.join(packageDir, 'dist/core/auth-storage.js'))),
  ]));
  const entry = await stage('catalog_read', () => validateCatalog(boundedJson(catalogPath, 16 * 1024 * 1024)));
  const readOnlyCatalog = {
    read: async (provider) => provider === IDENTITY.provider ? structuredClone(entry) : undefined,
    write: async () => { throw fail('catalog_is_read_only'); },
    delete: async () => { throw fail('catalog_is_read_only'); },
  };
  const runtime = await stage('runtime_create', () => ModelRuntime.create({
    credentials: new ReadOnlyAuthStorage(path.join(agentDir, 'auth.json')),
    modelsPath: null, modelsStore: readOnlyCatalog,
    allowModelNetwork: false, refreshOnCreate: false,
  }));
  await stage('catalog_refresh', async () => {
    const result = await runtime.refresh({ providers: [IDENTITY.provider], allowNetwork: false });
    // Pi 0.84.4 returns errors instead of rejecting. Do not silently fall back to
    // its built-in catalog after a failed restoration of the reviewed catalog.
    if (!result || typeof result.aborted !== 'boolean' || !(result.errors instanceof Map)) {
      throw fail('pi_refresh_contract_mismatch');
    }
    if (result.aborted) throw fail('pi_catalog_refresh_aborted');
    if (result.errors.size) throw fail('pi_catalog_refresh_failed');
  });
  const model = await stage('model_contract', () => validateModel(runtime.getModel(IDENTITY.provider, IDENTITY.model)));
  await stage('auth_check', async () => {
    if ((await runtime.checkAuth(IDENTITY.provider))?.type !== 'oauth') throw fail('pi_oauth_required');
  });
  // checkAuth only detects configured OAuth, even for expired tokens. getAuth
  // requires five minutes of validity. ReadOnlyAuthStorage refuses modify()
  // before the OAuth refresh callback, so near-expiry credentials fail closed.
  await stage('auth_resolution', async () => {
    if ((await runtime.getAuth(model))?.source !== 'OAuth') throw fail('pi_oauth_required');
  });
  return { runtime, model };
}

export async function runRequest(runtime, model, request, emit) {
  return stage('provider_stream', () => streamRequest(runtime, model, request, emit));
}

async function streamRequest(runtime, model, request, emit) {
  validateModel(model);
  if (request?.protocol !== IDENTITY.protocol || typeof request.system !== 'string'
      || typeof request.prompt !== 'string' || !Number.isInteger(request.timeout_ms)
      || request.timeout_ms < 1000 || request.timeout_ms > 120000) throw fail('invalid_request');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), request.timeout_ms);
  let started = 0;
  let terminal = 0;
  let dispatches = 0;
  let generatedBytes = 0;
  const oneFetch = async (url, options) => {
    if (String(url) !== IDENTITY.base_url + '/codex/responses' || options?.method !== 'POST'
        || ++dispatches !== 1) throw fail('pi_dispatch_contract_mismatch');
    emit({ type: 'pi.request', dispatch_count: dispatches });
    const response = await fetch(url, { ...options, redirect: 'error' });
    if (!response.body) throw fail('missing_response_body');
    const reader = response.body.getReader();
    let bytes = 0;
    const body = new ReadableStream({
      async pull(target) {
        const next = await reader.read();
        if (next.done) return target.close();
        bytes += next.value.length;
        if (bytes > 256 * 1024) {
          controller.abort();
          await reader.cancel();
          return target.error(fail('pi_response_byte_limit'));
        }
        target.enqueue(next.value);
      },
      cancel: () => reader.cancel(),
    });
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  };
  try {
    const stream = runtime.streamSimple(model, {
      systemPrompt: request.system,
      messages: [{ role: 'user', content: request.prompt, timestamp: Date.now() }], tools: [],
    }, {
      reasoning: IDENTITY.effort, toolChoice: 'none', transport: 'sse',
      maxRetries: 0, timeoutMs: request.timeout_ms, signal: controller.signal,
      cacheRetention: 'none', onPayload: validatePayload, fetch: oneFetch,
    });
    for await (const event of stream) {
      if (typeof event.delta === 'string') generatedBytes += Buffer.byteLength(event.delta);
      if (generatedBytes > 128 * 1024) {
        controller.abort();
        throw fail('pi_generated_byte_limit');
      }
      if (event.type === 'start') {
        if (++started !== 1) throw fail('multiple_provider_starts');
        emit({ type: 'pi.start', ...IDENTITY });
      } else if (event.type === 'done') {
        if (started !== 1 || ++terminal !== 1) throw fail('invalid_terminal');
        emit({ type: 'pi.result', message: event.message });
      } else if (event.type === 'error' || event.type.startsWith('toolcall')) {
        controller.abort();
        throw fail('pi_provider_stopped');
      } else if (!['text_start', 'text_delta', 'text_end', 'thinking_start', 'thinking_delta', 'thinking_end'].includes(event.type)) {
        controller.abort();
        throw fail('unknown_provider_event');
      }
    }
    if (started !== 1 || terminal !== 1 || dispatches !== 1) throw fail('missing_provider_terminal');
    emit({ type: 'pi.completed' });
  } finally { clearTimeout(timer); controller.abort(); }
}

async function main() {
  const [mode, packageDir, agentDir, catalogPath] = process.argv.slice(2);
  await stage('invocation', () => {
    if (!['--preflight', '--generate'].includes(mode) || process.argv.length !== 6
      || ![packageDir, agentDir, catalogPath].every(path.isAbsolute)
      || process.env.PI_OFFLINE !== '1' || process.env.PI_TELEMETRY !== '0') throw fail('invalid_invocation');
  });
  const { runtime, model } = await buildRuntime(packageDir, agentDir, catalogPath);
  const emit = (event) => process.stdout.write(JSON.stringify(event) + '\n');
  if (mode === '--preflight') {
    emit({ type: 'pi.ready', ...IDENTITY, auth_type: 'oauth', auth_refresh: false,
      tools: 0, resources: 0, automatic_retries: 0, agent_loop: false });
    return;
  }
  const request = await stage('request_read', async () => {
    const chunks = [];
    let bytes = 0;
    for await (const chunk of process.stdin) {
      bytes += chunk.length;
      if (bytes > LIMIT) throw fail('request_too_large');
      chunks.push(chunk);
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  });
  await runRequest(runtime, model, request, emit);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error) => {
    // Fixed stage/code only. No upstream exception text or credential metadata.
    process.stderr.write(JSON.stringify(describeFailure(error)) + '\n');
    process.exitCode = 1;
  });
}
