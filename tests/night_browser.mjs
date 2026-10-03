import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const config = JSON.parse(readFileSync(0, 'utf8'));
const evidence = { method: 'Chrome CDP with single-origin Django/FastAPI/Vue and generated synthetic PDF', checks: [], observations: [] };
const chrome = spawn(config.chrome, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${config.profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });
let socket;
try {
  const endpoint = await new Promise((resolve, reject) => {
    let stderr = '';
    const timeout = setTimeout(() => reject(new Error('Chrome startup timeout')), 15000);
    chrome.on('error', reject);
    chrome.on('exit', code => reject(new Error(`Chrome exited ${code}: ${stderr}`)));
    chrome.stderr.on('data', chunk => {
      stderr += chunk;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timeout); resolve(match[1]); }
    });
  });
  const browserOrigin = endpoint.replace(/^ws:/, 'http:').split('/devtools/')[0];
  const target = await (await fetch(`${browserOrigin}/json/new?about:blank`, { method: 'PUT' })).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0;
  const pending = new Map();
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Page.javascriptDialogOpening' && message.params.type === 'beforeunload') {
      send('Page.handleJavaScriptDialog', { accept: true });
      return;
    }
    const request = pending.get(message.id);
    if (!request) return;
    clearTimeout(request.timeout);
    pending.delete(message.id);
    if (message.error) request.reject(new Error(JSON.stringify(message.error)));
    else request.resolve(message.result);
  };
  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 15000);
      pending.set(id, { resolve, reject, timeout });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const response = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
    return response.result.value;
  }
  async function until(expression) {
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      if (await evaluate(expression)) return;
      await delay(100);
    }
    evidence.observations.push({label:'timeout-page', ...await evaluate('({url:location.href,text:document.body.innerText.slice(0,2500)})')});
    const shot = await send('Page.captureScreenshot', {format:'png'});
    writeFileSync(join(config.evidenceDir,'timeout.png'),Buffer.from(shot.data,'base64'));
    throw new Error(`Browser condition timeout: ${expression}`);
  }
  async function navigate(path, condition) {
    await send('Page.navigate', { url: config.baseUrl + path });
    await until(condition);
  }
  await send('Page.enable');
  await send('Network.enable');
  await navigate('/sprint/', "document.querySelector('input[name=username]') !== null");
  await evaluate(`document.querySelector('[name=username]').value='night-synthetic'; document.querySelector('[name=password]').value='night-test-only'; document.querySelector('form').requestSubmit()`);
  await until("document.querySelector('.landing-primary') !== null");
  await evaluate("document.querySelector('.landing-primary').click()");
  await until("document.querySelector('#curriculum-file') !== null");
  const doc = await send('DOM.getDocument');
  const input = await send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: '#curriculum-file' });
  await send('DOM.setFileInputFiles', { nodeId: input.nodeId, files: [config.pdf] });
  await evaluate("document.querySelector('form button').click()");
  await until("location.hash.includes('/revision') && document.querySelector('.upload-review') !== null");
  assert.ok(await evaluate("document.body.innerText.includes('No se pudo determinar')"));
  evidence.checks.push('v2 upload and source review rendered');
  await evaluate("document.querySelector('a[href$=actividad]').click()");
  await until("document.querySelector('.activity-editor textarea') !== null");
  const editorPath = await evaluate('location.pathname + location.hash');
  async function field(index, text) {
    await evaluate(`document.querySelectorAll('.activity-editor textarea')[${index}].focus(); document.querySelectorAll('.activity-editor textarea')[${index}].select()`);
    await send('Input.insertText', {text});
  }
  await field(0, '  Revisión sintética\n');
  await field(1, 'Observar la fuente y conversar.');
  await field(2, '');
  await field(3, 'Leer la fuente\n');
  await field(4, '');
  await send('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0});
  await evaluate("document.querySelector('.activity-editor button[type=submit]').click()");
  await until("document.querySelector('.activity-editor [role=alert]') !== null");
  assert.equal(await evaluate("document.querySelector('.activity-editor textarea').value"), '  Revisión sintética\n');
  await send('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
  await evaluate("document.querySelector('.activity-editor button[type=submit]').click()");
  await until("document.body.innerText.includes('Borrador guardado, pendiente') && !document.querySelector('.activity-editor [role=alert]')");
  await navigate(editorPath, "document.querySelector('.activity-editor textarea') !== null");
  const exact = await evaluate("[...document.querySelectorAll('.activity-editor textarea')].map(e=>e.value)");
  assert.deepEqual(exact, ['  Revisión sintética\n','Observar la fuente y conversar.','','Leer la fuente\n','']);
  assert.equal(await evaluate("document.querySelector('.activity-editor input[type=checkbox]').checked"), false);
  await evaluate("document.querySelector('.activity-editor input[type=checkbox]').click()");
  await evaluate("[...document.querySelectorAll('.activity-editor button')].find(b=>b.textContent.includes('Aprobar esta')).click()");
  await until("document.body.innerText.includes('Versión aprobada')");
  await field(0,'Edición posterior');
  await evaluate("document.querySelector('.activity-editor button[type=submit]').click()");
  await until("document.body.innerText.includes('Borrador guardado, pendiente')");
  await navigate(editorPath, "document.querySelector('.activity-editor textarea') !== null");
  assert.ok(await evaluate("document.body.innerText.includes('Consultar la última versión aprobada')"));
  assert.ok(await evaluate("document.body.innerText.includes('Historial de revisiones (4)')"));
  assert.equal(await evaluate("document.querySelector('.activity-editor textarea').value"), 'Edición posterior');
  const id = await evaluate("location.hash.split('/')[2]");
  const saved = await evaluate(`fetch('/api/v1/interpretations/${id}').then(r=>r.json())`);
  assert.equal(saved.schema_version,2);
  assert.equal(saved.draft.approval_status,'pending');
  assert.equal(saved.draft.revision,4);
  const history = await evaluate(`fetch('/api/v1/drafts/${id}/history').then(r=>r.json())`);
  assert.deepEqual(history.map(r=>r.action), ['created','edited','approved','edited']);
  assert.equal(history[2].draft.title,'  Revisión sintética\n');
  await evaluate("document.querySelector('a[href=\"#/documentos\"]').click()");
  await until("document.body.innerText.includes('Mis borradores guardados')");
  // The route heading is synchronous, but rows arrive from an authenticated
  // request that verifies source hashes. Await its visible result, not a delay.
  await until("[...document.querySelectorAll('article h2 a')].some(a => a.textContent === 'Edición posterior')");
  assert.ok(await evaluate("document.body.innerText.includes('Edición posterior')"));
  evidence.checks.push('offline failure retains text, explicit retry, exact empty fields/newlines, reopen, explicit approval, subsequent invalidation, immutable history and document listing');
  const shot = await send('Page.captureScreenshot', {format:'png'});
  writeFileSync(join(config.evidenceDir,'night-documents.png'),Buffer.from(shot.data,'base64'));
  writeFileSync(join(config.evidenceDir,'night-browser.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence));
} finally { socket?.close(); chrome.kill(); }
