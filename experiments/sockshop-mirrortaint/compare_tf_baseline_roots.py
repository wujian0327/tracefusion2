"""Compare logical occurrences, never object numbers across JVMs.

Independent per-JVM scoring remains the correctness oracle. This additional
check compares target states/versions and normalized origins/selectors.
"""
import argparse, json
from pathlib import Path
from run_planned_service import load, save
from summarize_galette_static_baselines import TASKS, folder
from seal_galette_static_baselines import H


def normalize(trial, answers):
    rows = [json.loads(x) for x in (trial/'capture/events.jsonl').read_text().splitlines()]
    seq = {r['seq']: r for r in rows}
    cases = load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests']
    case_index = {c['message']: i for i, c in enumerate(cases)}
    from external_transfer_oracle import RawFactIndex
    index = RawFactIndex(rows)
    result = {}
    for a in answers:
        sources = index.source_family(a['root_frame'])
        ordinals = {}; counts = {}
        for r in sorted(sources, key=lambda r: r['seq']):
            key = (r['kind'], r.get('callee'))
            counts[key] = counts.get(key, 0)+1; ordinals[r['seq']] = counts[key]
        def ref(token):
            kind, event, slot = token
            r = seq[event]
            if kind == 'field':
                f = r['fields'][slot]
                return (kind, r['kind'], r.get('callee'), ordinals.get(event),
                        f.get('path'), f['field'], f['version'])
            if kind == 'argument':
                return (kind, r['kind'], r.get('method'), slot)
            raise ValueError('Unnormalized evidence kind: '+str(token))
        key = (case_index[a['message']], a['path'])
        assert key not in result
        result[key] = {'known': a['known'], 'version': a['version'],
                       'origins': sorted([ref(t) for t in a['origins']], key=str),
                       'selectors': sorted([ref(t) for t in a['selectors']], key=str)}
    return result


def run(home, summary, out):
    out.mkdir(parents=True, exist_ok=False); reports = []
    for task in TASKS:
        normalized = {}
        for mode in ('full', 'static', 'selective'):
            evidence = load(summary/'roots'/(task+'-'+mode)/'root-evidence.json')
            normalized[mode] = normalize(folder(home, task, mode), evidence)
            save(out/(task+'-'+mode+'.json'), [{'case': k[0], 'path': k[1], **v} for k, v in sorted(normalized[mode].items())])
        assert normalized['full'] == normalized['static'] == normalized['selective'], task
        reports.append({'task': task, 'targets_per_mode': len(normalized['full']),
                        'state_version_origins_selectors_equal': True,
                        'nonempty_selector_targets': sum(bool(a['selectors']) for a in normalized['full'].values())})
    save(out/'summary.json', {'checks': reports, 'physical_instance_scoring_is_separate': True,
                             'no_cross_JVM_object_comparison': True})
    print(reports)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', type=Path, default=H)
    p.add_argument('--summary', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); run(a.home.resolve(), a.summary.resolve(), a.out.resolve())
