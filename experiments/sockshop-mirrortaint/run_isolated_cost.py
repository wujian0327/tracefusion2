#!/usr/bin/env python3
"""Fresh fixed-load costs for the isolated Agent; no changes to frozen semantics.

Reuse the reviewed HTTP timers, Docker sampler and independent source oracles.
Plans are selected before execution. Raw HTTP audit facts are deliberately ON
in both policies and their costs are included, rather than silently claiming a
minimum-instrumentation result. Historical results remain immutable.
"""
import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

from run_planned_service import ROOT, HERE, load, save, sha
from build_distributed_plans import build
from plan_capability_policy import choose
from run_quota_capability_acceptance import qualified_options
from audit_application_call_revision import class_hashes
import run_response_binding_revision as binding
import run_bound_query_cost as bound
import run_train_cost as price
import run_train_multisource as calibration
import run_sockshop_cost as sampler

ALGORITHM = '76d2050de6634c52db6583832aefa1e6892454c9'
CURRENT = ROOT/'artifacts/jackson-isolation-20261022/candidate-v2/final-capability'
OLD_COST = ROOT/'artifacts/call-lifecycle-revision-20261020'
JVM = '-Xms32m -Xmx256m -XX:ParallelGCThreads=1 -XX:CICompilerCount=2 -Djava.security.egd=file:/dev/urandom -Dspring.zipkin.enabled=false'


def install():
    bound.JVM = price.JVM = sampler.JVM = JVM
    # The frozen Agent buffers output. Count a stable prefix ending at the last
    # complete record, never a torn JSON line. This is a file-visible window;
    # final request-attributed counts are audited separately after shutdown.
    def position(dest, role):
        p = dest/role/'events.jsonl'
        raw = p.read_bytes() if p.exists() else b''
        end = raw.rfind(b'\n') + 1
        return {'events': raw[:end].count(b'\n'), 'bytes': end}
    bound.position = position
    price.log_position = lambda dest: {r: position(dest, r) for r in price.ROLES}
    original = calibration.observed
    def observed(spec, name, role, dest, base):
        original(spec, name, role, dest, base)
        spec['services'][name]['environment']['JAVA_OPTS'] = qualified_options(spec['services'][name]['environment']['JAVA_OPTS'])
    calibration.observed = observed


