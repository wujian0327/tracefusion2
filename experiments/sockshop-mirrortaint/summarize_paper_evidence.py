#!/usr/bin/env python3
"""Consolidate existing desktop measurements; never launch or rescore an experiment."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {}


def read(path):
    path = ROOT / path
    raw = path.read_bytes()
    SOURCES[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def metrics(row):
    off = row.get('offline') or {}
    phases = off.get('phases_seconds') or {}
    core = off.get('core_seconds')
    if phases:
        core = phases['graph_reconstruction'] + phases['query_or_native_origin_restore']
    return {
        'p50_ms': row['online_latency_ms']['p50'],
        'p95_ms': row['online_latency_ms']['p95'],
        'cpu_one_core_percent': row['resources']['observed_jvms']['cpu_one_core_percent_mean'],
        'rss_mean_bytes': row['resources']['observed_jvms']['rss_bytes_mean'],
        'events': sum(x['events'] for x in row['steady_capture'].values()),
        'bytes': sum(x['bytes'] for x in row['steady_capture'].values()),
        'offline_core_seconds': core,
        'offline_total_seconds': off.get('restore_score_export_seconds'),
        'offline_wall_seconds': off.get('subprocess_wall_seconds'),
        'offline_cpu_seconds': off.get('process_cpu_seconds'),
        'offline_peak_bytes': off.get('peak_rss_bytes'),
    }


def block(path, mode_key, numerator, denominator, receipt):
    check = read(f'{path}/{receipt}')
    read(f'{path}/config.json')
    assert (check.get('all_passed') is True or
            (check.get('run_status', {}).get('status') == 'passed' and
             check.get('performance_eligible') is True)), path
    rows = []
    for trial in sorted((ROOT / path).glob('round-*')):
        if not trial.is_dir():
            continue
        row = read(f'{trial.relative_to(ROOT)}/metrics.json')
        mode = trial.name.split('-')[-1] if mode_key == 'policy' else row['mode']
        expected_status = 'provenance-failed' if mode == 'boundary' else 'passed'
        assert row['status'] == expected_status and row['error_rate'] == 0, trial
        assert row['steady_requests'] == 120 and row['offered_rate_rps'] == 2, trial
        rows.append({'trial': trial.name, 'round': int(trial.name.split('-')[1]),
                     'mode': mode, 'metrics': metrics(row),
                     'accuracy': (row.get('offline') or {}).get('summary')})
    groups = {}
    for mode in sorted({r['mode'] for r in rows}):
        group = [r for r in rows if r['mode'] == mode]
        assert len(group) == 5 and {r['round'] for r in group} == set(range(1, 6))
        medians = {}
        for key in group[0]['metrics']:
            values = [r['metrics'][key] for r in group if r['metrics'][key] is not None]
            assert len(values) in (0, 5), (path, mode, key)
            medians[key] = median(values) if values else None
        groups[mode] = {
            'deployments': 5, 'steady_requests': 600,
            'medians': medians,
            'accuracy': {k: sum(r['accuracy'][k] for r in group) for k in
                         ('queries', 'exact', 'tp', 'fp', 'fn', 'unknown')}
                        if group[0]['accuracy'] else None,
        }
    paired = {}
    for key in rows[0]['metrics']:
        ratios = []
        for rnd in range(1, 6):
            a = next(r['metrics'][key] for r in rows if r['round'] == rnd and r['mode'] == numerator)
            b = next(r['metrics'][key] for r in rows if r['round'] == rnd and r['mode'] == denominator)
            if a is not None and b is not None and b > 0:
                ratios.append(a / b)
        paired[key] = ({'ratios': ratios, 'median': median(ratios),
                        'change_percent': 100 * (median(ratios) - 1),
                        'min': min(ratios), 'max': max(ratios)} if ratios else None)
    return {'source': path, 'comparison': f'{numerator}/{denominator}',
            'groups': groups, 'paired': paired, 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    blocks = {
        'sockshop_common': block('artifacts/fairness-expansion-20261015/source-ids-cost',
                                 'mode', 'tracefusion', 'mirrortaint', 'independent-validation.json'),
        'sockshop_ablation': block('artifacts/observation-ablation-formal-20261015',
                                   'policy', 'selective', 'full', 'comparison.json'),
        'trainticket_ablation': block('artifacts/trainticket-cost-formal-20261016',
                                      'mode', 'selective', 'full', 'independent-audit.json'),
    }
    legacy = read('artifacts/trainticket-multisource-20261016/legacy-correctness/comparison.json')['results']
    calibration = read('artifacts/trainticket-multisource-20261016/validation-02/independent-audit.json')
    assert calibration['all_passed']
    security = read('artifacts/security-leak-desktop-reproduction-20261015/results.json')
    security_counts = {}
    for name, profile in security['profiles'].items():
        queries = profile['queries']
        observed = {
            'queries': len(queries),
            'tp': sum(q['expected'] and q['prediction'] is True for q in queries),
            'fp': sum(not q['expected'] and q['prediction'] is True for q in queries),
            'fn_including_unknown_positive': sum(q['expected'] and q['prediction'] is not True for q in queries),
            'tn': sum(not q['expected'] and q['prediction'] is False for q in queries),
            'unknown': sum(not q['known'] for q in queries),
        }
        assert all(profile['metrics'][k] == v for k, v in observed.items()), name
        security_counts[name] = observed
    SOURCES[str(Path(__file__).resolve().relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.out.mkdir(parents=True, exist_ok=True)
    result = {'as_of': '2026-10-16', 'blocks': blocks, 'legacy_correctness': legacy,
              'train_calibration': calibration['results'], 'security': security_counts,
              'source_sha256': SOURCES,
              'validation_scope': 'Arithmetic independently recomputed from saved per-deployment metrics and per-query security predictions; reuse existing raw-evidence audit receipts. No new experiment, raw-timing re-audit or blind validation.'}
    (args.out / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for name, data in blocks.items():
        print(name, data['comparison'])
        for key, value in data['paired'].items():
            if value:
                print(f"  {key}: {value['change_percent']:+.4f}% [{value['min']:.6f}, {value['max']:.6f}]")
    print('security', security_counts)


if __name__ == '__main__':
    main()
