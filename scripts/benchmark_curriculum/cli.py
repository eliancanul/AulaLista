"""Public CLI; every generated artifact belongs to an explicit external workdir."""
import argparse
import sys
from pathlib import Path

from .common import ROOT, PYTHON, Runtime, read_json, write_json, sha_file


def main():
    # These two entry points are only launched by the runner in isolated processes.
    if len(sys.argv) > 1 and sys.argv[1] in ('worker', 'source'):
        command = sys.argv.pop(1)
        if command == 'worker':
            from .worker import main as entry
        else:
            from .metrics import main as entry
        raise SystemExit(entry())
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('setup', 'preflight', 'freeze-template', 'run', 'combine'):
        p = sub.add_parser(command)
        p.add_argument('--repo', required=True, type=Path, help='Git checkout containing the fixed comparison commits')
        p.add_argument('--workdir', required=True, type=Path, help='Private directory outside the repository')
        p.add_argument('--python', type=Path, default=PYTHON, help='Worker interpreter; invoke this CLI with the same interpreter')
        if command in ('preflight', 'run', 'combine', 'freeze-template'):
            p.add_argument('--out', required=True, help='New output path relative to workdir (or absolute within it)')
        if command == 'preflight':
            p.add_argument('--include-c01', action='store_true', help='Also use the exact already-versioned calibration PDF')
            p.add_argument('--config', type=Path, default=ROOT/'config.proposed.json')
        elif command == 'run':
            p.add_argument('--freeze', required=True, help='Closed freeze record inside workdir')
        elif command == 'freeze-template':
            p.add_argument('--protocol', required=True, type=Path, help='Coordinator-owned protocol file')
            p.add_argument('--config', type=Path, default=ROOT/'config.proposed.json')
        elif command == 'combine':
            p.add_argument('--a', required=True)
            p.add_argument('--b', required=True)
    args = parser.parse_args()
    runtime = Runtime(args.repo, args.workdir, args.python)
    if args.command == 'setup':
        from .setup_snapshots import setup
        result = setup(runtime)
    elif args.command == 'preflight':
        from .fixtures import build
        from .runner import execute, make_order, validate_config, verify_snapshots
        out = runtime.private_path(args.out)
        if out.exists():
            raise ValueError('Refusing to overwrite prior run; use a new run directory')
        config = read_json(args.config)
        validate_config(config)
        verify_snapshots(runtime)
        rows = build(runtime, include_c01=args.include_c01)
        result = execute(config, rows, make_order(rows), out, 'preflight', runtime)
    elif args.command == 'freeze-template':
        from .build_release import build_release
        result = build_release(runtime, args.out, args.protocol, args.config)
    elif args.command == 'run':
        from .runner import execute, load_freeze
        freeze, config, rows, order, weak = load_freeze(args.freeze, runtime)
        result = execute(config, rows, order, args.out, 'frozen_'+freeze['phase'], runtime, freeze, weak)
    else:
        from .weak_reference import combine
        a, b, out = (runtime.private_path(value) for value in (args.a, args.b, args.out))
        if out.exists():
            raise ValueError('Refusing to overwrite combined reference')
        result = combine(read_json(a), read_json(b))
        result['input_sha256'] = {'a': sha_file(a), 'b': sha_file(b)}
        write_json(out, result)
        result = {'status': 'combined_reference_written', 'semantic_accuracy': False}
    print(result['status'])
