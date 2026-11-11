"""Recheck saved evidence, not a deployment or performance measurement."""
import argparse
import copy
import csv
import json
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from run_planned_service import ROOT, save, load, sha
from diagnose_galette_hosted_template import H, OLD


def paired_sources(rows):
    assert [r['seq'] for r in rows] == list(range(1, len(rows) + 1))
    assert sum(r['kind'] == 'closed' for r in rows) == 1
    assert rows[-1]['kind'] == 'closed' and not rows[-1]['capture_invalid']
    assert not any(r['kind'] == 'problem' for r in rows)
    sources = [r for r in rows if r['kind'] == 'source']
    assert len({r['source_call_id'] for r in sources}) == len(sources)
    ids = {r['source_call_id'] for r in sources}
    assert {r['source_call_id'] for r in rows if r['kind'] == 'source-call-enter'} == ids
    assert {r['source_call_id'] for r in rows if r['kind'] == 'source-call-exit'} == ids
    for s in sources:
        a = [r for r in rows if r['kind'] == 'source-call-enter' and r['source_call_id'] == s['source_call_id']]
        b = [r for r in rows if r['kind'] == 'source-call-exit' and r['source_call_id'] == s['source_call_id']]
        assert len(a) == len(b) == 1 and a[0]['seq'] < s['seq'] < b[0]['seq']
        assert all(a[0][k] == s[k] == b[0][k] for k in (
            'source_call_id', 'caller', 'pc', 'callee', 'caller_frame', 'thread', 'root', 'message'))
        assert s['result'] == b[0]['result']
        enter = [r for r in rows if r['kind'] == 'enter' and r['frame'] == s['caller_frame']]
        end = [r for r in rows if r['kind'] == 'exit' and r['frame'] == s['caller_frame']]
        assert len(enter) == len(end) == 1
        assert enter[0]['method'] == end[0]['method'] == s['caller']
        assert enter[0]['seq'] < a[0]['seq'] < b[0]['seq'] < end[0]['seq']
        coordinates = [(f['owner'], f['field'], f['version']) for f in s['fields']]
        assert len(set(coordinates)) == len(coordinates)
        for f in s['fields']:
            assert f['label'] == '/'.join(map(str, (s['source_call_id'], f['owner'], f['field'], f['version'])))
    return sources


