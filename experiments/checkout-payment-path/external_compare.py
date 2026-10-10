#!/usr/bin/env python3
"""Pinned libdft64 compatibility diagnostics, NOT a performance benchmark."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import traceback
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'checkout-item-identity')]
from external_boundaries import plan_binary, check

LIBDFT_REV = '20804d5bae5d8aed31a71761b1a1149e35a0da95'
PIN_NAME = 'pin-3.20-98437-gf02b61307-gcc-linux'
PIN_URL = 'https://software.intel.com/sites/landingpage/pintool/downloads/' + PIN_NAME + '.tar.gz'
# SHA256 of the archive retrieved from Intel's official HTTPS URL, 2026-10-10.
PIN_SHA256 = 'ca2f542eee2013471961bb683d06ccb20ef5dd8ed0d02537cf4d47f09bd616bf'
PIN_LAUNCHER_SHA256 = 'd963f5b4b8ae14c7db331e3d65f54160d04e1c884efe24c0f3eb60fecabc904a'
PIN_ENGINE_SHA256 = '6c79a4ef55b7a693ddadf77669382a7d3cabf06cf02cda3793c9ed0ae86702d8'
RISKS = ['BDD tag store and shadow memory concurrency not qualified for Go runtime',
         'Opcode presence is not proof of operand-form/propagation correctness; flags and implicit flows ignored',
         'Per-instruction diagnostic callbacks prohibit performance interpretation',
         'No general goroutine migration, stack relocation, signal-context or GC qualification']


def save(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, out, cwd=None, extra=None, input=None, timeout=600, combined=False):
    argv = list(map(str, argv))
    record = dict(command=argv, cwd=str(cwd or ROOT))
    try:
        p = subprocess.run(argv, cwd=cwd or ROOT, env=dict(os.environ, **(extra or {})),
                           input=input, capture_output=True, text=True, timeout=timeout)
        record.update(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        record.update(error=str(exc))
        raise
    finally:
        with (out / 'commands.jsonl').open('a') as f:
            f.write(json.dumps(record) + '\n')
    if p.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(argv) + '\n' + p.stderr[-4000:])
    return p.stdout + p.stderr if combined else p.stdout


def hardware():
    # Read-only evidence; absence of a flag/device is not proof of CPU incapability.
    result = dict(platform=platform.platform(), machine=platform.machine(), python=sys.version)
    for key, path in {'cpuinfo': '/proc/cpuinfo', 'perf_event_paranoid': '/proc/sys/kernel/perf_event_paranoid',
                      'intel_pt_type': '/sys/bus/event_source/devices/intel_pt/type'}.items():
        try:
            text = Path(path).read_text()
            if key == 'cpuinfo':
                text = '\n'.join(line for line in text.splitlines() if line.startswith(('vendor_id', 'model name', 'flags')))
                text = '\n'.join(dict.fromkeys(text.splitlines()))
            result[key] = text.strip()
        except OSError as exc:
            result[key] = dict(unavailable=str(exc))
    result['runtime_overrides'] = {k: os.environ.get(k) for k in ('GODEBUG', 'GOMAXPROCS', 'GOAMD64', 'GOGC')}
    result['hardtaint_status'] = 'inventory_only; PTWRITE capability and usable PT capture not tested'
    return result


def dependencies(args, out):
    deps = ROOT / 'artifacts/external-tools'
    deps.mkdir(parents=True, exist_ok=True)
    pin = (args.pin_root or deps / PIN_NAME).resolve()
    lib = (args.libdft or deps / 'libdft64').resolve()
    if not pin.exists():
        check(args.pin_root is None, 'Supplied --pin-root does not exist')
        archive = deps / (PIN_NAME + '.tar.gz')
        print('Downloading pinned Intel Pin kit', flush=True)
        with urllib.request.urlopen(PIN_URL, timeout=120) as response, archive.open('wb') as f:
            shutil.copyfileobj(response, f)
        check(sha(archive) == PIN_SHA256, 'Pin archive checksum differs')
        # Pin contains symlinks; Python data filter permits only safe in-tree links.
        with tarfile.open(archive) as tar:
            check(hasattr(tarfile, 'data_filter'), 'Use Python with tarfile.data_filter (e.g. Python 3.12)')
            tar.extractall(deps, filter='data')
    if not lib.exists():
        check(args.libdft is None, 'Supplied --libdft does not exist')
        command(['git', 'clone', 'https://github.com/AngoraFuzzer/libdft64.git', lib], out)
        command(['git', 'checkout', '--detach', LIBDFT_REV], out, cwd=lib)
    check(command(['git', 'rev-parse', 'HEAD'], out, cwd=lib).strip() == LIBDFT_REV, 'Wrong libdft64 revision')
    check(not command(['git', 'status', '--porcelain', '--untracked-files=no'], out, cwd=lib).strip(), 'Modified libdft64 tracked files')
    check(not command(['git', 'ls-files', '--others', '--exclude-standard', '--', '*.h', '*.H', '*.cpp', '*.c'],
                      out, cwd=lib).strip(), 'Untracked code in libdft64 source checkout')
    check((pin / 'pin').is_file(), 'Pin launcher missing')
    check(sha(pin / 'pin') == PIN_LAUNCHER_SHA256 and sha(pin / 'intel64/bin/pinbin') == PIN_ENGINE_SHA256,
          'Pin executable hashes differ from pinned official kit')
    # Toolchain identity is recorded even for a manually supplied installation.
    save(out / 'dependencies.json', dict(libdft_revision=LIBDFT_REV, pin_expected_kit=PIN_NAME,
         pin_root=str(pin), pin_launcher_sha256=sha(pin / 'pin'),
         pin_engine_sha256=sha(pin / 'intel64/bin/pinbin'), libdft_source=str(lib)))
    return pin, lib


def build_tools(pin, lib, out):
    work = out / 'libdft-build'
    shutil.copytree(lib, work, ignore=shutil.ignore_patterns('.git', 'obj-*', '*.log'))
    # Extract only the upstream dispatcher's explicit opcode cases. This is an
    # audit aid, not an invented list of supported semantics.
    core = (work / 'src/libdft_core.cpp').read_text()
    opcodes = sorted(set(re.findall(r'case (XED_ICLASS_\w+)\s*:', core)))
    check(opcodes, 'No upstream opcode cases')
    header = 'static bool known_opcode(unsigned op) { switch(op) {\n'
    header += ''.join('case ' + op + ':\n' for op in opcodes)
    header += 'return true; default: return false; } }\n'
    (work / 'tools/libdft_known_opcodes.h').write_text(header)
    shutil.copy2(HERE / 'libdft_payment.cpp', work / 'tools/libdft_payment.cpp')
    make = ['make', '-j2', 'PIN_ROOT=' + str(pin)]
    command(make + ['-C', work / 'src'], out)
    command(make + ['-C', work / 'tools', 'TOOL_ROOTS=nullpin libdft_payment',
                    'obj-intel64/nullpin.so', 'obj-intel64/libdft_payment.so'], out)
    result = {name: work / 'tools/obj-intel64' / (name + '.so') for name in ('nullpin', 'libdft_payment')}
    save(out / 'tool-build.json', dict(compiled=True, tools={k: dict(path=str(v), sha256=sha(v)) for k, v in result.items()},
         upstream_opcode_cases=opcodes, propagation_code_modified=False, adapter_changes='boundary API calls and diagnostic callbacks only'))
    return result


def label_name(label, count):
    check(type(label) is int and 1 <= label <= 2 * count, 'Unrecognized source label')
    index = (label - 1) // 2
    prefix = 'shipping' if index == 0 else 'items[%d].Cost' % (index - 1)
    return prefix + ('.Units' if label % 2 else '.Nanos')


def parse_observation(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    finish = [r for r in rows if r['kind'] == 'finish']
    check(len(finish) == 1 and rows[-1]['kind'] == 'finish', 'Missing or duplicated tool completion')
    f = finish[0]
    check(f['exit_code'] == 0 and not f['bad'] and f['source_hits'] == f['end_hits'] == 1, 'Invalid invocation/completion')
    check(not any(r['kind'] == 'error' for r in rows), 'Tool reported an error')
    check(f['unhandled_opcode_kinds'] == 0 and not any(r['kind'] == 'unhandled_opcode' for r in rows), 'Uncovered opcode executed in amount interval')
    starts = [r for r in rows if r['kind'] == 'source_boundary']
    check(len(starts) == 1, 'Missing/duplicated source boundary')
    sinks = [r for r in rows if r['kind'] == 'sink']
    sources = [r for r in rows if r['kind'] == 'source_field_pair']
    if starts[0]['preparation_error']:
        check(not sinks and not sources and f['sink_hits'] == 0, 'Sink after preparation error')
        check([r['kind'] for r in rows] == ['source_boundary', 'finish'], 'Unexpected failure-path records')
        return dict(status='no_sink', origins={}, output=[])
    check(len(sinks) == f['sink_hits'] == 1 and 1 <= len(sources) <= 33, 'Missing source or sink')
    check([r['kind'] for r in rows] == ['source_boundary'] + ['source_field_pair'] * len(sources) + ['sink', 'finish'],
          'Unexpected or reordered records')
    check([r['index'] for r in sources] == list(range(len(sources))), 'Missing source pair')
    check(len({r['pointer'] for r in sources}) == len(sources), 'Aliased sources')
    sink = sinks[0]
    return dict(status='observed_origin_sets', output=sink['output'],
                origins={field: sorted({label_name(n, len(sources)) for n in sink[field]}) for field in ('Units', 'Nanos')})


def compare_truth(observation, truth):
    # The adapter/parse_observation never receives the oracle. Read it only here.
    has_sink = truth['sink_present']
    expected_status = 'observed_origin_sets' if has_sink else 'no_sink'
    fields = ('Units', 'Nanos') if has_sink else ()
    exact = sum(observation.get('origins', {}).get(k) == truth['origins'][k] for k in fields)
    return dict(matched=observation['status'] == expected_status and observation['output'] == truth['output'] and exact == len(fields),
                query_fields=len(fields), exact_fields=exact,
                note='Diagnostic agreement only; concurrency and instruction semantics remain unqualified')


def execute(args, out, report):
    report['stage'] = 'dependencies'
    pin, lib = dependencies(args, out)
    report['stage'] = 'tool_build'
    tools = build_tools(pin, lib, out)
    report['compiled'] = True
    if args.mode == 'build-tools':
        report['stage'] = 'tools_built_not_executed'
        return
    report['stage'] = 'pin_startup'
    version = command([pin / 'pin', '-version'], out, timeout=30, combined=True)
    check('98437' in version, 'Unexpected Pin version; keep pinned baseline')
    command([pin / 'pin', '-t', tools['nullpin'], '--', '/bin/true'], out, timeout=30)
    report['pin_startup_passed'] = True
    report['stage'] = 'target_build'
    # Earlier BPF runners may have created their checkout as root. This runner
    # intentionally runs without sudo; keep its default checkout independent.
    # Do not bypass Git's ownership checks or change global safe.directory.
    if args.checkout is None:
        args.checkout = ROOT / 'artifacts/external-tools/online-boutique-v0.10.4'
    report['target_checkout'] = str(args.checkout)
    spec = importlib.util.spec_from_file_location('external_fixture_builder', HERE.parent / 'checkout-item-identity/run.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    binary, plan, source_hash, _ = builder.build_target(args, out, HERE / 'payment_test.go', plan_binary)
    report.update(binary_sha256=sha(binary), main_go_sha256=source_hash)
    money = args.checkout / 'src/checkoutservice/money/money.go'
    check(sha(money) == 'c7e81c0e8e24cafce6ccf35b9846d76cea114969998355db34d01169687e67f3', 'Money source changed')
    config = out / 'boundary-pcs.txt'
    roles = {'source': 1, 'sink': 2, 'end': 3}
    config.write_text(''.join('%d %x\n' % (roles[s['kind']], s['address']) for s in plan['sites']))
    all_cases = json.loads((HERE / 'cases.json').read_text())
    cases = all_cases if args.all_cases else [c for c in all_cases if c['Name'] == args.case]
    check(cases, 'Unknown case')
    save(out / 'cases.json', cases)
    report['expected_cases'] = len(cases)
    for case in cases:
        row = dict(case=case['Name'])
        report['cases'].append(row)
        for stage in ('native', 'nullpin', 'libdft_payment'):
            report['stage'] = case['Name'] + '/' + stage
            print('Checking ' + report['stage'], flush=True)
            folder = out / case['Name'] / stage
            folder.mkdir(parents=True)
            truth_path = folder / 'truth.json'
            env = dict(TRACEFUSION_IDENTITY_CASE=case['Name'], TRACEFUSION_PAYMENT_CASE=json.dumps(case),
                       TRACEFUSION_IDENTITY_TRUTH=str(truth_path))
            argv = [binary] if stage == 'native' else [pin / 'pin', '-t', tools[stage]]
            if stage == 'libdft_payment':
                argv += ['-boundary_config', config, '-origin_log', folder / 'origins.jsonl']
            if stage != 'native':
                argv += ['--', binary]
            command(argv, out, extra=env, input='x', timeout=args.timeout)
            check(truth_path.is_file(), 'Fixture did not complete')
            if stage == 'libdft_payment':
                try:
                    observation = parse_observation(folder / 'origins.jsonl')
                except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
                    observation = dict(status='unknown', reason=str(exc), origins={}, output=[])
                save(folder / 'observation.json', observation)
                row['comparison'] = compare_truth(observation, json.loads(truth_path.read_text()))
            row[stage] = 'completed'
        save(out / 'summary.json', report)
        check(row['comparison']['matched'], 'External origin mismatch/unknown; stopping at first failing case')
    report['stage'] = 'diagnostic_cases_complete'
    report['diagnostic_all_matched'] = True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('run', 'build-tools'))
    p.add_argument('--pin-root', type=Path)
    p.add_argument('--libdft', type=Path)
    p.add_argument('--checkout', type=Path)
    p.add_argument('--go', default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    p.add_argument('--output', type=Path)
    p.add_argument('--timeout', type=int, default=180)
    group = p.add_mutually_exclusive_group()
    group.add_argument('--case', default='one')
    group.add_argument('--all-cases', action='store_true')
    args = p.parse_args()
    if args.checkout:
        args.checkout = args.checkout.resolve()
    out = (args.output or ROOT / 'artifacts' / ('checkout-external-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(mode=args.mode, stage='initialization', cases=[], compiled=False, pin_startup_passed=False,
                  diagnostic_all_matched=False, performance_eligible=False, external_baseline_qualified=False,
                  unresolved=RISKS, bpf_executed=False, hardware=hardware())
    source_dir = out / 'adapter-sources'
    source_dir.mkdir()
    for name in ('external_compare.py', 'external_boundaries.py', 'libdft_payment.cpp', 'payment_test.go', 'cases.json',
                 'test_external_compare.py', 'EXTERNAL-TOOLS.md'):
        shutil.copy2(HERE / name, source_dir / name)
    try:
        execute(args, out, report)
    except Exception as exc:
        report['failure'] = str(exc)
        (out / 'failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        save(out / 'summary.json', report)
        print('Return this result archive: ' + shutil.make_archive(str(out), 'zip', root_dir=out.parent, base_dir=out.name), flush=True)


if __name__ == '__main__':
    main()
