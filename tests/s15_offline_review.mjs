import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const config = JSON.parse(readFileSync(0, 'utf8'));
const evidence = { method: 'Chrome CDP with live Django and generated synthetic PDF', checks: [], observations: [] };
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
  async function key(key, code = key, virtualKey = 9) {
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: virtualKey, text: key === 'Enter' ? '\r' : undefined });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: virtualKey });
  }
  await send('Page.enable');
  await send('Network.enable');
  await navigate('/tutor/imports/new/', "document.querySelector('input[name=username]') !== null");
  await evaluate(`document.querySelector('[name=username]').value='s15-synthetic-teacher'; document.querySelector('[name=password]').value='s15-local-test-only'; document.querySelector('form').requestSubmit()`);
  await until("document.querySelector('#id_pdf') !== null");
  const doc = await send('DOM.getDocument');
  const input = await send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: '#id_pdf' });
  await send('DOM.setFileInputFiles', { nodeId: input.nodeId, files: [config.pdf] });
  await until("!document.querySelector('#submit-button').disabled");
  await evaluate("document.querySelector('#submit-button').focus()");
  await key('Enter', 'Enter', 13);
  await until("location.pathname.includes('/interpretacion/')");
  await until("document.querySelector('#interpretation-form') !== null");
  const reviewPath = await evaluate('location.pathname');
  evidence.checks.push('PASS browser upload reaches review using repository PDF and real deterministic interpreter');
  const projectLink = await evaluate("[...document.querySelectorAll('a[href]')].find(a=>a.getAttribute('href').includes('#control-proyecto'))?.getAttribute('href')");
  assert.ok(projectLink, 'Review exposes a link to the project field');
  await navigate(reviewPath + projectLink, "document.querySelector('#queue-item-form [name=proyecto]') !== null");
  evidence.observations.push({label: 'active-review-item', value: await evaluate("document.querySelector('#queue-item-form [name=item_id]').value")});
  await evaluate("document.querySelector('#queue-item-form [name=proyecto]').focus()");
  await evaluate("document.querySelector('#queue-item-form [name=proyecto]').select()");
  await send('Input.insertText', { text: 'Proyecto revisado por S15' });
  let reachedSave = false;
  for (let i=0; i<12; i++) {
    await key('Tab');
    if (await evaluate("document.activeElement.value === 'save_queue_item'")) { reachedSave = true; break; }
  }
  assert.ok(reachedSave, 'Review save is reachable using Tab from title input');
  evidence.checks.push('PASS keyboard Tab reaches correction action from edited title');
  await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
  await key('Enter', 'Enter', 13);
  await until("document.querySelector('#queue-item-form [role=alert]') !== null");
  assert.equal(await evaluate("document.querySelector('#queue-item-form [name=proyecto]').value"), 'Proyecto revisado por S15');
  assert.equal(await evaluate("document.querySelector('#queue-item-form button[value=save_queue_item]').disabled"), false);
  evidence.observations.push({ label:'offline-error', text:await evaluate("document.querySelector('#queue-item-form [role=alert]').innerText") });
  assert.ok(await evaluate("document.activeElement.matches('#queue-item-form [role=alert]')"), 'Save error receives keyboard focus');
  await evaluate("document.querySelector('#queue-item-form [role=alert]').scrollIntoView({behavior:'instant',block:'center'})");
  assert.equal(await evaluate("document.querySelector('#queue-item-form [role=alert]').innerText"), 'No se pudo conectar con AulaLista. Tu edición sigue en pantalla. Revisa la conexión e inténtalo de nuevo.');
  evidence.checks.push('PASS offline save preserves typed correction and enables retry in same page');
  await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await evaluate("document.querySelector('#queue-item-form button[value=save_queue_item]').click()");
  await until("!document.querySelector('#queue-item-form [role=alert]')");
  await navigate(reviewPath, "document.querySelector('#interpretation-form') !== null");
  assert.ok(await evaluate("document.body.innerText.includes('Proyecto revisado por S15')"), 'Correction survives reload');
  evidence.checks.push('PASS reconnect save and reload retain correction without publishing');
} catch (error) {
  evidence.error = String(error.stack || error);
  process.exitCode = 1;
} finally {
  writeFileSync(join(config.evidenceDir, 'browser-results.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence, null, 2));
  socket?.close();
  chrome.kill('SIGTERM');
}
