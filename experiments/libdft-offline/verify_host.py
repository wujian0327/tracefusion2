#!/usr/bin/env python3
"""Recheck an extracted host archive without executing its code or binaries."""
import argparse
from collections import Counter
import json
from pathlib import Path

from build_core import build, sha
from calibrate_host import adapter, convert, original, ROOT
from replay import replay, require, REGS


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify(host, upstream, out):
    out.mkdir(parents=True, exist_ok=False)
    # Only trusted checkout sources are compiled/executed. Uploaded ELF is disassembled.
    exe, extraction = build(upstream, out / 'rebuilt-core')
    source_hashes = {}
    for name in ('build_core.py', 'pin.H', 'core.cpp', 'replay.py',
                 'calibrate_host.py', 'check_local.py', 'requirements.txt'):
        local = Path(__file__).parent / name
        require(local.read_bytes() == (host / 'adapter-source' / name).read_bytes(),
                'adapter differs: ' + name)
        source_hashes[name] = sha(local.read_bytes())
    capture, capture_info = adapter(out)
    for p in (host / 'libdft_offline_capture.cpp',
              host / 'libdft-build/tools/libdft_offline_capture.cpp'):
        require(p.read_bytes() == capture.read_bytes(), 'capture adapter differs')
    claimed = read(host / 'validation.json')
    require(capture_info == claimed['capture_adapter'], 'capture manifest')
    archived = read(host / 'offline-core/extraction.json')
    require(archived == claimed['extraction'], 'extraction report disagreement')
    for key in ('revision', 'upstream_sha256', 'callbacks', 'adapter_sha256', 'generated_sha256'):
        require(extraction[key] == archived[key], 'extraction mismatch: ' + key)
    require(archived['returncode'] == 0, 'host offline build failed')
    for rel, digest in extraction['upstream_sha256'].items():
        paths = [host / 'libdft-build' / rel]
        paths.append(host / 'offline-core' / ('UPSTREAM-LICENSE' if rel == 'LICENSE'
                     else 'upstream/' + Path(rel).name))
        for p in paths:
            require(sha(p.read_bytes()) == digest, 'upstream source mismatch: ' + str(p))
    for name in ('callbacks.inc', 'core.cpp', 'shim/pin.H'):
        require((host / 'offline-core' / name).read_bytes() ==
                (out / 'rebuilt-core' / name).read_bytes(), 'generated core mismatch')
    require(sha((host / 'offline-core/libdft-replay-core').read_bytes()) ==
            archived['executable_sha256'], 'archived core digest')
    for name in ('main.c', 'operations.c', 'model.h'):
        require((host / 'fixture' / name).read_bytes() ==
                (ROOT / 'scenarios/loop-calls-provenance' / name).read_bytes(), 'fixture source')
    tools = read(host / 'tool-build.json')
    for name, item in tools['tools'].items():
        require(sha((host / 'libdft-build/tools/obj-intel64' / (name + '.so')).read_bytes()) ==
                item['sha256'], 'native tool digest')
    evidence = original.binary_evidence(host / 'fixture/program', out)
    saved = read(host / 'binary-evidence.json')
    saved['instructions'] = {int(k): v for k, v in saved['instructions'].items()}
    require(evidence == saved, 'ELF evidence differs')
    truth = original.truth_rows((host / 'native.jsonl').read_text())
    commands = rows(host / 'commands.jsonl')
    require(all(c['returncode'] == 0 for c in commands), 'host command failure')
    null = [c for c in commands if Path(c['command'][0]).name == 'pin' and
            any(str(x).endswith('/nullpin.so') for x in c['command'])]
    require(len(null) == 1 and original.truth_rows(null[0]['stdout']) == truth, 'nullpin output')
    results, callbacks, raw_records = [], Counter(), 0
    for seq in range(1, 25):
        q = host / f'query-{seq:02d}'
        raw = rows(q / 'observations.jsonl'); raw_records += len(raw)
        without_states = [r for r in raw if r['kind'] != 'state']
        normalized = out / f'query-{seq:02d}-original.jsonl'
        normalized.write_text(''.join(json.dumps(r) + '\n' for r in without_states))
        observed = original.parse_observation(normalized, seq, evidence)
        require(original.score(observed, truth[seq-1])['matched'], 'original oracle mismatch')
        trace, states, sink = convert(raw, evidence, seq)
        kinds = ['symbol'] * 5 + ['source'] + ['state', 'instruction'] * len(states) + ['sink', 'finish']
        require([r['kind'] for r in raw] == kinds, 'state/instruction ordering')
        require(json.loads(json.dumps(trace)) == read(q / 'trace.json'), 'saved concrete trace differs')
        result = replay(exe, trace)
        require(result == read(q / 'replay.json'), 'saved replay differs')
        require(result['byte_labels'] == sink['byte_labels'] and result['labels'] == sink['labels'],
                'final tags differ')
        for i, state in enumerate(states):
            actual = result['intermediate_tags_before'][i*17:(i+1)*17]
            require([x['bytes'] for x in actual] == state['tag_bytes'] + [state['sink_bytes']],
                    f'intermediate tags differ: query {seq}, step {i+1}')
        # Reconstruct workload truth independently of archived expected_* fields.
        round_index, f, c = (seq-1)//12, ((seq-1)%12)//4, (0,1,2,4)[(seq-1)%4]
        value = 424242 + round_index
        wanted = [] if not c else ([2] if f == 0 and c > 2 else
                                  [1,2] if f != 0 and c > 2 else [1])
        expected_value = (42 if not c else value) if f == 0 else c * (value if f == 1 else value ^ 0x55)
        require(trace['inputs'] == {'values': [value,value,99], 'count': c}, 'fixture inputs')
        require(trace['function'] == original.NAMES[f] and result['labels'] == wanted and
                sink['value'] == expected_value, 'independent formula mismatch')
        require(original.truth_rows((q / 'stdout.jsonl').read_text()) == truth, 'business output')
        cmd = rows(q / 'commands.jsonl')
        require(len(cmd) == 1 and cmd[0]['returncode'] == 0 and
                original.truth_rows(cmd[0]['stdout']) == truth, 'query command result')
        for step in result['dispatch']:
            for call in step['callbacks']:
                callbacks[call.split()[1] if call.startswith('call ') else call.split()[0]] += 1
        results.append(dict(sequence=seq, status='matched', steps=trace['steps'], labels=wanted,
                            intermediate_byte_checks=trace['steps']*(8*len(REGS)+4)))
    require(results == claimed['queries'] and claimed['native_pin_equivalence'] is True and
            claimed['status'] == 'pass_bounded_native_calibration' and
            claimed['performance_eligible'] is False, 'host summary mismatch')
    report = dict(status='verified_bounded_native_calibration', queries=results,
                  correct_queries=24, empty_source_queries=sum(not q['labels'] for q in results),
                  instruction_records=sum(q['steps'] for q in results), raw_jsonl_records=raw_records,
                  intermediate_byte_checks=sum(q['intermediate_byte_checks'] for q in results),
                  final_byte_checks=24*4, tp=sum(len(q['labels']) for q in results), fp=0, fn=0,
                  callback_counts=dict(callbacks), extracted_callbacks=len(extraction['callbacks']),
                  upstream_revision=extraction['revision'], upstream_files=len(extraction['upstream_sha256']),
                  adapter_sha256=source_hashes, binary_sha256=evidence['binary_sha256'],
                  capture_adapter=capture_info, uploaded_binaries_executed=False,
                  native_pin_equivalence=True, performance_eligible=False,
                  scope='24 single-thread immutable C queries; 16 GPRs and sink, not all memory',
                  host_environment='OS/CPU/compiler versions not recorded; no host attribution inferred',
                  files_sha256={str(p.relative_to(host)): sha(p.read_bytes())
                                for p in sorted(host.rglob('*')) if p.is_file()})
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('host', type=Path, help='Extracted archive directory')
    p.add_argument('--libdft', required=True, type=Path, help='Trusted pinned upstream checkout')
    p.add_argument('--output', required=True, type=Path, help='New verification output directory')
    a = p.parse_args()
    result = verify(a.host.resolve(), a.libdft.resolve(), a.output.resolve())
    print(json.dumps({k: v for k,v in result.items() if k not in
                      ('queries', 'files_sha256', 'adapter_sha256', 'capture_adapter')}))
