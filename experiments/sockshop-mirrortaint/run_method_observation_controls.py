"""Raw method observations plus literal provenance; fixed-graph identity stress."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,save,load,sha
from run_query_planner import command,JARS
from run_generic_observation_rules import metadata_build
from tf_static_baseline import configure
from plan_capability_policy import choose
from run_public_control_semantics import checked
from method_value_protocol import validate


def run(out,agent,stress_only=False):
    out.mkdir(parents=True,exist_ok=False);save(out/'protocol-before-jvm.json',{'fixture_sha256':sha(HERE/'MethodObservationFixture.java'),'Agent_sha256':sha(agent),'expected':'Eight identity primitive functions; reference identity preserves argument, two equal/distinct Integer and Long; null,void; mixed returns int arg; constructor preserves int source. Source Datum.value, selectors empty, Out version1. Stress 2x200 probes, after warmup no new graph objects.'})
    java=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java';classes=out/'classes';classes.mkdir();deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'));cp=':'.join(map(str,[classes,agent,*JARS,*deps]))
    command([str(java.with_name('javac')),'-cp',cp,'-d',str(classes),str(HERE/'MethodObservationFixture.java')],out/'compile.log');jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    metadata_build(out/'build',{'fixture':{'jar':str(jar),'targets':['MethodObservationFixture$Out.value']}})
    model=load(out/'build/fixture/model.json');entry='MethodObservationFixture.root(LMethodObservationFixture$Store;Ljava/lang/Integer;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/RuntimeException;)LMethodObservationFixture$Out;'
    plan,route=choose(model,{'entry':entry,'target':'MethodObservationFixture$Out.value','path':'/value','source_calls':['MethodObservationFixture$Store.read()LMethodObservationFixture$Datum;']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);plan=load(out/'plan.json');save(out/'route.json',route)
    reports=[]
    for mode in ('full','static','selective'):
        directory=out/mode;directory.mkdir();policy=configure(plan,mode);save(directory/'policy.json',policy)
        cmd=[str(java),'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(directory/'events.jsonl'),*policy['jvm_options'],'-cp',cp,'MethodObservationFixture',*(['stress']if stress_only else[])];save(directory/'command.json',cmd)
        printed=json.loads(command(cmd,directory/'stdout.log').stdout.splitlines()[-1]);rows=[json.loads(l)for l in(directory/'events.jsonl').read_text().splitlines()]
        if stress_only:
            save(directory/'counts.json',printed);growth=[printed[i]['IDS']-printed[i-1]['IDS']for i in (1,2)]
            if rows[0].get('method_value_version'):validate(plan,rows);assert growth==[0,0],growth
            reports.append({'mode':mode,'growth':growth,'counts':printed});continue
        assert printed=={'value':1000000}
        source=next(r for r in rows if r['kind']=='binding-source');index=next(i for i,f in enumerate(source['fields'])if f['field']=='MethodObservationFixture$Datum.value');truth={'origins':[['field',source['seq'],index]],'selectors':[],'version':1,'known':True};save(directory/'truth-before-prediction.json',truth)
        result=checked(plan,rows);save(directory/'prediction.json',result);answer=result['answers'][0];assert all(answer[k]==v for k,v in truth.items()),answer
        entries={r['frame']:r for r in rows if r['kind']=='enter'};primitive=set();refs=[]
        for r in rows:
            if r['kind']!='exit':continue
            start=entries[r['frame']];name=start['method'].split('.')[1].split('(')[0]
            if name in ('z','b','c','s','i','j','f','d'):
                assert start['args'][0]==r['result'];primitive.add(start['args'][0]['primitive'])
            elif name in ('integer','longer','object'):
                assert start['args'][0]==r['result'] and 'primitive'not in r['result'];refs.append(r['result']['object'])
            elif name=='mixed':assert start['args'][4]==r['result']
            elif name=='empty':assert r['result']=={'object':None,'value':None,'void':True}
        captures=[r['captures'][0]for r in rows if r['kind']=='execution-lambda'];assert len(captures)==2 and 'primitive'in captures[0] and captures[1]['object']is not None and 'primitive'not in captures[1]
        assert primitive==set('ZBCSIJFD') and len(set(x for x in refs if x))>=5 and None in refs
        reports.append({'mode':mode,'complete_correct':True,'eight_primitive_types':sorted(primitive),'real_reference_ids':refs,'normal_and_exceptional':True})
    save(out/'results.json',{'reports':reports,'gate':True,'stress':stress_only,'Agent_sha256':sha(agent)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--agent',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--stress-only',action='store_true');a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.stress_only)
