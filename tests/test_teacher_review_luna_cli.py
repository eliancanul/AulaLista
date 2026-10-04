"""Local CLI contract with an invented executable. Never run Codex or a model."""
import copy
import datetime
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pytest
from django.urls import reverse

from curriculum.luna_review_provider import (
    CLI_VERSION, LIMITATIONS, MODEL, PROFILE_SHA256, LunaCodexCliProvider,
)
from curriculum.codex_review_transport import CodexEvents, bounded_process, strict_json
from curriculum.teacher_review_provider import ReviewProviderError, SYSTEM
from test_teacher_review import ready_job, start, save, advance, ask_first

FAKE_CLI = r'''
import json, os, pathlib, sys, time
base=pathlib.Path(__file__).parent
scenario=json.loads((base/'scenario.json').read_text())
a=sys.argv[1:]
with (base/'calls.jsonl').open('a') as stream: stream.write(json.dumps(a)+'\n')
if a == ['--version']:
 print('codex-cli '+scenario.get('version','0.159.2'));sys.exit(0)
if a == ['exec','--help']:
 print('--ignore-user-config --strict-config --ephemeral --json --output-schema --output-last-message --skip-git-repo-check');sys.exit(0)
if a == ['login','status']:
 print('Logged in using ChatGPT' if not scenario.get('logout') else 'Not logged in');sys.exit(bool(scenario.get('logout')))
if a[0] == 'sandbox':
 if scenario.get('sandbox_fail'): print('synthetic sandbox unavailable',file=sys.stderr);sys.exit(1)
 cmd=a[a.index('--')+1:]
 if cmd == ['/bin/true']: sys.exit(0)
 if cmd[0] == '/bin/cat':
  if pathlib.Path(cmd[1]).name == 'read-canary.txt' or scenario.get('read_escape'):
   sys.stdout.buffer.write(pathlib.Path(cmd[1]).read_bytes());sys.exit(0)
  sys.exit(1)
 if cmd[0] == '/usr/bin/touch':
  if scenario.get('write_escape'): pathlib.Path(cmd[1]).touch();sys.exit(0)
  sys.exit(1)
 sys.exit(2)
assert a[0]=='exec' and a[-1]=='-'
prompt=sys.stdin.read()
(base/'captured.txt').write_text(prompt)
context=json.loads(prompt.split('\nDATOS:\n',1)[1])
(base/'captured-context.json').write_text(json.dumps(context))
def event(x): print(json.dumps(x),flush=True)
event({'type':'thread.started','thread_id':'synthetic-thread'})
event({'type':'turn.started'})
mode=scenario.get('mode','ok')
if mode=='tool':
 event({'type':'item.started','item':{'type':'command_execution','command':'INVENTED NEVER EXECUTED'}});time.sleep(5)
if mode=='timeout': time.sleep(5)
if mode=='oversize': print('x'*200000,flush=True);time.sleep(5)
if mode=='error': event({'type':'error','message':'PRIVATE_PROVIDER_ERROR_SENTINEL'});sys.exit(1)
if mode=='reroute': event({'type':'model.rerouted','model':'other-model'});sys.exit(0)
output=scenario.get('output',{'question':'Pregunta sintetica?', 'targets':[context['missing_target_ids'][0]] if context['missing_target_ids'] else [], 'answer_updates':[]})
text=json.dumps(output,ensure_ascii=False)
if mode=='invalid_json': text='{"question":null,"question":"duplicate","targets":[],"answer_updates":[]}'
event({'type':'item.completed','item':{'id':'synthetic-message','type':'agent_message','text':text}})
usage={'input_tokens':100,'cached_input_tokens':5,'output_tokens':20}
if mode=='missing_usage': usage.pop('output_tokens')
if mode=='bad_usage': usage['input_tokens']=True
if mode=='overcount_usage': usage['cached_input_tokens']=101
event({'type':'turn.completed','usage':usage})
if mode=='duplicate_terminal': event({'type':'turn.completed','usage':usage})
final=pathlib.Path(a[a.index('--output-last-message')+1])
if mode=='fifo_final':
 os.mkfifo(final)
elif mode=='symlink_final':
 target=base/'synthetic-final.txt';target.write_text(text);final.symlink_to(target)
else: final.write_text('different' if mode=='mismatch' else text+'\n')
'''


