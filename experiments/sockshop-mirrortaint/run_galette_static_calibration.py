"""Short calibration only. Does not contain an unchecked formal timing path."""
import argparse, copy, json, shutil, os
from pathlib import Path
from run_planned_service import ROOT, HERE, load, save, sha
from seal_galette_static_baselines import H, PRIOR
from tf_static_baseline import configure


def verify():
    if (H/'stop-host-runtime-preliminary').exists() and not os.environ.get('TF_CALIBRATION_FIXED_RUNTIME'):
        raise RuntimeError('Host runtime changed to 8u512; preliminary run stopped. Use sealed restored 8u504 runtime.')
    p = load(H/'protocol-before-calibration.json')
    for group in ('core_sources', 'public_contracts', 'files'):
        for path, digest in p[group].items():
            assert sha(Path(path)) == digest, path
    return p


def fixed_runtime(cfg):
    restored = H/'runtime-base/java-8-openjdk-amd64'
    receipt = load(H/'runtime-correction-before-fixed-calibration.json')
    for p, digest in receipt['restored_files'].items():
        assert sha(Path(p)) == digest, p
    for s in cfg['services'].values():
        s['volumes'] = [str(restored)+':'+v.split(':', 1)[1] if isinstance(v, str) and v.startswith('/usr/lib/jvm/java-8-openjdk-amd64:') else v for v in s.get('volumes', [])]
    return cfg


def work(rows):
    return {'events': len(rows),
            'boundary_scalars': sum(sum(r.get('target_observation', {}).get('scalar_fields', {}).values()) for r in rows),
            'boundary_members': sum(sum(r.get('target_observation', {}).get('container_values', {}).values()) for r in rows),
            'constructor_writes': sum(sum(r.get('execution_closure', {}).get('elided_writes', {}).values()) for r in rows),
            'ordinary_writes': sum(r['kind'] == 'write-version' for r in rows),
            'body_eligible': sum(bool(r.get('body_observation', {}).get('guard_eligible')) for r in rows),
            'body_selected': sum(bool(r.get('body_observation', {}).get('selected')) for r in rows),
            'body_reads': sum(r.get('body_observation_omissions', {}).get('field_reads', 0) for r in rows),
            'body_branches': sum(r.get('body_observation_omissions', {}).get('branches', 0) for r in rows),
            'field_hooks': next((r.get('field_hook_calls') for r in rows if r['kind'] == 'metrics'), None)}


def controlled(tier, baseline):
    import run_unrelated_work_scaling as old
    import audit_unrelated_work_scaling as audit
    import run_jvm_rule_revision as rules
    verify()
    old.H = audit.H = rules.H = H
    old.verify = audit.verify = verify
    if not (H/'protocol-before-tools.json').exists():
        shutil.copyfile(ROOT/'artifacts/unrelated-work-scaling-20261109/protocol-before-tools.json', H/'protocol-before-tools.json')
    dest = H/'controlled-build-04'/tier
    if not dest.exists():
        dest.mkdir(parents=True)
        for name in ('business.jar', 'model.json', 'schema.json', 'mt-config.json', 'plan.json'):
            shutil.copyfile(PRIOR/'controlled-build-04'/tier/name, dest/name)
    spec = old.controlled_spec
    def configured(out, task, mode, diagnostic=False):
        cfg = spec(out, task, 'selective' if mode == 'static' else mode, diagnostic)
        if mode in ('full', 'static', 'selective'):
            arm = configure(load(dest/'plan.json'), mode)
            cmd = cfg['services']['app']['command']
            cmd[:] = [a for a in cmd if not a.startswith(('-Dservice.mode=', '-Dservice.target.observation=', '-Dservice.write.observation=', '-Dservice.body.observation='))]
            at = cmd.index('-jar'); cmd[at:at] = arm['jvm_options']
            save(out/'baseline-policy.json', arm)
        return fixed_runtime(cfg)
    old.controlled_spec = configured
    out = H/'short-504'/('controlled-'+tier+'-'+baseline)
    result = old.controlled_trial(out, tier, baseline, 0, 3, 2)
    if tier == 'related-high' and baseline in ('full', 'static', 'selective'):
        score = rules.related_tf(out, baseline)
    else:
        score = audit.run(out, 'controlled', tier, 'selective' if baseline == 'static' else baseline)
    counts = work([json.loads(s) for s in (out/'capture/events.jsonl').read_text().splitlines()]) if baseline in ('full', 'static', 'selective') else {}
    save(out/'calibration.json', {'baseline': baseline, 'run': result, 'score': score,
                                 'actual_work': counts, 'short_run_no_speed_claim': True})


