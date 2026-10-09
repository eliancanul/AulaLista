"""Invented Pi/isolation processes only. No provider, credential or network use."""
import copy
import datetime
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pytest
from django.test import override_settings
from django.urls import reverse

from curriculum.pi_review_provider import CONTRACT_SHA256, DRIVER, LIMITATIONS, PiLunaProvider, digest_file, preflight_driver_diagnostic
from curriculum.pi_review_transport import IDENTITY, PiEvents
from curriculum.teacher_review_provider import ReviewProviderError, get_review_provider, provider_configuration_notice
from test_teacher_review import ready_job, start, save, advance, ask_first
from test_teacher_review_luna_cli import context

FAKE = r'''
import json, pathlib, sys, time
base = pathlib.Path(__file__).parent
scenario = json.loads((base/'scenario.json').read_text())
args = sys.argv[1:]
with (base/'calls.jsonl').open('a') as stream: stream.write(json.dumps(args)+'\n')
assert args[0]=='--work' and args[2]=='--'
cmd=args[3:]
mode=scenario.get('mode','ok')
if cmd[0]=='/usr/bin/true': sys.exit(1 if mode=='sandbox' else 0)
if cmd[0]=='/bin/cat':
 if pathlib.Path(cmd[1]).name=='read-canary.txt' or mode=='read_escape':
  sys.stdout.buffer.write(pathlib.Path(cmd[1]).read_bytes());sys.exit(0)
 sys.exit(1)
if cmd[0]=='/usr/bin/touch':
 if mode=='write_escape': pathlib.Path(cmd[1]).touch();sys.exit(0)
 sys.exit(1)
if cmd[-1]=='--version': print(scenario.get('node_version','v22.22.3'));sys.exit(0)
identity=json.loads((base/'identity.json').read_text())
def event(value): print(json.dumps(value),flush=True)
if '--preflight' in cmd:
 if 'preflight_stderr' in scenario:
  sys.stderr.write(scenario['preflight_stderr']);sys.exit(1)
 if mode=='preflight':sys.exit(1)
 event({'type':'pi.ready',**identity,'auth_type':'oauth','auth_refresh':False,
        'tools':0,'resources':0,'automatic_retries':0,'agent_loop':False});sys.exit(0)
assert '--generate' in cmd
raw=sys.stdin.read();(base/'captured.txt').write_text(raw)
request=json.loads(raw);context=json.loads(request['prompt'].split('\nDATOS:\n',1)[1])
event({'type':'pi.request','dispatch_count':1})
if mode=='timeout':time.sleep(5)
if mode=='oversize':print('x'*200000,flush=True);time.sleep(5)
if mode=='error':print('PRIVATE_ERROR_SENTINEL',file=sys.stderr);sys.exit(1)
event({'type':'pi.start',**identity})
if mode=='tool': event({'type':'tool_execution_start','toolName':'NEVER_EXECUTED'});time.sleep(5)
missing=context.get('missing_target_ids')
if missing is None: missing=[context['all_targets'][i][0] for i in context['missing_target_indices']]
output=scenario.get('output',{'question':'Pregunta sintética?', 'targets':missing[:1], 'answer_updates':[]})
text=json.dumps(output)
if mode=='duplicate_json':text='{"question":null,"question":"duplicate","targets":[],"answer_updates":[]}'
usage={'input':95,'cacheRead':5,'cacheWrite':0,'output':20,'totalTokens':120,'cost':{'total':1.5}}
if mode=='missing_usage':usage.pop('output')
if mode=='bool_usage':usage['input']=True
if mode=='sum_usage':usage['totalTokens']=999
if mode=='reasoning_usage':usage['reasoning']=21
if mode=='zero_usage':usage={k:0 for k in ['input','cacheRead','cacheWrite','output','totalTokens']}
message={'role':'assistant','provider':identity['provider'],'model':identity['model'],'api':identity['api'],
         'stopReason':'stop','content':[{'type':'text','text':text}],'usage':usage}
if mode=='reroute':message['responseModel']='other-model'
if mode=='wrong_provider':message['provider']='openai'
if mode=='length':message['stopReason']='length'
if mode=='tool_content':message['content']=[{'type':'toolCall','name':'NEVER_EXECUTED'}]
if mode=='diagnostics':message['diagnostics']=[{'type':'provider_transport_failure'}]
if mode=='big_final':message['content'][0]['text']='x'*33000
event({'type':'pi.result','message':message})
if mode=='duplicate_terminal':event({'type':'pi.result','message':message})
if mode!='missing_terminal':event({'type':'pi.completed'})
if mode=='truncated':sys.stdout.write('{')
if mode=='stderr_success':print('unexpected output',file=sys.stderr)
'''


