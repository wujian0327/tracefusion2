#!/usr/bin/env python3
"""Qualify libdft64 on the existing C loop/call fixture, without changing propagation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(HERE.parent / 'checkout-payment-path')]
import external_compare as shared
import hybrid_provenance as common
import loop_calls_provenance as loops
import interproc_provenance as collector

NAMES = ['loop_call_overwrite', 'loop_call_accumulate', 'loop_call_transform',
         'read_iteration', 'transform_iteration']
FIELDS = ['input.secret', 'input.public_value', 'input.noise']
check = shared.check
save = shared.save


def truth_rows(text):
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    check(len(rows) == 24 and [r['sequence'] for r in rows] == list(range(1, 25)), 'Incomplete native truth')
    for row in rows:
        check(row['function'] in NAMES[:3] and row['count'] in (0, 1, 2, 4), 'Invalid fixture invocation')
        check(row['output'] == row['expected_value'], 'Native business output contradicts independent truth')
        check(set(row['expected_sources']) <= set(FIELDS), 'Unknown truth source')
    return rows


def binary_evidence(binary, out):
    nm = shared.command(['nm', '-S', '--defined-only', binary], out)
    symbols = {}
    for line in nm.splitlines():
        words = line.split()
        if len(words) == 4 and words[3] in NAMES:
            check(words[3] not in symbols, 'Duplicate symbol')
            symbols[words[3]] = [int(words[0], 16), int(words[1], 16)]
    check(set(symbols) == set(NAMES), 'Missing original C function symbol')
    # This evidence is disassembly, not a selector or taint inference result.
    asm = shared.command(['objdump', '-d', '-M', 'intel', binary], out)
    (out / 'instruction-bytes.txt').write_text(asm)
    instructions = {}
    for line in asm.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s*((?:[0-9a-f]{2}\s+)+)\s*(\S.*)$', line)
        if match:
            instructions[int(match[1], 16)] = dict(bytes=match[2].split(), assembly=match[3])
    evidence = dict(symbols=symbols, instructions=instructions, binary_sha256=shared.sha(binary))
    save(out / 'binary-evidence.json', evidence)
    return evidence


def labels(value):
    check(isinstance(value, list) and all(type(x) is int and 1 <= x <= 3 for x in value), 'Unknown label namespace')
    check(value == sorted(set(value)), 'Noncanonical labels')
    return set(value)


def parse_observation(path, sequence, evidence):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    check(rows and rows[-1]['kind'] == 'finish', 'Missing tool completion')
    check(not any(r['kind'] == 'error' for r in rows), 'Adapter reported an error; result unknown')
    symbols = [r for r in rows if r['kind'] == 'symbol']
    source = [r for r in rows if r['kind'] == 'source']
    sink = [r for r in rows if r['kind'] == 'sink']
    ins = [r for r in rows if r['kind'] == 'instruction']
    check(len(symbols) == 5 and [r['name'] for r in symbols] == NAMES and
          [r['id'] for r in symbols] == list(range(5)), 'Incomplete or reordered image symbols')
    check(len(source) == len(sink) == 1, 'Missing/duplicate query boundaries')
    check([r['kind'] for r in rows] == ['symbol'] * 5 + ['source'] + ['instruction'] * len(ins) + ['sink', 'finish'],
          'Unexpected record ordering')
    f = rows[-1]
    check(f['exit_code'] == 0 and f['bad'] is False and f['active'] is False and f['roots'] == 24 and
          f['starts'] == f['sinks'] == 1 and f['threads'] == 1 and f['contexts'] == 0 and
          f['performance_eligible'] is False, 'Invalid process, query or context completion')
    start, end = source[0], sink[0]
    check(start['sequence'] == end['sequence'] == sequence and start['function'] == end['function'] and
          start['function'] in NAMES[:3], 'Wrong invocation identity')
    check(start['byte_labels'] == [[[i]] * 4 for i in range(1, 4)], 'Incorrect source tag initialization')
    check(len(start['values']) == 3 and start['values'][0] == start['values'][1], 'Not the same-value fixture')
    check(start['src'] > 0 and start['dst'] > 0 and
          (start['src'] + 12 <= start['dst'] or start['dst'] + 8 <= start['src']), 'Invalid source/sink objects')
    biases = set()
    for sym in symbols:
        address, size = evidence['symbols'][sym['name']]
        check(sym['end'] - sym['begin'] == size, 'Runtime symbol size differs from ELF')
        biases.add(sym['begin'] - address)
    check(len(biases) == 1, 'Inconsistent ELF relocation')
    bias = biases.pop()
    check(0 < len(ins) == f['steps'] <= 4096 and [r['step'] for r in ins] == list(range(1, len(ins) + 1)),
          'Incomplete instruction sequence')
    helper_entries = 0
    for row in ins:
        check(type(row['fid']) is int and 0 <= row['fid'] < 5 and row['covered'] is True and
              row['tid'] == start['tid'], 'Out-of-scope instruction or thread')
        sym = symbols[row['fid']]
        check(sym['begin'] <= row['pc'] < sym['end'] and row['pc'] - bias in evidence['instructions'],
              'Instruction address does not match ELF')
        helper_entries += row['fid'] >= 3 and row['pc'] == sym['begin']
    root = NAMES.index(start['function'])
    check(ins[0]['fid'] == root and ins[0]['pc'] == symbols[root]['begin'] and ins[-1]['fid'] == root and
          evidence['instructions'][ins[-1]['pc'] - bias]['assembly'].split()[0] in ('ret', 'retq'),
          'Missing entry or root return')
    check(end['helper_calls'] == helper_entries, 'Helper entry count mismatch')
    observed = labels(end['labels'])
    check(len(end['byte_labels']) == 4 and set().union(*(labels(x) for x in end['byte_labels'])) == observed,
          'Aggregate sink labels disagree with byte labels')
    return dict(sequence=sequence, function=start['function'], count=start['count'], value=end['value'],
                sources=sorted(FIELDS[n - 1] for n in observed), helper_calls=helper_entries,
                instructions=len(ins), status='observed_origin_set', oracle_used_for_inference=False)


def score(observation, truth):
    check(observation['sequence'] == truth['sequence'] and observation['function'] == truth['function'] and
          observation['count'] == truth['count'], 'Observation/truth invocation mismatch')
    actual, expected = set(observation['sources']), set(truth['expected_sources'])
    value_ok = observation['value'] == truth['expected_value']
    calls_ok = observation['helper_calls'] == truth['expected_helper_calls']
    return dict(matched=actual == expected and value_ok and calls_ok, exact_sources=actual == expected,
                value_matched=value_ok, helper_calls_matched=calls_ok,
                tp=len(actual & expected), fp=len(actual - expected), fn=len(expected - actual))


def execute(args, out, report):
    report['stage'] = 'build_original_fixture'
    fixture = out / 'fixture'
    fixture.mkdir()
    binary, _, _ = common.build(ROOT / 'scenarios/loop-calls-provenance', fixture,
                                planner=loops.plan_program, source_generator=collector.bpf_source)
    evidence = binary_evidence(binary, out)
    native = shared.command([binary], out)
    (out / 'native.jsonl').write_text(native)
    truth = truth_rows(native)
    save(out / 'truth.json', truth)
    report['native_queries'] = len(truth)
    report['stage'] = 'native_validated'
    if args.mode == 'native':
        return
    pin, lib = shared.dependencies(args, out)
    report['stage'] = 'build_tools'
    tools = shared.build_tools(pin, lib, out, HERE / 'libdft_c.cpp', 'libdft_c')
    report['compiled'] = True
    # Prove no upstream propagation source was changed in the build copy.
    manifest = {}
    for original in sorted((lib / 'src').rglob('*')):
        if original.is_file() and original.suffix in ('.c', '.cpp', '.h'):
            relative = original.relative_to(lib)
            check(shared.sha(original) == shared.sha(out / 'libdft-build' / relative), 'Upstream source changed')
            manifest[str(relative)] = shared.sha(original)
    save(out / 'upstream-source-manifest.json', manifest)
    report['stage'] = 'tools_built'
    if args.mode == 'build-tools':
        return
    report['stage'] = 'pin_startup'
    shared.command([pin / 'pin', '-t', tools['nullpin'], '--', '/bin/true'], out, timeout=args.timeout)
    nullpin = shared.command([pin / 'pin', '-t', tools['nullpin'], '--', binary], out, timeout=args.timeout)
    (out / 'nullpin.jsonl').write_text(nullpin)
    check(truth_rows(nullpin) == truth, 'Nullpin changed business result')
    report['pin_startup_passed'] = True
    report['stage'] = 'libdft_queries'
    selected = [args.sequence] if args.sequence else list(range(1, 25))
    for sequence in selected:
        case = out / ('query-%02d' % sequence)
        case.mkdir()
        result = dict(sequence=sequence, status='unknown')
        report['queries'].append(result)
        try:
            stdout = shared.command([pin / 'pin', '-t', tools['libdft_c'], '-sequence', sequence,
                                     '-origin_log', case / 'observations.jsonl', '--', binary], case, timeout=args.timeout)
            (case / 'stdout.jsonl').write_text(stdout)
            check(truth_rows(stdout) == truth, 'libdft run changed native output or independent truth')
            observation = parse_observation(case / 'observations.jsonl', sequence, evidence)
            save(case / 'inference.json', observation)
            evaluation = score(observation, truth[sequence - 1])
            save(case / 'evaluation.json', evaluation)
            result.update(status='matched' if evaluation['matched'] else 'mismatch', **evaluation)
        except Exception as exc:
            result['reason'] = str(exc)
            (case / 'failure.txt').write_text(traceback.format_exc())
        save(out / 'summary.json', report)
    report['stage'] = 'queries_complete'
    report['matched_queries'] = sum(r['status'] == 'matched' for r in report['queries'])
    report['unknown_queries'] = sum(r['status'] == 'unknown' for r in report['queries'])
    report['mismatched_queries'] = sum(r['status'] == 'mismatch' for r in report['queries'])
    report['diagnostic_all_matched'] = report['matched_queries'] == len(selected)
    report['full_fixture_agreement'] = len(selected) == 24 and report['diagnostic_all_matched']
    report['resolved_relation_totals'] = {k: sum(r.get(k, 0) for r in report['queries']) for k in ('tp', 'fp', 'fn')}
    if not report['diagnostic_all_matched']:
        raise RuntimeError('Some queries are unknown or disagree; inspect preserved per-query evidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('native', 'build-tools', 'run'))
    parser.add_argument('--pin-root', type=Path)
    parser.add_argument('--libdft', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sequence', type=int, choices=range(1, 25))
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    out = (args.output or ROOT / 'artifacts' / ('c-libdft-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(mode=args.mode, stage='initialization', compiled=False, pin_startup_passed=False, queries=[],
                  diagnostic_all_matched=False, full_fixture_agreement=False, performance_eligible=False,
                  external_baseline_qualified=False, bpf_executed=False,
                  scope='Existing immutable C u32 loop/call fixture; input-field explicit data sources only',
                  isolation='Fresh process for each queried root; unmodified driver executes all 24 calls',
                  limitation='Agreement here does not qualify arbitrary C/C++, opcode forms, signals, concurrency or performance')
    sources = out / 'adapter-sources'
    sources.mkdir()
    for path in (HERE / 'compare.py', HERE / 'libdft_c.cpp', HERE / 'README.md',
                 HERE / 'test_compare.py',
                 HERE.parent / 'checkout-payment-path/external_compare.py'):
        shutil.copy2(path, sources / path.name)
    try:
        head = shared.command(['git', 'rev-parse', 'HEAD'], out).strip()
        save(out / 'adapter-identity.json', dict(repository_head=head,
             files={p.name: shared.sha(p) for p in sources.iterdir()}))
        execute(args, out, report)
    except Exception as exc:
        report['failure'] = str(exc)
        (out / 'failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        save(out / 'summary.json', report)
        archive = shutil.make_archive(str(out), 'zip', root_dir=out.parent, base_dir=out.name)
        print('Return this result archive: ' + archive, flush=True)


if __name__ == '__main__':
    main()
