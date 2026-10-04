// Actual frozen JS run against a deterministic, synthetic DOM-event harness.
// This is not browser or visual acceptance and does not load any URL.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';
const source = fs.readFileSync(process.argv[2] || new URL('../static/curriculum/teacher-review.js',import.meta.url),'utf8');
class Target {
  constructor(){this.listeners={};this.dataset={};this.attributes={};this.disabled=false;}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  removeEventListener(name,fn){this.listeners[name]=(this.listeners[name]||[]).filter(x=>x!==fn);}
  dispatch(name,extra={}){const e={target:this,currentTarget:this,defaultPrevented:false,returnValue:undefined,preventDefault(){this.defaultPrevented=true;},...extra};for(const fn of this.listeners[name]||[])fn(e);return e;}
  setAttribute(k,v){this.attributes[k]=v;}
  removeAttribute(k){delete this.attributes[k];}
}
function setup(initial=''){
 const win=new Target();win.location={href:'https://synthetic.invalid/review'};
 const input=new Target();input.value=initial;const epoch={value:'0'};const status={textContent:''};const form=new Target();
 const saveButton=new Target();saveButton.name='action';saveButton.value='answer';
 const discardButton=new Target();discardButton.name='action';discardButton.value='discard_draft';
 const blockedButton=new Target();blockedButton.dataset.domainDisabled='true';blockedButton.disabled=true;
 const buttons=[saveButton,discardButton,blockedButton];const submissions=[];
 form.querySelector=s=>s==='textarea'?input:s==='[name="draft_epoch"]'?epoch:null;
 form.querySelectorAll=s=>s==='button'?buttons:[];
 form.requestSubmit=submitter=>{const e=form.dispatch('submit',{submitter});if(!e.defaultPrevented)submissions.push({answer:input.value,action:submitter?.value});};
 const doc=new Target();doc.querySelector=s=>s==='#teacher-answer-form'?form:s==='#draft-status'?status:null;doc.querySelectorAll=s=>s==='form'?[form]:[];
 let nextId=1;const timers=new Map();const requests=[];
 class FormData {constructor(f){this.fields=new Map([['answer',input.value],['draft_epoch',epoch.value]]);}set(k,v){this.fields.set(k,v);}get(k){return this.fields.get(k);}}
 function fetch(url,opts){return new Promise((resolve,reject)=>requests.push({url,opts,resolve,reject}));}
 vm.runInNewContext(source,{document:doc,window:win,FormData,fetch,Promise,Error,String,setTimeout:(fn,ms)=>{const id=nextId++;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id)});
 const tick=async()=>{for(let n=0;n<10;n++)await Promise.resolve();};
 const flush=async(ms=600)=>{for(const [id,t] of [...timers])if(t.ms<=ms){timers.delete(id);t.fn();}await tick();};
 const type=text=>{input.value=text;input.dispatch('input');};
 const ack=async(i,n=i+1)=>{requests[i].resolve({ok:true,json:async()=>({saved:true,draft_epoch:n})});await tick();};
 return {win,input,epoch,status,form,saveButton,discardButton,blockedButton,submissions,requests,timers,type,tick,flush,ack};
}
function isGuarded(s){const event=s.win.dispatch('beforeunload');return event.defaultPrevented||event.returnValue!==undefined;}
test('unsaved text is guarded before the 600 ms autosave debounce',()=>{const s=setup();s.type('UNSAVED');assert.equal(s.requests.length,0);assert.ok(isGuarded(s),'Refresh/link/back currently leaves before any request and without an unsaved-text warning.');});
test('in-flight save stays guarded; acknowledged save clears guard',async()=>{const s=setup();s.type('IN FLIGHT');await s.flush();assert.equal(s.requests.length,1);assert.ok(isGuarded(s));await s.ack(0);assert.equal(isGuarded(s),false);assert.match(s.status.textContent,/Borrador guardado/);});
test('failed autosave keeps current text and a leave warning',async()=>{const s=setup();s.type('FAILED SAVE');await s.flush();s.requests[0].reject(new Error('offline'));await s.tick();assert.equal(s.input.value,'FAILED SAVE');assert.match(s.status.textContent,/No se pudo guardar/);assert.ok(isGuarded(s));});
test('actual JS serializes writes and advances epoch before dispatching next',async()=>{const s=setup();s.type('FIRST');await s.flush();s.type('SECOND');await s.flush();assert.equal(s.requests.length,1);await s.ack(0,10);assert.equal(s.requests.length,2);assert.equal(s.requests[1].opts.body.get('draft_epoch'),'10');assert.equal(s.requests[1].opts.body.get('answer'),'SECOND');await s.ack(1,11);assert.equal(s.epoch.value,'11');});
test('duplicate submit is suppressed while an already dispatched save completes',async()=>{const s=setup();s.type('ANSWER');await s.flush();s.form.requestSubmit(s.saveButton);s.form.requestSubmit(s.saveButton);assert.equal(s.submissions.length,0);await s.ack(0);assert.equal(s.submissions.length,1);assert.equal(s.submissions[0].answer,'ANSWER');assert.equal(s.submissions[0].action,'answer');});
test('pageshow restores buttons except domain-disabled controls',async()=>{const s=setup();s.form.requestSubmit(s.saveButton);await s.tick();await s.flush(0);assert.equal(s.saveButton.disabled,true);s.win.dispatch('pageshow',{persisted:true});assert.equal(s.saveButton.disabled,false);assert.equal(s.blockedButton.disabled,true);assert.equal(s.form.dataset.submitting,undefined);assert.equal(s.form.dataset.prepared,undefined);assert.equal(s.form.attributes['aria-busy'],undefined);});
test('existing acknowledged server draft needs no warning until changed',()=>{const s=setup('SERVER DRAFT');assert.equal(isGuarded(s),false);s.type('NEW DRAFT');assert.ok(isGuarded(s));});
test('native textarea Enter is not intercepted or submitted',()=>{const s=setup();const e=s.input.dispatch('keydown',{key:'Enter'});assert.equal(e.defaultPrevented,false);assert.equal(s.submissions.length,0);});
test('deliberate form submission bypasses warning; pageshow restores dirty protection',async()=>{const s=setup();s.type('UNSAVED DIRECT SUBMIT');s.form.requestSubmit(s.saveButton);await s.tick();assert.equal(s.submissions.length,1);assert.equal(isGuarded(s),false);s.win.dispatch('pageshow',{persisted:true});assert.ok(isGuarded(s));});