@pytest.fixture
def fake_pi(tmp_path, monkeypatch):
    for key in ('OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL','NODE_OPTIONS','NODE_PATH',
                'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        monkeypatch.delenv(key, raising=False)
    base = tmp_path / 'fixture'
    base.mkdir()
    launcher = base / 'isolation'
    launcher.write_text('#!' + sys.executable + '\n' + FAKE)
    launcher.chmod(0o755)
    node = base / 'node'
    node.write_text('synthetic runtime, never invoked directly')
    node.chmod(0o755)
    package = base / 'pi'
    (package / 'dist/core').mkdir(parents=True)
    (package / 'package.json').write_text('{"name":"@earendil-works/pi-coding-agent","version":"0.84.4"}')
    for name in ('model-runtime', 'auth-storage'):
        (package / 'dist/core' / (name + '.js')).write_text('// invented fixture')
    agent = base / 'agent'
    agent.mkdir()
    catalog = base / 'models-store.json'
    catalog.write_text('{}')
    review = base / 'review.json'
    hashes = {'node_sha256': digest_file(node), 'isolation_launcher_sha256': digest_file(launcher),
              'driver_sha256': digest_file(DRIVER), 'package_manifest_sha256': digest_file(package/'package.json'),
              'model_runtime_sha256': digest_file(package/'dist/core/model-runtime.js'),
              'auth_storage_sha256': digest_file(package/'dist/core/auth-storage.js'),
              'catalog_sha256': digest_file(catalog)}
    review.write_text(json.dumps({'schema':'aulalista.pi-external-review.v1', 'review_id':str(uuid.uuid4()),
        'reviewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'evidence_sha256':hashlib.sha256(b'INVENTED TEST FIXTURE, NOT AN ACTUAL REVIEW').hexdigest(),
        'contract_sha256':CONTRACT_SHA256, 'runtime':hashes,
        'isolation':'reviewed_external_boundary_no_unrestricted_fallback', 'limitations':LIMITATIONS}))
    (base / 'scenario.json').write_text('{}')
    (base / 'identity.json').write_text(json.dumps(IDENTITY))
    def provider(**kwargs):
        return PiLunaProvider(node=str(node),package_dir=str(package),agent_dir=str(agent),
            catalog_file=str(catalog),isolation_launcher=str(launcher),runtime_review=str(review),
            attempt_root=tmp_path/'attempts',live_enabled=True,**kwargs)
    def scenario(**values): (base/'scenario.json').write_text(json.dumps(values))
    def calls():
        file=base/'calls.jsonl'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []
    return base, provider, scenario, calls


def test_full_context_stdin_and_pi_usage_are_preserved(fake_pi):
    base, factory, _, calls = fake_pi
    original = context()
    reply = factory()(original)
    raw = (base/'captured.txt').read_text()
    request = json.loads(raw)
    assert raw == json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    encoded_text = request['prompt'].split('\nDATOS:\n')[1]
    assert encoded_text == json.dumps(json.loads(encoded_text), ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':'))
    schema_text = request['prompt'].split('\nDATOS:\n')[0].split('\n', 1)[1]
    assert schema_text == json.dumps(json.loads(schema_text), separators=(',', ':'))
    from curriculum.teacher_review_context import restore_provider_context
    assert restore_provider_context(json.loads(request['prompt'].split('\nDATOS:\n')[1])) == original
    assert original == context()
    assert not any('EXACT SOURCE' in str(args) for args in calls())
    assert sum('--generate' in args for args in calls()) == 1
    assert all(args[0]=='--work' and args[2]=='--' for args in calls())
    receipt = reply.provider_receipt
    assert receipt['requested_model']=='gpt-6-luna' and receipt['observed_model'] is None
    assert receipt['requested_provider']=='openai-codex' and receipt['pi_version']=='0.84.4'
    assert receipt['reported_usage']=={'input':95,'cacheRead':5,'cacheWrite':0,'output':20,'totalTokens':120,'reasoning':None}
    assert receipt['provider_dispatch_count']==1 and receipt['automatic_retries']==0
    assert receipt['real_cost_currency'] is None and receipt['execution_status']=='completed'
    assert 'EXACT SOURCE' not in json.dumps(receipt)
    root=factory().attempt_root
    assert json.loads(next(root.glob('*/receipt.json')).read_text())==receipt
    assert next(root.glob('*/final.json')).exists()
    assert not (root/'STOP_REQUIRED.json').exists() and not (root/'.dispatch.lock').exists()


