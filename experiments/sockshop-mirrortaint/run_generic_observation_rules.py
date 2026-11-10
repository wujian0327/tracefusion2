"""Frozen-binary rule controls; no collector compilation or contract changes."""
import argparse
import hashlib
import json
import shutil
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from run_planned_service import ROOT, HERE, load, save, sha
from run_query_planner import JARS, command

FROZEN = ROOT/'artifacts/pruning-contribution-audit-20261106/final-candidate/historical'
AGENT = FROZEN/'frozen-base/distributed-observer.jar'
COMMIT = 'bcdf0590d1b22ea13717afded657a062f070e1df'
JAVA = '/usr/lib/jvm/java-8-openjdk-amd64/bin/java'


def verify():
    freeze = load(FROZEN/'algorithm-freeze.json')
    revised = HERE/'infer_execution_closure.py'
    assert sha(revised) == '0f87dbd6062afc5289a149951217038dd2381648952a3a65689155502896f74a'
    for path, digest in freeze['sources'].items():
        if Path(path) != revised:
            assert sha(Path(path)) == digest, path
    assert sha(AGENT) == '367cbb2300e507e5db4716c4e2fcbed1a39898c5e6c6f5f23583c4c1487e2764'
    return {'core': COMMIT, 'sources': freeze['sources'], 'agent': str(AGENT),
            'agent_sha256': sha(AGENT), 'core_changed': True,
            'only_offline_change': {str(revised): sha(revised)},
            'contracts': {p: h for p, h in freeze['sources'].items() if p.endswith('.json')},
            'jdk': {str(p): sha(p) for p in (Path(JAVA), Path(JAVA).parents[1]/'jre/lib/rt.jar', Path(JAVA).parents[1]/'jre/lib/amd64/server/libjvm.so')}}


def metadata_build(out, inputs):
    """Extract original bytecode; reuse the exact frozen collector and model tool."""
    from contract_applicability import library_inventory
    from plan_distributed_fields import augment
    from plan_response_binding import plan_response
    from plan_date_projection import attach_date_projection
    out.mkdir(parents=True, exist_ok=False)
    tools = out/'tools'; tools.mkdir()
    for f in (FROZEN/'frozen-base/tools').glob('*.class'):
        shutil.copyfile(f, tools/f.name)
    shutil.copyfile(AGENT, out/'distributed-observer.jar')
    manifest = {'agent_sha256': sha(AGENT), 'inputs': {}, 'build_kind': 'metadata-only, frozen binary'}
    for role, cfg in inputs.items():
        source = Path(cfg['jar']).resolve(); dest = out/role; app = dest/'app'
        app.mkdir(parents=True)
        wanted = set(cfg.get('bytecode_dependencies', [])) | {t.rsplit('.', 1)[0].replace('.', '/') for t in cfg.get('targets', [])}
        with ZipFile(source) as z:
            for n in z.namelist():
                if n.startswith('BOOT-INF/classes/') and n.endswith('.class'):
                    p = app/n[len('BOOT-INF/classes/'):]; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(z.read(n))
                elif n.startswith('BOOT-INF/lib/') and n.endswith('.jar'):
                    with ZipFile(BytesIO(z.read(n))) as dep:
                        for owner in wanted:
                            if owner+'.class' in dep.namelist():
                                p = app/(owner+'.class'); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(dep.read(owner+'.class'))
        command([JAVA, '-cp', ':'.join(map(str, [tools, *JARS])), 'QueryBytecodeModel', str(app), str(dest/'model.json')], dest/'model.log')
        model = load(dest/'model.json'); model['library_inventory'] = library_inventory(source); save(dest/'model.json', model)
        local = None
        if cfg.get('entry'):
            local = plan_response(model, cfg['entry'], cfg['targets'][0], cfg['response_path'], cfg.get('source_calls'), cfg.get('read_forward_contracts', False), cfg.get('execution_kernel', False), cfg.get('application_calls', False))
        plan = attach_date_projection(augment(model, local), model)
        save(dest/'plan.json', plan); shutil.copyfile(source, dest/'original.jar')
        manifest['inputs'][role] = {'original_jar_sha256': sha(source), 'plan_sha256': sha(dest/'plan.json')}
    save(out/'build.json', manifest)


