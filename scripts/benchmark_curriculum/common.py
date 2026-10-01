"""Portable benchmark common I/O. No product imports."""
from __future__ import annotations
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = Path(sys.executable).absolute()
COMMITS = {
    'B0': '2541faf04bda4dad1215a4673e3802567ca7c5c9',
    'B2': '1aae48b93c2d83aec80c1248a38c24d5960a3d2a',
    'B3': 'a4dfe5cf9975d9e9b74a256aff718aec35f11f39',
}
C01_SHA = '33d7c2862a7d14127b2906518b26bc16f0f571f85d765dd6cd63325f52337648'
C01_RELATIVE = 'output/pdf/prueba-issue-96-paginas-4-a-8.pdf'
HARNESS_VERSION = '1.2.0-portable'
METRIC_CONTRACT_VERSION = '1.0.0'
DEFAULT_PROFILE = 'b0-b2-b3'
PROFILE_NAMES = (DEFAULT_PROFILE, 'b0-b3-b4')


def comparison_identity(profile=DEFAULT_PROFILE):
    """Two reviewed comparisons only; callers cannot supply commits or pairs."""
    if not isinstance(profile, str) or profile not in PROFILE_NAMES:
        raise ValueError('Unsupported comparison profile')
    if profile == DEFAULT_PROFILE:
        commits = dict(COMMITS)
        pairs = [['B0', 'B3'], ['B2', 'B3']]
    else:
        commits = {'B0': COMMITS['B0'], 'B3': COMMITS['B3'],
                   'B4': 'bf1ae21eae80ed38ef02179ea5724b7b0aa7b1c7'}
        pairs = [['B0', 'B4'], ['B3', 'B4']]
    return {'harness_version': HARNESS_VERSION, 'comparison_profile': profile,
            'source_commits': commits, 'comparison_pairs': pairs}


# Exact paths; no recursive removal by key name. History timestamp only for prepare.
VOLATILE_PATHS = ['/dossier/created_at', '/dossier/updated_at', '/dossier/history/*/timestamp']

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def sha_file(path):
    return sha_bytes(Path(path).read_bytes())

def canonical_bytes(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_bytes(canonical_bytes(value))
    os.replace(tmp, path)

def read_json(path):
    def duplicate_guard(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text('utf-8'), object_pairs_hook=duplicate_guard,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(f'nonfinite JSON: {s}')))

def canonical_output(raw):
    result = json.loads(json.dumps(raw, allow_nan=False))
    dossier = result.get('dossier') if isinstance(result, dict) else None
    if isinstance(dossier, dict):
        for key in ('created_at', 'updated_at'):
            dossier.pop(key, None)
        history = dossier.get('history')
        # Only the declared list schema has volatile history timestamps. Retain
        # every unexpected type verbatim so canonicalization cannot hide defects.
        if isinstance(history, list):
            for entry in history:
                if isinstance(entry, dict) and entry.get('action') == 'prepare':
                    entry.pop('timestamp', None)
    return result

def tree_manifest(root):
    root = Path(root)
    return {str(p.relative_to(root)):sha_file(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}

def child_env(workdir, python=PYTHON):
    # An allowlist, never a copy of the parent environment. HOME is not repurposed.
    # The process-local guard is instrumentation, not a filesystem sandbox.
    workdir = Path(workdir)
    return {'PATH': str(Path(python).parent)+os.pathsep+os.defpath,
            'TMPDIR': str(workdir), 'XDG_CACHE_HOME': str(workdir/'cache'),
            'HF_HOME': str(workdir/'cache'/'huggingface'),
            'PYTHONHASHSEED':'0', 'PYTHONDONTWRITEBYTECODE':'1',
            'PYTHONNOUSERSITE':'1', 'LC_ALL':'C.UTF-8', 'LANG':'C.UTF-8', 'TZ':'UTC',
            'OMP_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1',
            'TOKENIZERS_PARALLELISM':'false', 'HF_HUB_OFFLINE':'1',
            'TRANSFORMERS_OFFLINE':'1', 'WANDB_MODE':'disabled', 'OTEL_SDK_DISABLED':'true',
            'DO_NOT_TRACK':'1'}


def inside(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    return path == root or root in path.parents


def reject_quarantine(path):
    # Inspect lexical and resolved paths so a symlink cannot hide the label.
    for candidate in (Path(path).absolute(), Path(path).resolve()):
        if any('quarantine' in part.lower() or 'cuarentena' in part.lower()
               for part in candidate.parts):
            raise ValueError('Quarantine paths cannot be benchmark inputs')


@dataclass(frozen=True)
class Runtime:
    repo: Path
    workdir: Path
    python: Path = PYTHON
    profile: str = DEFAULT_PROFILE

    def __post_init__(self):
        comparison_identity(self.profile)
        # Preserve the venv executable path (resolving it would select base Python).
        object.__setattr__(self, 'repo', Path(self.repo).resolve())
        object.__setattr__(self, 'workdir', Path(self.workdir).resolve())
        object.__setattr__(self, 'python', Path(self.python).absolute())
        code_repo = ROOT.parents[1]
        if any(inside(self.workdir, root) or inside(root, self.workdir)
               for root in (self.repo, code_repo)):
            raise ValueError('Private workdir must be external to, and not contain, the repository')
        if not self.python.is_file():
            raise ValueError('Selected Python executable does not exist')
        if not (self.repo/'.git').exists():
            raise ValueError('Explicit repo must be a Git checkout')
        reject_quarantine(self.workdir)

    @property
    def commits(self):
        return comparison_identity(self.profile)['source_commits']

    @property
    def config_path(self):
        return ROOT/('config.proposed.json' if self.profile == DEFAULT_PROFILE
                     else 'config.b0-b3-b4.proposed.json')

    @property
    def snapshots(self):
        return self.private_path(self.workdir/'snapshots')

    def private_path(self, path):
        path = Path(path)
        if not path.is_absolute():
            path = self.workdir/path
        reject_quarantine(path)
        path = path.resolve()
        if not inside(path, self.workdir) or path == self.workdir:
            raise ValueError('Artifact path must remain inside the private workdir')
        return path

    def command(self, command, *args):
        # -P excludes cwd from imports; entrypoint explicitly adds only this code checkout.
        return [str(self.python), '-P', str(ROOT/'entrypoint.py'), command,
                '--profile', self.profile, *map(str, args)]


def require_selected_python(runtime):
    if Path(sys.executable).absolute() != runtime.python:
        raise ValueError('Run the command with the same interpreter selected by --python')
