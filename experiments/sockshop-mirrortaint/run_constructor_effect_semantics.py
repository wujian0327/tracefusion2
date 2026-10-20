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
    cp=':'.join(map(str,[base/'tools',*JARS]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'ConstructorEffectFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'ConstructorEffectFixture.root(LConstructorEffectFixture$Input;LConstructorEffectFixture$Input;I)LConstructorEffectFixture$Out;','targets':['ConstructorEffectFixture$Out.text'],'response_path':'/text','execution_kernel':True,'application_calls':True}})
    plan=load(b/'fixture/plan.json');reports={}
    # Literal expected parameter field for each original fixture mode. None is
    # intentionally unknown; empty tuple is the constant fallback, not unknown.
    expected={0:0,1:0,2:1,3:1,5:0,6:1,7:None,8:0,9:1,10:0,11:0,12:None}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'ConstructorEffectFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);rows=[json.loads(x) for x in (cap/'fixture/events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='problem' for r in rows)
        graph=Reconstruction(b,cap,['fixture']);checks=[]
        for case in cases:
            if case['status']=='aborted':continue
            answer=graph.query(case['message'],'/text','fixture',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);want=expected[case['mode']]
            assert answer['target']['observed'].get('value')==case['response']['text']
            assert answer['known']==(want is not None),(mode,case['mode'],answer)
            if want is not None:
                truth=set()
                if want!=():
                    source=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==case['message'] and r['argument']==want)
                    field=next(f for f in source['fields'] if f['field']=='ConstructorEffectFixture$Input.text');truth={(case['message'],source['frame'],source['seq'],field['owner'],field['field'],field['version'],field['path'])}
                assert {(s['message'],s['root_frame'],s['seq'],s['owner'],s['field'],s['version'],s['path']) for s in answer['sources']}==truth,(mode,case,answer,truth)
            checks.append({'mode':case['mode'],'known':answer['known'],'expected_argument':want,'answer':answer})
        limited=copy.deepcopy(plan);limited['execution_kernel']['step_limit']=1
        try:infer_execution(limited,rows)
        except AnalysisLimit as error:assert failure_status(error)=='analysis_limited'
        else:raise AssertionError('Budget silently truncated')
        faults={}
        for label in ('missing-constructor-frame','wrong-constructor-parent','wrong-constructor-receiver','missing-constructor-write','missing-constructor-completion','wrong-constructor-exception','wrong-constructor-argument','missing-filter-callback','wrong-filter-member','wrong-filter-predicate','wrong-filter-result','filter-runtime-hash'):
            altered=copy.deepcopy(rows)
            ctor=next(r for r in altered if r['kind']=='enter' and '.<init>' in r['method'])
            if label=='missing-constructor-frame':altered.remove(ctor)
            elif label=='wrong-constructor-parent':ctor['parent']='wrong-parent'
            elif label=='wrong-constructor-receiver':ctor['receiver']='wrong-new-object'
            elif label=='missing-constructor-write':altered.remove(next(r for r in altered if r['kind']=='write' and r.get('frame')==ctor['frame']))
            elif label=='missing-constructor-completion':altered.remove(next(r for r in altered if r['kind']=='execution-constructed'))
            elif label=='wrong-constructor-exception':next(r for r in altered if r['kind']=='execution-constructor-throw')['exception']['object']='different-error'
            elif label=='wrong-constructor-argument':ctor['args'][0]['object']='same-value-different-input'
            elif label=='missing-filter-callback':altered.remove(next(r for r in altered if r['kind']=='enter' and r.get('callback_call_id')))
            elif label=='wrong-filter-member':next(r for r in altered if r['kind']=='enter' and r.get('callback_call_id'))['args'][-1]['object']='same-valued-wrong-member'
            elif label=='wrong-filter-predicate':next(r for r in altered if r['kind']=='collection-call-exit' and r.get('contract',{}).get('kind')=='filter-first')['contract']['predicate']='wrong-predicate'
            elif label=='wrong-filter-result':next(r for r in altered if r['kind']=='collection-call-exit' and r.get('contract',{}).get('kind')=='filter-first')['contract']['selected']['object']='wrong-selected-member'
            elif label=='filter-runtime-hash':next(r for r in altered if r['kind']=='collection-call-exit' and r.get('contract',{}).get('kind')=='stream-filter')['contract']['filter_class_sha256']='bad-hash'
            try:infer_execution(plan,altered)
            except ValueError:faults[label]=True
            else:raise AssertionError('Bad evidence accepted: '+label)
        reports[mode]={'targets':len(checks),'known':sum(c['known'] for c in checks),'expected_unknown':sum(not c['known'] for c in checks),'aborted':sum(c['status']=='aborted' for c in cases),'budget_status':'analysis_limited','faults':faults,'checks':checks}
        save(out/'results.json',{'all_passed':True,'modes':reports,'scope':'Controlled JVM semantics; not real-application coverage or costs.'})
        print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