@pytest.fixture
def fake_cli(tmp_path):
    base = tmp_path / 'fake-cli'
    base.mkdir()
    exe = base / 'codex-fixture'
    exe.write_text('#!' + sys.executable + '\n' + FAKE_CLI)
    exe.chmod(0o755)
    review = base / 'review.json'
    review.write_text(json.dumps({
        'schema':'aulalista.codex-local-review.v1', 'cli_version':CLI_VERSION,
        'launcher_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'profile_contract_sha256':PROFILE_SHA256, 'review_id':str(uuid.uuid4()),
        'reviewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'evidence_sha256':hashlib.sha256(b'invented fixture review, not actual safety evidence').hexdigest(),
        'external_surface_review':'reviewed_no_external_surfaces', 'limitations_acknowledged':LIMITATIONS,
    }))
    (base / 'scenario.json').write_text('{}')
    def adapter(**kwargs):
        return LunaCodexCliProvider(executable=str(exe),runtime_review=str(review),
            attempt_root=tmp_path/'attempts',live_enabled=True,**kwargs)
    def scenario(**values): (base/'scenario.json').write_text(json.dumps(values))
    def calls(): return [json.loads(line) for line in (base/'calls.jsonl').read_text().splitlines()] if (base/'calls.jsonl').exists() else []
    return base, review, adapter, scenario, calls


def context():
    target = {'target_id':'general/proposito','field_name':'proposito','human_label':'Propósito'}
    return {'all_targets':[target], 'missing_fields':[copy.deepcopy(target)], 'questions_remaining':6,
            'dossier':{'version':1,'sessions':[{'id':'one'},{'id':'later'}]},
            'source_document':{'source_sha256':'a'*64,'pages':[{'page_number':1,'text':'EXACT SOURCE'}]},'turns':[]}


def test_cli_stdin_schema_requested_identity_full_context_and_receipt(fake_cli):
    base, _, adapter, _, calls = fake_cli
    original = context()
    result = adapter()(original)
    from curriculum.teacher_review_context import restore_provider_context
    captured = json.loads((base/'captured-context.json').read_text())
    assert restore_provider_context(captured) == original
    assert original == context()
    prompt = (base/'captured.txt').read_text()
    assert prompt.startswith(SYSTEM + '\nDATOS:\n')
    executions = [a for a in calls() if a[0]=='exec' and '--help' not in a]
    assert len(executions) == 1
    args = executions[0]
    assert args[args.index('--model')+1] == MODEL
    assert 'model_reasoning_effort="high"' in args
    assert args[-1] == '-' and 'EXACT SOURCE' not in str(args)
    assert '--ignore-rules' not in args and '--sandbox' not in args
    assert not any('dangerously' in a or 'full-access' in a or 'sandbox_mode' in a for a in args)
    assert 'permissions.aulalista_luna_review.network.enabled=false' in args
    assert 'shell_environment_policy.inherit="none"' in args
    tables=[arg for arg in args if arg.startswith('permissions.aulalista_luna_review.filesystem=')]
    assert len(tables)==1 and tables[0].split('=',1)[1].startswith('{')
    import tomllib
    assert tomllib.loads('filesystem='+tables[0].split('=',1)[1])['filesystem'][':root']=='deny'
    receipt = result.provider_receipt
    assert receipt['requested_model'] == MODEL and receipt['observed_model'] is None
    assert receipt['requested_effort'] == 'high'
    assert receipt['reported_usage'] == {'input_tokens':100,'cached_input_tokens':5,'output_tokens':20,'reasoning_output_tokens':None}
    assert receipt['transport_internal_retries'] is None and receipt['provider_dispatch_count'] is None
    assert receipt['tool_prevention_attested'] is False
    assert receipt['execution_status'] == 'completed'
    assert 'EXACT SOURCE' not in json.dumps(receipt)
    root=adapter().attempt_root
    assert not (root/'STOP_REQUIRED.json').exists() and not (root/'.dispatch.lock').exists()
    recorded=list(root.glob('*/receipt.json'));assert len(recorded)==1
    assert json.loads(recorded[0].read_text()) == receipt


