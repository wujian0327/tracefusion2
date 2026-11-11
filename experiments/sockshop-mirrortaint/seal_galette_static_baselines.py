"""Seal fixed tasks before calibration; never selects by tool results."""
import argparse, json, subprocess
from pathlib import Path
from run_planned_service import ROOT, HERE, load, save, sha
from tf_static_baseline import configure

H = ROOT/'artifacts/galette-static-baselines-20261111'
PRIOR = ROOT/'artifacts/jvm-rule-evidence-20261110'


def run(home):
    out = home/'protocol-before-calibration.json'
    if out.exists():
        raise FileExistsError(out)
    freeze = load(PRIOR/'post-experiment-v1-guard-fix.json')
    for p, h in freeze['core_sources'].items():
        assert sha(Path(p)) == h, p
    old = load(ROOT/'artifacts/unrelated-work-scaling-20261109/protocol-before-tools.json')
    tasks = {}
    for tier in ('low', 'medium', 'high', 'related-high'):
        d = PRIOR/'controlled-build-04'/tier
        tasks[tier] = {'business_jar': str(d/'business.jar'), 'plan': str(d/'plan.json'),
                       'inputs': ['GET /query'] * 6, 'target_path': '/target',
                       'source_calls': ['bench/Store.read()Lbench/Payload;'],
                       'expected_source_occurrences': 257 if tier == 'related-high' else 1,
                       'oracle': 'Raw paired Store.read field instances; literal original sum only for related-high.',
                       'fixed_mt_bundle': str(ROOT/'artifacts/heldout29-first-20261023/native-bundle')}
    ref = ROOT/'artifacts/shared-transfer-optimization-20261106/final-candidate'
    tasks['mall'] = {'plan': str(ref/'mall/planning-first/mall-swarm-3/002-plan.json'),
                     'compose': str(ref/'mall/tool-runs/mall-swarm-3/full/query-002/compose.json'),
                     'inputs': 'Six original admin/macro123 legitimate OAuth requests; no new prewarm.',
                     'target_path': '/data/expiresIn',
                     'source_calls': ['com/macro/mall/service/AuthService.getAccessToken'],
                     'oracle': 'Actual RPC return field and call interval in this JVM, plus original response and login-log count.',
                     'fixed_mt_bundle': str(ROOT/'artifacts/heldout29-first-20261023/native-bundle')}
    tasks['zlt-user'] = {'plan': str(ref/'zlt/planning-first/ZLT-MP-4/000-plan.json'),
                         'compose': str(ref/'zlt/runs/ZLT-MP-4/full/compose.json'),
                         'task_seal': str(ref/'zlt/task-seal.json'),
                         'inputs': 'Exactly original six sealed pagination inputs including empty page.',
                         'target_path': '/data/*/username',
                         'source_calls': ['SysUserMapper.findList'],
                         'oracle': 'Actual paired mapper return members/fields/versions in this JVM, not labels or graph.',
                         'fixed_mt_compose': str(ROOT/'artifacts/offline-zlt-revision-20261031/final-zlt-MT-isolated-01/runs/ZLT-MP-4/mirrortaint/compose.json')}
    files = {str(ROOT/'artifacts/pruning-contribution-audit-20261106/final-candidate/historical/frozen-base/distributed-observer.jar')}
    for task in tasks.values():
        for k in ('plan', 'business_jar', 'compose', 'task_seal', 'fixed_mt_compose'):
            if k in task:
                p = Path(task[k]); assert p.is_file(), p; files.add(str(p))
        task['source_calls_exact'] = load(Path(task['plan']))['response_binding']['source_calls']
        task['TF_baselines'] = {m: configure(load(Path(task['plan'])), m) for m in ('full', 'static', 'selective')}
        for k in ('compose', 'fixed_mt_compose'):
            if k not in task:
                continue
            for s in load(Path(task[k]))['services'].values():
                for v in s.get('volumes', []):
                    if isinstance(v, str) and v.startswith('/'):
                        src = Path(v.split(':')[0])
                        if src.is_file() and src.suffix in ('.jar', '.json', '.sql'):
                            files.add(str(src))
    for p in (ROOT/'artifacts/heldout29-first-20261023/native-bundle').rglob('*.jar'):
        files.add(str(p))
    files.add(str(ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'))
    jdk = Path('/usr/lib/jvm/java-8-openjdk-amd64')
    for n in ('bin/java', 'bin/javac', 'jre/lib/rt.jar', 'jre/lib/amd64/server/libjvm.so'):
        files.add(str(jdk/n))
    contracts = sorted(HERE.glob('*contracts*.json'))
    receipt = {'main_before_work': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'measurement_reference': 'c8918bf8b0ed6ac90c0065558fe4df540bd76a2c',
               'offline_fix_reference': 'c866d670628610d5abf3242318581c575e1c9fb6',
               'core_sources': freeze['core_sources'],
               'public_contracts': {str(p): sha(p) for p in contracts},
               'files': {p: sha(Path(p)) for p in sorted(files)},
               'galette_commit': subprocess.check_output(['git', '-C', str(home/'galette-original'), 'rev-parse', 'HEAD'], text=True).strip(),
               'galette_official_build': 'JDK17, mvn -DskipTests install; original source unchanged',
               'galette_JDK_instrumentation': 'Official instrument JAR on original OpenJDK8u504, output new directory; transformations separately hashed.',
               'tasks': tasks, 'configs': ['original', 'mirrortaint', 'galette', 'full', 'static', 'selective'],
               'calibration': {'requests': 6, 'speed_claims': False, 'explicit_data_sources_primary': True,
                               'selectors_separate': True, 'no_task_substitution': True},
               'formal': {'tasks': ['high', 'mall'], 'rounds': 5, 'max_deployments': 60,
                          'warm_seconds': 30, 'measure_seconds': 60, 'rps': 2, 'concurrency': 2,
                          'random_seed': 6111117, 'gate': 'All six configurations independently correct on the same task; baseline definitions and measurement issues resolved.',
                          'primary': 'Paired same-task CPU seconds/completed minus original; no growth-trend claim.',
                          'oracle_time': 'Separate from normal provenance, all necessary evidence checks retained.'},
               'old_negative_growth_result_preserved': True,
               'images': old['images']}
    save(out, receipt)
    print(out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', type=Path, default=H)
    run(p.parse_args().home.resolve())
