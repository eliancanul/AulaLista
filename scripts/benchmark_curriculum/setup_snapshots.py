"""Export immutable commit snapshots without changing product checkout or refs."""
import io
import importlib.metadata
import os
import platform
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from scripts.benchmark_curriculum.common import *

def command(runtime, *args):
    return subprocess.check_output(args, env=child_env(runtime.workdir, runtime.python))

def environment_manifest(runtime):
    require_selected_python(runtime)
    lock = runtime.private_path('requirements.lock')
    from packaging.requirements import Requirement
    requirements = [Requirement(line.removesuffix('\\').strip()) for line in lock.read_text().splitlines() if re.match(r'^[A-Za-z0-9_.-]+==',line)]
    pins = {r.name: next(iter(r.specifier)).version for r in requirements if not r.marker or r.marker.evaluate()}
    normalize = lambda s: re.sub(r'[-_.]+','-',s).lower()
    installed = {normalize(d.metadata['Name']):d for d in importlib.metadata.distributions()}
    mismatches=[]
    packages=[]
    for name, version in sorted(pins.items()):
        dist = installed.get(normalize(name))
        if not dist or dist.version != version:
            mismatches.append({'name':name,'lock':version,'installed':dist.version if dist else None})
            continue
        contents={}
        for file in sorted(dist.files or []):
            if str(file).endswith('.pyc'):
                continue
            path=dist.locate_file(file)
            if path.is_file():
                contents[str(file)]=sha_file(path)
        packages.append({'name':name,'version':version,'installed_files_sha256':sha_bytes(canonical_bytes(contents)),
                         'file_count':len(contents)})
    return {'schema_version':'1.0.0','python_executable':str(runtime.python),'python_realpath':str(runtime.python.resolve()),
            'python_version':sys.version,'python_sha256':sha_file(runtime.python.resolve()),'platform':platform.platform(),
            'machine':platform.machine(),'lock_sha256':sha_file(lock),'package_pins':pins,
            'installed_packages':packages,'mismatches':mismatches,
            'extra_distributions':{k:v.version for k,v in installed.items() if k not in {normalize(n) for n in pins}},
            'provenance_limit':'Lock contains allowed distribution hashes; original installer receipt unavailable. Installed bytes separately hashed, no claim of retrospectively verified wheel download.',
            'child_environment':child_env('<RUN_DIRECTORY>', runtime.python)}

def setup(runtime):
    require_selected_python(runtime)
    runtime.workdir.mkdir(parents=True, exist_ok=True)
    generated = (runtime.snapshots, runtime.private_path('requirements.lock'),
                 runtime.private_path('environment_manifest.json'))
    if any(path.exists() for path in generated):
        raise ValueError('Refusing to overwrite snapshot setup; use a fresh private workdir')
    runtime.snapshots.mkdir()
    records = {}
    for version, commit in COMMITS.items():
        path = runtime.snapshots/version
        archive = command(runtime, 'git', '-C', str(runtime.repo), 'archive', '--format=tar', commit)
        path.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
            tf.extractall(path, filter='data')
        files = tree_manifest(path)
        record = {'commit': commit,
                  'tree': command(runtime, 'git', '-C', str(runtime.repo), 'rev-parse', f'{commit}^{{tree}}').decode().strip(),
                  'git_archive_sha256': sha_bytes(archive), 'files': files,
                  'file_manifest_sha256': sha_bytes(canonical_bytes(files))}
        write_json(runtime.snapshots/f'{version}.manifest.json', record)
        records[version] = {k: v for k, v in record.items() if k != 'files'}
    lock_hashes = {v: sha_file(runtime.snapshots/v/'requirements.lock') for v in COMMITS}
    if len(set(lock_hashes.values())) != 1:
        raise ValueError('Locks differ; comparative algorithm-only run forbidden')
    runtime.private_path('requirements.lock').write_bytes((runtime.snapshots/'B3'/'requirements.lock').read_bytes())
    write_json(runtime.snapshots/'index.json', records)
    env = environment_manifest(runtime)
    write_json(runtime.private_path('environment_manifest.json'), env)
    if env['mismatches']:
        raise ValueError(f"Installed dependency mismatch: {env['mismatches']}")
    return {'status': 'setup_completed', 'new_corpus_executed': False}