def controls(out):
    out.mkdir(parents=True, exist_ok=False)
    save(out/'freeze.json', verify())
    save(out/'protocol.json', {'before_controls': True, 'oracle': 'Literal fixture modes plus raw binding source/input object, field, version, slot and call facts; never TF graph.',
         'cases': ['same-value-distinct-source', 'constant-overwrite', 'null-and-scalar', 'callback-write-and-exception', 'target-write-full', 'unrelated-write-version', 'guard-fallback', 'corruption-rejected'],
         'offline_projection': 'Only existing licenses with facts available before omission; otherwise not-testable. No forged header, completion or guard.'})
    import check_member_state_transfer
    check_member_state_transfer.run()
    import run_remove_if_controls as removal
    removal.build = metadata_build; removal.run(out/'remove-if')
    import run_json_list_copy_controls as copying
    copying.build = metadata_build
    business = ROOT/'artifacts/target-closure-revision-20261103/external-candidates/ruoyi-cloud/ruoyi-modules/ruoyi-system/target/ruoyi-modules-system.jar'
    copying.run(out/'json-copy', AGENT, business)
    copying.run(out/'json-copy-cold', AGENT, business, cold=True)
    import run_application_call_semantics as calls
    calls.build = metadata_build
    import run_application_write_cut as writes
    writes.run(out/'write-values')
    member_slots(out/'member-slots')
    guard_off(out/'write-guard-off')
    save(out/'completed.json', {'core_verification': verify(), 'all_runners_passed': True, 'scope': 'New frozen-Agent JVM controls, no performance measurements.'})


def guard_off(out):
    import run_application_call_semantics as calls
    from plan_capability_policy import choose
    original_build, original_command = calls.build, calls.command
    def build(dest, inputs):
        metadata_build(dest, inputs); c = inputs['fixture']
        plan, _ = choose(load(dest/'fixture/model.json'), {'entry': c['entry'], 'target': c['targets'][0], 'path': c['response_path']})
        save(dest/'fixture/plan.json', plan)
    def command_with_guard(cmd, log):
        if any(str(v).startswith('-javaagent:') for v in cmd):
            cmd = [cmd[0], '-Dservice.write.observation=false', *cmd[1:]]
        return original_command(cmd, log)
    calls.build, calls.command = build, command_with_guard
    try:
        calls.run(out)
        rows = [json.loads(s) for s in (out/'selective/fixture/events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='write-version' for r in rows)
    finally:
        calls.build, calls.command = original_build, original_command


def member_slots(out):
    from plan_capability_policy import choose
    from infer_execution_kernel import infer_execution
    out.mkdir(parents=True, exist_ok=False); classes = out/'classes'; classes.mkdir()
    cp = ':'.join(map(str, [classes, AGENT, *JARS]))
    command([JAVA[:-4]+'javac', '-cp', cp, '-d', str(classes), str(HERE/'MemberIdentityRuleFixture.java')], out/'compile.log')
    jar = out/'fixture.jar'
    with ZipFile(jar, 'w') as z:
        for f in classes.glob('*.class'): z.write(f, 'BOOT-INF/classes/'+f.name)
    metadata_build(out/'build', {'fixture': {'jar': str(jar), 'targets': ['MemberIdentityRuleFixture$Out.text']}})
    plan, route = choose(load(out/'build/fixture/model.json'), {'entry': 'MemberIdentityRuleFixture.root(LMemberIdentityRuleFixture$Store;I)LMemberIdentityRuleFixture$Out;', 'target': 'MemberIdentityRuleFixture$Out.text', 'path': '/text', 'source_calls': ['MemberIdentityRuleFixture$Store.read(I)LMemberIdentityRuleFixture$Out;']})
    save(out/'plan.json', plan); save(out/'route.json', route)
    baseline = json.loads(command([JAVA, '-cp', cp, 'MemberIdentityRuleFixture'], out/'baseline.log').stdout.splitlines()[-1]); reports = {}
    for mode in ('full', 'selective'):
        dest = out/mode; dest.mkdir()
        cases = json.loads(command([JAVA, '-javaagent:'+str(AGENT), '-Dservice.plan='+str(out/'plan.json'), '-Dservice.mode='+mode, '-Dservice.events='+str(dest/'events.jsonl'), '-cp', cp, 'MemberIdentityRuleFixture'], dest/'stdout.log').stdout.splitlines()[-1])
        assert cases == baseline
        rows = [json.loads(s) for s in (dest/'events.jsonl').read_text().splitlines()]
        answers = infer_execution(plan, rows)['answers']; assert len(answers)==4
        expected = []
        for case, answer in zip(cases, answers):
            reads = [r for r in rows if r['kind']=='binding-source' and r.get('message')==case['message']]
            assert len(reads)==3
            source = reads[min(case['case'], 2)]
            slot = next(i for i, f in enumerate(source['fields']) if f['field']=='MemberIdentityRuleFixture$Out.text')
            truth = [] if case['case']==3 else [['field', source['seq'], slot]]
            assert answer['known'] and answer['origins']==truth, (case, answer, truth)
            expected.append({'case': case['case'], 'oracle': truth, 'answer': answer})
        reports[mode] = expected
    save(out/'results.json', reports)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--stage', choices=['all', 'member-slots', 'guard-off'], default='all')
    a = p.parse_args(); {'all': controls, 'member-slots': member_slots, 'guard-off': guard_off}[a.stage](a.out.resolve())