def test_counts(directory):
    total = Counter(suites=0, tests=0, failures=0, errors=0, skipped=0)
    reasons = Counter()
    for p in sorted((directory / 'reports').glob('TEST-*.xml')):
        suite = ET.parse(p).getroot()
        total['suites'] += 1
        for k in ('tests', 'failures', 'errors', 'skipped'):
            total[k] += int(suite.attrib.get(k, 0))
        for s in suite.findall('.//testcase/skipped'):
            reasons[s.attrib.get('message', (s.text or '').strip())] += 1
    total['passed'] = total['tests'] - total['failures'] - total['errors'] - total['skipped']
    assert dict(total) == load(directory / 'counts.json')
    return {'counts': dict(total), 'skip_reasons': dict(reasons)}


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    protocol = load(H / 'protocol-before-revisions.json')
    assert all(sha(Path(p)) == digest for p, digest in protocol['core_sources'].items())
    assert sha(Path(protocol['original_protocol'])) == protocol['original_protocol_sha256']
    built_patch = ROOT / 'experiments/sockshop-mirrortaint/galette-hosted-template-built-20261111.patch'
    assert subprocess.check_output(['git', '-C', str(H / 'modified-galette'), 'diff'], text=True) == built_patch.read_text()
    for path, fact in protocol['tool_receipt']['files'].items():
        assert sha(Path(path)) == fact['sha256']
    agent = ROOT / 'artifacts/pruning-contribution-audit-20261106/final-candidate/historical/frozen-base/distributed-observer.jar'
    assert sha(agent) == '367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764'
    tests = {d: test_counts(H / d) for d in ('official-tests-related-02', 'official-tests-full', 'modified-tests-full')}
    assert load(H / 'template-evidence-02/original/result.json')['returncode'] == 0
    assert load(H / 'template-evidence-02/galette/result.json')['returncode'] != 0
    probes = load(H / 'modified-probes-01/results.json')
    assert all(p['returncode'] == 0 for p in probes['probes'].values())
    assert probes['recompiled_Agent_classes_identical'] and probes['JVM_binary_matches_base']
    ordinary = OLD / 'jdk8-galette/jre/lib/rt.jar'
    modified = H / 'modified-jre8-02/lib/rt.jar'
    with ZipFile(ordinary) as a, ZipFile(modified) as b:
        names = [n for n in a.namelist() if n.endswith('.class')]
        assert set(names) == {n for n in b.namelist() if n.endswith('.class')}
        changed = [n for n in names if a.read(n) != b.read(n)]
    assert changed == ['java/lang/invoke/MethodHandleImpl$BindCaller$T.class']
    calibration = []
    targets = []
    raw = None
    dirs = [('low', 'final-low-01'), ('medium', 'final-medium-01'), ('high', 'final-high-02'),
            ('related-high', 'final-related-high-01'), ('mall', 'final-mall-01'), ('zlt-user', 'final-zlt-user-03')]
    for task, d in dirs:
        home = H / d
        rows = [json.loads(s) for s in (home / 'capture/galette.jsonl').read_text().splitlines()]
        sources = paired_sources(rows)
        raw = raw or rows
        summary = load(home / 'independent-score/summary.json')
        scores = load(home / 'independent-score/scores.json')
        assert summary['correct'] == summary['targets'] == (9 if task == 'zlt-user' else 6)
        assert not summary['wrong_known']
        calibration.append({'task': task, 'variant': 'modified Galette', **summary, 'artifact': str(home.relative_to(ROOT))})
        for s in scores:
            request_sources = [r for r in sources if r['message'] == s['message']]
            labels = set(s['target']['labels'])
            facts = [dict(source_call_id=r['source_call_id'], caller=r['caller'], pc=r['pc'], caller_frame=r['caller_frame'],
                          source_seq=r['seq'], path=f['path'], owner=f['owner'], field=f['field'], version=f['version'])
                     for r in request_sources for f in r['fields'] if f['label'] in labels]
            assert len(facts) == s['expected_count'] == len(labels)
            targets.append({'task': task, 'message': s['message'], 'path': s.get('path', '/data/expiresIn' if task == 'mall' else '/target'), 'state': 'correct',
                            'target_owner': s['target']['owner'], 'target_field': s['target']['field'],
                            'target_version': s['target']['version'], 'source_count': len(facts), 'physical_sources': facts})
    # Negative checks validate the independent raw-call audit, not native tag propagation.
    guards = []
    for fault in ('missing-completion', 'duplicate-completion', 'missing-source', 'ambiguous-field', 'wrong-caller', 'wrong-object', 'problem'):
        rows = copy.deepcopy(raw)
        end = next(r for r in rows if r['kind'] == 'source-call-exit')
        if fault == 'missing-completion': rows.remove(end)
        elif fault == 'duplicate-completion': rows.insert(rows.index(end), copy.deepcopy(end))
        elif fault == 'missing-source': rows.remove(next(r for r in rows if r['kind'] == 'source'))
        elif fault == 'ambiguous-field':
            source = next(r for r in rows if r['kind'] == 'source')
            source['fields'].append(copy.deepcopy(source['fields'][0]))
        elif fault == 'wrong-caller': end['caller'] += '-wrong'
        elif fault == 'wrong-object': end['result'] = 'wrong-object'
        else: rows[-1]['capture_invalid'] = True
        for i, r in enumerate(rows, 1): r['seq'] = i
        rejected = False
        try: paired_sources(rows)
        except AssertionError: rejected = True
        assert rejected
        guards.append({'fault': fault, 'independent_raw_audit_rejected': True})
    choice = load(H / 'selection-controls-02/results.json')
    direct = load(H / 'direct-selection-controls-02/results.json')
    assert not choice['correctness_gate_passed'] and direct['correctness_gate_passed']
    for mode in ('full', 'static', 'selective'):
        assert choice['modes'][mode]['data_correct'] == direct['modes'][mode]['data_correct'] == 2
        assert choice['modes'][mode]['correct_nonempty_selector_targets'] == 0
        assert direct['modes'][mode]['correct_nonempty_selector_targets'] == 2
    save(out / 'tests.json', tests)
    save(out / 'calibration.json', calibration)
    save(out / 'targets.json', targets)
    with (out / 'targets.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=('task', 'message', 'path', 'state', 'target_owner', 'target_field', 'target_version', 'source_count', 'physical_sources'), lineterminator='\n')
        writer.writeheader()
        for t in targets:
            writer.writerow({**t, 'physical_sources': json.dumps(t['physical_sources'], ensure_ascii=False, separators=(',', ':'))})
    save(out / 'independent-raw-audit-guards.json', guards)
    save(out / 'summary.json', {'TF_core_files_unchanged': len(protocol['core_sources']), 'TF_Agent_sha256': sha(agent),
         'ordinary_to_modified_rt_changed_classes': changed, 'official_test_results': tests,
         'modified_Galette_targets_verified': len(targets), 'branch_predicate_selection_gate': False,
         'direct_predicate_selection_gate': True, 'static_label': 'fixed-permission/body-off',
         'formal_gate_passed': False, 'formal_deployments': 0, 'formal_cost': None})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    run(p.parse_args().out.resolve())