@pytest.mark.parametrize('mode', ['sandbox','read_escape','write_escape','preflight'])
def test_preflight_failure_never_admits_prompt(fake_pi,mode):
    base,factory,scenario,calls=fake_pi;scenario(mode=mode)
    with pytest.raises(ReviewProviderError,match='pi_.*preflight_failed'):factory()(context())
    assert not (base/'captured.txt').exists()
    assert not list(factory().attempt_root.glob('*/admission.json'))
    assert not any('--generate' in args for args in calls())


@pytest.mark.parametrize('mode', ['tool','timeout','oversize','error','reroute','wrong_provider','length','tool_content',
    'diagnostics','missing_usage','bool_usage','sum_usage','reasoning_usage','zero_usage','big_final',
    'duplicate_json','duplicate_terminal','missing_terminal','truncated','stderr_success'])
def test_unknown_or_rejected_attempt_stops_without_relaunch(fake_pi,mode):
    _,factory,scenario,calls=fake_pi;scenario(mode=mode)
    provider=factory(timeout=1)
    with pytest.raises(ReviewProviderError,match='^pi_(attempt_unknown|response_rejected)$') as error:
        provider(context())
    assert 'PRIVATE_ERROR_SENTINEL' not in str(error.value)
    assert (provider.attempt_root/'STOP_REQUIRED.json').exists()
    before=len(calls())
    with pytest.raises(ReviewProviderError,match='^pi_prior_attempt_blocked$'):provider(context())
    assert len(calls())==before


def test_disabled_route_missing_review_changed_runtime_and_override_fail_closed(fake_pi,monkeypatch):
    base,factory,_,calls=fake_pi
    provider=factory();provider.live_enabled=False
    with pytest.raises(ReviewProviderError,match='pi_live_not_enabled'):provider(context())
    provider.live_enabled=True
    monkeypatch.setenv('OPENAI_API_KEY','NEVER_READ_OR_TRANSMITTED')
    with pytest.raises(ReviewProviderError,match='pi_environment_override_present'):provider(context())
    monkeypatch.delenv('OPENAI_API_KEY')
    (base/'node').write_text('changed runtime')
    with pytest.raises(ReviewProviderError,match='pi_runtime_review_required'):provider(context())
    assert calls()==[]


def test_bad_node_version_blocks_before_inference(fake_pi):
    _,factory,scenario,calls=fake_pi;scenario(node_version='v24.19.0')
    with pytest.raises(ReviewProviderError,match='pi_node_version_unsupported'):factory()(context())
    assert not any('--generate' in args for args in calls())


def test_request_bound_and_existing_admission_block(fake_pi,monkeypatch):
    _,factory,_,calls=fake_pi;provider=factory()
    monkeypatch.setattr('curriculum.pi_review_provider.MAX_REQUEST_BYTES',1)
    with pytest.raises(ReviewProviderError,match='pi_full_context_too_large'):provider(context())
    monkeypatch.setattr('curriculum.pi_review_provider.MAX_REQUEST_BYTES',4 * 1024 * 1024)
    provider.attempt_root.mkdir(mode=0o700)
    old=provider.attempt_root/'old';old.mkdir();(old/'admission.json').write_text('{}')
    with pytest.raises(ReviewProviderError,match='pi_prior_attempt_blocked'):provider(context())
    assert calls()==[]


@pytest.mark.parametrize('output', [
    {'question':1,'targets':[],'answer_updates':[]},
    {'question':None,'targets':[True],'answer_updates':[]},
    {'question':None,'targets':[],'answer_updates':[],'approved':True},
])
def test_schema_cannot_grant_new_authority(fake_pi,output):
    _,factory,scenario,_=fake_pi;scenario(output=output)
    with pytest.raises(ReviewProviderError,match='pi_response_rejected'):factory()(context())