def galette_preflight(tier, out):
    """Original-JAR compatibility, explicitly not a source-scored baseline."""
    import run_unrelated_work_scaling as old
    verify(); old.H = H; old.verify = verify
    jar = H/'controlled-build-04'/tier/'business.jar'
    assert jar.is_file() and sha(jar) == verify()['files'][str(PRIOR/'controlled-build-04'/tier/'business.jar')]
    agent = H/'galette-original/galette-agent/target/galette-agent-1.0.0-SNAPSHOT.jar'
    spec = old.controlled_spec
    def configured(dest, task, mode, diagnostic=False):
        cfg = fixed_runtime(spec(dest, task, 'original', False)); s = cfg['services']['app']
        s['volumes'] = [v for v in s['volumes'] if v.split(':')[1] != '/approved-jdk']
        s['volumes'] += [str(H/'jdk8-galette')+':/approved-jdk:ro', str(agent)+':/tf2/galette-agent.jar:ro']
        at = s['command'].index('-jar')
        s['command'][at:at] = ['-Xbootclasspath/a:/tf2/galette-agent.jar', '-javaagent:/tf2/galette-agent.jar']
        save(dest/'compatibility-only.json', {'source_adapter': False, 'source_scoring': 'unscored; boot/business compatibility only',
              'business_jar_sha256': sha(jar), 'galette_agent_sha256': sha(agent)})
        return cfg
    old.controlled_spec = configured
    return old.controlled_trial(out, tier, 'original', 0, 3, 2)


def business(task, baseline):
    import sockshop
    verify()
    ref = ROOT/'artifacts/shared-transfer-optimization-20261106/final-candidate'
    agent = ROOT/'artifacts/pruning-contribution-audit-20261106/final-candidate/historical/frozen-base'
    actual = sockshop.Deployment
    def deployment(args, dest, compose):
        cfg = load(compose)
        for s in cfg['services'].values():
            cmd = s.get('command', [])
            if any(a.startswith('-javaagent:') and 'observer' in a for a in cmd):
                p = next(Path(v.split(':')[0]) for v in s['volumes'] if v.split(':')[1] == '/tf2/plan.json')
                policy = configure(load(p), baseline)
                cmd[:] = [a for a in cmd if not a.startswith(('-Dservice.mode=', '-Dservice.body.observation=', '-Dservice.target.observation=', '-Dservice.write.observation='))]
                cmd[cmd.index('-jar'):cmd.index('-jar')] = policy['jvm_options']
                save(dest/'baseline-policy.json', policy)
        save(compose, fixed_runtime(cfg))
        return actual(args, dest, compose)
    sockshop.Deployment = deployment
    mode = 'selective' if baseline == 'static' else baseline
    name = task+'-'+baseline
    if task == 'mall':
        import execute_unrelated_work_scaling as run
        import audit_unrelated_work_scaling as audit
        import run_frozen_locality_cost as mall
        run.H = audit.H = H; run.verify = audit.verify = verify
        shutil.copyfile(Path(verify()['tasks']['mall']['plan']), H/'mall-plan.json') if not (H/'mall-plan.json').exists() else None
        out = H/'short-business-504'/name
        import run_sockshop_cost as cost
        sampler = cost.Sampler
        class ShortSampler(sampler):
            def summary(self, *args, **kwargs):
                return {'short_correctness_only': True, 'performance_summary_not_applicable': True}
        cost.Sampler = ShortSampler
        try:
            result = run.mall_trial(out, mode, 0, 3, 2)
        finally:
            cost.Sampler = sampler
        score = audit.run(out, 'mall', '2', mode)
    else:
        import run_target_closure_cost as run
        from run_shared_work_business import verify_business
        run.Deployment = deployment
        run.FINAL = ref; run.BASE = agent; run.verify = verify; run.fresh = lambda *a: None
        out = H/'short-business-504'/name
        run.zlt_trial(out.parent, out.name, task, mode, 0, 3, sample=False)
        verify_business(out, task)
        result = load(out/'result.json')
        if mode == 'original':
            score = {'targets': sum(len(c['response']['data']) for c in load(out/'measure.json')['requests']), 'not_scored': True}
        else:
            local = out/'scoring-protocol'; local.mkdir()
            q = next(q for q in load(ref/'zlt/task-seal.json')['entries'] if q['id'] == 'ZLT-MP-4')
            save(local/'protocol-before-calibration.json', {'tasks': {task: {'query': q}}})
            run.zlt_offline(local, out, out/'independent-score', task, mode)
            score = load(out/'independent-score/summary.json')
    rows = [json.loads(s) for s in (out/'capture/events.jsonl').read_text().splitlines()] if mode in ('full', 'selective') else []
    save(out/'calibration.json', {'baseline': baseline, 'run': result, 'score': score,
                                 'actual_work': work(rows) if rows else {}, 'short_run_no_speed_claim': True})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--task', choices=('low', 'medium', 'high', 'related-high', 'mall', 'zlt-user'), required=True)
    p.add_argument('--baseline', choices=('original', 'mirrortaint', 'full', 'static', 'selective', 'galette-preflight'), required=True)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    if a.baseline == 'galette-preflight':
        if a.out is None: p.error('--out is required for compatibility preflight')
        galette_preflight(a.task, a.out.resolve())
    else:
        (business if a.task in ('mall', 'zlt-user') else controlled)(a.task, a.baseline)