def node(root, name, **values):
    save(root/'logs'/(name+'.json'), {'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(), **values})
    print(json.dumps({'node': name, **values}, ensure_ascii=False), flush=True)


def check(root):
    f = load(root/'algorithm-freeze.json')
    assert f['algorithm_commit'] == ALGORITHM
    for p, h in f['core_sources'].items():
        assert sha(ROOT/p) == h, ('Frozen core changed', p)
    for p, h in f['driver_sources'].items():
        assert sha(ROOT/p) == h, ('Frozen driver changed', p)
    for kind in ('cart', 'train', 'price'):
        binding.verify_build(root/(kind+'-build'))
    return f


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    (root/'logs').mkdir()
    previous = load(CURRENT/'algorithm-freeze.json')
    sources = previous['sources']
    core = {str(Path(p).relative_to(ROOT)): h for p, h in sources.items()}
    for p, h in core.items():
        assert sha(ROOT/p) == h, p
    base_manifest = load(CURRENT/'frozen-base/build.json')
    build(root/'bound-base', {r: base_manifest['inputs'][r]['query_config'] for r in ('carts', 'train')})
    policies = {}
    for kind in ('cart', 'train'):
        q = bound.query(kind)
        plan, policy = choose(load(root/'bound-base'/q['role']/'model.json'), q)
        assert plan['source_evidence'] is True
        binding.query_build(root/(kind+'-build'), root/'bound-base', q, plan)
        policies[kind] = {'query': q, 'policy': policy, 'profile': plan['profile']}
    old = load(OLD_COST/'price-build/build.json')
    configs = {r: {**v['query_config'], 'source_evidence': True} for r, v in old['inputs'].items()}
    build(root/'price-build', configs)
    policies['price'] = {'profile': 'collection-computation', 'reason': 'Existing bytecode-derived collection fast path, fixed before execution; original two price entries and original HTTP response source boundaries.'}
    classes = class_hashes(CURRENT/'frozen-base/distributed-observer.jar')
    for b in ('bound-base', 'price-build'):
        assert class_hashes(root/b/'distributed-observer.jar') == classes
        for r, v in load(root/b/'build.json')['inputs'].items():
            assert v['original_jar_sha256'] == previous['original_jars'][r]
    drivers = ['run_isolated_cost.py', 'run_bound_query_cost.py', 'run_train_cost.py',
               'run_sockshop_cost.py', 'run_train_multisource.py',
               'run_sockshop_model_revision.py', 'run_response_binding_revision.py',
               'run_frozen_capability_acceptance.py', 'run_execution_kernel_pilot.py',
               'audit_train_multisource.py', 'measure_offline_memory.py']
    freeze = {'commit': ALGORITHM, 'algorithm_commit': ALGORITHM,
              'experiment_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'core_sources': core, 'driver_sources': {str((HERE/n).relative_to(ROOT)): sha(HERE/n) for n in drivers},
              'original_jars': previous['original_jars'], 'prior_freeze_sha256': sha(CURRENT/'algorithm-freeze.json'),
              'policies': policies, 'jvm': JVM, 'rounds': 5, 'warmup_seconds': 30,
              'measurement_seconds': 60, 'offered_rps': 2, 'max_concurrency': 2,
              'resource_sample_seconds': 2, 'business_cpu': 1, 'business_memory_mib': 768,
              'mongo_cpu': 1, 'mongo_memory_mib': 384, 'source_evidence': True,
              'scope': 'All required evidence and raw HTTP audit bytes included. Not a minimum-diagnostic configuration. No saturation inference; sealed 29 queries untouched.',
              'independence': 'Fresh containers and volumes per trial, all online trials sequential; matched round ratios, no request-level pseudo-replication.'}
    save(root/'algorithm-freeze.json', freeze)
    for p in core.keys() | freeze['driver_sources'].keys():
        d = root/'sources'/p; d.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/p, d)
    save(root/'formal-run-map.json', {k: 'cost-'+k for k in ('cart', 'train', 'price')})
    node(root, '00-protocol', algorithm=ALGORITHM, policies=policies, rounds=5, source_evidence=True)


def calibrate(root):
    check(root)
    out = root/'calibration'; out.mkdir()
    results = {}
    for kind in ('cart', 'train'):
        for mode in ('full', 'selective'):
            d = out/(kind+'-'+mode)
            m = bound.trial_run(d, root/(kind+'-build'), kind, mode, bound.templates(kind), 3, 6, 2, 2, 2)
            results[kind+'-'+mode] = m['offline']['summary']
    cfg = load(OLD_COST/'cost-price/config.json')
    inputs = Path(cfg['inputs'])
    p = out/'price'
    calibration.freeze(p, root/'price-build', inputs, 161019)
    for mode in ('full', 'selective'):
        calibration.capture(p, root/'price-build', inputs, mode)
        calibration.evaluate(p, root/'price-build', mode)
    from audit_train_multisource import audit
    audit(p, root/'price-build')
    results['price'] = load(p/'independent-audit.json')
    save(root/'calibration-audit.json', {'all_passed': True, 'results': results})
    node(root, '01-calibration', all_passed=True, source_evidence=True)


def freeze_runs(root):
    assert load(root/'calibration-audit.json')['all_passed']
    for i, kind in enumerate(('cart', 'train', 'price')):
        args = argparse.Namespace(out=root/('cost-'+kind), build=root/(kind+'-build'),
                                  kind=kind, rounds=5, warmup=30., seconds=60., rate=2.,
                                  concurrency=2, sample_interval=2., seed=221020+i,
                                  inputs=Path(load(OLD_COST/'cost-price/config.json')['inputs']),
                                  calibration=root/'calibration/price', offline_timeout=600.)
        if kind == 'price':
            price.freeze(args, args.out)
        else:
            bound.freeze(args)
    node(root, '02-all-orders-frozen', deployments=45)


def run(root):
    check(root)
    for kind in ('cart', 'train', 'price'):
        home = root/('cost-'+kind); cfg = load(home/'config.json')
        save(home/'run-status.json', {'status': 'running'})
        for name, mode in cfg['order']:
            check(root)
            d = home/name
            if d.exists():
                raise ValueError('Never overwrite or silently replace a trial: '+str(d))
            if kind == 'price':
                args = argparse.Namespace(**{k: Path(v) if k in ('out','build','inputs','calibration') else v for k,v in cfg.items()})
                price.trial_run(args, d, mode, home)
            else:
                bound.trial_run(d, root/(kind+'-build'), kind, mode, load(home/'templates.json'),
                                cfg['warmup'], cfg['seconds'], cfg['rate'], cfg['concurrency'], cfg['sample_interval'])
            finished = sum((home/n/'metrics.json').exists() for n,_ in cfg['order'])
            save(home/'progress.json', {'completed': finished, 'total': 15, 'last': name})
            if finished % 3 == 0:
                node(root, kind+'-'+name[:8], all_three_passed=True, completed=finished)
        save(home/'run-status.json', {'status': 'passed'})
    node(root, '03-online-complete', deployments=45)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('prepare','calibrate','freeze','run'))
    p.add_argument('--root', required=True, type=Path)
    a = p.parse_args(); root = a.root.resolve(); install()
    {'prepare': prepare, 'calibrate': calibrate, 'freeze': freeze_runs, 'run': run}[a.stage](root)


if __name__ == '__main__':
    main()
