"""Actual JVM predicates, same values/different reads, and deferred failures."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from build_distributed_plans import build
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'));cp=':'.join(map(str,[classes,ROOT/'artifacts/ruoyi-request-scope-20261104/final-03/candidate/distributed-observer.jar',*JARS,*deps]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'RemoveIfFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for p in classes.glob('*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['RemoveIfFixture$Box.text']}})
    plan,_=choose(load(b/'fixture/model.json'),{'entry':'RemoveIfFixture.root(LRemoveIfFixture$Store;ILjava/util/function/Predicate;)LRemoveIfFixture$Out;','target':'RemoveIfFixture$Box.text','path':'/items/*/text','source_calls':['RemoveIfFixture$Store.read(I)LRemoveIfFixture$Box;']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);agent=b/'distributed-observer.jar';classpath=':'.join(map(str,[classes,agent,*JARS,*deps]));baseline=json.loads(command([java,'-cp',classpath,'RemoveIfFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
    for mode in('full','selective'):
        d=out/mode;d.mkdir();actual=json.loads(command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),'-Dservice.mode='+mode,'-cp',classpath,'RemoveIfFixture'],d/'stdout.log').stdout.splitlines()[-1]);assert [{k:v for k,v in r.items()if k!='message'}for r in actual]==baseline
        rows=[json.loads(x)for x in(d/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem']
        result=infer_execution(plan,rows);checks=[]
        for case in actual:
            if case['case']==6:assert len(case['items'])==3;continue
            ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message']);answers=[a for a in result['answers']if a['root_frame']==ret['frame']and a['field']=='RemoveIfFixture$Box.text']
            expected={0:[1],1:[0],2:[0,1],3:[],4:[None,1],5:[0,1],7:['unknown','unknown']}[case['case']];assert len(answers)==len(expected)
            reads=[r for r in rows if r['kind']=='binding-source'and r.get('message')==case['message']and r['callee'].startswith('RemoveIfFixture$Store.read')]
            assert len(reads)==2
            for answer,index in zip(answers,expected):
                if index=='unknown':assert not answer['known'];continue
                assert answer['known'],(mode,case,answer)
                wanted=[]if index is None else [['field',reads[index]['seq'],next(i for i,f in enumerate(reads[index]['fields'])if f['field']=='RemoveIfFixture$Box.text')]]
                assert answer['origins']==wanted,(mode,case,answer,wanted)
            checks.append({'case':case['case'],'targets':len(answers),'known':sum(a['known']for a in answers)})
        guards=[]
        for fault in('missing-proof','wrong-members','wrong-predicate','wrong-modcount','missing-callback','duplicate-callback'):
            altered=copy.deepcopy(rows);start=next(r for r in altered if r['kind']=='collection-call-enter'and'remove_if_start'in r);finish=next(r for r in altered if r['kind']=='collection-call-exit'and r.get('call_id')==start['call_id']);callback=next(r for r in altered if r['kind']=='enter'and r.get('callback_call_id')==start['call_id'])
            if fault=='missing-proof':finish.pop('remove_if')
            elif fault=='wrong-members':finish['remove_if']['after']['elements']=[]
            elif fault=='wrong-predicate':start['remove_if_start']['predicate']={'object':'wrong'}
            elif fault=='wrong-modcount':finish['remove_if']['after']['mod_count']+=1
            elif fault=='missing-callback':altered.remove(callback)
            else:altered.insert(altered.index(callback),copy.deepcopy(callback))
            try:infer_execution(plan,altered)
            except ValueError:guards.append(fault)
            else:raise AssertionError(fault)
        reports[mode]={'business_equal':True,'checks':checks,'CME_callback_append_preserved':True,'guards':guards}
    unsupported=[]
    baseline_bad=json.loads(command([java,'-cp',classpath,'RemoveIfFixture','unsupported'],out/'baseline-unsupported.log').stdout.splitlines()[-1])
    for mode in('full','selective'):
        d=out/(mode+'-unsupported');d.mkdir()
        actual=json.loads(command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),'-Dservice.mode='+mode,'-cp',classpath,'RemoveIfFixture','unsupported'],d/'stdout.log').stdout.splitlines()[-1]);assert actual==baseline_bad
        rows=[json.loads(x)for x in(d/'events.jsonl').read_text().splitlines()];assert any(r['kind']=='problem'for r in rows)and next(r for r in rows if r['kind']=='metrics')['capture_invalid']
        unsupported.append({'mode':mode,'business_equal':True,'no_extra_iterator':True,'capture_invalid':True})
    save(out/'results.json',{'agent_sha256':sha(agent),'modes':reports,'unsupported_subclass':unsupported});print(reports,unsupported,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
