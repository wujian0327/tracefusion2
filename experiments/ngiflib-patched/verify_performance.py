#!/usr/bin/env python3
"""Recompute cost results and provenance from an existing host archive.

Never execute uploaded binaries/scripts. Timings are host-reported wait4 and
clock observations: consistency checks do not authenticate remote execution.
Only a locally generated layout probe against a verified header is executed.
"""
import argparse
import io
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import zipfile

from PIL import Image
import compare_host as runner
_spec = importlib.util.spec_from_file_location('ngif_cost_runner', Path(__file__).with_name('performance.py'))
perf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(perf)
from perf_records import normalize
from verify_host import digest, committed, INPUT_HASHES, METRICS

EXPECTED_COMMIT = 'd6d3d6608e6047d2826bdef6cb466b255d68c645'
check = runner.check


def measurement(m):
    check(m['returncode'] == 0 and m['timed_out'] is False and
          m['scope'] == 'whole child process including launch and exit', 'Failed or unsupported timing record')
    for k in ('wall_seconds', 'user_seconds', 'system_seconds', 'cpu_seconds'):
        check(type(m[k]) in (int, float) and math.isfinite(m[k]) and m[k] >= 0, 'Invalid timing number')
    check(m['wall_seconds'] > 0 and m['cpu_seconds'] == m['user_seconds'] + m['system_seconds'] and
          type(m['peak_rss_bytes']) is int and m['peak_rss_bytes'] > 0, 'Resource arithmetic mismatch')


def phases_check(phases, timed, detail):
    for kind in ('wall', 'cpu'):
        vals = [phases[f'{part}_{kind}_seconds'] for part in ('parse_validate', 'infer', 'output')]
        total = phases[f'total_{kind}_seconds']
        check(all(math.isfinite(v) and v >= 0 for v in vals) and math.isclose(sum(vals), total, abs_tol=1e-9),
              'Offline phase arithmetic mismatch')
        check(timed[f'{kind}_seconds'] + 1e-5 >= total, 'Internal phase exceeds whole process cost')
    check(phases['raw_records'] == detail['raw_records'] and phases['source_fills'] == detail['source_fills'] and
          phases['instruction_diagnostics'] is False and
          0 < phases['process_peak_rss_bytes'] <= timed['peak_rss_bytes'], 'Offline phase counters/RSS differ')


