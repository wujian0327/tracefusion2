#!/usr/bin/env python3
"""Fixed serial payment workload: paired steady-state measurements, not new scenarios."""
import argparse
from collections import Counter
import ctypes as ct
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import statistics
import struct
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / 'scripts'), str(HERE.parent / 'checkout-item-identity')]
import payment_adapter as adapter
from hybrid_model import require

POLICIES = ('native', 'boundaries', 'all_branches', 'selected')
SAMPLE_HEADER = struct.Struct('<II')  # CPU number, original perf callback size
DEFAULTS = dict(blocks=10, warmups=20, requests=100, seed=20261009)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def percentile(values, q):
    require(values and 0 < q <= 1, 'Invalid percentile input')
    return sorted(values)[math.ceil(len(values) * q) - 1]


def schedule(blocks, seed):
    rng = random.Random(seed)
    rows = []
    for block in range(blocks):
        order = list(POLICIES)
        rng.shuffle(order)
        rows.append(dict(block=block, policies=order))
    return rows


def usage():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return dict(user_seconds=r.ru_utime, system_seconds=r.ru_stime)


def delta(a, b):
    return {k: b[k] - a[k] for k in a}


def rss(pid):
    # Instantaneous process RSS, not lifetime VmHWM (which includes compilation).
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmRSS:'):
            return int(line.split()[1]) * 1024
    raise ValueError(f'VmRSS unavailable for process {pid}')


def stats_snapshot(bpf, count, lost):
    if bpf is None:
        return dict(submitted=0, samples=0, lost=0, submit_errors=0, read_errors=0,
                    namespace_errors=0, probe_hits=0, pid_rejections=0, namespace_differences=0)
    names = ('submitted', 'submit_errors', 'read_errors', 'probe_hits', 'namespace_errors',
             'pid_rejections', 'namespace_differences')
    result = {key: int(bpf['stats'][ct.c_int(i)].value) for i, key in enumerate(names)}
    result.update(samples=count, lost=lost)
    return result


def check_capture(stats):
    require(stats['submitted'] == stats['samples'], 'Submitted/sample count mismatch')
    require(not any(stats[k] for k in ('lost', 'submit_errors', 'read_errors', 'namespace_errors')),
            'Incomplete/error capture')


def wait_marker(proc, marker, poll, timeout, samples=None):
    deadline = time.monotonic() + timeout
    while not marker.exists():
        require(proc.poll() is None, f'Target exited before {marker.name}; inspect target.stderr')
        require(time.monotonic() < deadline, f'Timeout waiting for {marker.name}')
        poll(10)
        if samples is not None:
            samples()
    require(proc.poll() is None, 'Target did not remain at its phase gate')


