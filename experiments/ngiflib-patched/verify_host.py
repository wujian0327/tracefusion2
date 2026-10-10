#!/usr/bin/env python3
"""Audit a native ngiflib archive without executing uploaded code or binaries.

Only the locally generated layout probe against the digest-checked upstream
header is compiled/executed. Replay sees boundaries, never reference answers
or instruction diagnostics. This verifier audits reported host evidence; it
does not authenticate the host or reproduce Pin execution.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import zipfile

from PIL import Image
import compare_host as runner
from host_records import normalize

EXPECTED_COMMIT = 'f23114e1f57285b5f9109bbf562bd4e9b5aa1aa9'
INPUT_HASHES = dict(
    single_pixel='c57064d499c56ffce47e02486824e696f842d6c1ae31871d63227a7aaf69fe51',
    stripes='6f852572c10270ef465ce7e8509b4041335c8bc568b9380c2346e3581e01f16e',
    checker='5664a6446689dc9fbb87489e07ccc43043c28da1a660e03e0c41b054eaf7b979',
    blocks='3b25564231852543879ef8ec12e2d965f3247a4f0a3473d4ce624a37bb14c40d')
METRICS = ('queries', 'value_matches', 'exact_format_sources', 'covered_required_bytes',
           'missing_required_bytes', 'additional_source_bytes')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def committed(repo, revision, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', revision + ':' + path])


def verify(archive, upstream):
    check = runner.check
    with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory() as temp:
        names = z.namelist()
        check(len(names) == len(set(names)), 'Duplicate archive members')
        check(sum(i.file_size for i in z.infolist()) < 256 * 1024 * 1024, 'Archive exceeds audit budget')
        check(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names),
              'Invalid archive path')
        roots = {n.split('/')[0] for n in names}
        check(len(roots) == 1, 'Expected one archive root')
        prefix = roots.pop() + '/'
        read = lambda p: z.read(prefix + p)
        doc = lambda p: json.loads(read(p))
        work = Path(temp)
        identity = doc('adapter-identity.json')
        check(identity['repository_head'] == EXPECTED_COMMIT, 'Unexpected experiment commit')
        paths = {'experiments/ngiflib-patched/' + n for n in
                 ('compare_host.py', 'host_records.py', 'libdft_ngif.cpp', 'query.py', 'gif_reference.py', 'validate_normal.py')}
        paths |= {'scripts/' + n for n in ('c_bit_machine.py', 'interproc_model.py', 'hybrid_model.py', 'language_adapters.py')}
        paths.add('experiments/checkout-payment-path/external_compare.py')
        check(set(identity['files']) == paths, 'Incomplete adapter identity')
        for path in sorted(paths):
            data = read('adapter-sources/' + path)
            check(digest(data) == identity['files'][path] and data == committed(runner.ROOT, EXPECTED_COMMIT, path),
                  'Adapter snapshot differs from committed source: ' + path)
            check((runner.ROOT / path).read_bytes() == data, 'Local inference/audit dependency changed: ' + path)

        fixture = doc('fixture-identity.json')
        check(fixture['revision'] == runner.REVISION and fixture['fix'] == runner.FIX and
              fixture['source_sha256'] == runner.SOURCE_HASHES and fixture['input_sha256'] == INPUT_HASHES and
              fixture['source_modified'] is False and fixture['ordinary_inputs_only'] is True, 'Fixture contract changed')
        source = work / 'source'
        source.mkdir()
        for name, expected in runner.SOURCE_HASHES.items():
            data = read('fixture/source/' + name)
            check(digest(data) == expected, 'Business source changed: ' + name)
            (source / name).write_bytes(data)
        binary = work / 'host-elf'
        binary.write_bytes(read('fixture/gif2tga'))
        check(digest(binary.read_bytes()) == fixture['binary_sha256'], 'ELF digest mismatch')
        plan = runner.query.plan(binary, source, work)
        check(plan == doc('plan.json'), 'Fresh ELF plan/layout differs from saved plan')
        expanded = runner.expand_adapter(plan, work).read_bytes()
        check(expanded == read('libdft_ngif.cpp') == read('libdft-build/tools/libdft_ngif.cpp'), 'Built adapter changed')
        check(json.loads((work / 'adapter-layout.json').read_text()) == doc('adapter-layout.json'), 'ABI constants changed')

        manifest = doc('upstream-source-manifest.json')
        revision = runner.shared.LIBDFT_REV
        files = subprocess.check_output(['git', '-C', str(upstream), 'ls-tree', '-r', '--name-only', revision, '--', 'src/'], text=True).splitlines()
        check(set(manifest) == {p for p in files if Path(p).suffix in ('.c', '.cpp', '.h')}, 'Incomplete upstream manifest')
        pristine = work / 'libdft'
        (pristine / 'src').mkdir(parents=True)
        for path, expected in manifest.items():
            data = read('libdft-build/' + path)
            check(digest(data) == expected and data == committed(upstream, revision, path), 'Upstream propagation changed: ' + path)
            if path == 'src/libdft_core.cpp':
                (pristine / path).write_bytes(data)
        semantics = runner.audit(pristine, work)
        check(semantics == doc('upstream-semantics.json'), 'Upstream semantic audit changed')
        opcodes = sorted(set(re.findall(r'case (XED_ICLASS_\w+)\s*:', read('libdft-build/src/libdft_core.cpp').decode())))
        header = 'static bool known_opcode(unsigned op) { switch(op) {\n'
        header += ''.join('case ' + op + ':\n' for op in opcodes)
        header += 'return true; default: return false; } }\n'
        check(read('libdft-build/tools/libdft_known_opcodes.h').decode() == header, 'Opcode diagnostic header changed')
        build = doc('tool-build.json')
        check(build['compiled'] is True and build['propagation_code_modified'] is False and
              build['upstream_opcode_cases'] == opcodes, 'Build contract changed')
        for name in ('nullpin', 'libdft_ngif'):
            check(digest(read('libdft-build/tools/obj-intel64/' + name + '.so')) == build['tools'][name]['sha256'], 'Tool digest mismatch')
        deps = doc('dependencies.json')
        check(deps['libdft_revision'] == revision and deps['pin_launcher_sha256'] == runner.shared.PIN_LAUNCHER_SHA256 and
              deps['pin_engine_sha256'] == runner.shared.PIN_ENGINE_SHA256, 'Dependency identity changed')

        summary = doc('summary.json')
        check(summary['stage'] == 'comparison_complete' and summary['mode'] == 'run' and summary['compiled'] is True and
              summary['pin_startup_passed'] is True and summary['all_runs_observed'] is True and
              summary['observed_method_runs'] == 16 and summary['unknown_method_runs'] == 0 and len(summary['cases']) == 8,
              'Incomplete host comparison')
        check(summary['binary_sha256'] == plan['binary_sha256'] and summary['semantics'] == semantics and
              all(summary[k] is False for k in ('bpf_executed', 'performance_eligible', 'external_baseline_qualified')), 'Summary scope changed')
        methods = ('boundary_replay', 'libdft64')
        totals = {m: dict.fromkeys(METRICS, 0) for m in methods}
        counts = {m: dict(raw_records=0, instruction_records=0, source_fills=0, ignored_shift_executions=0) for m in methods}
        cases = []
        differences = []
        for name in runner.CASES:
            data = read('fixture/' + name + '/normal.gif')
            check(digest(data) == INPUT_HASHES[name], 'Input changed')
            with Image.open(io.BytesIO(data)) as im:
                size, rgb, indexed_pixels = im.size, im.convert('RGB').tobytes(), im.tobytes()
            for indexed in (False, True):
                folder = name + ('-indexed' if indexed else '-truecolor')
                native_stdout = read(folder + '/native/stdout.txt')
                native_tga = read(folder + '/native/image_out01.tga')
                for group in ('native', 'nullpin', *methods):
                    check(read(folder + '/' + group + '/stdout.txt') == native_stdout and
                          read(folder + '/' + group + '/image_out01.tga') == native_tga, 'Business output differs: ' + folder + '/' + group)
                output = work / 'image.tga'
                output.write_bytes(native_tga)
                check(runner.tga_rgb(output) == (size, rgb), 'Output pixels differ from Pillow')
                case = dict(input=name, indexed=indexed, methods={})
                for method in methods:
                    base = folder + '/' + method + '/'
                    rows = [json.loads(line) for line in read(base + 'raw.jsonl').splitlines() if line.strip()]
                    trace, external, detail = normalize(rows, plan, data, method == 'libdft64')
                    check(trace == doc(base + 'transport.json') and detail == doc(base + 'diagnostics.json'), 'Raw transport recomputation differs')
                    if method == 'boundary_replay':
                        inference = runner.query.infer(plan, trace, data)
                        observed = inference['queries']
                        check(len(observed) == len(detail['instruction_paths']), 'Diagnostic path count mismatch')
                        for result, pcs in zip(observed, detail['instruction_paths']):
                            check(result['instruction_path_sha256'] == digest(json.dumps(pcs).encode()), 'Replay/native instruction path differs')
                    else:
                        observed = external
                        inference = dict(method=method, queries=external, original_propagation=True,
                                         semantics_qualified=False, ignored_shift_executions=detail['ignored_shift_executions'])
                    check(inference == doc(base + 'inference.json'), 'Saved inference differs from raw recomputation')
                    # Reference construction is downstream of inference.
                    reference, pixels = runner.decode(runner.parse(data))
                    check(pixels == indexed_pixels and reference == doc(folder + '/reference.json'), 'Independent reference differs')
                    evaluation = runner.compare_reference(observed, reference)
                    check(evaluation == doc(base + 'evaluation.json'), 'Saved evaluation differs')
                    item = dict(status='observed', **{k: evaluation[k] for k in METRICS},
                                ignored_shift_executions=detail['ignored_shift_executions'], native_pixels_match=True)
                    case['methods'][method] = item
                    for k in METRICS:
                        totals[method][k] += evaluation[k]
                    counts[method]['raw_records'] += len(rows)
                    counts[method]['instruction_records'] += sum(r['kind'] == 'instruction' for r in rows)
                    counts[method]['source_fills'] += detail['source_fills']
                    counts[method]['ignored_shift_executions'] += detail['ignored_shift_executions']
                    if method == 'libdft64':
                        for actual, expected, score in zip(observed, reference, evaluation['rows']):
                            if not score['exact_format_sources']:
                                context = bytes.fromhex(trace['records'][actual['sequence'] - 1]['entry']['context'])
                                layout = plan['layout']['ngiflib_decode_context']
                                differences.append(dict(input=name, indexed=indexed, sequence=actual['sequence'],
                                    value=actual['value'], observed=actual['source_file_offsets'],
                                    required=expected['source_file_offsets'], extra=score['additional_source_bytes'],
                                    missing=score['missing_required_bytes'], entry_nbbit=context[layout['nbbit']],
                                    entry_restbits=context[layout['restbits']],
                                    entry_lbyte=int.from_bytes(context[layout['lbyte']:layout['lbyte'] + 2], 'little')))
                check(case == summary['cases'][len(cases)], 'Case summary differs')
                cases.append(case)
        return dict(archive_sha256=digest(Path(archive).read_bytes()), experiment_commit=EXPECTED_COMMIT,
                    elf_sha256=plan['binary_sha256'], source_revision=runner.REVISION, libdft_revision=revision,
                    distinct_inputs=4, output_modes=2, native_process_runs=32, observed_method_runs=16,
                    distinct_input_code_positions=totals['boundary_replay']['queries'] // 2,
                    methods=totals, records=counts, cases=cases, libdft_format_differences=differences,
                    unchanged_upstream_source_files=len(manifest),
                    source_snapshots_match_committed_files=True, plan_rebuilt_from_uploaded_elf=True,
                    saved_inference_and_evaluation_match_recomputation=True, replay_paths_match_native_diagnostics=True,
                    native_nullpin_and_instrumented_outputs_match=True, independent_reference_and_pixels_match=True,
                    reported_context_changes=0, reported_adapter_errors=0, unknown_method_runs=0,
                    source_identity='Sequential file offsets and successful buffer-fill versions, not equal-value matching',
                    reference_semantics='Fixed-metadata GIF bitstream byte windows; not a common instruction-taint oracle',
                    upstream_semantics=semantics, executed_uploaded_code=False, bpf_executed=False,
                    performance_eligible=False, external_baseline_qualified=False,
                    conclusion='Native boundary replay and original libdft64 compared on patched ngiflib normal inputs; '
                               'format-source precision only, not selected/eBPF cost or general taint superiority')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--libdft', type=Path, required=True, help='Local checkout containing the pinned upstream Git objects')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.archive, args.libdft)
    if args.output:
        runner.save(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('cases', 'libdft_format_differences')}, indent=2))


if __name__ == '__main__':
    main()
