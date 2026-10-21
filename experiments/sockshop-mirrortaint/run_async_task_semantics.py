#!/usr/bin/env python3
"""Pinned real Spring tasks, independent lifecycle scenarios and evidence mutations."""
import argparse, copy, json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command, JARS
from run_planned_service import ROOT, HERE, load, save
from infer_async_protocol import validate_async_protocol


def run(out, libs):
    out.mkdir(parents=True, exist_ok=False)
    classes = out/'classes'; classes.mkdir()
    runtime_cp = ':'.join(map(str, [*JARS, *sorted(libs.glob('*.jar'))]))
    cp = runtime_cp+':'+str(ROOT/'artifacts/orders-foundation-revision-20261021/final-validation-build/tools')
    command(['javac', *java8_target()[1], '-cp', cp, '-d', str(classes),
             str(HERE/'AsyncTaskFixture.java')], out/'compile.log')
    jar = out/'fixture.jar'
    with ZipFile(jar, 'w') as z:
        for f in classes.glob('*.class'): z.write(f, 'BOOT-INF/classes/'+f.name)
    b = out/'build'
    build(b, {'fixture': {'jar': str(jar), 'entry': 'AsyncTaskFixture.root(LAsyncTaskFixture$Worker;LAsyncTaskFixture$Item;LAsyncTaskFixture$Item;I)LAsyncTaskFixture$Out;',
                         'targets': ['AsyncTaskFixture$Out.text'], 'response_path': '/text',
                         'execution_kernel': True, 'application_calls': True, 'async_evidence': True}})
    plan = load(b/'fixture/plan.json'); results = {}
    for mode in ('full', 'selective'):
        cap=out/mode; cap.mkdir()
        command(['java', '-javaagent:'+str(b/'distributed-observer.jar'),
                 '-Dservice.plan='+str(b/'fixture/plan.json'), '-Dservice.mode='+mode,
                 '-Dservice.events='+str(cap/'events.jsonl'), '-cp',str(classes)+':'+runtime_cp,
                 'AsyncTaskFixture'], cap/'stdout.log')
        cases=json.loads((cap/'stdout.log').read_text().splitlines()[-1])
        assert [c['status'] for c in cases] == ['normal','exceptional','normal','normal','normal','exceptional','normal','exceptional','normal']
        rows=[json.loads(s) for s in (cap/'events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='problem' for r in rows)
        audit=validate_async_protocol(plan,rows)
        assert len(audit['tasks'])==15, len(audit['tasks'])
        assert sum(t['status']=='submission_rejected' for t in audit['tasks'])==1
        assert sum(t['status']=='worker_exceptional' for t in audit['tasks'])==1
        assert sum(t['status']=='not_started' for t in audit['tasks'])==1
        faults={}
        labels=('missing-worker-completion','wrong-task-id','wrong-worker-object','wrong-argument-object',
                'wrong-outer-future','wrong-inner-future','wrong-unwrapped-result','wrong-get-result',
                'wrong-runtime-hash','wrong-framework-hash','wrong-failure-cause','missing-submission','missing-get-proof','same-value-other-task')
        for label in labels:
            changed=copy.deepcopy(rows)
            if label=='missing-worker-completion': changed.remove(next(r for r in changed if r['kind']=='async-worker-end'))
            elif label=='wrong-task-id': next(r for r in changed if r.get('async_future') and r['async_future']['task_id'])['async_future']['task_id']=-1
            elif label=='wrong-worker-object': next(r for r in changed if r['kind']=='enter' and r.get('async_task_id'))['receiver']='wrong-object'
            elif label=='wrong-argument-object': next(r for r in changed if r['kind']=='async-submit-begin')['args'][0]['object']='wrong-same-value-object'
            elif label=='wrong-outer-future': next(r for r in changed if r['kind']=='async-submit-end')['future']['object']='wrong-future'
            elif label=='wrong-inner-future': next(r for r in changed if r['kind']=='async-worker-inner')['inner']['object']='wrong-inner'
            elif label=='wrong-unwrapped-result': next(r for r in changed if r['kind']=='async-worker-unwrapped')['result']['object']='wrong-result'
            elif label=='wrong-get-result': next(r for r in changed if r.get('async_future') and r['async_future']['completion']=='normal' and r['async_future']['operation']=='get')['result']['object']='wrong-get'
            elif label=='wrong-runtime-hash': next(r for r in changed if r['kind']=='async-runtime')['class_sha256']['java/util/concurrent/FutureTask']='wrong'
            elif label=='wrong-framework-hash': next(r for r in changed if r['kind']=='async-framework')['sha256']='wrong'
            elif label=='wrong-failure-cause': next(r for r in changed if r.get('async_future',{}).get('exception_type')=='java.util.concurrent.ExecutionException')['async_future']['cause']['object']='wrong-error'
            elif label=='missing-submission': changed.remove(next(r for r in changed if r['kind']=='async-submit-begin'))
            elif label=='missing-get-proof': del next(r for r in changed if r.get('async_future') and r['async_future']['operation']=='get')['async_future']
            else:
                gets=[r for r in changed if r.get('async_future') and r['async_future']['completion']=='normal' and r['async_future']['operation']=='get']
                gets[0]['result']=copy.deepcopy(next(r for r in gets if r['async_future']['task_id'] != gets[0]['async_future']['task_id'])['result'])
            try: validate_async_protocol(plan,changed)
            except ValueError: faults[label]=True
            else: raise AssertionError('Accepted '+label)
        results[mode]={'cases':cases,'audit':audit,'faults':faults,'source_accuracy':'N/A: lifecycle protocol only, no origins inferred'}
        save(out/'results.json',{'all_passed':True,'modes':results})
        print(mode,len(audit['tasks']),len(faults),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--libs',type=Path,required=True)
    a=p.parse_args();run(a.out.resolve(),a.libs.resolve())
