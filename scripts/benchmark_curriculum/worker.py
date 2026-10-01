"""Exactly prepare -> compile claims -> verify; never model generation or DB setup."""
from __future__ import annotations
import argparse
import io
import resource
import sys
import time
import traceback
from pathlib import Path
from scripts.benchmark_curriculum.common import DEFAULT_PROFILE, comparison_identity, write_json, sha_file
from scripts.benchmark_curriculum.offline_guard import install, OfflineViolation, WriteBoundaryViolation

def main(profile=DEFAULT_PROFILE):
    identity = comparison_identity(profile)
    ap = argparse.ArgumentParser()
    ap.add_argument('--snapshot', required=True)
    ap.add_argument('--pdf', required=True)
    ap.add_argument('--expected-sha', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--timeout', type=int, required=True)
    ap.add_argument('--memory', type=int, required=True)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    resource.setrlimit(resource.RLIMIT_AS, (args.memory,args.memory))
    resource.setrlimit(resource.RLIMIT_CPU, (args.timeout,args.timeout+1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128*1024*1024,128*1024*1024))
    events = install(out)
    status = {'status':'running', **identity, 'stages':{},'offline_events':events}
    raw = {}
    stage = 'input'
    start = time.monotonic()
    try:
        if sha_file(args.pdf) != args.expected_sha:
            raise ValueError('Input SHA mismatch')
        content = Path(args.pdf).read_bytes()
        sys.path.insert(0, str(Path(args.snapshot).resolve()))
        stage = 'import'
        from curriculum.source_interpreter import CurriculumSourceInterpreter
        from curriculum.claims import compile_dossier_to_atomic_claims
        from curriculum.verification import verify_curriculum_dossier
        stage = 'prepare'
        t = time.monotonic()
        dossier = CurriculumSourceInterpreter.prepare(io.BytesIO(content), selection=None, job=None,
                                                      timeout_seconds=args.timeout)
        raw['dossier'] = dossier.to_dict()
        status['stages'][stage] = {'seconds':time.monotonic()-t,'completed':True}
        write_json(out/'raw.json', raw)
        stage = 'claims'
        t = time.monotonic()
        raw['claims'] = [claim.to_dict() for claim in compile_dossier_to_atomic_claims(dossier)]
        status['stages'][stage] = {'seconds':time.monotonic()-t,'completed':True}
        write_json(out/'raw.json', raw)
        stage = 'verify'
        t = time.monotonic()
        raw['verification'] = verify_curriculum_dossier(dossier, io.BytesIO(content)).to_dict()
        status['stages'][stage] = {'seconds':time.monotonic()-t,'completed':True}
        write_json(out/'raw.json', raw)
        if events:
            raise OfflineViolation('An attempted forbidden operation was caught inside product code')
        status['status'] = 'completed'
    except BaseException as exc:
        status['status'] = ('offline_violation' if isinstance(exc, OfflineViolation) else
                            'write_boundary_violation' if isinstance(exc, WriteBoundaryViolation) else 'error')
        status['error'] = {'stage':stage,'type':type(exc).__name__,'message':str(exc)}
        traceback.print_exc()
    finally:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_scale = 1 if sys.platform == 'darwin' else 1024
        rusage_peak = usage.ru_maxrss*rss_scale
        peak = rusage_peak
        proc_status = Path('/proc/self/status')
        if proc_status.is_file():
            for line in proc_status.read_text().splitlines():
                if line.startswith('VmHWM:'):
                    peak = int(line.split()[1])*1024
        status.update(seconds=time.monotonic()-start, maxrss_bytes=peak, rusage_maxrss_bytes=rusage_peak,
                      user_cpu_seconds=usage.ru_utime, system_cpu_seconds=usage.ru_stime)
        write_json(out/'worker_status.json',status)
    return 0 if status['status']=='completed' else 72 if events else 1

if __name__ == '__main__':
    raise SystemExit(main())
