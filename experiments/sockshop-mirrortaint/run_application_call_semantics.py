#!/usr/bin/env python3
"""Real application-frame JVM semantics with separate literal independent oracle."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import HERE,save,load
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
from analysis_status import AnalysisLimit,failure_status


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    # Existing observer tools are compile dependencies only, never business replacements.
    base=HERE.parents[1]/'artifacts/call-lifecycle-revision-20261020/base-build'
    cp=':'.join(map(str,[base/'tools',*JARS]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'ApplicationCallFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'ApplicationCallFixture.root(LApplicationCallFixture$Item;LApplicationCallFixture$Item;I)LApplicationCallFixture$Item;','targets':['ApplicationCallFixture$Item.text'],'response_path':'/text','execution_kernel':True,'application_calls':True}})
    plan=load(b/'fixture/plan.json');reports={}
    # Literal expected parameter field for each original fixture mode. None is
    # intentionally unknown; empty tuple is the constant fallback, not unknown.
    expected={0:0,1:1,2:0,3:1,4:None,5:1,6:0,8:0,9:None,10:None,11:0,12:0,13:1,14:(),15:None,16:1,17:0}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'ApplicationCallFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);rows=[json.loads(x) for x in (cap/'fixture/events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='problem' for r in rows)
        graph=Reconstruction(b,cap,['fixture']);checks=[]
        for case in cases:
            if case['status']=='aborted':continue
            answer=graph.query(case['message'],'/text','fixture',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);want=expected[case['mode']]
            assert answer['known']==(want is not None),(mode,case['mode'],answer)
            if want is not None:
                truth=set()
                if want!=():
                    source=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==case['message'] and r['argument']==want)
                    field=next(f for f in source['fields'] if f['field']=='ApplicationCallFixture$Item.text');truth={(field['owner'],field['field'],field['version'])}
                assert {(s['owner'],s['field'],s['version']) for s in answer['sources']}==truth,(mode,case,answer,truth)
            checks.append({'mode':case['mode'],'known':answer['known'],'expected_argument':want,'answer':answer})
        limited=copy.deepcopy(plan);limited['execution_kernel']['step_limit']=1
        try:infer_execution(limited,rows)
        except AnalysisLimit as error:assert failure_status(error)=='analysis_limited'
        else:raise AssertionError('Budget silently truncated')
        faults={}
        for label in ('missing-child','wrong-parent','duplicate-call-id','missing-constructor-write','same-value-wrong-argument','wrong-exception'):
            altered=copy.deepcopy(rows)
            if label=='missing-child':altered.remove(next(r for r in altered if r['kind']=='enter' and r['method']!=plan['entry']))
            elif label=='wrong-parent':next(r for r in altered if r['kind']=='enter' and r['method']!=plan['entry'])['parent']='wrong-frame'
            elif label=='duplicate-call-id':
                calls=[r for r in altered if r['kind']=='collection-call-enter'];calls[1]['call_id']=calls[0]['call_id']
            elif label=='missing-constructor-write':altered.remove(next(r for r in altered if r['kind']=='write' and '.<init>' in r['site']))
            elif label=='same-value-wrong-argument':next(r for r in altered if r['kind']=='enter' and r['method']!=plan['entry'])['args'][0]['object']='same-valued-wrong-object'
            else:next(r for r in altered if r['kind']=='collection-call-throw')['exception']['object']='wrong-exception-instance'
            try:infer_execution(plan,altered)
            except ValueError:faults[label]=True
            else:raise AssertionError('Bad evidence accepted: '+label)
        reports[mode]={'targets':len(checks),'known':sum(c['known'] for c in checks),'expected_unknown':sum(not c['known'] for c in checks),'aborted':sum(c['status']=='aborted' for c in cases),'budget_status':'analysis_limited','faults':faults,'checks':checks}
        save(out/'results.json',{'all_passed':True,'modes':reports,'scope':'Controlled JVM semantics; not real-application coverage or costs.'})
        print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
