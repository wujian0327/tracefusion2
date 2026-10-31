"""Actual instrumentation cut with conservative fallback and raw-source oracle."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from build_distributed_plans import build
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    libs=ROOT/'artifacts/zlt-completion-slice-20261031/locality-sequence-controls-01/libs'
    bootstrap=ROOT/'artifacts/zlt-completion-slice-20261031/sql-controls-06/build/distributed-observer.jar'
    java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';deps=sorted(libs.glob('*.jar'))
    cp=':'.join(map(str,[bootstrap,*deps,*JARS]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'BodyObservationFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for p in classes.glob('BodyObservationFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
        for p in deps:z.write(p,'BOOT-INF/lib/'+p.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['BodyObservationFixture$Result.message']}})
    plan,route=choose(load(b/'fixture/model.json'),{'entry':'BodyObservationFixture.root(I)LBodyObservationFixture$Result;',
        'target':'BodyObservationFixture$Result.message','path':'/message',
        'source_calls':['BodyObservationFixture$API.fetch()LBodyObservationFixture$Result;']})
    assert plan['execution_kernel'].get('body_observation');plan.pop('communication_identity',None)
    save(b/'fixture/plan.json',plan);save(out/'route.json',route)
    cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*deps,*JARS]))
    baseline=json.loads(command([java,'-cp',cp,'BodyObservationFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={};captures={}
    for mode in ('full','selective'):
        cap=out/mode;cap.mkdir();observed=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),
            '-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),
            '-Dservice.mode='+mode,'-cp',cp,'BodyObservationFixture'],cap/'stdout.log')
        assert json.loads(observed.stdout.splitlines()[-1])==baseline
        rows=[json.loads(s) for s in (cap/'events.jsonl').read_text().splitlines()];captures[mode]=rows
        assert not any(r['kind']=='problem' for r in rows),[r for r in rows if r['kind']=='problem']
        answers=infer_execution(plan,rows)['answers'];assert len(answers)==8
        checks=[]
        for case in baseline:
            ret=next(r for r in rows if r['kind']=='binding-return' and r['message']==case['message'])
            answer=next(a for a in answers if a['root_frame']==ret['frame']);known=case['mode']not in (3,7)
            assert answer['known']==known,(mode,case,answer)
            source=next(r for r in rows if r['kind']=='binding-source' and r.get('message')==case['message'])
            index=next(i for i,f in enumerate(source['fields']) if f['field']=='BodyObservationFixture$Result.message')
            if known:assert set(map(tuple,answer['origins']))==(set() if case['mode']==1 else {('field',source['seq'],index)})
            decisions=[r['body_observation'] for r in rows if r['kind']=='collection-call-enter'
                       and r.get('body_observation',{}).get('root_frame')==ret['frame']]
            assert len(decisions)==1
            eligible=case['mode'] in (0,5,6)
            assert decisions[0]['guard_eligible']==eligible and decisions[0]['selected']==(eligible and mode=='selective'),(case,decisions)
            checks.append({'mode':case['mode'],'known':known,'positive':known and case['mode']!=1,'selected':decisions[0]['selected']})
        reports[mode]={'business_equal':True,'checks':checks,'event_count':len(rows),'bytes':(cap/'events.jsonl').stat().st_size}
    guards={};rows=captures['selective']
    for fault in ('missing-source-proof','wrong-cut-call','wrong-certificate','missing-mode','missing-counts','wrong-root-return','wrong-throw','missing-close','sticky-invalid'):
        bad=copy.deepcopy(rows);selected=next(r for r in bad if r.get('body_observation',{}).get('selected'))
        if fault=='missing-source-proof':bad.remove(next(r for r in bad if r['kind']=='locality-end' and r['call_id']==selected['body_observation']['source_call_id']))
        elif fault=='wrong-cut-call':selected['body_observation']['callee']='wrong'
        elif fault=='wrong-certificate':selected['body_observation']['ownership_id']=-1
        elif fault=='missing-mode':next(r for r in bad if r['kind']=='enter' and r.get('body_observation_call')==selected['call_id']).pop('body_observation_call')
        elif fault=='missing-counts':next(r for r in bad if r['kind']=='exit' and 'body_observation_omissions'in r).pop('body_observation_omissions')
        elif fault=='wrong-root-return':next(r for r in bad if r['kind']=='binding-return' and r['frame']==selected['body_observation']['root_frame'])['result']['object']='wrong'
        elif fault=='wrong-throw':next(r for r in bad if r['kind']=='collection-call-throw')['exception']['object']='wrong'
        elif fault=='missing-close':bad.remove(next(r for r in bad if r['kind']=='exit' and 'body_observation_call'in r))
        else:next(r for r in bad if r['kind']=='metrics')['capture_invalid']=True
        try:infer_execution(plan,bad)
        except ValueError:guards[fault]=True
        else:raise AssertionError(fault)
    assert reports['selective']['event_count']<reports['full']['event_count']
    save(out/'results.json',{'modes':reports,'guards':guards,'actual_new_capture':True,'offline_filtering':False,
        'agent_sha256':sha(b/'distributed-observer.jar')});print(reports,guards)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out.resolve())
