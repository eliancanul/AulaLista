import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createActivityFile } from '../src/features/export/activityExport.ts';

const scratch = process.env.AULALISTA_SCRATCH_DIR;
assert.ok(scratch, 'AULALISTA_SCRATCH_DIR is required for isolated browser artifacts');
const output = resolve(scratch, 's14-export-browser');
await mkdir(output, { recursive: true });
const chrome = spawn(process.env.S14_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  `--user-data-dir=${output}/profile`, '--remote-debugging-pipe', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] });
let errors = '';
chrome.stderr.on('data', chunk => { errors += chunk; });
const pending = new Map();
let sequence = 0;
let buffer = '';
const requests = [];
let downloadComplete;
chrome.stdio[4].on('data', chunk => {
  buffer += chunk;
  let end;
  while ((end = buffer.indexOf('\0')) !== -1) {
    const message = JSON.parse(buffer.slice(0, end));
    buffer = buffer.slice(end + 1);
    if (message.id) {
      const request = pending.get(message.id);
      if (request) {
        clearTimeout(request.timer);
        pending.delete(message.id);
        message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result);
      }
    }
    if (message.method === 'Network.requestWillBeSent') requests.push(message.params.request.url);
    if (message.method === 'Browser.downloadProgress' && message.params.state === 'completed') downloadComplete?.();
  }
});
function send(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out: ${errors.slice(-1000)}`)); }, 15000);
    pending.set(id, { resolve, reject, timer });
    chrome.stdio[3].write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0');
  });
}

try {
  const version = await send('Browser.getVersion');
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const page = (method, params) => send(method, params, sessionId);
  await page('Network.enable');
  await page('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: output, eventsEnabled: true });
  const { state, source } = JSON.parse(await readFile(new URL('../src/features/export/fixtures/activity.json', import.meta.url), 'utf8'));
  const file = createActivityFile(state, source, 'draft', true);
  const implementation = stripTypeScriptTypes(await readFile(new URL('../src/features/export/activityExport.ts', import.meta.url), 'utf8')).replace(/^export /gm, '');
  let downloadTimer;
  const completed = new Promise((resolve, reject) => {
    downloadComplete = resolve;
    downloadTimer = setTimeout(() => reject(new Error('Offline download did not complete')), 10000);
  });
  try {
    const download = await page('Runtime.evaluate', { expression: `${implementation}\nJSON.stringify(downloadActivityFile(${JSON.stringify(file)}))`, returnByValue: true });
    assert.ok(JSON.parse(download.result.value).ok);
    await completed;
  } finally { clearTimeout(downloadTimer); }
  const downloaded = resolve(output, file.filename);
  assert.equal(await readFile(downloaded, 'utf8'), file.content);
  await page('Page.enable');
  const navigation = await page('Page.navigate', { url: pathToFileURL(downloaded).href });
  assert.equal(navigation.errorText, undefined);
  const dom = await page('Runtime.evaluate', {
    expression: `new Promise(resolve => { const inspect = () => resolve({ text: document.body.innerText, online: navigator.onLine, external: document.querySelectorAll('script,img,iframe,link,a[href]').length }); document.readyState === 'complete' ? inspect() : window.addEventListener('load', inspect, { once: true }); })`,
    awaitPromise: true, returnByValue: true,
  });
  assert.equal(dom.result.value.online, false);
  assert.equal(dom.result.value.external, 0);
  for (const expected of [state.draft.title, state.draft.objective, ...state.draft.steps, state.draft.assessment, source.source_segments[0].text]) {
    assert.ok(dom.result.value.text.includes(expected), `Offline DOM missing ${expected}`);
  }
  await page('Emulation.setDeviceMetricsOverride', { width: 900, height: 1400, deviceScaleFactor: 1, mobile: false });
  const screenshot = await page('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  await writeFile(resolve(output, 'activity.png'), Buffer.from(screenshot.data, 'base64'));
  const pdf = await page('Page.printToPDF', { printBackground: true, preferCSSPageSize: true });
  await writeFile(resolve(output, 'activity.pdf'), Buffer.from(pdf.data, 'base64'));
  assert.deepEqual(requests.filter(url => /^https?:/.test(url)), []);
  const evidence = { browser: version.product, offline: true, exactDownloadedHTML: true, exactTeacherTextInDOM: true, externalElements: 0, httpRequests: 0, pdfBytes: Buffer.from(pdf.data, 'base64').length, output };
  await writeFile(resolve(output, 'evidence.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  await send('Browser.close').catch(() => chrome.kill());
  for (const entry of pending.values()) clearTimeout(entry.timer);
}