def collect_trial(binary, plan, folder, policy, warmups, requests, timeout):
    """One ready process and (if enabled) one BPF attachment for both phases.

    Callbacks spool original perf samples; decode/inference/JSON export run later.
    Collector CPU includes polling, raw spooling and RSS sampling, not inference.
    """
    folder.mkdir()
    env = dict(os.environ, TRACEFUSION_PERFORMANCE_OUT=str(folder),
               TRACEFUSION_PERFORMANCE_WARMUPS=str(warmups),
               TRACEFUSION_PERFORMANCE_REQUESTS=str(requests))
    proc = bpf = None
    errors = []
    metadata = dict(policy=policy, binary_sha256=plan['binary_sha256'],
                    kernel=platform.release(), python=sys.version, collector_pid=os.getpid(),
                    cpu_affinity=sorted(os.sched_getaffinity(0)), loadavg_start=list(os.getloadavg()))
    count = 0
    lost = 0
    sizes = Counter()
    warm_stats = final_stats = None
    samples = []
    rss_unavailable = {}
    stdout = (folder / 'target.stdout').open('wb')
    stderr = (folder / 'target.stderr').open('wb')
    raw = (folder / 'samples.bin').open('wb')
    try:
        require(hashlib.sha256(binary.read_bytes()).hexdigest() == plan['binary_sha256'], 'Binary changed')
        launched = time.monotonic_ns()
        proc = subprocess.Popen([str(binary)], env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
        metadata.update(target_pid=proc.pid, launch_ns=time.monotonic_ns() - launched)
        if policy != 'native':
            import bcc
            metadata['bcc_version'] = getattr(bcc, '__version__', 'unknown')
            ns = Path(f'/proc/{proc.pid}/ns/pid').stat()
            metadata['namespace'] = dict(dev=ns.st_dev, ino=ns.st_ino)
            code = adapter.source(plan, proc.pid, ns)
            (folder / 'collector.c').write_text(code)
            started = time.monotonic_ns()
            bpf = bcc.BPF(text=code)
            metadata['bpf_compile_ns'] = time.monotonic_ns() - started
            started = time.monotonic_ns()
            probes = adapter.physical_probes(plan)
            for probe in probes:
                bpf.attach_uprobe(name=str(binary), addr=probe['address'], fn_name=probe['name'], pid=-1)
            metadata.update(bpf_attach_ns=time.monotonic_ns() - started, physical_probes=len(probes))

            def callback(cpu, data, size):
                nonlocal count
                raw.write(SAMPLE_HEADER.pack(cpu, size))
                raw.write(ct.string_at(data, size))
                count += 1
                sizes[str(size)] += 1

            def lost_callback(cpu, n):
                nonlocal lost
                lost += n

            bpf['events'].open_perf_buffer(callback, page_cnt=64, lost_cb=lost_callback)
        else:
            metadata.update(bpf_compile_ns=0, bpf_attach_ns=0, physical_probes=0)

        def poll(ms):
            if bpf is None:
                time.sleep(ms / 1000)
            else:
                bpf.perf_buffer_poll(timeout=ms)

        def gate(b):
            proc.stdin.write(b)
            proc.stdin.flush()

        def sample_memory():
            row = dict(monotonic_ns=time.monotonic_ns())
            for role, pid in (('target', proc.pid), ('collector', os.getpid())):
                try:
                    row[role + '_rss_bytes'] = rss(pid)
                except (OSError, ValueError) as exc:
                    row[role + '_rss_bytes'] = None
                    rss_unavailable[role] = repr(exc)
            samples.append(row)

        gate(b'x')
        wait_marker(proc, folder / 'warmup.done', poll, timeout)
        for _ in range(5):
            poll(20)
        warm_stats = stats_snapshot(bpf, count, lost)
        check_capture(warm_stats)
        warm_sizes = Counter(sizes)
        warm_samples = count
        before = usage()
        started = time.monotonic_ns()
        sample_memory()
        gate(b'm')
        wait_marker(proc, folder / 'measure.done', poll, timeout, sample_memory)
        measured_end = time.monotonic_ns()
        after = usage()
        # Target remains alive at 'q'; infer from complete drained samples, not
        # an arbitrary final callback count observed at the completion marker.
        for _ in range(5):
            poll(20)
        raw.flush()
        final_stats = stats_snapshot(bpf, count, lost)
        check_capture(final_stats)
        metadata.update(collector_window_wall_ns=measured_end - started,
                        collector_cpu=delta(before, after),
                        final_drain_wall_ns=time.monotonic_ns() - measured_end,
                        final_drain_cpu=delta(after, usage()),
                        warmup_stats=warm_stats, total_stats=final_stats,
                        measured_stats=delta(warm_stats, final_stats),
                        warmup_samples=warm_samples, total_samples=count,
                        measured_samples=count - warm_samples,
                        sample_sizes=dict(sizes), measured_sample_sizes=dict(sizes - warm_sizes),
                        measured_perf_bytes=sum(int(k) * n for k, n in (sizes - warm_sizes).items()),
                        total_perf_bytes=sum(int(k) * n for k, n in sizes.items()))
        require(warm_stats['samples'] > 0 or policy == 'native', 'No warmup events')
        require(final_stats['samples'] > warm_stats['samples'] or policy == 'native', 'No measured events')
        gate(b'q')
        proc.stdin.close()
        proc.wait(timeout=30)
        require(proc.returncode == 0, 'Target failed; inspect target.stderr')
    except Exception as exc:
        errors.append(repr(exc))
        raise
    finally:
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            metadata['returncode'] = proc.returncode
        if bpf:
            try:
                bpf.cleanup()
            except Exception as exc:
                errors.append('cleanup: ' + repr(exc))
        raw.close(); stdout.close(); stderr.close()
        metadata.update(capture_errors=errors, rss_samples=samples, rss_unavailable=rss_unavailable,
                        target_sampled_peak_rss_bytes=None if 'target' in rss_unavailable else max((s['target_rss_bytes'] for s in samples), default=None),
                        collector_sampled_peak_rss_bytes=None if 'collector' in rss_unavailable else max((s['collector_rss_bytes'] for s in samples), default=None))
        save(folder / 'capture.json', metadata)
    require(not errors, 'Collector cleanup failed')
    return metadata


def decode_samples(path, plan):
    sites = {s['id']: s for s in plan['sites']}
    events = []
    sizes = Counter()
    with path.open('rb') as f:
        while header := f.read(SAMPLE_HEADER.size):
            require(len(header) == SAMPLE_HEADER.size, 'Truncated raw sample header')
            cpu, size = SAMPLE_HEADER.unpack(header)
            require(size in (ct.sizeof(adapter.Raw), ((ct.sizeof(adapter.Raw)+11)//8)*8-4), 'Invalid raw sample size')
            data = f.read(size)
            require(len(data) == size, 'Truncated raw perf sample')
            event = adapter.decode_record(ct.create_string_buffer(data), size, sites)
            event.update(cpu=cpu, sequence=len(events))
            events.append(event)
            sizes[str(size)] += 1
    return events, sizes


def split_invocations(events, expected):
    """Serial source-to-end streams; each invocation gets a fresh Replay heap.

    A missing completion/start or cross-G event cannot be repaired by ordinal
    matching. Ordinals bind the protocol's serial calls, not equal output values.
    """
    ordered = sorted(events, key=lambda e: e['timestamp'])
    require(all(a['timestamp'] < b['timestamp'] for a, b in zip(ordered, ordered[1:])), 'Ambiguous event order')
    groups = []
    current = []
    identity = None
    for e in ordered:
        start = e['kind'] == 'source' and e['tag'] == 0
        if start:
            require(not current, 'New invocation before previous completion')
            identity = (e['pid_tid'] >> 32, e['g'])
            require(identity[1], 'Missing G identity')
        require(identity is not None, 'Event outside an invocation')
        require((e['pid_tid'] >> 32, e['g']) == identity, 'Cross-process/G invocation event')
        current.append(e)
        if e['kind'] == 'end':
            groups.append(current)
            current = []
            identity = None
    require(not current and len(groups) == expected, 'Missing/extra invocation evidence')
    return groups


def replay_trial(plan, folder, warmups, requests):
    capture = json.loads((folder / 'capture.json').read_text())
    require(not capture['capture_errors'] and capture['returncode'] == 0, 'Failed capture')
    require(capture['binary_sha256'] == plan['binary_sha256'], 'Capture/binary mismatch')
    check_capture(capture['total_stats'])
    started = time.perf_counter_ns()
    events, sizes = decode_samples(folder / 'samples.bin', plan)
    decode_ns = time.perf_counter_ns() - started
    require(len(events) == capture['total_samples'] and dict(sizes) == capture['sample_sizes'], 'Raw sample counts differ')
    started = time.perf_counter_ns()
    groups = split_invocations(events, warmups + requests)
    require(sum(map(len, groups[:warmups])) == capture['warmup_samples'], 'Warmup/measurement cut mismatch')
    split_ns = time.perf_counter_ns() - started
    results = []
    inference_times = []
    for index, group in enumerate(groups):
        doc = dict(binary_sha256=plan['binary_sha256'], capture_errors=[], returncode=0, events=group,
                   stats=dict(submitted=len(group), lost=0, read_errors=0, submit_errors=0, namespace_errors=0))
        # Global counters were checked above before forming per-call documents.
        started = time.perf_counter_ns()
        results.append(adapter.infer(plan, doc))
        inference_times.append(time.perf_counter_ns() - started)
    inference_ns = sum(inference_times[warmups:])
    with (folder / 'inference.jsonl').open('w') as f:
        for index, result in enumerate(results):
            f.write(json.dumps(dict(index=index, phase='warmup' if index < warmups else 'measured', result=result)) + '\n')
    # Independent answers are unavailable to the reconstruction up to this point.
    truth = json.loads((folder / 'truth.json').read_text())
    require(truth['warmups'] == warmups and truth['requests'] == requests, 'Driver/trial count mismatch')
    metrics = {k: 0 for k in ('query_fields', 'exact_fields', 'definite_fields', 'wrong_definite_fields', 'tp', 'fp', 'fn')}
    statuses = Counter()
    evaluations = []
    for index, result in enumerate(results):
        row = adapter.evaluate(plan, result, dict(truth, case=f'request-{index}'))
        # Exact-set rate is field-grained even if only one field is wrong. The
        # whole-call passed gate still rejects any value/source discrepancy.
        if result['status'] == 'exact_data_origins':
            row['exact_fields'] = sum(set(result['origins'].get(field, [])) == set(truth['origins'][field])
                                      for field in ('Units', 'Nanos'))
        evaluations.append(dict(index=index, phase='warmup' if index < warmups else 'measured', **row))
        if index >= warmups:
            statuses[result['status']] += 1
            for key in metrics:
                metrics[key] += row[key]
    metrics.update(status_counts=dict(statuses), exact_set_rate=metrics['exact_fields'] / (2 * requests),
                   definite_coverage=metrics['definite_fields'] / (2 * requests),
                   relation_precision=metrics['tp'] / (metrics['tp'] + metrics['fp']) if metrics['tp'] + metrics['fp'] else None,
                   relation_recall=metrics['tp'] / (metrics['tp'] + metrics['fn']) if metrics['tp'] + metrics['fn'] else None)
    all_passed = all(row['passed'] for row in evaluations)
    save(folder / 'evaluation.json', dict(all_passed=all_passed, warmup_requests=warmups, measured_requests=requests,
                                         metrics=metrics, cases=evaluations, decode_ns=decode_ns,
                                         split_ns=split_ns, inference_ns=inference_ns, inference_requests=requests,
                                         warmup_inference_ns=sum(inference_times[:warmups]), per_call_inference_ns=inference_times))
    require(all_passed, 'Origin/output mismatch; failed queries retained in evaluation.json and inference.jsonl')
    return dict(metrics=metrics, decode_ns=decode_ns, inference_ns=inference_ns,
                inference_requests=requests)


def summarize(rows, blocks):
    require(len(rows) == blocks * len(POLICIES), 'Incomplete paired blocks')
    grouped = {}
    for row in rows:
        pair = grouped.setdefault(row['block'], {})
        require(row['policy'] in POLICIES and row['policy'] not in pair, 'Duplicate/unknown trial')
        require(row['passed'], 'Failed trial cannot enter performance statistics')
        pair[row['policy']] = row
    require(len(grouped) == blocks and all(set(p) == set(POLICIES) for p in grouped.values()), 'Incomplete paired block')
    paired = []
    for block, group in sorted(grouped.items()):
        native = group['native']
        require(native['p50_ns'] > 0 and native['target_cpu_seconds'] > 0, 'Invalid native denominator')
        for policy in POLICIES[1:]:
            row = group[policy]
            paired.append(dict(block=block, policy=policy, p50_ratio=row['p50_ns'] / native['p50_ns'],
                               p95_ratio=row['p95_ns'] / native['p95_ns'],
                               target_cpu_ratio=row['target_cpu_seconds'] / native['target_cpu_seconds']))
    aggregates = {}
    for policy in POLICIES:
        selected = [r for r in rows if r['policy'] == policy]
        aggregates[policy] = {}
        missing = {}
        for key in ('p50_ns', 'p95_ns', 'target_cpu_seconds', 'collector_cpu_seconds',
                    'target_sampled_peak_rss_bytes', 'collector_sampled_peak_rss_bytes',
                    'measured_events', 'measured_perf_bytes', 'inference_ns'):
            values = [r[key] for r in selected]
            missing[key] = sum(v is None for v in values)
            aggregates[policy][key + '_block_median'] = None if missing[key] else statistics.median(values)
        aggregates[policy]['missing_metric_trials'] = missing
        p = [r for r in paired if r['policy'] == policy]
        if p:
            aggregates[policy].update({key + '_paired_median': statistics.median(r[key] for r in p)
                                       for key in ('p50_ratio', 'p95_ratio', 'target_cpu_ratio')})
    # Direct selected/all comparison within each paired block, never a ratio
    # silently substituted for the median of paired ratios.
    direct = [dict(block=block, p50_ratio=g['selected']['p50_ns']/g['all_branches']['p50_ns'],
                   target_cpu_ratio=g['selected']['target_cpu_seconds']/g['all_branches']['target_cpu_seconds'])
              for block, g in sorted(grouped.items())]
    return dict(aggregates=aggregates, paired_vs_native=paired, selected_vs_all_branches=direct,
                percentile='nearest rank within each measured block; block summaries and paired ratios kept separate')


def trial_row(block, policy, folder, capture, replay, warmups, requests):
    measurement = json.loads((folder / 'measurements.json').read_text())
    require(measurement['requests'] == requests and measurement['warmups'] == warmups, 'Wrong measurement counts')
    latencies = measurement['latency_ns']
    require(len(latencies) == requests and all(n > 0 for n in latencies), 'Missing/nonpositive latency')
    cpu = delta(measurement['cpu_start'], measurement['cpu_end'])
    require(all(n >= 0 for n in cpu.values()), 'Invalid target CPU')
    return dict(block=block, policy=policy, passed=True, folder=folder.name, requests=requests,
                p50_ns=percentile(latencies, .5), p95_ns=percentile(latencies, .95),
                target_wall_ns=measurement['wall_ns'], target_cpu_seconds=sum(cpu.values()) / 1e6,
                collector_cpu_seconds=sum(capture['collector_cpu'].values()),
                collector_window_wall_ns=capture['collector_window_wall_ns'],
                target_sampled_peak_rss_bytes=capture['target_sampled_peak_rss_bytes'],
                collector_sampled_peak_rss_bytes=capture['collector_sampled_peak_rss_bytes'],
                measured_events=capture['measured_samples'], measured_perf_bytes=capture['measured_perf_bytes'],
                **replay)


def execute(args, out):
    require(platform.system() == 'Linux' and platform.machine() in ('x86_64', 'amd64'), 'Requires Linux amd64')
    spec = importlib.util.spec_from_file_location('identity_builder', HERE.parent / 'checkout-item-identity/run.py')
    shared = importlib.util.module_from_spec(spec); spec.loader.exec_module(shared)
    started = time.monotonic_ns()
    binary, plan, main_hash, command = shared.build_target(args, out, HERE / 'performance_test.go', adapter.plan_binary)
    build_and_plan_ns = time.monotonic_ns() - started
    money = (args.checkout or ROOT / 'artifacts/online-boutique-v0.10.4') / 'src/checkoutservice/money/money.go'
    money_hash = hashlib.sha256(money.read_bytes()).hexdigest()
    require(money_hash == 'c7e81c0e8e24cafce6ccf35b9846d76cea114969998355db34d01169687e67f3', 'Original money source differs')
    plan['assumptions'] = [a.replace('One PlaceOrder invocation/process', 'One serial PlaceOrder invocation at a time; fresh replay state per source-return event') for a in plan['assumptions']]
    save(out / 'plan.json', plan)
    plans = {policy: adapter.strategy_plan(plan, policy) for policy in POLICIES[1:]}
    for policy, p in plans.items():
        save(out / ('plan-' + policy + '.json'), p)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    changes = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    protocol = dict(workload=dict(items=8, quantity=2, serial=True, local_peers=True),
                    blocks=args.blocks, warmups=args.warmups, requests=args.requests, seed=args.seed,
                    mode=args.mode, frozen_protocol=args.mode == 'run' and all(getattr(args,k)==v for k,v in DEFAULTS.items()),
                    repository_commit=revision, repository_worktree_status=changes,
                    upstream_commit=shared.COMMIT, main_go_sha256=main_hash, money_go_sha256=money_hash,
                    binary_sha256=plan['binary_sha256'], fixture_sha256=hashlib.sha256((HERE/'performance_test.go').read_bytes()).hexdigest(),
                    build_and_plan_ns=build_and_plan_ns, kernel=platform.release(), machine=platform.machine(),
                    cpu_count=os.cpu_count(), cpu_affinity=sorted(os.sched_getaffinity(0)),
                    common_trace='No additional OTel SDK; same original checkout configuration and binary in every policy',
                    resource_scope='Target CPU: exact Go getrusage window including colocated mocks/common checks. Collector CPU: gate release to measure marker, plus separately reported final drain. RSS: sampled VmRSS, not lifetime peak. Kernel-wide BPF memory/CPU not separately measured.',
                    latency_scope='Monotonic time around each original PlaceOrder call; no build/attach/inference/oracle export',
                    rss_sampling='One /proc sample per perf poll/10ms wait; event wakeups may shorten spacing; retained timestamps permit inspection')
    save(out / 'protocol.json', protocol)
    # Include the tools actually run, including uncommitted/new files. A commit
    # identifier or tracked-only patch alone is insufficient provenance.
    tracked = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    added = ['experiments/checkout-payment-path/'+name for name in
             ('performance.py','performance_test.go','test_performance.py','PERFORMANCE.md')]
    hashes = {}
    for relative in sorted(set(tracked + added) - {''}):
        src = ROOT/relative
        require(src.is_file(), 'Source snapshot missing: '+relative)
        dest = out/'source'/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dest)
        hashes[relative] = hashlib.sha256(src.read_bytes()).hexdigest()
    save(out/'source-sha256.json',hashes)
    (out/'cpuinfo.txt').write_text(Path('/proc/cpuinfo').read_text())
    (out / 'source.patch').write_text(subprocess.check_output(['git','diff','HEAD'],cwd=ROOT,text=True))
    order = schedule(args.blocks, args.seed) if args.mode == 'run' else [dict(block=0, policies=['native'])]
    save(out / 'schedule.json', order)
    rows = []
    for block in order:
        for policy in block['policies']:
            print(f'Block {block["block"]+1}/{len(order)}: {policy}; warmup={args.warmups}, measured={args.requests}', flush=True)
            folder = out / f'block-{block["block"]:02d}-{policy}'
            # Fresh collector process for every policy/block prevents previous
            # inference heaps or BCC compilation objects inflating later RSS.
            command_line = [sys.executable, str(HERE/'performance.py'), '_collect',
                            '--binary', str(binary), '--plan', str(out/('plan.json' if policy=='native' else 'plan-'+policy+'.json')),
                            '--policy', policy, '--output', str(folder), '--warmups', str(args.warmups),
                            '--requests', str(args.requests), '--timeout', str(args.timeout)]
            completed = subprocess.run(command_line, capture_output=True, text=True, timeout=2*args.timeout+600)
            (out/(folder.name+'-collector.stdout')).write_text(completed.stdout)
            (out/(folder.name+'-collector.stderr')).write_text(completed.stderr)
            require(completed.returncode == 0, 'Trial failed: '+str(folder)+'; '+completed.stderr[-2000:])
            capture = json.loads((folder/'capture.json').read_text())
            replay = dict(inference_ns=0, decode_ns=0, metrics=None)
            if policy != 'native':
                replay = replay_trial(plans[policy], folder, args.warmups, args.requests)
            else:
                truth = json.loads((folder / 'truth.json').read_text())
                require(truth['requests'] == args.requests and truth['warmups'] == args.warmups, 'Native count mismatch')
            row = trial_row(block['block'], policy, folder, capture, replay, args.warmups, args.requests)
            rows.append(row)
            with (out / 'trials.jsonl').open('a') as f:
                f.write(json.dumps(row) + '\n')
            print(json.dumps({k:row[k] for k in ('policy','p50_ns','p95_ns','measured_events','target_cpu_seconds')}), flush=True)
    require(hashlib.sha256(money.read_bytes()).hexdigest() == money_hash, 'Business source changed')
    report = dict(all_passed=True, performance_protocol_executed=args.mode == 'run', frozen_protocol=protocol['frozen_protocol'],
                  trials=len(rows), scope=plan['scope'], assumptions=plan['assumptions'],
                  summary=summarize(rows,args.blocks) if args.mode == 'run' else None,
                  note='Native build mode is only workload/lifecycle validation, not comparative performance evidence')
    save(out / 'summary.json', report)


def main():
    if len(sys.argv)>1 and sys.argv[1]=='_collect':
        parser=argparse.ArgumentParser(description='Internal fresh-process trial collector')
        parser.add_argument('--binary',type=Path,required=True)
        parser.add_argument('--plan',type=Path,required=True)
        parser.add_argument('--policy',choices=POLICIES,required=True)
        parser.add_argument('--output',type=Path,required=True)
        parser.add_argument('--warmups',type=int,required=True)
        parser.add_argument('--requests',type=int,required=True)
        parser.add_argument('--timeout',type=float,required=True)
        args=parser.parse_args(sys.argv[2:])
        collect_trial(args.binary,json.loads(args.plan.read_text()),args.output,args.policy,args.warmups,args.requests,args.timeout)
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('build', 'run'))
    parser.add_argument('--checkout', type=Path)
    parser.add_argument('--go', default=os.environ.get('TRACEFUSION_GO') or shutil.which('go'))
    parser.add_argument('--output', type=Path)
    for key, value in DEFAULTS.items():
        parser.add_argument('--' + key, type=int, default=value)
    parser.add_argument('--timeout', type=float, default=600, help='Deadline per warmup/measured phase in seconds')
    args = parser.parse_args()
    require(args.blocks >= 1 and args.warmups >= 1 and args.requests >= 1 and args.timeout > 0, 'Positive counts/deadline required')
    out = (args.output or ROOT/'artifacts'/('checkout-payment-performance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        execute(args, out)
    except Exception:
        (out/'failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        print('Return this result archive: ' + shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name),flush=True)


if __name__ == '__main__':
    main()
