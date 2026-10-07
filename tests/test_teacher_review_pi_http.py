"""OFF integration through the real HTTP/factory/process/driver/parser seam.

Pi, authentication and fetch are invented fixture modules. Product preflight is
replaced explicitly ONLY here: this is not OS isolation or Mac runtime evidence.
The actual installed Node version runs the real driver without falsifying its
version or changing the production contract. No real Pi package is imported.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
import pytest

from curriculum.models import CurriculumImportJob, CurriculumTeacherReview, PublishedPackageSnapshot
from curriculum.pi_review_provider import PiLunaProvider, DRIVER, CONTRACT
from curriculum.pi_review_transport import IDENTITY
from helpers import tutor_client
from test_t15_curriculum_import import make_minimal_pdf


@pytest.fixture
def synthetic_pi_process(tmp_path, settings, monkeypatch, record_property):
    node = shutil.which('node')
    if not node:
        pytest.fail('The OFF bridge integration requires an already installed Node runtime')
    node = str(Path(node).resolve())
    version = subprocess.check_output([node, '--version'], text=True).strip()
    record_property('runtime_node_actual', version)
    record_property('test_only', 'true')
    record_property('production_preflight_verified', 'false')
    # Test settings never grant authority to a genuine provider or runtime.
    for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'NODE_OPTIONS',
                 'NODE_PATH', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / 'invented-pi'
    core = root / 'package/dist/core'
    ai = root / 'package/node_modules/@earendil-works/pi-ai'
    core.mkdir(parents=True)
    ai.mkdir(parents=True)
    (root / 'agent').mkdir()
    (root / 'package/package.json').write_text(json.dumps({
        'name': '@earendil-works/pi-coding-agent', 'version': '0.84.4', 'type': 'module'}))
    (ai / 'package.json').write_text(json.dumps({
        'name': '@earendil-works/pi-ai', 'version': '0.84.4', 'type': 'module',
        'exports': {'.': {'import': './index.js'}}}))
    (ai / 'index.js').write_text('export {};')
    model = {'id': IDENTITY['model'], 'provider': IDENTITY['provider'], 'api': IDENTITY['api'],
             'baseUrl': IDENTITY['base_url'], 'reasoning': True}
    (root / 'catalog.json').write_text(json.dumps({IDENTITY['provider']: {'models': [model]}}))
    (root / 'scenario.json').write_text(json.dumps({'mode': 'ok'}))
    (core / 'auth-storage.js').write_text('''
export class ReadOnlyAuthStorage {
  constructor(file) { /* Invented marker; never opens any authentication file. */ }
}
''')
    (core / 'model-runtime.js').write_text('''
import fs from 'node:fs';
const root = ROOT;
const model = MODEL;
const usage = {input:95, output:20, cacheRead:5, cacheWrite:0, totalTokens:120};
// The real driver invokes this explicitly invented fetch. No DNS or HTTP occurs.
globalThis.fetch = async (url, options) => {
  fs.appendFileSync(root + '/fetch.jsonl', JSON.stringify({url, method:options.method}) + '\\n');
  return new Response('synthetic fixture bytes');
};
export class ModelRuntime {
  static async create(options) {
    if (options.modelsPath !== null || options.allowModelNetwork !== false || options.refreshOnCreate !== false)
      throw Error('unexpected synthetic runtime options');
    return new ModelRuntime();
  }
  async refresh() { return {aborted:false, errors:new Map()}; }
  getModel() { return model; }
  async checkAuth() { return {type:'oauth'}; }
  async getAuth() { return {source:'OAuth'}; }
  async *streamSimple(given, context, options) {
    const scenario = JSON.parse(fs.readFileSync(root + '/scenario.json'));
    fs.writeFileSync(root + '/captured.json', JSON.stringify(context));
    if (options.maxRetries !== 0 || options.toolChoice !== 'none' || context.tools.length)
      throw Error('unsafe fixture invocation');
    options.onPayload({model:model.id, tool_choice:'none', tools:[], reasoning:{effort:'high'}, store:false});
    await options.fetch(model.baseUrl + '/codex/responses', {method:'POST'});
    yield {type:'start'};
    if (scenario.mode === 'timeout') await new Promise(resolve => setTimeout(resolve, 10000));
    const data = JSON.parse(context.messages[0].content.split('\\nDATOS:\\n')[1]);
    const target = data.question_policy.candidate_target_ids[0];
    const output = {question:'Pregunta sintética del bridge: ¿qué dato falta?', targets:[target], answer_updates:[]};
    yield {type:'done', message:{role:'assistant', provider:model.provider, model:model.id, api:model.api,
      stopReason:scenario.mode === 'length' ? 'length' : 'stop',
      content:[{type:'text', text:JSON.stringify(output)}], usage}};
  }
}
'''.replace('ROOT', json.dumps(str(root))).replace('MODEL', json.dumps(model)))
    # This fixture launcher accepts only the exact invented-runtime command.
    launcher = root / 'fixture-launcher'
    launcher.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
root = pathlib.Path(__file__).parent
args = sys.argv[1:]
assert args[:1] == ['--work'] and args[2] == '--'
command = args[3:]
assert command == EXPECTED
with (root / 'launches.jsonl').open('a') as out: out.write(json.dumps(command) + '\\n')
os.execv(command[0], command)
'''.replace('EXPECTED', repr([node, str(DRIVER), '--generate', str(root / 'package'),
                                str(root / 'agent'), str(root / 'catalog.json')])))
    launcher.chmod(0o700)
    identity = {'runtime_review_sha256': hashlib.sha256(b'INVENTED OFF TEST ONLY').hexdigest()}

    def synthetic_preflight(provider, directory):
        assert provider.package_dir == root / 'package'
        assert not (root / 'agent/auth.json').exists()
        work = directory / 'work'
        work.mkdir(mode=0o700)
        return identity, work

    monkeypatch.setattr(PiLunaProvider, 'preflight', synthetic_preflight)
    monkeypatch.setattr(PiLunaProvider, '_identity', lambda provider: identity)
    settings.AULALISTA_TEACHER_REVIEW_PROVIDER = 'pi_luna'
    settings.AULALISTA_TEACHER_REVIEW_CONTEXT_MODE = 'complete'
    settings.AULALISTA_PI_LIVE_ENABLED = True  # Invented modules and paths only.
    settings.AULALISTA_PI_NODE_EXECUTABLE = node
    settings.AULALISTA_PI_PACKAGE_DIR = str(root / 'package')
    settings.AULALISTA_PI_AGENT_DIR = str(root / 'agent')
    settings.AULALISTA_PI_CATALOG_FILE = str(root / 'catalog.json')
    settings.AULALISTA_PI_ISOLATION_LAUNCHER = str(launcher)
    settings.AULALISTA_PI_RUNTIME_REVIEW = str(root / 'not-a-production-review')
    settings.AULALISTA_PI_ATTEMPT_DIR = str(root / 'attempts')
    settings.AULALISTA_PI_TIMEOUT_SECONDS = 3
    settings.AULALISTA_LUNA_LIVE_ENABLED = False
    settings.AULALISTA_GEMINI_LIVE_ENABLED = False

    def forbidden(*args, **kwargs):
        pytest.fail('No other provider may be invoked by the OFF integration')

    monkeypatch.setattr('curriculum.luna_review_provider.LunaCodexCliProvider.__call__', forbidden)
    monkeypatch.setattr('curriculum.gemini_review_provider.GeminiHighAgyProvider.__call__', forbidden)
    monkeypatch.setattr('curriculum.curriculum_import.chat_json', forbidden)

    def calls():
        path = root / 'launches.jsonl'
        return len(path.read_text().splitlines()) if path.exists() else 0

    assert CONTRACT['node_version'] == 'v22.22.3'  # Never rewrite the production gate.
    return root, calls


@pytest.fixture
def uploaded_job(synthetic_pi_process):
    client = tutor_client('pi-http-synthetic-teacher')
    pdf = make_minimal_pdf(['Proyecto: Lectura sintetica\nSESION 1: Lectura\n'
                            'Inicio: Leer el cuento.\nCierre: Compartir una idea.'])
    response = client.post(reverse('tutor-import-upload'), {
        'pdf': SimpleUploadedFile('pi-http-synthetic.pdf', pdf, content_type='application/pdf')})
    assert response.status_code == 302
    job = CurriculumImportJob.objects.get()
    assert job.has_valid_ready_dossier()
    return client, job


def post_form(client, url, action, **fields):
    page = client.get(url)
    assert page.status_code == 200
    soup = BeautifulSoup(page.content, 'html.parser')
    button = soup.find('button', attrs={'value': action})
    assert button is not None, soup.get_text()
    data = {field['name']: field.get('value', '') for field in button.find_parent('form').find_all('input')}
    return client.post(url, {**data, 'action': action, **fields}), data


@pytest.mark.django_db
def test_uploaded_source_reaches_real_driver_once_then_keeps_answer_off(uploaded_job, synthetic_pi_process, settings):
    client, job = uploaded_job
    root, calls = synthetic_pi_process
    url = reverse('tutor-import-interpretation', args=[job.pk])
    assert calls() == 0
    response, original_form = post_form(client, url, 'continue')
    assert response.status_code == 302 and calls() == 1
    review = CurriculumTeacherReview.objects.get(job=job)
    assert review.state['status'] == 'asking'
    assert len(review.state['turns']) == 1
    receipt = review.state['events'][-1]['provider_receipt']
    assert receipt['requested_model'] == 'gpt-6-luna' and receipt['requested_effort'] == 'high'
    assert receipt['observed_model'] is None
    assert receipt['reported_usage']['totalTokens'] == 120
    assert receipt['provider_dispatch_count'] == 1 and receipt['automatic_retries'] == 0
    assert receipt['real_cost_currency'] is None
    assert len((root / 'fetch.jsonl').read_text().splitlines()) == 1
    # Duplicate POST and GET/reopening do not dispatch a second process.
    assert client.post(url, {**original_form, 'action': 'continue'}).status_code == 409
    page = client.get(url)
    soup = BeautifulSoup(page.content, 'html.parser')
    assert len(soup.find_all('textarea')) == 1 and calls() == 1
    form = soup.find('form', id='teacher-answer-form')
    data = {field['name']: field.get('value', '') for field in form.find_all('input')}
    answer = '  Texto humano sintético y conservado.\n'
    assert client.post(url, {**data, 'action': 'save_draft', 'answer': answer}).status_code == 200
    teacher = get_user_model().objects.get(pk=job.created_by_id)
    reopened = Client()
    reopened.force_login(teacher)
    assert BeautifulSoup(reopened.get(url).content, 'html.parser').textarea.text == answer
    settings.AULALISTA_PI_LIVE_ENABLED = False
    response, _ = post_form(reopened, url, 'answer', answer=answer)
    assert response.status_code == 302
    review.refresh_from_db()
    assert review.state['turns'][0]['answer'] == answer
    assert review.state['error'] == 'pi_live_not_enabled'
    assert calls() == 1
    job.refresh_from_db()
    assert not job.is_approved and not PublishedPackageSnapshot.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize('mode', ['length', 'timeout'])
def test_driver_failure_blocks_another_http_dispatch(uploaded_job, synthetic_pi_process, settings, mode):
    client, job = uploaded_job
    root, calls = synthetic_pi_process
    (root / 'scenario.json').write_text(json.dumps({'mode': mode}))
    settings.AULALISTA_PI_TIMEOUT_SECONDS = 1 if mode == 'timeout' else 3
    url = reverse('tutor-import-interpretation', args=[job.pk])
    response, original_form = post_form(client, url, 'continue')
    assert response.status_code == 302 and calls() == 1
    review = CurriculumTeacherReview.objects.get(job=job)
    assert review.state['error'] == 'pi_attempt_unknown'
    receipt = review.state['events'][-1]['provider_receipt']
    assert receipt['usage_complete'] is False and receipt['accounting_status'] == 'unknown'
    assert (receipt['reported_usage']['totalTokens'] if receipt['reported_usage'] else None) == (120 if mode == 'length' else None)
    assert (root / 'attempts/STOP_REQUIRED.json').exists()
    page = client.get(url)
    assert page.context['provider_blocked'] is True
    assert b'value="continue"' not in page.content
    client.post(url, {**original_form, 'action': 'continue'})
    assert calls() == 1
    job.refresh_from_db()
    assert not job.is_approved
