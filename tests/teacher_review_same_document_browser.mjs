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
  await send('Network.setBlockedURLs',{urls:['https://*']});

  async function login() {
    await navigate('/tutor/imports/new/', "document.querySelector('[name=username]') !== null", true);
    await evaluate(`document.querySelector('[name=username]').value=${JSON.stringify(config.username)};document.querySelector('[name=password]').value=${JSON.stringify(config.password)};document.querySelector('form').requestSubmit()`);
    await until("document.querySelector('#id_pdf') !== null");
  }
  await login();
  const doc=await send('DOM.getDocument');
  const upload=await send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#id_pdf'});
  await send('DOM.setFileInputFiles',{nodeId:upload.nodeId,files:[config.pdf]});
  await until("!document.querySelector('#submit-button').disabled");
  await evaluate("document.querySelector('#submit-button').click()");
  await until("location.pathname.includes('/interpretacion/') && document.querySelector('button[value=continue]') !== null");
  const reviewPath=await evaluate('location.pathname');
  evidence.sameDocumentPath=reviewPath;
  await evaluate("document.querySelector('button[value=continue]').click()");
  await until("document.querySelector('#teacher-answer') !== null");
  for(let index=0;index<config.answers.length;index++){
    assert.equal(await evaluate("Number(document.querySelector('[data-asked-count]').dataset.askedCount)"),index+1);
    assert.equal(await evaluate("document.querySelectorAll('textarea').length"),1);
    const answer=config.answers[index];
    await evaluate("document.querySelector('#teacher-answer').focus();document.querySelector('#teacher-answer').select()");
    await send('Input.insertText',{text:answer});
    await until("document.querySelector('#draft-status').textContent.includes('Borrador guardado')");
    // A genuinely new authenticated Django session reopens this same document.
    await send('Network.clearBrowserCookies');
    await login();
    await navigate(reviewPath,"document.querySelector('#teacher-answer')?.value === "+JSON.stringify(answer));
    assert.equal(await evaluate("Number(document.querySelector('[data-asked-count]').dataset.askedCount)"),index+1);
    const shot=await send('Page.captureScreenshot',{format:'png'});
    if(index===0)writeFileSync(join(config.evidenceDir,'same-document-draft.png'),Buffer.from(shot.data,'base64'));
    await evaluate("document.querySelector('button[value=answer]').click()");
    await until(index<config.answers.length-1 ? "document.querySelector('[data-asked-count]')?.dataset.askedCount === '"+(index+2)+"'" : "document.querySelector('form.review-approval') !== null");
    evidence.checks.push('Same uploaded job: one box, acknowledged draft, new authenticated session, literal reopened answer '+(index+1));
  }
  assert.equal(await evaluate('location.pathname'),reviewPath);
  assert.equal(await evaluate("Number(document.querySelector('[data-asked-count]').dataset.askedCount)"),config.answers.length);
  assert.equal(await evaluate("document.querySelectorAll('textarea').length"),0);
  await evaluate("(()=>{const f=document.querySelector('form.review-approval');f.querySelector('[name=confirm_approval]').checked=true;const p=f.querySelector('[name=confirm_pending_items]');if(p)p.checked=true;f.requestSubmit()})()");
  await until("document.body.innerText.includes('aprobación docente vigente')");
  assert.equal(await evaluate('location.pathname'),reviewPath);
  const layout=await send('Page.getLayoutMetrics');
  const size=layout.cssContentSize;
  const approved=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:size.width,height:size.height,scale:1}});
  writeFileSync(join(config.evidenceDir,'same-document-approved.png'),Buffer.from(approved.data,'base64'));
  evidence.checks.push('Same uploaded PDF and job, four coherent questions <= six, explicit teacher-role confirmation, no publication');
  await navigate(config.legacyReviewPath,"document.querySelector('#teacher-answer') !== null");
  assert.equal(await evaluate("document.querySelector('#review-question-heading').textContent.trim()"),config.legacyQuestion);
  assert.equal(await evaluate("document.querySelector('#teacher-answer').value"),config.legacyDraft);
  assert.equal(await evaluate("Number(document.querySelector('[data-asked-count]').dataset.askedCount)"),1);
  assert.equal(await evaluate("document.querySelectorAll('textarea').length"),1);
  await send('Network.clearBrowserCookies');
  await login();
  await navigate(config.legacyReviewPath,"document.querySelector('#teacher-answer')?.value === "+JSON.stringify(config.legacyDraft));
  assert.equal(await evaluate("document.querySelector('#review-question-heading').textContent.trim()"),config.legacyQuestion);
  evidence.checks.push('Historical sixteen-target question and preexisting literal draft survive policy update and a fresh authenticated session without regeneration');
  evidence.method='Actual installed Chrome CDP, Django, generated two-page PDF, production pi_luna selector with explicitly declared Pi call double; all live flags OFF';
  evidence.liveInference=false;
  writeFileSync(join(config.evidenceDir,'same-document-browser-checks.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify({browser_checks:evidence.checks,live_inference:false,same_document:true,questions:config.answers.length}));
} catch(error) {
  writeFileSync(join(config.evidenceDir,'same-document-browser-failure.json'),JSON.stringify({code:'synthetic_browser_check_failed',checks:evidence.checks,observations:evidence.observations},null,2));
  throw error;
} finally {
  socket?.close();chrome.kill('SIGTERM');
}
