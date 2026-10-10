#!/usr/bin/env python3
"""Launch-inclusive ngiflib costs: native, nullpin, boundary replay, libdft64.

Original converter and four existing normal images. This is NOT a steady-state
benchmark. Two methods pay the same buffered boundary-snapshot protocol; libdft
propagation remains upstream. Both methods pay offline decoding/result output.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
import traceback

import compare_host as base
import perf_records

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GROUPS = ('native', 'nullpin', 'boundary_replay', 'libdft64')
check, save = base.check, base.save


def environment(cpu, allowed):
    result = dict(platform=platform.platform(), python=sys.version, allowed_cpus=allowed, selected_cpu=cpu,
                  loadavg_start=list(os.getloadavg()), filesystem_sync=False,
                  page_cache='warm cache; no privileged cache dropping')
    for name, path in [('cpuinfo', '/proc/cpuinfo'), ('memory', '/proc/meminfo'),
                       ('governor', f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor')]:
        try:
            lines = Path(path).read_text().splitlines()
            if name == 'cpuinfo':
                lines = sorted(set(x for x in lines if x.startswith(('model name', 'vendor_id'))))
            if name == 'memory':
                lines = [x for x in lines if x.startswith(('MemTotal:', 'MemAvailable:'))]
            result[name] = '\n'.join(lines)
        except OSError as exc:
            result[name] = dict(unavailable=type(exc).__name__)
    return result


def measured(argv, folder, timeout):
    """Linux wait4: exact child CPU/HWM, no polling quantization of short runs."""
    argv = list(map(str, argv))
    with (folder / 'stdout.txt').open('wb') as stdout, (folder / 'stderr.txt').open('wb') as stderr:
        started = time.perf_counter_ns()
        proc = subprocess.Popen(argv, cwd=folder, stdout=stdout, stderr=stderr, start_new_session=True)
        expired = []
        def kill():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                expired.append(True)
            except ProcessLookupError:
                pass
        timer = threading.Timer(timeout, kill)
        timer.daemon = True
        timer.start()
        try:
            _, status, usage = os.wait4(proc.pid, 0)
            wall = (time.perf_counter_ns() - started) / 1e9
            proc.returncode = os.waitstatus_to_exitcode(status)
        finally:
            timer.cancel()
    result = dict(command=argv, wall_seconds=wall, user_seconds=usage.ru_utime,
                  system_seconds=usage.ru_stime, cpu_seconds=usage.ru_utime + usage.ru_stime,
                  peak_rss_bytes=usage.ru_maxrss * 1024, returncode=proc.returncode,
                  timed_out=bool(expired), scope='whole child process including launch and exit')
    save(folder / 'measurement.json', result)
    check(not expired and proc.returncode == 0, 'Measured process failed; inspect ' + str(folder))
    return result


def worker(args):
    """No oracle here. Plan/input loading, parsing, inference and output timed."""
    start, cpu = time.perf_counter(), time.process_time()
    plan = json.loads(args.plan.read_text())
    data = args.input.read_bytes()
    trace, external, detail = perf_records.read_log(args.raw, plan, data, args.method == 'libdft64')
    parsed, parsed_cpu = time.perf_counter(), time.process_time()
    if args.method == 'boundary_replay':
        result = base.query.infer(plan, trace, data)
    else:
        result = dict(queries=external, original_propagation=True, semantics_qualified=False)
    inferred, inferred_cpu = time.perf_counter(), time.process_time()
    save(args.output / 'inference.json', result)
    finished, finished_cpu = time.perf_counter(), time.process_time()
    save(args.output / 'phases.json', dict(
        parse_validate_wall_seconds=parsed-start, parse_validate_cpu_seconds=parsed_cpu-cpu,
        infer_wall_seconds=inferred-parsed, infer_cpu_seconds=inferred_cpu-parsed_cpu,
        output_wall_seconds=finished-inferred, output_cpu_seconds=finished_cpu-inferred_cpu,
        total_wall_seconds=finished-start, total_cpu_seconds=finished_cpu-cpu,
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        raw_records=detail['raw_records'], source_fills=detail['source_fills'],
        instruction_diagnostics=False))


def schedule(warmups, blocks, seed):
    rng = random.Random(seed)
    result = []
    for block in range(-warmups, blocks):
        cases = [(n, indexed) for n in base.CASES for indexed in (False, True)]
        rng.shuffle(cases)
        for name, indexed in cases:
            groups = list(GROUPS)
            rng.shuffle(groups)
            result.append(dict(block=block, warmup=block < 0, input=name, indexed=indexed, groups=groups))
    return result


def statistics_of(values):
    return dict(n=len(values), median=statistics.median(values), minimum=min(values), maximum=max(values),
                p90=sorted(values)[math.ceil(.9*len(values))-1])


def summarize(trials):
    output = []
    for name in base.CASES:
        for indexed in (False, True):
            rows = [r for r in trials if not r['warmup'] and r['input'] == name and r['indexed'] == indexed]
            groups = {}
            for group in GROUPS:
                samples = [r for r in rows if r['group'] == group]
                check(samples, 'Missing measured samples')
                metrics = {k: statistics_of([r[k] for r in samples]) for k in
                           ('online_wall_seconds', 'online_cpu_seconds', 'online_peak_rss_bytes',
                            'offline_wall_seconds', 'offline_cpu_seconds', 'offline_peak_rss_bytes',
                            'complete_wall_seconds', 'complete_cpu_seconds', 'complete_peak_rss_bytes', 'raw_bytes')}
                groups[group] = metrics
            paired = []
            for block in sorted({r['block'] for r in rows}):
                by = {r['group']: r for r in rows if r['block'] == block}
                check(set(by) == set(GROUPS), 'Incomplete paired block')
                replay, lib = by['boundary_replay'], by['libdft64']
                paired.append(dict(block=block,
                    online_wall_reduction_percent=100*(1-replay['online_wall_seconds']/lib['online_wall_seconds']),
                    complete_wall_reduction_percent=100*(1-replay['complete_wall_seconds']/lib['complete_wall_seconds']),
                    complete_cpu_reduction_percent=100*(1-replay['complete_cpu_seconds']/lib['complete_cpu_seconds'])))
            output.append(dict(input=name, indexed=indexed, groups=groups, paired_raw=paired,
                paired_replay_vs_libdft={k: statistics_of([r[k] for r in paired]) for k in paired[0] if k != 'block'}))
            output[-1]['paired_online_wall_slowdown_vs_native'] = {
                group: statistics_of([next(r for r in rows if r['block']==block and r['group']==group)['online_wall_seconds'] /
                                      next(r for r in rows if r['block']==block and r['group']=='native')['online_wall_seconds']
                                      for block in sorted({r['block'] for r in rows})])
                for group in GROUPS if group != 'native'}
    return output


def prepare(args, out, report):
    started = time.perf_counter()
    binary, source, inputs = base.fixture(args, out)
    from verify_host import INPUT_HASHES
    check(all(base.shared.sha(inputs/name/'normal.gif') == expected for name, expected in INPUT_HASHES.items()),
          'Inputs differ from the verified correctness workload')
    report['fixture_prepare_seconds'] = time.perf_counter()-started
    started = time.perf_counter()
    plan = base.query.plan(binary, source, out)
    save(out/'plan.json', plan)
    report['static_plan_seconds'] = time.perf_counter()-started
    pin, lib = base.shared.dependencies(args, out)
    report['semantics'] = base.audit(lib, out)
    # Reuse only ABI constant generation, then use the separate cost adapter.
    base.expand_adapter(plan, out)
    fields = json.loads((out/'adapter-layout.json').read_text())
    body = (HERE/'libdft_ngif_perf.cpp').read_text()
    marker = '// ABI_CONTRACT -- replaced by header offsets verified against target ELF DWARF.'
    check(body.count(marker) == 1, 'ABI marker changed')
    adapter = out/'libdft_ngif_perf.cpp'
    adapter.write_text(body.replace(marker, '\n'.join(f'static const unsigned {k}={v};' for k,v in fields.items())))
    started = time.perf_counter()
    built = base.shared.build_tools(pin, lib, out, adapter, 'libdft_ngif_perf')
    build_identity = json.loads((out/'tool-build.json').read_text())
    build_identity['adapter_changes'] = 'Buffered boundary observations only; no per-instruction analysis callback'
    save(out/'tool-build.json', build_identity)
    report['tool_build_seconds'] = time.perf_counter()-started
    manifest = {}
    for path in sorted((lib/'src').rglob('*')):
        if path.is_file() and path.suffix in ('.c', '.cpp', '.h'):
            rel = path.relative_to(lib)
            check(base.shared.sha(path) == base.shared.sha(out/'libdft-build'/rel), 'Upstream source changed')
            manifest[str(rel)] = base.shared.sha(path)
    save(out/'upstream-source-manifest.json', manifest)
    report.update(compiled=True, binary_sha256=plan['binary_sha256'], unchanged_upstream_files=len(manifest))
    return binary, inputs, pin, built


def execute(args, out, report):
    binary, inputs, pin, built = prepare(args, out, report)
    if args.mode == 'build-tools':
        report['stage'] = 'compiled_not_executed'
        return
    report['stage'] = 'pin_startup'
    base.shared.command([pin/'pin', '-t', built['nullpin'], '--', '/bin/true'], out, timeout=args.timeout)
    report['pin_startup_passed'] = True
    # Inherited by all processes, including offline workers; no frequency changes.
    allowed = sorted(os.sched_getaffinity(0))
    cpu = args.cpu if args.cpu is not None else allowed[0]
    check(cpu in allowed, 'Requested CPU outside allowed affinity')
    os.sched_setaffinity(0, {cpu})
    save(out/'environment.json', environment(cpu, allowed))
    order = schedule(args.warmups, args.blocks, args.seed)
    save(out/'schedule.json', order)
    golden = json.loads((HERE/'host-validation-20261010.json').read_text())
    trials = []
    for index, entry in enumerate(order):
        print(f"Case {index+1}/{len(order)}: block={entry['block']} {entry['input']} indexed={entry['indexed']}", flush=True)
        name, indexed = entry['input'], entry['indexed']
        path = inputs/name/'normal.gif'
        reference, _ = base.decode(base.parse(path.read_bytes()))
        expected = {r['sequence']: r['source_file_offsets'] for r in reference}
        expected_lib = dict(expected)
        for difference in golden['libdft_format_differences']:
            if difference['input'] == name and difference['indexed'] == indexed:
                expected_lib[difference['sequence']] = difference['observed']
        with base.Image.open(path) as image:
            pixels = image.size, image.convert('RGB').tobytes()
        outputs = []
        for group in entry['groups']:
            folder = out / f"trial-{index:04d}-{group}"
            folder.mkdir()
            raw = folder/'raw.jsonl'
            prefix = [] if group == 'native' else [pin/'pin', '-t', built['nullpin']]
            if group in ('boundary_replay', 'libdft64'):
                prefix = [pin/'pin', '-t', built['libdft_ngif_perf'], '-enable_taint', str(int(group=='libdft64')),
                          '-input_file', path, '-origin_log', raw]
            if prefix:
                prefix.append('--')
            online = measured([*prefix, binary, *(['--indexed'] if indexed else []), '--outbase', 'image', path], folder, args.timeout)
            # Validation and independent truth run outside measured processes.
            check(base.tga_rgb(folder/'image_out01.tga') == pixels, 'Business pixels changed')
            outputs.append((base.shared.sha(folder/'image_out01.tga'), (folder/'stdout.txt').read_bytes()))
            offline = dict(wall_seconds=0, cpu_seconds=0, peak_rss_bytes=0)
            evaluation = None
            if group in ('boundary_replay', 'libdft64'):
                work = folder/'offline'
                work.mkdir()
                offline = measured([sys.executable, HERE/'performance.py', '_worker', '--plan', out/'plan.json',
                    '--input', path, '--raw', raw, '--method', group, '--output', work], work, args.timeout)
                observed = json.loads((work/'inference.json').read_text())['queries']
                evaluation = base.compare_reference(observed, reference)
                check(evaluation['value_matches'] == len(reference), 'Value differs from format reference')
                required = expected if group == 'boundary_replay' else expected_lib
                check(all(r['source_file_offsets'] == required[r['sequence']] for r in observed),
                      'Cost profile changed source results from verified correctness profile')
                save(folder/'evaluation.json', evaluation)
            row = dict(block=entry['block'], warmup=entry['warmup'], input=name, indexed=indexed, group=group,
                loadavg_after_validation=list(os.getloadavg()),
                directory=folder.name, online_wall_seconds=online['wall_seconds'], online_cpu_seconds=online['cpu_seconds'],
                online_peak_rss_bytes=online['peak_rss_bytes'], offline_wall_seconds=offline['wall_seconds'],
                offline_cpu_seconds=offline['cpu_seconds'], offline_peak_rss_bytes=offline['peak_rss_bytes'],
                complete_wall_seconds=online['wall_seconds']+offline['wall_seconds'],
                complete_cpu_seconds=online['cpu_seconds']+offline['cpu_seconds'],
                complete_peak_rss_bytes=max(online['peak_rss_bytes'], offline['peak_rss_bytes']),
                raw_bytes=raw.stat().st_size if raw.exists() else 0, sources_checked=evaluation is not None, pixels_match=True)
            trials.append(row)
            with (out/'trials.jsonl').open('a') as stream:
                stream.write(json.dumps(row)+'\n')
        check(len(set(outputs)) == 1, 'Group stdout or TGA differs')
    report.update(stage='performance_complete', all_results_checked=True, measured_trials=sum(not r['warmup'] for r in trials),
                  warmup_trials=sum(r['warmup'] for r in trials), results=summarize(trials))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'build-tools', '_worker'))
    for name in ('source', 'validation', 'pin-root', 'libdft', 'output', 'plan', 'input', 'raw'):
        parser.add_argument('--'+name, type=Path)
    parser.add_argument('--method', choices=('boundary_replay', 'libdft64'))
    parser.add_argument('--blocks', type=int, default=10)
    parser.add_argument('--warmups', type=int, default=2)
    parser.add_argument('--seed', type=int, default=20261010)
    parser.add_argument('--cpu', type=int)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    if args.mode == '_worker':
        worker(args)
        return
    check(args.blocks >= 3 and args.warmups >= 1 and args.timeout > 0, 'Use >=3 blocks, >=1 warmup and positive timeout')
    out = args.output or ROOT/'artifacts'/('ngiflib-performance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    out.mkdir(parents=True, exist_ok=False)
    report = dict(stage='prepare', compiled=False, pin_startup_passed=False, all_results_checked=False,
        profile='boundary-cost-v1', blocks=args.blocks, warmups=args.warmups, seed=args.seed,
        bpf_executed=False, steady_state=False, startup_included=True, fsync_included=False,
        snapshot_policy='Same full buffered boundary snapshots in both methods; not a minimal libdft-only adapter',
        offline_policy='Fresh Python process: imports, read/validate, infer/extract, serialize; oracle scoring excluded',
        semantics_qualified=False)
    # Archive all local implementation dependencies, never only summary numbers.
    paths = list(HERE.glob('*.py')) + list(HERE.glob('*.cpp')) + [HERE/'host-validation-20261010.json']
    paths += [ROOT/'scripts'/n for n in ('c_bit_machine.py','interproc_model.py','hybrid_model.py','language_adapters.py')]
    paths += [HERE.parent/'checkout-payment-path/external_compare.py']
    for path in paths:
        dest = out/'adapter-sources'/path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    save(out/'adapter-identity.json', dict(repository_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         files={str(p.relative_to(ROOT)):base.shared.sha(p) for p in paths}))
    try:
        execute(args, out, report)
    except Exception as exc:
        report['failure'] = str(exc)
        (out/'failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        save(out/'summary.json', report)
        print('Return this result archive: '+shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name),flush=True)


if __name__ == '__main__':
    main()
