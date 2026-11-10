"""Two sealed Petclinic queries; preserve static rejection before any deployment."""
import argparse
import csv
import json
import subprocess
from pathlib import Path

from run_generic_observation_rules import metadata_build, verify, ROOT
from run_planned_service import load, save, sha
from plan_capability_policy import choose


def plan(protocol, out):
    p = load(protocol); verify()
    assert sha(Path(p['jar'])) == p['jar_sha256']
    configs = {q['id']: {'jar': p['jar'], 'targets': [q['target']],
                         'bytecode_dependencies': ['org/springframework/http/ResponseEntity', 'org/springframework/http/HttpEntity', 'org/springframework/http/HttpStatus']} for q in p['queries']}
    metadata_build(out, configs); results = []
    for q in p['queries']:
        dest = out/q['id']; model = load(dest/'model.json')
        try:
            executable, route = choose(model, q, deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
            save(dest/'executable-plan.json', executable); save(dest/'route.json', route)
            state, error = 'planned_not_executed', None
        except ValueError as e:
            state, error = 'planning_rejected', str(e)
        results.append({'id': q['id'], 'state': state, 'first_blocker': error,
                        'model_sha256': sha(dest/'model.json'), 'configuration_calibrated': False})
    save(out/'first-results.json', {'protocol_sha256': sha(protocol), 'results': results, 'core': verify()})


def original(protocol, out, container, planning):
    p = load(protocol); out.mkdir(parents=True, exist_ok=False)
    results = load(planning)['results']; by_query = {r['id']: r for r in results}
    instances, requests = [], []
    for q in p['queries']:
        for case, input_id in enumerate(q['inputs']):
            url = q['url'].format(id=input_id)
            r = subprocess.run(['docker', 'exec', container, 'curl', '--silent', '--show-error', '--max-time', '30', '--write-out', '\n%{http_code}', 'http://127.0.0.1:9966'+url], capture_output=True, text=True, check=True)
            (out/(q['id']+'-'+str(case)+'.http')).write_text(r.stdout)
            body, status = r.stdout.rsplit('\n', 1); assert status == '200', (url, status, body)
            obj = json.loads(body)
            leaves = [('/name', obj['name'])] if q['id'] == 'specialty-name' else [('/pets/'+str(i)+'/name', item['name']) for i, item in enumerate(obj['pets'])]
            assert leaves and all(value is not None for _, value in leaves)
            requests.append({'query': q['id'], 'case': case, 'input': input_id, 'status': 200, 'leaves': len(leaves), 'body': obj})
            for path, value in leaves:
                for mode in ('full', 'selective'):
                    instances.append({'query': q['id'], 'case': case, 'input': input_id, 'path': path,
                        'original_value': value, 'mode': mode, 'state': by_query[q['id']]['state'],
                        'target_physical_binding': 'not_acquired_no_executable_plan',
                        'source_boundary': q['source_calls'][0], 'source_call_id': '', 'source_owner': '', 'source_version': '',
                        'oracle_adequate': False, 'known_correct': '', 'FP': '', 'FN': '',
                        'oracle_gap': 'No TF JVM source/target facts: static rejection. Seed/wire equality is not an instance oracle.'})
    save(out/'requests.json', requests)
    with (out/'per-target.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(instances[0])); w.writeheader(); w.writerows(instances)
    save(out/'summary.json', {'queries': len(p['queries']), 'original_requests': len(requests),
        'actual_targets_per_mode': len(instances)//2, 'tf_new_deployments': 0,
        'known_correct': 0, 'physical_oracle_available': 0,
        'planning_rejected_per_mode': sum(r['state']=='planning_rejected' for r in instances)//2,
        'protocol_sha256': sha(protocol), 'scope': 'First static refusals and original obligations; not propagation FP/FN, not a successful new-application reuse.'})


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--protocol', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True); a.add_argument('--stage', choices=['plan', 'original'], required=True)
    a.add_argument('--container', default='tf2-generic-rules-original'); a.add_argument('--planning', type=Path)
    x = a.parse_args()
    if x.stage == 'plan': plan(x.protocol.resolve(), x.out.resolve())
    else: original(x.protocol.resolve(), x.out.resolve(), x.container, x.planning.resolve())
