import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';


// Diagnostic-only allowlist; never include CSRF, passwords or response text.
function safeReviewPost(body = '') {
  const multipart = body.startsWith('--');
  const params = multipart ? null : new URLSearchParams(body);
  const pick = key => multipart
    ? body.match(new RegExp('name="' + key + '"\\r?\\n\\r?\\n([^\\r\\n]*)'))?.[1]
    : params.get(key);
  const action = pick('action');
  const actions = ['answer','edit','skip','save_draft','discard_draft','continue','retry_interrupted','resume_changed'];
  const numeric = key => /^[0-9]{1,20}$/.test(pick(key) || '') ? pick(key) : null;
  return {action: action == null ? 'missing' : actions.includes(action) ? action : 'other',
    expected_revision:numeric('expected_revision'), expected_version:numeric('expected_version'),
    draft_epoch:numeric('draft_epoch')};
}
// End diagnostic allowlist.

const config = JSON.parse(readFileSync(0, 'utf8'));
const evidence = { method: 'CI Chrome CDP, current Django one-box, generated two-page PDF, explicitly mocked adaptive provider; no Gemini execution', checks: [], observations: [] };
const chrome = spawn(config.chrome, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${config.profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });
let socket;
let tracingAnswerTransition = false;
const tracedPosts = new Map();
const transitionNetwork = [];
const transitionExceptions = [];
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
    if (tracingAnswerTransition && transitionExceptions.length < 20 && message.method === 'Runtime.exceptionThrown') {
      const details = message.params.exceptionDetails;
      transitionExceptions.push({className:String(details.exception?.className || 'Error').slice(0,80),
        lineNumber:details.lineNumber,columnNumber:details.columnNumber,
        frames:(details.stackTrace?.callFrames || []).slice(0,4).map(f=>({functionName:String(f.functionName || '').slice(0,80),lineNumber:f.lineNumber,columnNumber:f.columnNumber}))});
    }
    if (tracingAnswerTransition && message.method === 'Network.requestWillBeSent') {
      const request = message.params.request;
      if (message.params.redirectResponse && tracedPosts.has(message.params.requestId) && tracedPosts.get(message.params.requestId).responses.length < 8) {
        tracedPosts.get(message.params.requestId).responses.push({phase:'redirect',status:message.params.redirectResponse.status});
      }
      if (transitionNetwork.length < 20 && request.method === 'POST' && /^\/tutor\/imports\/\d+\/interpretacion\/$/.test(new URL(request.url).pathname)) {
        const item = {requestId:message.params.requestId, method:'POST', path:new URL(request.url).pathname,
          ...safeReviewPost(request.postData || ''), postDataAvailable:typeof request.postData === 'string', responses:[]};
        transitionNetwork.push(item);tracedPosts.set(message.params.requestId,item);
      }
    }
    if (message.method === 'Network.responseReceived' && tracedPosts.has(message.params.requestId) && tracedPosts.get(message.params.requestId).responses.length < 8) {
      tracedPosts.get(message.params.requestId).responses.push({phase:'response',status:message.params.response.status});
    }
    if (message.method === 'Network.loadingFailed' && tracedPosts.has(message.params.requestId)) {
      tracedPosts.get(message.params.requestId).failure = /^net::ERR_[A-Z_]{1,60}$/.test(message.params.errorText || '') ? message.params.errorText : 'network_failure';
    }
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
      try { if (await evaluate('document.readyState === \"complete\" && ('+expression+')')) return; }
      catch (error) { if (!/Execution context was destroyed|Cannot find context|Inspected target navigated/.test(String(error))) throw error; }
      await delay(100);
    }
    evidence.observations.push({label:'timeout-page', ...await evaluate('({url:location.href,text:document.body.innerText.slice(0,2500), transition:window.__oneboxTransitionTrace || [], form:window.__oneboxTransitionSnapshot?.() || null})')});
    const shot = await send('Page.captureScreenshot', {format:'png'});
    writeFileSync(join(config.evidenceDir,'timeout.png'),Buffer.from(shot.data,'base64'));
    throw new Error(`Browser condition timeout: ${expression}`);
  }
  async function navigate(path, condition, allowRedirect = false) {
    const result = await send('Page.navigate', { url: config.baseUrl + path });
    if (result.errorText) throw new Error(result.errorText);
    if (result.loaderId) {
      const deadline=Date.now()+15000;
      while (Date.now()<deadline) {
        const tree=await send('Page.getFrameTree');
        if (tree.frameTree.frame.loaderId===result.loaderId) break;
        await delay(50);
      }
    }
    await until(allowRedirect ? condition : 'location.pathname + location.search === '+JSON.stringify(path)+' && ('+condition+')');
  }
  await send('Page.enable');
  await send('Network.enable');
  await send('Runtime.enable');
  const inputSelector = '#teacher-answer';
  const formSelector = '#teacher-answer-form';
  const savedCondition = "document.querySelector('#draft-status')?.textContent.includes('Borrador guardado')";
  const count = () => evaluate("Number(document.querySelector('[data-asked-count]')?.dataset.askedCount)");
  const oneBox = async () => assert.equal(await evaluate("document.querySelectorAll('textarea').length"), 1);
  async function typeAnswer(text) {
    await evaluate(`document.querySelector(${JSON.stringify(inputSelector)}).focus(); document.querySelector(${JSON.stringify(inputSelector)}).select()`);
    await send('Input.insertText', {text});
  }
  async function clickAction(action) {
    await evaluate(`document.querySelector('button[name=action][value=${action}]').click()`);
  }
  async function nativeEnter() {
    await send('Input.dispatchKeyEvent', {type:'keyDown', key:'Enter', code:'Enter', windowsVirtualKeyCode:13, text:'\r', unmodifiedText:'\r'});
    await send('Input.dispatchKeyEvent', {type:'keyUp', key:'Enter', code:'Enter', windowsVirtualKeyCode:13});
  }
  const first = config.firstAnswer;
  const edited = config.editedAnswer;
  const pendingAnswer = config.pendingAnswer;
  await navigate('/tutor/imports/new/', "document.querySelector('input[name=username]') !== null", true);
  // Genuine login and CSRF middleware, not a injected cookie or synthetic auth bypass.
  await evaluate(`document.querySelector('[name=username]').value=${JSON.stringify(config.username)}; document.querySelector('[name=password]').value=${JSON.stringify(config.password)}; document.querySelector('form').requestSubmit()`);
  await until("document.querySelector('#id_pdf') !== null");
  const doc = await send('DOM.getDocument');
  const uploadInput = await send('DOM.querySelector', {nodeId:doc.root.nodeId, selector:'#id_pdf'});
  await send('DOM.setFileInputFiles', {nodeId:uploadInput.nodeId, files:[config.pdf]});
  await until("!document.querySelector('#submit-button').disabled");
  await evaluate("document.querySelector('#submit-button').click()");
  await until("location.pathname.includes('/interpretacion/') && document.querySelector('button[value=continue]') !== null");
  const reviewPath = await evaluate('location.pathname');
  const csrfFailure = await evaluate(`fetch(location.pathname,{method:'POST',body:new URLSearchParams({action:'continue'}),credentials:'same-origin'}).then(r=>r.status)`);
  assert.equal(csrfFailure,403);
  assert.equal(await count(),0);
  evidence.checks.push('Real login and generated upload; current Django route; tokenless POST rejected with 403');

  await clickAction('continue');
  await until("document.querySelector('#teacher-answer') !== null && document.querySelector('[data-asked-count]').dataset.askedCount === '1'");
  await oneBox();
  assert.ok(await evaluate("document.querySelector('label[for=teacher-answer]') !== null"));
  assert.equal(await evaluate("document.querySelector('#draft-status').getAttribute('aria-live')"),'polite');
  tracingAnswerTransition = true;
  // Autosave failure, text retention and explicit user input retry on reconnection.
  await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
  await typeAnswer(first);
  await until("document.querySelector('#draft-status').textContent.includes('No se pudo guardar')");
  assert.equal(await evaluate("document.querySelector('#teacher-answer').value"),first);
  assert.equal(await evaluate("(()=>{const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented})()"),true);
  await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await typeAnswer(first);
  await until(savedCondition);
  await navigate(reviewPath,"document.querySelector('#teacher-answer') !== null && document.querySelector('#teacher-answer').value === "+JSON.stringify(first));
  await oneBox();
  assert.equal(await count(),1);
  // Instrument only the generated-fixture Q1 transition. No default is prevented.
  tracingAnswerTransition = true;
  await evaluate(`(() => {
    const form = document.querySelector('#teacher-answer-form');
    const trace = window.__oneboxTransitionTrace = [];
    const buttonInfo = b => b ? {tag:b.tagName,id:b.id,name:b.name,
      action:b.name === 'action' ? b.value : null,disabled:!!b.disabled,
      belongsToAnswerForm:b.form === form} : null;
    const snapshot = window.__oneboxTransitionSnapshot = () => ({
      prepared:form.dataset.prepared || null,submitting:form.dataset.submitting || null,
      busy:form.getAttribute('aria-busy'),valid:[...form.elements].every(e=>!e.willValidate || e.validity.valid),
      draftEpoch:form.querySelector('[name=draft_epoch]')?.value,
      revision:form.querySelector('[name=expected_revision]')?.value,
      answerLength:form.querySelector('textarea')?.value.length,
      actionControls:[...form.querySelectorAll('[name=action]')].map(buttonInfo),
      active:buttonInfo(document.activeElement),
    });
    const record = (kind,extra={}) => {if(trace.length<60)trace.push({kind,...extra,form:snapshot()});};
    for (const type of ['keydown','keypress','keyup','click','submit','invalid','formdata']) {
      for (const capture of [true,false]) document.addEventListener(type,event => {
        if (!(event.target === form || form.contains(event.target))) return;
        if (type.startsWith('key') && !['Enter','Tab'].includes(event.key)) return;
        record(type,{phase:capture?'capture':'bubble',key:event.key || null,
          charCode:event.charCode || null,defaultPrevented:event.defaultPrevented,
          submitter:buttonInfo(event.submitter),target:buttonInfo(event.target),
          actions:type==='formdata'?event.formData.getAll('action').map(v=>['answer','edit','skip','save_draft','discard_draft'].includes(v)?v:'other'):null});
      },capture);
    }
    const original = form.requestSubmit;
    form.requestSubmit = function(submitter) {
      record('requestSubmit-before',{submitter:buttonInfo(submitter)});
      try {return original.call(this,submitter);}
      finally {record('requestSubmit-after',{submitter:buttonInfo(submitter)});}
    };
    record('trace-installed');
  })()`);
  // Native keyboard traversal from the answer reaches its explicit submit action.
  await evaluate("document.querySelector('#teacher-answer').focus()");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  assert.equal(await evaluate('document.activeElement.value'),'answer');
  await nativeEnter();
  await until("document.querySelector('[data-asked-count]')?.dataset.askedCount === '2'");
  tracingAnswerTransition = false;
  await oneBox();
  assert.ok(await evaluate("document.querySelector('#review-question-heading').textContent").then(t=>t.includes(first.trim())));
  evidence.checks.push('One labeled box; offline autosave retains exact text and leave guard; retry acknowledgment, reload and keyboard submit advance one adaptive fake question');

  await typeAnswer(pendingAnswer);
  await until(savedCondition);
  const q2 = await evaluate("document.querySelector('[name=turn_id]').value");
  const editPath = await evaluate("location.pathname + document.querySelector('a[href^=\"?edit=\"]').getAttribute('href')");
  await navigate(editPath,"document.querySelector('[name=draft_mode]')?.value === 'edit'");
  await typeAnswer('Edit draft to cancel');
  await until(savedCondition);
  await clickAction('discard_draft');
  await until("document.querySelector('[name=draft_mode]')?.value === 'answer' && document.querySelector('#teacher-answer')?.value === "+JSON.stringify(pendingAnswer));
  assert.equal(await evaluate("document.querySelector('[name=turn_id]').value"),q2);
  await navigate(editPath,"document.querySelector('[name=draft_mode]')?.value === 'edit'");
  await typeAnswer(edited);
  await until(savedCondition);
  await clickAction('edit');
  await until("document.querySelector('[name=draft_mode]')?.value === 'answer' && document.querySelector('#teacher-answer')?.value === "+JSON.stringify(pendingAnswer));
  assert.equal(await count(),2);
  assert.equal(await evaluate("document.querySelector('[name=turn_id]').value"),q2);
  await evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)");
  assert.ok(await evaluate('document.body.innerText').then(t=>t.includes(edited.trim()) && t.includes('Historial de correcciones')));
  evidence.checks.push('Per-turn draft survives editing/discarding old answer; explicit correction retains history and current question without spending another question');

  const sourceDetails = await evaluate(`(()=>{const d=[...document.querySelectorAll('details')].find(d=>d.querySelector('summary')?.textContent==='Planeación completa y procedencia'); return {text:d.innerText,edits:d.querySelectorAll('input,textarea,select,form').length,links:[...d.querySelectorAll('a[href*="/fuente/"]')].map(a=>a.getAttribute('href'))}})()`);
  assert.equal(sourceDetails.edits,0);
  assert.match(sourceDetails.text,/Primera lectura/);
  assert.match(sourceDetails.text,/Segunda lectura/);
  assert.match(sourceDetails.text,/Anexo/);
  assert.ok(sourceDetails.links.length>0);
  const source = await evaluate(`(async()=>{const r=await fetch(${JSON.stringify(sourceDetails.links[0])});const bytes=await r.arrayBuffer();const digest=await crypto.subtle.digest('SHA-256',bytes);return {status:r.status,type:r.headers.get('content-type'),sha:[...new Uint8Array(digest)].map(n=>n.toString(16).padStart(2,'0')).join('')}})()`);
  assert.equal(source.status,200);assert.match(source.type,/application\/pdf/);assert.equal(source.sha,config.pdfSha);
  evidence.checks.push('Full two-session dossier and annex inspection remains read-only; authenticated source bytes match generated PDF SHA');

  while (await count() < 6) {
    const before=await count();await clickAction('skip');
    await until(`Number(document.querySelector('[data-asked-count]')?.dataset.askedCount) === ${before+1}`);
    await oneBox();
  }
  await clickAction('skip');
  await until("document.querySelector('#teacher-answer') === null && document.body.innerText.includes('máximo de seis preguntas')");
  assert.equal(await count(),6);
  assert.ok(await evaluate('document.body.innerText').then(t=>t.includes('datos pendientes')));
  assert.equal(await evaluate("document.querySelector('.review-approval')"),null);
  const approvePath=reviewPath.replace('/interpretacion/','/aprobar/');
  const blockedApproval=await evaluate(`fetch(${JSON.stringify(approvePath)},{method:'POST',credentials:'same-origin',body:new URLSearchParams({csrfmiddlewaretoken:document.querySelector('[name=csrfmiddlewaretoken]').value,expected_version:document.querySelector('.view-heading').textContent.match(/Versión ([0-9]+)/)[1],confirm_approval:'1',confirm_pending_items:'1'})}).then(r=>r.status)`);
  assert.ok([400,409].includes(blockedApproval),`Unresolved approval must be rejected, got ${blockedApproval}`);
  evidence.checks.push('Six-question hard stop; honest missing data; no auto-approval and direct premature approval rejected');

  // Separate fully resolved, server-authored synthetic dossier exercises human approval.
  await navigate(config.completeReviewPath,"document.querySelector('button[value=continue]') !== null");
  await clickAction('continue');
  await until("document.querySelector('.review-approval') !== null");
  assert.equal(await count(),0);
  assert.equal(await evaluate("document.querySelector('.review-approval [name=confirm_approval]').checked"),false);
  const unchecked=await evaluate(`(async()=>{const f=document.querySelector('.review-approval');return (await fetch(f.action,{method:'POST',body:new FormData(f),credentials:'same-origin'})).status})()`);
  assert.ok([400,409].includes(unchecked));
  await evaluate("document.querySelectorAll('.review-approval input[type=checkbox]').forEach(c=>c.click());document.querySelector('.review-approval button').click()");
  await until("document.body.innerText.includes('aprobación docente vigente')");
  evidence.checks.push('Resolved dossier ends before first question; approval is unchecked and independently required, then explicitly succeeds');
  const shot=await send('Page.captureScreenshot',{format:'png'});
  writeFileSync(join(config.evidenceDir,'current-onebox-approved-synthetic.png'),Buffer.from(shot.data,'base64'));
  await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Cerrar sesión').click()");
  await until("document.querySelector('input[name=username]') !== null");
  const protectedSource=await evaluate(`fetch(${JSON.stringify(sourceDetails.links[0])},{credentials:'same-origin',redirect:'follow'}).then(r=>({type:r.headers.get('content-type'),url:r.url}))`);
  assert.doesNotMatch(protectedSource.type||'',/application\/pdf/);
  evidence.checks.push('Logout clears authenticated source access; Python wrapper checks immutable histories, approval count and no publication/session side effects');
} catch (error) {
  evidence.error=String(error.stack||error);process.exitCode=1;
} finally {
  evidence.transitionNetwork=transitionNetwork; evidence.transitionExceptions=transitionExceptions;
  writeFileSync(join(config.evidenceDir,'teacher-review-browser.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence,null,2));socket?.close();chrome.kill('SIGKILL');
}