@override_settings(AULALISTA_TEACHER_REVIEW_PROVIDER='pi_luna', AULALISTA_PI_LIVE_ENABLED=False)
def test_opt_in_selection_never_changes_codex_or_launches_on_get():
    assert isinstance(get_review_provider(),PiLunaProvider)
    assert provider_configuration_notice()['code']=='pi_live_not_enabled'
    with pytest.raises(ReviewProviderError,match='pi_live_not_enabled'):get_review_provider()(context())
    with override_settings(AULALISTA_TEACHER_REVIEW_PROVIDER='luna'):
        assert provider_configuration_notice()['code']=='luna_route_not_configured'


@pytest.mark.django_db
def test_pi_failure_preserves_literal_answer_and_blocks_automatic_retry(ready_job,fake_pi):
    client,user,job=ready_job
    review=save(start(job,user,ask_first),user,'  Respuesta literal.\n')
    _,factory,scenario,calls=fake_pi;scenario(mode='error')
    review=advance(review,user,factory())
    assert review.state['turns'][0]['answer']=='  Respuesta literal.\n'
    assert review.state['error']=='pi_attempt_unknown'
    page=client.get(reverse('tutor-import-interpretation',args=[job.pk]))
    assert page.context['provider_blocked'] is True
    assert b'value="continue"' not in page.content
    before=len(calls())
    from curriculum.teacher_review import ReviewError
    with pytest.raises(ReviewError):advance(review,user,factory())
    assert len(calls())==before and not job.is_approved


@pytest.mark.django_db
def test_pi_success_persists_question_and_receipt_without_approval(ready_job,fake_pi):
    _,user,job=ready_job
    _,factory,_,_=fake_pi
    review=start(job,user,factory())
    assert review.state['status']=='asking' and len(review.state['turns'])==1
    assert review.state['events'][-1]['provider_receipt']['transport']=='local_pi_sdk'
    assert not job.is_approved


def test_out_of_order_unversioned_and_nonfinite_envelopes_rejected():
    for raw in (b'{"type":"pi.completed"}\n', b'{"type":"agent_settled"}\n',
                b'{"type":"pi.request","dispatch_count":true}\n',
                b'{"type":"pi.request","dispatch_count":NaN}\n'):
        events=PiEvents();events.feed(raw);events.finish()
        assert events.reason and not events.accounting_complete


def test_preflight_retains_only_fixed_driver_diagnostic_and_never_admits_prompt(fake_pi):
    base, factory, scenario, calls = fake_pi
    diagnostic = {'type': 'pi.error', 'stage': 'auth_resolution', 'code': 'pi_stage_failed'}
    scenario(preflight_stderr=json.dumps(diagnostic) + '\n')
    with pytest.raises(ReviewProviderError, match='pi_runtime_preflight_failed'):
        factory()(context())
    record = json.loads(next(factory().attempt_root.glob('*/preflight.json')).read_text())
    assert record == {'status': 'blocked_before_model_launch', 'code': 'pi_runtime_preflight_failed',
                      'driver_diagnostic': diagnostic}
    assert not (base/'captured.txt').exists()
    assert not list(factory().attempt_root.glob('*/admission.json'))
    assert not any('--generate' in args for args in calls())


@pytest.mark.parametrize('raw', [
    b'PRIVATE_SENTINEL',
    b'{"type":"pi.error","stage":"auth_resolution","code":"PRIVATE_SENTINEL"}',
    b'{"type":"pi.error","stage":"PRIVATE_SENTINEL","code":"pi_stage_failed"}',
    b'{"type":"pi.error","stage":"auth_resolution","code":"pi_stage_failed","message":"PRIVATE_SENTINEL"}',
    b'{"type":"pi.error","stage":"auth_resolution","code":"pi_stage_failed","code":"pi_oauth_required"}',
    b'{"type":"pi.error","stage":[],"code":"pi_stage_failed"}',
    b'{"type":"pi.error","stage":"provider_stream","code":"pi_stage_failed"}',
    b'[]', b'null', b'{', b'x' * 257,
])
def test_preflight_diagnostic_rejects_untrusted_or_malformed_stderr(raw):
    assert preflight_driver_diagnostic(raw) is None


def test_preflight_does_not_persist_raw_stderr(fake_pi):
    _, factory, scenario, _ = fake_pi
    scenario(preflight_stderr='PRIVATE_SENTINEL')
    with pytest.raises(ReviewProviderError, match='pi_runtime_preflight_failed'):
        factory()(context())
    record = next(factory().attempt_root.glob('*/preflight.json')).read_text()
    assert 'PRIVATE_SENTINEL' not in record and 'driver_diagnostic' not in record
