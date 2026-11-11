"""Calibration and work counts only; does not manufacture timing rows."""
import argparse, csv, json
from pathlib import Path
from run_planned_service import ROOT, load, save, sha
from seal_galette_static_baselines import H

TASKS = ('low', 'medium', 'high', 'related-high', 'mall', 'zlt-user')
MODES = ('original', 'mirrortaint', 'galette', 'full', 'static', 'selective')


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader(); w.writerows(rows)


def folder(home, task, mode):
    return home/('short-business-504' if task in ('mall', 'zlt-user') else 'short-504')/(
        task+'-'+mode if task in ('mall', 'zlt-user') else 'controlled-'+task+'-'+mode)


def root_evidence(home, task, trial, dest):
    from infer_distributed_fields import Reconstruction
    from infer_response_binding import matches
    plan = Path(load(home/'protocol-before-calibration.json')['tasks'][task]['plan'])
    build = dest/'build/role'; build.mkdir(parents=True)
    cap = dest/'capture/role'; cap.mkdir(parents=True)
    original = trial/'capture/events.jsonl'
    assert not original.with_name(original.name+'.invalid').exists()
    (build/'plan.json').write_bytes(plan.read_bytes()); (cap/'events.jsonl').symlink_to(original.resolve())
    g = Reconstruction(dest/'build', dest/'capture', ['role'])
    messages = {r['frame']: r['message'] for r in g.rows['role'] if r['kind'] == 'binding-return'}
    result = []
    for a in g.local_queries['role']['answers']:
        if not matches(load(plan)['response_binding']['path'], a['path']): continue
        result.append({k: a[k] for k in ('root_frame', 'seq', 'path', 'owner', 'field', 'version', 'known', 'origins', 'selectors')})
        result[-1]['message'] = messages[a['root_frame']]
    save(dest/'root-evidence.json', result)
    return {(a['message'], a['path']): a for a in result}