def verify(archive, upstream):
    with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory() as temp:
        names = z.namelist()
        check(len(names) == len(set(names)), 'Duplicate archive members')
        check(sum(i.file_size for i in z.infolist()) < 512*1024*1024, 'Archive exceeds audit budget')
        check(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names), 'Invalid archive path')
        roots = {n.split('/')[0] for n in names}
        check(len(roots) == 1, 'Expected one archive root')
        prefix = roots.pop()+'/'
        read = lambda p: z.read(prefix+p)
        doc = lambda p: json.loads(read(p))
        work = Path(temp)
        identity = doc('adapter-identity.json')
        check(identity['repository_head'] == EXPECTED_COMMIT, 'Unexpected performance commit')
        tracked = subprocess.check_output(['git','-C',str(runner.ROOT),'ls-tree','-r','--name-only',EXPECTED_COMMIT,
                                          '--','experiments/ngiflib-patched/'],text=True).splitlines()
        paths = {p for p in tracked if Path(p).suffix in ('.py','.cpp')}
        paths |= {'scripts/'+n for n in ('c_bit_machine.py','interproc_model.py','hybrid_model.py','language_adapters.py')}
        paths |= {'experiments/checkout-payment-path/external_compare.py', 'experiments/ngiflib-patched/host-validation-20261010.json'}
        check(set(identity['files']) == paths, 'Incomplete implementation snapshot')
        for path in sorted(paths):
            data = read('adapter-sources/'+path)
            check(digest(data) == identity['files'][path] and data == committed(runner.ROOT,EXPECTED_COMMIT,path),
                  'Snapshot differs from committed source: '+path)
            check((runner.ROOT/path).read_bytes() == data, 'Local audit dependency differs: '+path)

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
        check(expanded == read('libdft_ngif.cpp'), 'Base ABI adapter changed')
        fields = json.loads((work/'adapter-layout.json').read_text())
        body = (runner.HERE/'libdft_ngif_perf.cpp').read_text()
        marker = '// ABI_CONTRACT -- replaced by header offsets verified against target ELF DWARF.'
        expected_adapter = body.replace(marker, '\n'.join(f'static const unsigned {k}={v};' for k,v in fields.items())).encode()
        check(expected_adapter == read('libdft_ngif_perf.cpp') == read('libdft-build/tools/libdft_ngif_perf.cpp'), 'Cost adapter changed')
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
        for name in ('nullpin', 'libdft_ngif_perf'):
            check(digest(read('libdft-build/tools/obj-intel64/' + name + '.so')) == build['tools'][name]['sha256'], 'Tool digest mismatch')
        deps = doc('dependencies.json')
        check(deps['libdft_revision'] == revision and deps['pin_launcher_sha256'] == runner.shared.PIN_LAUNCHER_SHA256 and
              deps['pin_engine_sha256'] == runner.shared.PIN_ENGINE_SHA256, 'Dependency identity changed')


        summary = doc('summary.json')
        check(summary['stage'] == 'performance_complete' and summary['compiled'] is True and
              summary['pin_startup_passed'] is True and summary['all_results_checked'] is True and
              summary['profile'] == 'boundary-cost-v1' and summary['startup_included'] is True and
              all(summary[k] is False for k in ('bpf_executed','steady_state','fsync_included','semantics_qualified')),
              'Incomplete result or changed measurement scope')
        check(summary['binary_sha256'] == plan['binary_sha256'] and summary['semantics'] == semantics and
              summary['unchanged_upstream_files'] == len(manifest), 'Result identity differs')
        check(summary['blocks'] == 10 and summary['warmups'] == 2 and summary['seed'] == 20261010, 'Unexpected study schedule')
        order = perf.schedule(summary['warmups'],summary['blocks'],summary['seed'])
        check(order == doc('schedule.json'), 'Recorded order differs from preregistered shuffle')
        trials = [json.loads(line) for line in read('trials.jsonl').splitlines()]
        check(len(trials) == len(order)*4, 'Missing/extra timing trials')
        golden = doc('adapter-sources/experiments/ngiflib-patched/host-validation-20261010.json')
        native_command = doc(next(r['directory'] for r in trials if r['group']=='native')+'/measurement.json')['command']
        host_binary = PurePosixPath(native_command[0])
        check(host_binary.name == 'gif2tga' and host_binary.parent.name == 'fixture', 'Unexpected target command')
        host_root = host_binary.parent.parent
        methods = ('boundary_replay','libdft64')
        totals = {phase: {m: dict.fromkeys(METRICS,0) for m in methods} for phase in ('measured','warmup')}
        counts = {m: dict(raw_records=0,source_fills=0,processes=0) for m in methods}
        offline_phases = []
        result_rows = []
        for index, entry in enumerate(order):
            data = read('fixture/'+entry['input']+'/normal.gif')
            check(digest(data) == INPUT_HASHES[entry['input']], 'Input changed')
            with Image.open(io.BytesIO(data)) as image:
                expected_pixels = image.size,image.convert('RGB').tobytes()
                indexed_pixels = image.tobytes()
            outputs = []
            for group in entry['groups']:
                row = trials[len(result_rows)]
                directory = f'trial-{index:04d}-{group}'
                check(all(row[k] == entry[k] for k in ('block','warmup','input','indexed')) and
                      row['group'] == group and row['directory'] == directory, 'Trial order differs')
                online = doc(directory+'/measurement.json')
                measurement(online)
                input_path = str(host_binary.parent/entry['input']/'normal.gif')
                command = [] if group == 'native' else [str(PurePosixPath(deps['pin_root'])/'pin'),'-t',build['tools']['nullpin']['path']]
                if group in methods:
                    command = [str(PurePosixPath(deps['pin_root'])/'pin'),'-t',build['tools']['libdft_ngif_perf']['path'],
                               '-enable_taint',str(int(group=='libdft64')),'-input_file',input_path,
                               '-origin_log',str(host_root/directory/'raw.jsonl')]
                if command:
                    command.append('--')
                command += [str(host_binary), *(['--indexed'] if entry['indexed'] else []),'--outbase','image',input_path]
                check(online['command'] == command, 'Wrong online command, mode or target')
                tga = read(directory+'/image_out01.tga')
                (work/'image.tga').write_bytes(tga)
                check(runner.tga_rgb(work/'image.tga') == expected_pixels, 'Output pixels differ')
                outputs.append((digest(tga),read(directory+'/stdout.txt')))
                offline = dict(wall_seconds=0,cpu_seconds=0,peak_rss_bytes=0)
                raw_bytes = 0
                if group in methods:
                    raw = read(directory+'/raw.jsonl')
                    raw_bytes = len(raw)
                    rows = [json.loads(line) for line in raw.splitlines()]
                    trace, external, detail = normalize(rows,plan,data,group=='libdft64')
                    if group == 'boundary_replay':
                        inference = runner.query.infer(plan,trace,data)
                    else:
                        inference = dict(queries=external,original_propagation=True,semantics_qualified=False)
                    check(inference == doc(directory+'/offline/inference.json'), 'Recomputed inference differs')
                    reference, pixels = runner.decode(runner.parse(data))
                    check(pixels == indexed_pixels, 'Reference pixels differ')
                    evaluation = runner.compare_reference(inference['queries'],reference)
                    check(evaluation == doc(directory+'/evaluation.json') and evaluation['value_matches'] == len(reference), 'Evaluation mismatch')
                    expected = {r['sequence']:r['source_file_offsets'] for r in reference}
                    if group == 'libdft64':
                        for d in golden['libdft_format_differences']:
                            if d['input'] == entry['input'] and d['indexed'] == entry['indexed']:
                                expected[d['sequence']] = d['observed']
                    check(all(r['source_file_offsets'] == expected[r['sequence']] for r in inference['queries']), 'Changed provenance result')
                    phase = 'warmup' if entry['warmup'] else 'measured'
                    for k in METRICS:
                        totals[phase][group][k] += evaluation[k]
                    counts[group]['raw_records'] += len(rows)
                    counts[group]['source_fills'] += detail['source_fills']
                    counts[group]['processes'] += 1
                    offline = doc(directory+'/offline/measurement.json')
                    measurement(offline)
                    cmd = offline['command']
                    check(len(cmd)==13 and cmd[1].endswith('/experiments/ngiflib-patched/performance.py') and
                          cmd[2:] == ['_worker','--plan',str(host_root/'plan.json'),'--input',input_path,
                            '--raw',str(host_root/directory/'raw.jsonl'),'--method',group,'--output',str(host_root/directory/'offline')],
                          'Wrong offline worker command')
                    phases = doc(directory+'/offline/phases.json')
                    phases_check(phases,offline,detail)
                    if not entry['warmup']:
                        offline_phases.append(dict(input=entry['input'],indexed=entry['indexed'],group=group,**phases))
                actual = dict(online_wall_seconds=online['wall_seconds'],online_cpu_seconds=online['cpu_seconds'],
                    online_peak_rss_bytes=online['peak_rss_bytes'],offline_wall_seconds=offline['wall_seconds'],
                    offline_cpu_seconds=offline['cpu_seconds'],offline_peak_rss_bytes=offline['peak_rss_bytes'],
                    complete_wall_seconds=online['wall_seconds']+offline['wall_seconds'],
                    complete_cpu_seconds=online['cpu_seconds']+offline['cpu_seconds'],
                    complete_peak_rss_bytes=max(online['peak_rss_bytes'],offline['peak_rss_bytes']),raw_bytes=raw_bytes,
                    sources_checked=group in methods,pixels_match=True)
                check(all(row[k] == v for k,v in actual.items()), 'Trial resource arithmetic differs')
                result_rows.append(row)
            check(len(set(outputs)) == 1, 'Paired native/nullpin/method outputs differ')
        results = perf.summarize(result_rows)
        check(results == summary['results'], 'Recomputed statistical summary differs')
        measured = sum(not r['warmup'] for r in result_rows)
        check(measured == summary['measured_trials'] == 320 and len(result_rows)-measured == summary['warmup_trials'] == 64, 'Warmup accounting differs')
        rss_values = sorted({r[k] for r in result_rows if not r['warmup']
                             for k in ('online_peak_rss_bytes','offline_peak_rss_bytes') if r[k]})
        env = doc('environment.json')
        check(env['selected_cpu'] in env['allowed_cpus'] and env['filesystem_sync'] is False, 'Environment contract differs')
        # Public aggregate excludes commands, runtime addresses and private paths.
        phase_results = []
        for result in results:
            for group in methods:
                rows = [r for r in offline_phases if r['input']==result['input'] and r['indexed']==result['indexed'] and r['group']==group]
                keys = ('parse_validate_wall_seconds','infer_wall_seconds','output_wall_seconds','total_wall_seconds')
                phase_results.append(dict(input=result['input'],indexed=result['indexed'],group=group,
                    phases={k:perf.statistics_of([r[k] for r in rows]) for k in keys}))
        return dict(archive_sha256=digest(Path(archive).read_bytes()),experiment_commit=EXPECTED_COMMIT,
            binary_sha256=plan['binary_sha256'],source_revision=runner.REVISION,libdft_revision=revision,
            measured_online_processes=measured,warmup_online_processes=len(trials)-measured,offline_processes=sum(c['processes'] for c in counts.values()),
            distinct_inputs=4,output_modes=2,distinct_input_code_positions=510,blocks=10,warmups=2,
            source_and_tool_identity_verified=True,unchanged_upstream_source_files=len(manifest),
            elf_plan_rebuilt=True,raw_inference_recomputed=True,pixels_and_source_results_verified=True,
            schedule_and_every_timing_row_checked=True,statistics_recomputed=True,record_counts=counts,query_totals=totals,
            memory_measurement_qualified=False,formal_nonzero_peak_rss_values_bytes=rss_values,
            memory_issue='wait4/RUSAGE_SELF high-water marks include pre-exec fork memory; identical recorded values do not establish equal target memory',
            results=results,offline_phases=phase_results,
            environment={k:env[k] for k in ('platform','cpuinfo','selected_cpu','governor')},
            initialization_seconds={k:summary[k] for k in ('fixture_prepare_seconds','static_plan_seconds','tool_build_seconds')},
            startup_included=True,steady_state=False,bpf_executed=False,executed_uploaded_code=False,
            source_semantics_qualified=False,reported_adapter_errors=0,reported_context_changes=0,
            limitations=['Common full boundary snapshots, not minimal libdft overhead','Pin startup/JIT not isolated',
                         'Host-reported clock/wait4 observations, not remote attestation','Buffered writes without fsync',
                         'Fixed-metadata GIF source semantics differ from ordinary byte taint'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--libdft',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = verify(args.archive,args.libdft)
    runner.save(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','offline_phases')},indent=2))


if __name__ == '__main__':
    main()
