#!/usr/bin/env python3
import argparse,copy,json,sys
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from build_distributed_plans import build
from run_query_planner import command,JARS
from run_planned_service import HERE,ROOT,load,save
from plan_capability_policy import choose
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution

def run(out,agent):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();deps=out/'deps';deps.mkdir()
    jar=ROOT/'artifacts/external-frozen-transfer-20261029/78a9534/business-jars/mall-portal.jar'
    with ZipFile(jar)as z:
        for name in z.namelist():
            if name.startswith('BOOT-INF/lib/')and name.endswith('.jar')and any(x in name for x in ('/spring-aop-','/spring-core-','/spring-beans-','/spring-jcl-')):(deps/Path(name).name).write_bytes(z.read(name))
    cp=':'.join(map(str,[agent,*deps.glob('*.jar'),*JARS]));command(['/usr/lib/jvm/java-8-openjdk-amd64/bin/javac','-cp',cp,'-d',str(classes),str(HERE/'DirectDispatchFixture.java')],out/'compile.log')
    fixture=out/'fixture.jar'
    with ZipFile(fixture,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(fixture),'targets':['DirectDispatchFixture$Box.text']}})
    from contract_applicability import library_inventory
    model=load(b/'fixture/model.json');model['library_inventory']=library_inventory(jar)
    query={'entry':'DirectDispatchFixture.root(I)LDirectDispatchFixture$Box;','target':'DirectDispatchFixture$Box.text','path':'/text','source_calls':['DirectDispatchFixture$Store.read()LDirectDispatchFixture$Box;']}
    environment=load(ROOT/'artifacts/plan-applicability-revision-20261029/deployment-environment.json')
    plan,route=choose(model,query,deployment=environment);save(b/'fixture/plan.json',plan);save(out/'route.json',route)
    java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';classpath=str(classes)+':'+cp
    command([java,'-cp',classpath,'DirectDispatchFixture'],out/'baseline.txt');baseline=json.loads((out/'baseline.txt').read_text().splitlines()[-1]);reports={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',classpath,'DirectDispatchFixture'],cap/'stdout.txt')
        actual=json.loads((cap/'stdout.txt').read_text().splitlines()[-1]);assert actual==baseline
        rows=[json.loads(s)for s in (cap/'fixture/events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows)
        replay=infer_execution(plan,rows);checks=[]
        for c in actual:
            if c['status']=='exceptional':assert c['same_exception'];continue
            ret=next(r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']);answer=next(a for a in replay['answers']if a['root_frame']==ret['frame']and a['path']=='/text');expected_known=c['mode']==0
            assert answer['known']==expected_known,(mode,c['mode'],answer['known'])
            if expected_known:
                source=next(r for r in rows if r['kind']=='binding-source'and r.get('message')==c['message']);f=next(f for f in source['fields']if f['field']=='DirectDispatchFixture$Box.text')
                index=source['fields'].index(f);assert set(map(tuple,answer['origins']))=={('field',source['seq'],index)}
            checks.append({'mode':c['mode'],'known':answer['known']})
        guards={}
        for name in ('wrong-call','wrong-target','wrong-class','nonempty-chain','wrong-argument','duplicate-proof','missing-proof','missing-framework','wrong-source-call','missing-source','ambiguous-source'):
            altered=copy.deepcopy(rows);fact=next(r for r in altered if r['kind']=='execution-direct-dispatch')
            if name=='wrong-call':fact['call_id']=-1
            elif name=='wrong-target':fact['target']='wrong-object'
            elif name=='wrong-class':fact['target_sha256']='wrong-hash'
            elif name=='nonempty-chain':fact['empty_chain']=False
            elif name=='wrong-argument':fact['args']=[{'value':100}]
            elif name=='duplicate-proof':altered.insert(altered.index(fact)+1,copy.deepcopy(fact))
            elif name=='missing-proof':altered.remove(fact)
            elif name=='missing-framework':altered.remove(next(r for r in altered if r['kind']=='direct-dispatch-framework'))
            elif name=='wrong-source-call':next(r for r in altered if r['kind']=='binding-source')['source_call_id']=-1
            elif name=='missing-source':altered.remove(next(r for r in altered if r['kind']=='binding-source'))
            elif name=='ambiguous-source':
                source=next(r for r in altered if r['kind']=='binding-source');altered.insert(altered.index(source)+1,copy.deepcopy(source))
            try:
                replay=infer_execution(plan,altered)
                assert name in ('missing-proof','missing-source','ambiguous-source')and all(not a['known']for a in replay['answers']if a['root_frame']==fact['frame'])
            except ValueError:pass
            guards[name]=True
        reports[mode]={'business_same':True,'known_positive':sum(c['known']for c in checks),'unknown':sum(not c['known']for c in checks),'same_business_exception':2,'guards':guards,'checks':checks}
    save(out/'results.json',{'all_passed':True,'scope':'Invocation-only proxy/source control; no synthetic HTTP evidence','modes':reports});print({m:{k:v for k,v in x.items()if k!='checks'}for m,x in reports.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.agent.resolve())