def run(home, out):
    out.mkdir(parents=True, exist_ok=False)
    protocol = load(home/'protocol-before-calibration.json')
    for group in ('core_sources', 'public_contracts', 'files'):
        for p, digest in protocol[group].items():
            assert sha(Path(p)) == digest, p
    table, instances, work = [], [], []
    for task in TASKS:
        reference = folder(home, task, 'original')
        original = load(reference/'warmup.json')['requests'] + load(reference/'measure.json')['requests']
        denominator = sum(len(c['response']['data']) for c in original) if task == 'zlt-user' else len(original)
        assert len(original) == 6 and denominator == (9 if task == 'zlt-user' else 6)
        for mode in MODES:
            d = folder(home, task, mode)
            row = {'task': task, 'configuration': mode, 'original_targets': denominator,
                   'business_requests': 6, 'business_correct': '', 'physical_binding': '',
                   'source_facts_adequate': '', 'correct': 0, 'wrong': 0, 'unknown': 0,
                   'rejected_or_invalid': 0, 'unscored': 0, 'state': '', 'first_blocker': '', 'evidence': str(d)}
            if mode == 'galette':
                row.update(unscored=denominator, state='startup_blocked_unscored' if task == 'high' else 'not_run_after_compatibility_blocker',
                           first_blocker='high original JAR: MethodHandleImpl$BindCaller$T.finalize(TagFrame) VerifyError before query/adapter',
                           evidence=str(home/'galette-boot-high-02') if task == 'high' else str(home/'tool-build-receipt.json'))
                if task == 'high': row['business_correct'] = 0
                for i, c in enumerate(original):
                    paths = ['/data/'+str(j)+'/username' for j in range(len(c['response']['data']))] if task == 'zlt-user' else [protocol['tasks'][task]['target_path']]
                    for path in paths:
                        instances.append({'task': task, 'configuration': mode, 'case_index': i, 'path': path,
                                          'state': 'unscored', 'expected_source_count': '', 'actual_source_count': '',
                                          'target_version': '', 'selectors': '', 'physical_fact_and_prediction_file': row['evidence']})
            elif mode == 'original':
                r = load(d/'calibration.json'); row.update(business_correct=r['run']['business_passed'], unscored=denominator,
                    state='original_business_reference', first_blocker='No provenance instrumentation; source prediction not applicable')
            else:
                r = load(d/'calibration.json'); s = r['score']
                row['business_correct'] = r['run']['business_passed']
                if task == 'related-high' and mode in ('full', 'static', 'selective'):
                    scoresfile = d/'audit-related-257/scores.json'
                else:
                    scoresfile = d/('independent-score/scores.json' if task == 'zlt-user' else 'audit/scores.json')
                scores = load(scoresfile)
                roots = root_evidence(home, task, d, out/'roots'/(task+'-'+mode)) if mode in ('full', 'static', 'selective') else {}
                case_messages = {c['case']: c['message'] for c in load(d/'warmup.json')['requests']+load(d/'measure.json')['requests']}
                if s.get('error'):
                    row.update(state='calibration_failed', first_blocker=s['error'], rejected_or_invalid=denominator)
                else:
                    assert len(scores) == denominator, (task, mode, len(scores), denominator)
                    correct = sum(bool(x.get('correct', x.get('exact'))) for x in scores)
                    wrong = sum(bool(x.get('known')) and not bool(x.get('correct', x.get('exact'))) for x in scores)
                    row.update(correct=correct, wrong=wrong, unknown=denominator-correct-wrong,
                               physical_binding=len(scores), source_facts_adequate=True,
                               state='calibrated' if correct == denominator else 'answers_not_preserved')
                for i, x in enumerate(scores):
                    answer = x.get('answer', {})
                    message = x.get('message', case_messages.get(x.get('case')))
                    target_path = x.get('path', protocol['tasks'][task]['target_path'])
                    root = roots.get((message, target_path), {})
                    expected = x.get('expected', [])
                    actual = x.get('actual', [])
                    instances.append({'task': task, 'configuration': mode,
                        'case_index': x.get('case', x.get('message', i)),
                        'path': x.get('path', protocol['tasks'][task]['target_path']),
                        'state': x.get('state', 'known_correct' if x.get('correct', x.get('exact')) else 'unknown'),
                        'expected_source_count': x.get('expected_count', len(expected)),
                        'actual_source_count': x.get('actual_count', len(actual)),
                        'target_version': root.get('version', x.get('version', answer.get('target', {}).get('version', ''))),
                        'selectors': json.dumps(root.get('selectors'), ensure_ascii=False) if roots else 'not_available_in_native_explicit_data_export',
                        'physical_fact_and_prediction_file': str(scoresfile)})
                if mode in ('full', 'static', 'selective'):
                    counts = r['actual_work']
                    work.append({'task': task, 'configuration': mode, **counts,
                                 'protocol_bytes': (d/'capture/events.jsonl').stat().st_size,
                                 'requests': 6, 'scope': 'complete short capture including startup; no speed inference'})
            table.append(row)
    body = load(home/'static-body-controls-504/checks.json')
    receipt = load(home/'tool-build-receipt.json')
    assert receipt['business_preflight']['formal_gate_passed'] is False
    result = {'core_changed': False, 'Agent_changed': False, 'contracts_changed': False,
              'calibration': table, 'actual_work': work, 'standalone_body_control': body,
              'formal_gate_passed': False, 'formal_deployments': 0,
              'formal_stop': 'Galette cannot start the unchanged high business JAR on instrumented 8u504, before source adapter. No shared-correctness cost ranking.',
              'Galette_source_adapter': 'Not implemented/calibrated: preceding JVM compatibility failure retained. No propagation-error claim.',
              'old_growth_result_unchanged': True,
              'static_definition': 'Existing fixed conservative permissions with original validity guards; live-locality body omission disabled. Same binary uses service.mode=selective plus explicit body=false.',
              'static_runtime_cost_boundary': 'Frozen Agent still computes/emits body eligibility evidence when body selection is disabled; equal cuts are not evidence of equal decision cost or pure-static runtime.',
              'cost_conclusions': 'No new formal timing or external ranking. Short counts do not prove CPU improvement.'}
    write_csv(out/'calibration.csv', table); write_csv(out/'instances.csv', instances); write_csv(out/'work.csv', work)
    save(out/'summary.json', result)
    save(out/'input-manifest.json', {str(p): sha(p) for p in sorted(home.rglob('calibration.json'))})
    print('Calibration rows:', len(table), 'instance rows:', len(instances), 'formal deployments: 0')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', type=Path, default=H); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); run(a.home.resolve(), a.out.resolve())
