"""Actual JVM counterexample: later computation must force full collection.

The reference run intentionally records any old full/selective disagreement;
its failure is preserved, never recategorized as a repaired reference success.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
from zipfile import ZipFile


def run(out,source_root=None):
    actual=Path(__file__).resolve().parents[2]
    here=actual/'experiments/sockshop-mirrortaint'
    if source_root:sys.path.insert(0,str(source_root))
    from run_query_planner import command,JARS
    from run_planned_service import load,save,sha
    from build_distributed_plans import build
    from plan_capability_policy import choose
    from infer_execution_kernel import infer_execution
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    deps=sorted((actual/'artifacts/zlt-completion-slice-20261031/locality-sequence-controls-01/libs').glob('*.jar'))
    bootstrap=actual/'artifacts/zlt-completion-slice-20261031/final-candidate-01/historical/frozen-base/distributed-observer.jar'
    java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    cp=':'.join(map(str,[bootstrap,*deps,*JARS]))
    source=here/'FutureStateObservationFixture.java'
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(source)],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for p in classes.glob('FutureStateObservationFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
        for p in deps:z.write(p,'BOOT-INF/lib/'+p.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['FutureStateObservationFixture$Result.message']}})
    cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*deps,*JARS]))
    results={}
    for entry in ('root','containerFuture','forward','guarded'):
        plan,route=choose(load(b/'fixture/model.json'),{'entry':'FutureStateObservationFixture.'+entry+'(I)LFutureStateObservationFixture$Result;',
            'target':'FutureStateObservationFixture$Result.message','path':'/message',
            'source_calls':['FutureStateObservationFixture$API.fetch()LFutureStateObservationFixture$Result;']},
            deployment=load(actual/'artifacts/zlt-completion-slice-20261031/final-candidate-01/mall/deployment-environment.json'))
        plan.pop('communication_identity',None)
        directory=out/entry;directory.mkdir();save(directory/'plan.json',plan);save(directory/'route.json',route)
        prop=['-Dfixture.'+entry+'=true']if entry in ('containerFuture','forward','guarded')else[]
        baseline=json.loads(command([java,*prop,'-cp',cp,'FutureStateObservationFixture'],directory/'baseline.log').stdout.splitlines()[-1])
        modes={};captures={}
        for mode in ('full','selective'):
            cap=directory/mode;cap.mkdir()
            output=command([java,*prop,'-javaagent:'+str(b/'distributed-observer.jar'),
                '-Dservice.plan='+str(directory/'plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),
                '-Dservice.mode='+mode,'-cp',cp,'FutureStateObservationFixture'],cap/'stdout.log')
            assert json.loads(output.stdout.splitlines()[-1])==baseline
            rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];captures[mode]=rows
            assert not any(r['kind']=='problem'for r in rows)
            inference=infer_execution(plan,rows);save(cap/'inference.json',inference)
            answers=inference['answers'];assert len(answers)==len(baseline)
            expected=[]
            for case in baseline:
                ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message'])
                answer=next(a for a in answers if a['root_frame']==ret['frame'])
                if answer['known']:
                    if entry in ('root','containerFuture')or entry=='guarded'and case['mode']==1:assert answer['origins']==[]
                    else:
                        source_row=next(r for r in rows if r['kind']=='binding-source'and r.get('message')==case['message'])
                        index=next(i for i,f in enumerate(source_row['fields'])if f['field']=='FutureStateObservationFixture$Result.message')
                        assert set(map(tuple,answer['origins']))=={('field',source_row['seq'],index)}
                if not source_root:assert answer['known']==(entry!='guarded'or case['mode']not in (3,7)),(entry,mode,case,answer)
                expected.append({'case':case['mode'],'known':answer['known'],'positive':entry not in ('root','containerFuture')and not(entry=='guarded'and case['mode']==1)})
            cuts=sum(bool(r.get('body_observation',{}).get('selected'))for r in rows)
            omissions=sum(sum(r.get('target_observation',{}).get('scalar_fields',{}).values())for r in rows)
            modes[mode]={'business_equal':True,'answers':expected,'known':sum(a['known']for a in answers),
                         'body_cuts':cuts,'scalar_values_omitted':omissions,'events':len(rows),
                         'bytes':(cap/'events.jsonl').stat().st_size,'capture_sha256':sha(cap/'events.jsonl')}
        guards={}
        if not source_root:
            assert modes['full']['known']==modes['selective']['known']==(6 if entry=='guarded'else 2)
            if entry in ('root','containerFuture'):assert modes['selective']['body_cuts']==0,'Later field/container read did not fall back before omission'
            else:assert modes['selective']['body_cuts']==(3 if entry=='guarded'else 2)
            assert modes['selective']['scalar_values_omitted']>0
            assert modes['selective']['bytes']<modes['full']['bytes']
            for fault in ('missing-proof','wrong-policy','necessary-field','full-omission','missing-source','sticky-invalid'):
                bad=copy.deepcopy(captures['selective'])
                row=next(r for r in bad if r.get('target_observation',{}).get('scalar_fields'))
                if fault=='missing-proof':row.pop('target_observation')
                elif fault=='wrong-policy':row['target_observation']['policy_sha256']='wrong'
                elif fault=='necessary-field':row['target_observation']['scalar_fields']['FutureStateObservationFixture$Result.message']=1
                elif fault=='full-omission':bad[0]['mode']='full'
                elif fault=='missing-source':bad.remove(next(r for r in bad if r['kind']=='binding-source'))
                else:next(r for r in bad if r['kind']=='metrics')['capture_invalid']=True
                try:infer_execution(plan,bad)
                except ValueError:guards[fault]=True
                else:raise AssertionError(fault)
        results[entry]={'modes':modes,'guards':guards,
                        'reference_full_selective_equal':modes['full']['answers']==modes['selective']['answers']}
        save(out/'progress.json',results)
    save(out/'results.json',{'implementation':'frozen-reference'if source_root else'development',
                           'agent_sha256':sha(b/'distributed-observer.jar'),'source_fixture_sha256':sha(source),'entries':results})
    print(json.dumps(results))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--source-root',type=Path)
    a=p.parse_args();run(a.out.resolve(),a.source_root.resolve()if a.source_root else None)
