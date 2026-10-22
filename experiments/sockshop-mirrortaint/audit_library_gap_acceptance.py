#!/usr/bin/env python3
"""Fresh original-431 scoring, frozen controls and observed runtime policy."""
import argparse
import json
import hashlib
import subprocess
from pathlib import Path

from run_planned_service import ROOT, HERE, load, save, sha
from audit_application_call_revision import class_hashes
from audit_frozen_capability_acceptance import audit as source_audit
import run_frozen_capability_acceptance as driver


def audit(root, out):
    out.mkdir(parents=True, exist_ok=False)
    driver.HOME = root
    driver.check()
    freeze = load(root / 'algorithm-freeze.json')
    protocol = HERE / 'library-gap-acceptance-protocol-20261022.json'
    frozen_protocol = subprocess.check_output(['git', 'show', freeze['commit'] + ':' + str(protocol.relative_to(ROOT))], cwd=ROOT)
    assert sha(protocol) == hashlib.sha256(frozen_protocol).hexdigest()
    for name, digest in freeze['oracle_sources'].items():
        assert sha(Path(name)) == digest, name
    for name in ('run_frozen_capability_acceptance.py', 'run_response_binding_revision.py',
                 'run_execution_kernel_pilot.py', 'run_sockshop_model_revision.py',
                 'normalize_orders_origins.py', 'audit_baseline_capabilities.py'):
        path = HERE / name
        frozen_source = subprocess.check_output(['git', 'show', freeze['commit'] + ':' + str(path.relative_to(ROOT))], cwd=ROOT)
        assert sha(path) == hashlib.sha256(frozen_source).hexdigest(), name
    assert not (root / 'business-repeats').exists(), 'This protocol admits no replacement receipts'
    source = source_audit(root, out / 'source-union')
    agent = class_hashes(root / 'frozen-base/distributed-observer.jar')
    controls = {}
    control_root = root.parent / 'frozen-controls'
    for group in ('kernel', 'application', 'conversion', 'uuid', 'date', 'received', 'legacy'):
        folder = control_root / group
        result = load(folder / 'results.json')
        assert result['all_passed'], group
        assert class_hashes(folder / 'build/distributed-observer.jar') == agent, group
        controls[group] = {'all_passed': True, 'results_sha256': sha(folder / 'results.json'),
                           'modes': result.get('modes', result.get('profiles'))}
    queries = {q['id']: q for q in driver.QUERIES}
    captures = []
    for worker in sorted(root.glob('all62-*')):
        for directory in sorted(worker.glob('*-*')):
            if (directory / 'capture/compose.json').exists():
                mode, qid = directory.name.split('-', 1)
                captures.append((directory, queries[qid]['role'], mode, qid))
    for mode in ('full', 'selective'):
        captures.append((root / 'cart-create-pair' / mode, 'carts', mode,
                         'sockshop-carts-get-customerId:create-repeat'))
    policy = []
    for directory, role, mode, qid in captures:
        cap = directory / 'capture'
        name = role if role in ('orders', 'carts') else 'ts-' + role + '-service'
        cfg = load(cap / 'compose.json')['services'][name]
        opts = cfg['environment']['JAVA_OPTS']
        assert cfg['cpus'] == 1 and cfg['mem_limit'] == '768m'
        assert '-Xms32m -Xmx256m' in opts
        assert opts.count('-XX:ParallelGCThreads=1') == opts.count('-XX:CICompilerCount=2') == 1
        assert '-Dservice.mode=' + mode in opts
        assert not any(s in opts for s in ('-Dservice.diagnostic', '-XX:+PrintGC', '-Xloggc:'))
        raw = cap / role / 'events.jsonl'
        rows = [json.loads(line) for line in raw.read_text().splitlines()]
        assert rows[0]['mode'] == mode
        assert not any('diagnostic_monotonic_ns' in r for r in rows)
        if role == 'orders':
            timed = [r for r in rows if r['kind'] == 'collection-call-enter'
                     and r.get('callee', '').startswith('java/util/concurrent/Future.get(J')]
            assert timed and all(r['args'][0]['value'] == 5 for r in timed)
        policy.append({'mode': mode, 'query': qid, 'CPU': cfg['cpus'], 'memory_limit': cfg['mem_limit'],
                       'heap': '32m/256m', 'GC_threads': 1, 'compiler_threads': 2,
                       'source_evidence': load(directory / 'build' / role / 'plan.json')['source_evidence'],
                       'raw_sha256': sha(raw), 'compose_sha256': sha(cap / 'compose.json')})
    assert len(policy) == 126, len(policy)
    contracts = load(HERE / 'plain-conversion-contracts-20261022.json')
    actual = contracts['class_sha256']
    bundled = contracts['original_business_class_sha256']
    differences = {k: {'actual_observed': v, 'original_business_bundled': bundled[k]}
                   for k, v in actual.items() if k in bundled and v != bundled[k]}
    assert differences and freeze['original_runtime_library_caveat']
    unresolved = []
    for item in load(out / 'source-union/instances.json'):
        if item['state'] != 'unknown':
            continue
        cap = Path(item['capture'])
        role = queries[item['query']]['role']
        raw = cap / role / 'events.jsonl'
        rows = [json.loads(line) for line in raw.read_text().splitlines()]
        returns = [r for r in rows if r['kind'] == 'binding-return' and r.get('message') == item['message']]
        assert len(returns) == 1
        frames = driver.family(rows, returns[0])
        saves = [{k: r.get(k) for k in ('seq', 'frame', 'call_id', 'preconditions', 'valid',
                                      'listeners_verified', 'events', 'callback_invocations', 'mapping', 'listeners')}
                 for r in rows if r['kind'] == 'mongo-save-effect' and r.get('frame') in frames]
        unresolved.append({'mode': item['mode'], 'query': item['query'], 'case': item['case'],
                           'path': item['path'], 'root_frame': returns[0]['frame'],
                           'raw_sha256': sha(raw), 'unverified_save_witnesses': saves,
                           'not_a_proof_that_save_is_the_only_remaining_barrier': True})
    save(out / 'unresolved-evidence.json', unresolved)
    planning = load(root / 'frozen-plans/planning.json')
    assert len(planning) == 62
    result = {**source, 'observed_target_JVM_configurations': len(policy),
              'runtime_policy_verified': True, 'controls': controls,
              'runtime_library_caveat': freeze['original_runtime_library_caveat'],
              'runtime_library_differences': differences,
              'source_coordinate_revision': freeze['source_coordinate_revision'],
              'unresolved_evidence_sha256': sha(out / 'unresolved-evidence.json'),
              'oracle_sources_sha256': freeze['oracle_sources'],
              'new_unseen_queries': False, 'new_performance_claim': False,
              'protocol_sha256': sha(protocol), 'all_passed': source['all_passed']}
    save(out / 'runtime-policy.json', policy)
    save(out / 'controls.json', controls)
    save(out / 'audit.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root.resolve(), args.out.resolve())
    print(json.dumps({k: result[k] for k in ('algorithm_commit', 'all_passed', 'modes',
                     'observed_target_JVM_configurations', 'first_attempt_business_all_passed')}, indent=2))
