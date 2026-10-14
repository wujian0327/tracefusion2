#!/usr/bin/env python3
"""Audit saved plain/MirrorTaint/TraceFusion pilots without rerunning inference.

These are request/business-record-field calibrations, not version-specific or
end-to-end distributed path accuracy. FlowDist results are deliberately separate.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shlex
import statistics

METHODS = ('newOrder', 'get', 'delete', 'mergeCarts', 'postShipping')
MODES = ('plain', 'mirrortaint', 'tracefusion')


def load(path):
    return json.loads(path.read_text())


def base_options(value):
    return [x for x in shlex.split(value) if not x.startswith((
        '-javaagent:', '-Dtracefusion.', '-Dtaint.', '-Dtf2.mt.', '-Duser.home='))]


def audit(pilot, originals, out):
    if out.exists():
        raise ValueError('Use a new output directory to preserve prior evidence')
    sources, reports, specs, protocols, workloads = {}, {}, [], [], []
    accuracy, costs = [], []

    def pin(path):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()

    for path in originals.values():
        pin(path)
    for mode in MODES:
        run = pilot / mode
        report = load(run / 'evaluation.json')
        execution = load(run / 'result.json')
        protocol = load(run / 'protocol.json')
        spec = load(run / 'compose.lock.json')
        reports[mode] = report
        protocols.append(protocol)
        specs.append(spec)
        cases = execution['cases']
        if execution['status'] != 'business-passed' or execution['frontend_errors']:
            raise ValueError('Business or adapter failure: ' + mode)
        if len(cases) != 151 or len({c['case'] for c in cases}) != 151:
            raise ValueError('Unexpected business denominator: ' + mode)
        if not all(c['business_passed'] for c in cases):
            raise ValueError('Failed business case: ' + mode)
        if Counter(c['phase'] for c in cases) != {'accuracy': 26, 'warmup': 25, 'measurement': 100}:
            raise ValueError('Unexpected phases: ' + mode)
        workloads.append([(c['case'], c['method'], c['phase']) for c in cases])
        for name in ('evaluation.json', 'result.json', 'protocol.json', 'compose.lock.json'):
            pin(run / name)
        for service, original in originals.items():
            app = run / (service + '.jar')
            pin(app)
            if sources[str(app)] != sources[str(original)]:
                raise ValueError('Original application mismatch: ' + mode + '/' + service)
            capture = run / 'cost-events' / service / 'events.jsonl'
            pin(capture)
            events = [json.loads(line) for line in capture.read_text().splitlines() if line.strip()]
            if [e['seq'] for e in events] != list(range(1, len(events) + 1)):
                raise ValueError('Broken cost sequence')
            if any(e['kind'] == 'problem' for e in events):
                raise ValueError('Cost capture failure')
            by_seq = {e['seq']: e for e in events}
            for method in METHODS:
                role = 'orders' if method == 'newOrder' else 'shipping' if method == 'postShipping' else 'carts'
                if role != service:
                    continue
                summary = report['cost'][method]
                samples = summary['samples']
                measured = {c['case']: c for c in cases if c['phase'] == 'measurement' and c['method'] == method}
                if len(samples) != 20 or len({s['case'] for s in samples}) != 20 or {s['case'] for s in samples} != set(measured):
                    raise ValueError('Wrong measurement denominator')
                for sample in samples:
                    event = by_seq[sample['seq']]
                    if event['kind'] != 'exit' or event['parent'] != 0 or event['trace_id'] != measured[sample['case']]['trace_id']:
                        raise ValueError('Wrong invocation join')
                    for key in ('runtime_ns', 'process_allocated_bytes', 'thread_allocated_bytes', 'rss_kb'):
                        if event[key] != sample[key] or event[key] < 0:
                            raise ValueError('Raw sample mismatch')
                row = {'method': method, 'configuration': mode, 'n': len(samples)}
                for label, key, scale in (('controller_ms', 'runtime_ns', 1e6),
                                          ('resident_kB', 'rss_kb', 1),
                                          ('allocated_kB', 'process_allocated_bytes', 1024)):
                    value = statistics.mean(s[key] / scale for s in samples)
                    if not math.isclose(value, summary[label]['mean'], abs_tol=1e-9):
                        raise ValueError('Cost mean mismatch')
                    row[label] = value
                costs.append(row)
        if mode == 'plain':
            continue
        for method in METHODS:
            queries = report['queries'][method]
            counts = Counter(tp=0, fp=0, fn=0, exact=0, unknown=0)
            for query in queries:
                expected = {tuple(c) for c in query['expected']}
                found = {tuple(c) for c in query['actual']}
                counts['tp'] += len(expected & found)
                counts['fp'] += len(found - expected)
                counts['fn'] += len(expected - found)
                exact = expected == found and not query['unknown']
                if bool(query['exact']) != exact:
                    raise ValueError('Incorrect exact flag')
                counts['exact'] += exact
                counts['unknown'] += bool(query['unknown'])
            if any(counts[k] != report['accuracy'][method][k] for k in counts):
                raise ValueError('Incorrect saved scores')
            tp, fp, fn = (counts[k] for k in ('tp', 'fp', 'fn'))
            accuracy.append({'method': method, 'configuration': mode, 'queries': len(queries),
                             **dict(counts), 'precision': tp / (tp + fp) if tp + fp else None,
                             'recall': tp / (tp + fn) if tp + fn else None,
                             'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                             'exact_rate': counts['exact'] / len(queries)})
        no_target = report['no_target']
        if len(no_target) != 2 or sum(q['checks'] for q in no_target) != 8 or not all(q['passed'] for q in no_target) or not report['all_no_target_passed']:
            raise ValueError('No-target calibration failed')
    if any(p != protocols[0] for p in protocols) or any(w != workloads[0] for w in workloads):
        raise ValueError('Incompatible protocol or workload')
    images = [{k: v['image'] for k, v in spec['services'].items()} for spec in specs]
    if any(i != images[0] for i in images):
        raise ValueError('Different application images')
    for service in originals:
        options = [base_options(s['services'][service]['environment']['JAVA_OPTS']) for s in specs]
        if any(o != options[0] for o in options):
            raise ValueError('Different base JVM options')
    for row in costs:
        plain = next(c for c in costs if c['method'] == row['method'] and c['configuration'] == 'plain')
        row['runtime_overhead_percent'] = 100 * (row['controller_ms'] / plain['controller_ms'] - 1)
    for method in METHODS:
        left, right = [next(a for a in accuracy if a['method'] == method and a['configuration'] == mode)
                       for mode in MODES[1:]]
        if left['queries'] != right['queries']:
            raise ValueError('Different query denominator')
    report = {
        'kind': 'audited-dynamic-baseline-calibration',
        'grain': 'request/business-record/field; repeated reads or versions may be collapsed',
        'cross_service_path_qualified': False, 'version_specific_qualified': False,
        'accuracy_eligible': False, 'performance_eligible': False,
        'business_per_configuration': 151, 'business_total': 453,
        'raw_cost_samples_checked': 300, 'protocol': protocols[0],
        'accuracy': accuracy, 'costs': costs,
        'offline': {mode: {k: reports[mode].get(k) for k in (
            'offline_evaluation_and_reconstruction_ms', 'offline_process_peak_rss_kB', 'offline_process_scope')}
                    for mode in MODES[1:]},
        'compatibility': [
            {'configuration': mode, 'business_passed': 151, 'status': 'calibration-complete',
             'no_target_checks_passed': 8 if mode != 'plain' else None} for mode in MODES],
        'limitations': [
            'MirrorTaint includes disclosed field-boundary, integration, stream, thread and logging adapters.',
            'One deployment per configuration in fixed order; no formal performance ranking.',
            'Controller time includes online tracing but excludes startup, static analysis, shutdown and offline reconstruction.',
            'Memory is whole-service JVM RSS in KiB; allocation is a separate per-call delta in KiB.',
            'No-target cases are separate from field relation accuracy; absence is not an observed empty source answer.',
            'Independent fixtures define expected answers, but this exporter audits saved normalized claims rather than rerunning engines.',
            'Unknown queries fail exact matching; version-specific qualification and cross-JVM transport remain separate tasks.'],
        'source_sha256': sources}
    out.mkdir(parents=True)
    (out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    for name, rows in (('field-calibration.csv', accuracy), ('online-costs.csv', costs)):
        with (out / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = ['# Sock Shop dynamic baseline calibration', '',
             'Request/business-record/field calibration; not version-specific or cross-service path accuracy.', '',
             '| Method | Configuration | Queries | TP/FP/FN | P/R/F1 | Exact | Runtime ms | JVM RSS KiB |',
             '| --- | --- | ---: | --- | --- | --- | ---: | ---: |']
    for method in METHODS:
        for mode in MODES[1:]:
            a = next(a for a in accuracy if a['method'] == method and a['configuration'] == mode)
            c = next(c for c in costs if c['method'] == method and c['configuration'] == mode)
            metrics = '/'.join(f'{a[k]:.1%}' if a[k] is not None else 'N/A' for k in ('precision', 'recall', 'f1'))
            lines.append(f"| {method} | {mode} | {a['queries']} | {a['tp']}/{a['fp']}/{a['fn']} | {metrics} | {a['exact']}/{a['queries']} | {c['controller_ms']:.3f} | {c['resident_kB']:.1f} |")
    lines += ['', 'Limits:', *['- ' + s for s in report['limitations']], '']
    (out / 'comparison.md').write_text('\n'.join(lines))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--orders', type=Path, default=Path('artifacts/sockshop-orders-original-20261012/app.jar'))
    for role in ('carts', 'shipping'):
        parser.add_argument('--' + role, type=Path, default=Path('artifacts/sockshop-five-methods-original-20261013') / (role + '.jar'))
    args = parser.parse_args()
    result = audit(args.pilot.resolve(), {role: getattr(args, role).resolve() for role in ('orders', 'carts', 'shipping')}, args.out.resolve())
    print(f"Verified {result['business_total']} business calls and {result['raw_cost_samples_checked']} measured samples")
