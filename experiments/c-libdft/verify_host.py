#!/usr/bin/env python3
"""Recheck the C libdft host archive without executing uploaded code or binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

import compare as runner

EXPECTED_COMMIT = 'c3561ad38b2215152bab22f0fb1fc53411a532d1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def committed(repo, revision, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', revision + ':' + path])


def verify(archive, upstream):
    check = runner.check
    with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory() as temp:
        names = z.namelist()
        check(len(names) == len(set(names)), 'Duplicate archive members')
        check(sum(info.file_size for info in z.infolist()) < 256 * 1024 * 1024, 'Archive exceeds audit budget')
        roots = {n.split('/')[0] for n in names}
        check(len(roots) == 1, 'Expected one archive root')
        prefix = roots.pop() + '/'
        read = lambda p: z.read(prefix + p)
        doc = lambda p: json.loads(read(p))
        identity = doc('adapter-identity.json')
        check(identity['repository_head'] == EXPECTED_COMMIT, 'Unexpected experiment commit')
        paths = {name: 'experiments/c-libdft/' + name for name in ('compare.py', 'libdft_c.cpp', 'README.md', 'test_compare.py')}
        paths['external_compare.py'] = 'experiments/checkout-payment-path/external_compare.py'
        check(set(identity['files']) == set(paths), 'Unexpected adapter snapshot')
        for name, path in paths.items():
            data = read('adapter-sources/' + name)
            check(digest(data) == identity['files'][name] and data == committed(runner.ROOT, EXPECTED_COMMIT, path),
                  'Adapter differs from committed source: ' + name)
        check(read('libdft-build/tools/libdft_c.cpp') == read('adapter-sources/libdft_c.cpp'), 'Built adapter differs')
        fixture_identity = doc('fixture/build-identity.json')
        for name, expected in fixture_identity['sources'].items():
            data = read('fixture/sources/' + name)
            check(digest(data) == expected, 'Fixture source digest mismatch')
            if name != 'layout_check.c':
                check(data == committed(runner.ROOT, EXPECTED_COMMIT, 'scenarios/loop-calls-provenance/' + name),
                      'Business fixture changed')
        manifest = doc('upstream-source-manifest.json')
        upstream_files = subprocess.check_output(['git', '-C', str(upstream), 'ls-tree', '-r', '--name-only',
                                                  runner.shared.LIBDFT_REV, '--', 'src/'], text=True).splitlines()
        check(set(manifest) == {p for p in upstream_files if Path(p).suffix in ('.c', '.cpp', '.h')},
              'Incomplete upstream manifest')
        for path, expected in manifest.items():
            data = read('libdft-build/' + path)
            check(digest(data) == expected and data == committed(upstream, runner.shared.LIBDFT_REV, path),
                  'Upstream propagation source changed: ' + path)
        opcodes = sorted(set(re.findall(r'case (XED_ICLASS_\w+)\s*:', read('libdft-build/src/libdft_core.cpp').decode())))
        header = 'static bool known_opcode(unsigned op) { switch(op) {\n'
        header += ''.join('case ' + op + ':\n' for op in opcodes)
        header += 'return true; default: return false; } }\n'
        check(read('libdft-build/tools/libdft_known_opcodes.h').decode() == header, 'Changed opcode coverage gate')
        tool_build = doc('tool-build.json')
        check(tool_build['propagation_code_modified'] is False and tool_build['upstream_opcode_cases'] == opcodes,
              'Tool build contract changed')
        for name in ('nullpin', 'libdft_c'):
            check(digest(read('libdft-build/tools/obj-intel64/' + name + '.so')) == tool_build['tools'][name]['sha256'],
                  'Built tool digest mismatch')
        dependencies = doc('dependencies.json')
        check(dependencies['libdft_revision'] == runner.shared.LIBDFT_REV and
              dependencies['pin_launcher_sha256'] == runner.shared.PIN_LAUNCHER_SHA256 and
              dependencies['pin_engine_sha256'] == runner.shared.PIN_ENGINE_SHA256, 'Unexpected dependency identity')
        work = Path(temp)
        binary = work / 'host-elf'
        binary.write_bytes(read('fixture/hybrid-demo'))
        check(digest(binary.read_bytes()) == fixture_identity['binary_sha256'], 'ELF digest mismatch')
        # Only local nm/objdump inspect the uploaded ELF. Never execute it.
        evidence = runner.binary_evidence(binary, work)
        saved = doc('binary-evidence.json')
        saved['instructions'] = {int(k): v for k, v in saved['instructions'].items()}
        check(evidence == saved, 'Saved binary evidence differs from freshly disassembled ELF')
        truth = runner.truth_rows(read('native.jsonl').decode())
        check(truth == doc('truth.json') == runner.truth_rows(read('nullpin.jsonl').decode()), 'Truth/native/nullpin mismatch')
        # Independently recompute the original, unchanged driver oracle, never used by inference.
        for sequence, row in enumerate(truth, 1):
            round_id, within = divmod(sequence - 1, 12)
            fid, ci = divmod(within, 4)
            count = (0, 1, 2, 4)[ci]
            value = 424242 + round_id
            expected_value = (42 if count == 0 else value) if fid == 0 else count * (value if fid == 1 else value ^ 0x55)
            sources = [] if count == 0 else (['input.secret'] if count <= 2 else
                      ['input.public_value'] if fid == 0 else ['input.secret', 'input.public_value'])
            check(row == dict(sequence=sequence, function=runner.NAMES[fid], count=count,
                              expected_helper_calls=count * (2 if fid == 2 else 1), expected_sources=sources,
                              expected_value=expected_value, output=expected_value), 'Driver oracle mismatch')
        summary = doc('summary.json')
        check(summary['stage'] == 'queries_complete' and len(summary['queries']) == 24, 'Incomplete query run')
        results = []
        total_instructions = total_raw_rows = 0
        for sequence in range(1, 25):
            folder = 'query-%02d/' % sequence
            check(runner.truth_rows(read(folder + 'stdout.jsonl').decode()) == truth, 'Instrumented business output changed')
            log = work / 'observations.jsonl'
            log.write_bytes(read(folder + 'observations.jsonl'))
            observation = runner.parse_observation(log, sequence, evidence)
            evaluation = runner.score(observation, truth[sequence - 1])
            check(observation == doc(folder + 'inference.json') and evaluation == doc(folder + 'evaluation.json'),
                  'Recomputed inference/evaluation differs from saved result')
            check(evaluation['matched'], 'Source set or value mismatch')
            expected_summary = dict(sequence=sequence, status='matched', **evaluation)
            check(summary['queries'][sequence - 1] == expected_summary, 'Per-query summary mismatch')
            total_instructions += observation['instructions']
            total_raw_rows += len(log.read_text().splitlines())
            results.append(evaluation)
        totals = {k: sum(r[k] for r in results) for k in ('tp', 'fp', 'fn')}
        check(summary['resolved_relation_totals'] == totals and summary['matched_queries'] == 24 and
              summary['unknown_queries'] == summary['mismatched_queries'] == 0 and
              summary['full_fixture_agreement'] is True and summary['performance_eligible'] is False,
              'Overall summary mismatch')
        return dict(archive_sha256=digest(Path(archive).read_bytes()), experiment_commit=EXPECTED_COMMIT,
                    elf_sha256=evidence['binary_sha256'], adapter_sha256=identity['files']['libdft_c.cpp'],
                    verified_queries=24, matched_queries=24, empty_source_queries=sum(not r['expected_sources'] for r in truth),
                    unknown_queries=0, mismatched_queries=0, relation_totals=totals,
                    raw_instruction_records=total_instructions, raw_jsonl_records=total_raw_rows,
                    unchanged_upstream_source_files=len(manifest),
                    native_nullpin_and_all_instrumented_outputs_match=True, recomputed_oracle_matches=True,
                    source_snapshots_match_committed_files=True, saved_inference_matches_recomputation=True,
                    source_byte_labels_validated=True, instruction_pcs_checked_against_uploaded_elf=True,
                    reported_context_changes=0, reported_uncovered_opcodes=0, reported_adapter_errors=0,
                    executed_uploaded_code=False, bpf_rerun=False, performance_eligible=False,
                    conclusion='Original libdft64 matches all input-field source queries in this bounded C fixture; no general C/C++ or performance claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--libdft', type=Path, required=True, help='Checkout containing the pinned upstream commit')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.archive, args.libdft)
    if args.output:
        runner.save(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