test('an older acknowledgment cannot clear a newer edit with identical text',async()=>{const s=setup();s.type('A');await s.flush();s.type('B');await s.flush();s.type('A');await s.ack(0);assert.ok(isGuarded(s));await s.ack(1);assert.ok(isGuarded(s));await s.flush();await s.ack(2);assert.equal(isGuarded(s),false);});

// CDP keyDown must carry Enter's character event to activate a native button.
// This checks the actual browser-harness helper; it does not launch a browser.
test('CDP Enter carries carriage return without replacing native keyboard activation', async () => {
  const harness = fs.readFileSync(new URL('./teacher_review_browser.mjs', import.meta.url), 'utf8');
  const helper = harness.match(/  async function nativeEnter\(\) \{([\s\S]*?)\n  \}/);
  assert.ok(helper, 'The current journey must retain its native Enter helper');
  const events = [];
  await vm.runInNewContext(`(async () => {${helper[0]}; await nativeEnter();})()`, {
    send: async (method, params) => events.push(JSON.parse(JSON.stringify({method, params}))),
  });
  assert.deepEqual(events, [
    {method: 'Input.dispatchKeyEvent', params: {
      type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13,
      text: '\r', unmodifiedText: '\r',
    }},
    {method: 'Input.dispatchKeyEvent', params: {
      type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13,
    }},
  ]);
});

// Diagnostic parser tests: no browser, network or full form serialization.
test('review POST diagnostics allow only action and numeric concurrency metadata', () => {
  const harness=fs.readFileSync(new URL('./teacher_review_browser.mjs',import.meta.url),'utf8');
  const helper=harness.slice(harness.indexOf('function safeReviewPost('),harness.indexOf('// End diagnostic allowlist.'));
  const parse=vm.runInNewContext(`(${helper.trim()})`,{URLSearchParams});
  const clean=value=>JSON.parse(JSON.stringify(parse(value)));
  const body=new URLSearchParams({action:'answer',expected_revision:'5',expected_version:'2',draft_epoch:'8',
    csrfmiddlewaretoken:'SECRET_CSRF_SENTINEL',password:'SECRET_PASSWORD_SENTINEL',answer:'PRIVATE_ANSWER_SENTINEL'}).toString();
  assert.deepEqual(clean(body),{action:'answer',expected_revision:'5',expected_version:'2',draft_epoch:'8'});
  assert.doesNotMatch(JSON.stringify(clean(body)),/SECRET|PRIVATE/);
  assert.equal(clean('draft_epoch=9').action,'missing');
  assert.equal(clean('action=UNTRUSTED_SECRET&draft_epoch=abc').action,'other');
  assert.equal(clean('action=answer&draft_epoch=abc').draft_epoch,null);
  assert.equal(clean('action=answer&draft_epoch='+ '9'.repeat(21)).draft_epoch,null);
});
test('multipart autosave diagnostic redaction keeps action and epoch only', () => {
  const harness=fs.readFileSync(new URL('./teacher_review_browser.mjs',import.meta.url),'utf8');
  const helper=harness.slice(harness.indexOf('function safeReviewPost('),harness.indexOf('// End diagnostic allowlist.'));
  const parse=vm.runInNewContext(`(${helper.trim()})`,{URLSearchParams});
  const part=(name,value)=>`--safe\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`;
  const data=part('action','save_draft')+part('draft_epoch','3')+part('csrfmiddlewaretoken','SECRET')+part('answer','PRIVATE')+'--safe--\r\n';
  const result=JSON.parse(JSON.stringify(parse(data)));
  assert.deepEqual(result,{action:'save_draft',expected_revision:null,expected_version:null,draft_epoch:'3'});
  assert.doesNotMatch(JSON.stringify(result),/SECRET|PRIVATE/);
});