@pytest.mark.parametrize('options,code', [
    ({'version':'0.158.0'},'luna_cli_version_unsupported'),
    ({'logout':True},'luna_login_required'),
    ({'sandbox_fail':True},'luna_sandbox_preflight_failed'),
    ({'read_escape':True},'luna_sandbox_preflight_failed'),
    ({'write_escape':True},'luna_sandbox_preflight_failed'),
])
def test_failed_preflight_never_creates_admission_or_sends_prompt(fake_cli,options,code):
    base,_,adapter,scenario,calls=fake_cli;scenario(**options)
    with pytest.raises(ReviewProviderError,match='^'+code+'$'): adapter()(context())
    assert not (base/'captured.txt').exists()
    assert not list(adapter().attempt_root.glob('*/admission.json'))
    assert not any(a[0]=='exec' and '--help' not in a for a in calls())
    if options.get('sandbox_fail'):
        assert len([a for a in calls() if a[0]=='sandbox'])==1


@pytest.mark.parametrize('mode', ['tool','timeout','oversize','error','reroute','missing_usage','bad_usage',
                                  'overcount_usage','duplicate_terminal','invalid_json','mismatch','symlink_final','fifo_final'])
def test_uncertain_or_rejected_output_blocks_any_second_launch(fake_cli,mode):
    _,_,adapter,scenario,calls=fake_cli;scenario(mode=mode)
    provider=adapter(timeout=1)
    with pytest.raises(ReviewProviderError,match='^luna_(attempt_unknown|response_rejected)$') as error:
        provider(context())
    assert (provider.attempt_root/'STOP_REQUIRED.json').is_file()
    assert 'PRIVATE_PROVIDER_ERROR_SENTINEL' not in str(error.value)
    launches=lambda:len([a for a in calls() if a[0]=='exec' and '--help' not in a])
    assert launches()==1
    with pytest.raises(ReviewProviderError,match='^luna_prior_attempt_blocked$'): provider(context())
    assert launches()==1


def test_disabled_missing_review_and_oversize_fail_before_process(fake_cli,monkeypatch):
    _,review,adapter,_,calls=fake_cli
    provider=adapter();provider.live_enabled=False
    with pytest.raises(ReviewProviderError,match='luna_live_not_enabled'):provider(context())
    provider.live_enabled=True
    review.write_text('{}')
    with pytest.raises(ReviewProviderError,match='luna_runtime_review_required'):provider(context())
    monkeypatch.setattr('curriculum.luna_review_provider.MAX_REQUEST_BYTES',16)
    with pytest.raises(ReviewProviderError,match='luna_full_context_too_large'):provider(context())
    assert calls()==[]


def test_unfinished_admission_or_lock_cannot_be_reused(fake_cli):
    _,_,adapter,_,calls=fake_cli;provider=adapter();root=provider.attempt_root
    root.mkdir(mode=0o700);d=root/'old';d.mkdir();(d/'admission.json').write_text('{}')
    with pytest.raises(ReviewProviderError,match='luna_prior_attempt_blocked'):provider(context())
    assert calls()==[]


@pytest.mark.django_db
def test_cli_failure_preserves_literal_answer_and_blocks_review_continue(ready_job,fake_cli):
    client,user,job=ready_job
    review=save(start(job,user,ask_first),user,'  Literal teacher answer.\n')
    _,_,adapter,scenario,calls=fake_cli;scenario(mode='error')
    review=advance(review,user,adapter())
    assert review.state['turns'][0]['answer']=='  Literal teacher answer.\n'
    assert review.state['error']=='luna_attempt_unknown'
    page=client.get(reverse('tutor-import-interpretation',args=[job.pk]))
    assert page.context['provider_blocked'] is True
    assert b'value="continue"' not in page.content
    before=len(calls())
    from curriculum.teacher_review import ReviewError
    with pytest.raises(ReviewError):advance(review,user,adapter())
    assert len(calls())==before
    assert not job.is_approved


@pytest.mark.django_db
def test_cli_success_uses_existing_literal_authority_and_persists_question(ready_job,fake_cli):
    _,user,job=ready_job
    _,_,adapter,_,_=fake_cli
    review=start(job,user,adapter())
    assert review.state['status']=='asking' and len(review.state['turns'])==1
    assert review.state['events'][-1]['provider_receipt']['requested_model']==MODEL
    assert review.state['events'][-1]['provider_receipt']['observed_model'] is None
    assert not job.is_approved


