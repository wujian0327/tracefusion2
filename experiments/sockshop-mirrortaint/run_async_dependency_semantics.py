#!/usr/bin/env python3
"""Independent argument-instance truth for worker replay, joins and mutation protection."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
from analysis_status import AnalysisLimit
import run_response_binding_revision as old


def run(out,libs):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    runtime_cp=':'.join(map(str,[*JARS,*sorted(libs.glob('*.jar'))]));compile_cp=runtime_cp+':'+str(ROOT/'artifacts/async-protocol-revision-20261021/base-build/tools')
    command(['javac',*java8_target()[1],'-cp',compile_cp,'-d',str(classes),str(HERE/'AsyncDependencyFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'AsyncDependencyFixture.root(LAsyncDependencyFixture$Worker;Ljava/lang/String;Ljava/lang/String;LAsyncDependencyFixture$Out;I)LAsyncDependencyFixture$Out;','targets':['AsyncDependencyFixture$Out.text'],'response_path':'/text','execution_kernel':True,'application_calls':True,'async_dependencies':True}})
    plan=load(b/'fixture/plan.json');expected={0:[1],1:[1],2:[],3:[2],4:None,5:None,6:None,7:None,8:[],9:None,10:[1],11:[],12:[1],13:[2],14:None};reports={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+runtime_cp,'AsyncDependencyFixture'],cap/'stdout.log')
        cases=json.loads((cap/'stdout.log').read_text().splitlines()[-1]);g=Reconstruction(b,cap,['fixture']);checks=[]
        for c in cases:
            answer=g.query(c['message'],'/text','fixture',boundary=old.BOUNDARY);want=expected[c['mode']]
            if c['mode']==12:assert c['response']['text']=='pre:SAME'
            assert answer['known']==(want is not None),(mode,c,answer)
            if want is not None:
                actual={old.predicted_coord(s) for s in answer['sources']}
                selected={int(s['field'].split(':')[1]) for s in answer['sources'] if s.get('kind')=='argument'}
                # Root entry argument coordinates, never worker parameters.
                assert selected==set(want) and len(actual)==len(want),(mode,c,answer,want)
                root=next(r for r in g.rows['fixture'] if r['kind']=='binding-return' and r.get('message')==c['message'])
                assert all(s['root_frame']==root['frame'] for s in answer['sources']),(c,answer)
            checks.append({'case':c,'expected_root_arguments':want,'answer':answer})
        rows=g.rows['fixture'];faults={}
        first_wire=next(r for r in rows if r['kind']=='http-json' and r.get('phase')=='write')
        prefix=[r for r in rows if r['seq']<=first_wire['seq']]
        first=infer_execution(plan,prefix)['roots'][0]
        assert first['steps_including_tasks']>first['steps']
        limited=copy.deepcopy(plan);limited['execution_kernel']['step_limit']=first['steps']
        try:infer_execution(limited,prefix)
        except AnalysisLimit:budget_status='analysis_limited'
        else:raise AssertionError('Worker execution steps not included in request budget')
        for label in ('missing-payload-witness','wrong-payload-object','wrong-wrapper-hash','missing-worker-write','same-value-wrong-get','missing-get-proof'):
            changed=copy.deepcopy(rows)
            if label=='missing-payload-witness':del next(r for r in changed if r.get('async_result'))['async_result']
            elif label=='wrong-payload-object':next(r for r in changed if r.get('async_result'))['async_result']['payload']['object']='wrong-object'
            elif label=='wrong-wrapper-hash':next(r for r in changed if r.get('async_result'))['async_result']['class_sha256']='wrong'
            elif label=='missing-worker-write':
                frames={r['frame'] for r in changed if r['kind']=='enter' and r.get('async_task_id')};changed.remove(next(r for r in changed if r['kind']=='write' and r.get('frame') in frames))
            elif label=='same-value-wrong-get':next(r for r in changed if r.get('async_future',{}).get('completion')=='normal' and r['async_future']['operation']=='get')['result']['object']='wrong-object'
            else:del next(r for r in changed if r.get('async_future'))['async_future']
            try:infer_execution(plan,changed)
            except ValueError:faults[label]=True
            else:raise AssertionError('Accepted '+label)
        reports[mode]={'targets':len(checks),'known_exact':sum(x['answer']['known'] for x in checks),'expected_unknown':sum(not x['answer']['known'] for x in checks),'faults':faults,'budget_status':budget_status,'checks':checks}
        save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--libs',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.libs.resolve())