@pytest.mark.parametrize('raw', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'])
def test_strict_json_rejects_ambiguous_or_nonfinite_data(raw):
    with pytest.raises(ValueError):strict_json(raw)


def test_out_of_order_terminal_is_not_accepted():
    audit=CodexEvents(MODEL)
    audit.feed(b'{"type":"turn.completed","usage":{"input_tokens":1,"cached_input_tokens":0,"output_tokens":1}}\n')
    assert audit.reason=='invalid_terminal'


@pytest.mark.parametrize('output', [
    {'question':1,'targets':[],'answer_updates':[]},
    {'question':None,'targets':[False],'answer_updates':[]},
    {'question':None,'targets':[],'answer_updates':[{'turn_id':[],'target_id':'x','quote':'text'}]},
    {'question':None,'targets':[],'answer_updates':[],'approved':True},
    {'question':None,'targets':[],'answer_updates':[{'turn_id':'x','target_id':'y','quote':'z','origin':'teacher_entered'}]},
])
def test_cli_final_schema_rejects_wrong_types_and_extra_authority(fake_cli,output):
    _,_,adapter,scenario,_=fake_cli;scenario(output=output)
    with pytest.raises(ReviewProviderError,match='luna_response_rejected'):
        adapter()(context())


@pytest.mark.django_db
def test_semantic_rejection_keeps_transport_receipt_and_never_applies_source_only_quote(ready_job,fake_cli):
    _,user,job=ready_job
    review=save(start(job,user,ask_first),user,'Explicit teacher answer')
    turn=review.state['turns'][0]
    _,_,adapter,scenario,_=fake_cli
    scenario(output={'question':None,'targets':[],'answer_updates':[
        {'turn_id':turn['id'],'target_id':turn['targets'][0],'quote':'Source-only invented authority'}]})
    review=advance(review,user,adapter())
    assert review.state['error']=='unsupported_human_value'
    assert review.state['turns'][0]['applied']==[]
    assert review.state['turns'][0]['answer']=='Explicit teacher answer'
    assert review.state['events'][-1]['provider_receipt']['reported_usage']['input_tokens']==100
    assert not job.is_approved


@pytest.mark.django_db
@pytest.mark.parametrize('code',['gemini_attempt_unknown','luna_attempt_unknown','luna_response_rejected'])
def test_answer_correction_or_source_resume_cannot_clear_a_blocked_attempt(ready_job,code):
    _,user,job=ready_job
    review=save(start(job,user,ask_first),user,'Original literal answer')
    review.state.update(status='pending',error=code)
    review.save(update_fields=['state'])
    from curriculum.teacher_review import submit_answer,resume_changed_dossier,ReviewError
    review,_=submit_answer(job_id=job.pk,user=user,expected_revision=review.revision,
        expected_version=review.dossier_version,expected_draft_epoch=review.draft_epoch,
        receipt=str(uuid.uuid4()),turn_id=review.state['turns'][0]['id'],answer='Corrected literal answer',edit=True)
    assert review.state['error']==code
    review=resume_changed_dossier(job_id=job.pk,user=user,expected_revision=review.revision,
                                 expected_version=review.dossier_version)
    assert review.state['error']==code and review.state['turns'][0]['answer']=='Corrected literal answer'
    with pytest.raises(ReviewError):advance(review,user,lambda _:pytest.fail('No new model call'))


@pytest.mark.django_db
def test_luna_configured_notice_is_settings_only(ready_job,settings,monkeypatch):
    client,_,job=ready_job
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER='luna'
    settings.AULALISTA_LUNA_CLI_EXECUTABLE='/synthetic-not-executed/codex'
    settings.AULALISTA_LUNA_RUNTIME_REVIEW='/synthetic-not-read/review.json'
    monkeypatch.setattr(LunaCodexCliProvider,'preflight',lambda *_:pytest.fail('GET cannot run CLI'))
    for enabled,code in [(False,'luna_live_not_enabled'),(True,'provider_configured_unverified')]:
        settings.AULALISTA_LUNA_LIVE_ENABLED=enabled
        page=client.get(reverse('tutor-import-interpretation',args=[job.pk]))
        assert page.context['provider_notice']['code']==code
        assert 'CLI' in page.context['provider_notice']['message']
        assert page.context['state']['turns']==[]


@pytest.mark.parametrize('name',['CODEX_API_KEY','OPENAI_API_KEY','OPENAI_BASE_URL'])
def test_auth_overrides_are_refused_by_name_without_reading_secret_values(fake_cli,monkeypatch,name):
    from curriculum.luna_review_provider import auth_override_present
    class NamesOnly(dict):
        def __getitem__(self,key): pytest.fail('Credential values must not be read')
        def get(self,*args): pytest.fail('Credential values must not be read')
    assert auth_override_present(NamesOnly({name:object()}))
    assert not auth_override_present(NamesOnly({'HOME':object(),'CODEX_HOME':object()}))
    monkeypatch.setattr('curriculum.luna_review_provider.auth_override_present',lambda:True)
    _,_,adapter,_,calls=fake_cli
    with pytest.raises(ReviewProviderError,match='luna_auth_override_present'):adapter()(context())
    assert calls()==[]


def test_regular_reader_rejects_fifo_without_waiting_for_a_writer(tmp_path):
    import os,time
    from curriculum.codex_review_transport import read_regular
    fifo=tmp_path/'invented-fifo';os.mkfifo(fifo)
    started=time.monotonic()
    with pytest.raises(ValueError):read_regular(fifo,16)
    assert time.monotonic()-started<1



def test_group_cleanup_stops_an_ordinary_detached_pipe_descendant(tmp_path):
    import time
    marker=tmp_path/'child-survived'
    code="""
import os,sys,time
if os.fork()==0:
 os.close(0);os.close(1);os.close(2)
 time.sleep(0.4)
 with open(sys.argv[1],'w') as f:f.write('survived')
 os._exit(0)
"""
    result=bounded_process([sys.executable,'-c',code,str(marker)],cwd=tmp_path,timeout=2,max_bytes=1024)
    assert result['returncode']==0 and result['reaped'] is True
    time.sleep(0.6)
    assert not marker.exists()


def test_writable_operator_review_is_not_trusted(fake_cli):
    _,review,adapter,_,calls=fake_cli;review.chmod(0o666)
    with pytest.raises(ReviewProviderError,match='luna_runtime_review_required'):adapter()(context())
    assert calls()==[]


def test_runtime_review_fingerprint_binds_every_emitted_security_setting(tmp_path):
    from curriculum.luna_review_provider import PROFILE_CONTRACT,profile_options
    import tomllib
    options=profile_options(tmp_path/'work',tmp_path/'state',tmp_path/'logs')
    assert len(options)==2*len(PROFILE_CONTRACT['config'])
    for key in PROFILE_CONTRACT['config']:
        assert any(arg.startswith(key+'=') for arg in options)
    assert hashlib.sha256(json.dumps(PROFILE_CONTRACT,sort_keys=True,separators=(',',':')).encode()).hexdigest()==PROFILE_SHA256
    for field in ['web_search','allow_login_shell','shell_environment_policy.ignore_default_excludes',
                  'shell_environment_policy.experimental_use_profile','shell_environment_policy.set']:
        assert field in PROFILE_CONTRACT['config']


def test_failed_receipt_storage_retains_a_lock_and_unfinished_admission(fake_cli,monkeypatch):
    import curriculum.luna_review_provider as module
    _,_,adapter,scenario,calls=fake_cli;scenario(mode='tool')
    original=module.commit_json
    def fail_terminal(path,value):
        if Path(path).name in ('receipt.json','STOP_REQUIRED.json'):
            raise OSError('synthetic storage failure')
        return original(path,value)
    monkeypatch.setattr(module,'commit_json',fail_terminal)
    provider=adapter()
    with pytest.raises(ReviewProviderError,match='luna_attempt_unknown'):provider(context())
    assert (provider.attempt_root/'.dispatch.lock').exists()
    assert list(provider.attempt_root.glob('*/admission.json'))
    before=len(calls())
    with pytest.raises(ReviewProviderError,match='luna_prior_attempt_blocked'):provider(context())
    assert len(calls())==before
