"""Physical JSON source facts and Long narrowing: original JVM execution, separate truth rules."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from build_distributed_plans import build
from plan_capability_policy import choose
from contract_applicability import library_inventory
from infer_execution_kernel import infer_execution
from infer_json_tree_observation import validate
from audit_zlt_foundation_revision import tf_pair

def run(out,agent,business):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();deps=out/'deps';deps.mkdir()
    with ZipFile(business)as z:
        for n in z.namelist():
            if n.startswith('BOOT-INF/lib/')and '/fastjson2-'in n:(deps/Path(n).name).write_bytes(z.read(n))
    cp=':'.join(map(str,[classes,agent,*JARS,*deps.glob('*.jar')]))
    java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';reports={}
    for name in ('JsonTreeObservationFixture','LongNarrowingFixture','LongRenderFixture'):
        d=out/name;d.mkdir();command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/(name+'.java'))],d/'compile.log')
        jar=d/'fixture.jar'
        with ZipFile(jar,'w')as z:
            for f in classes.glob(name+'*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
        numeric=name.startswith('Long');render=name=='LongRenderFixture';target=name+'$Out.'+('value'if numeric else'text');b=d/'build';build(b,{'fixture':{'jar':str(jar),'targets':[target]}})
        model=load(b/'fixture/model.json');model['library_inventory']=library_inventory(business)
        entry=name+'.root(L'+name+'$Store;'+('JI'if numeric else'I')+')L'+name+'$Out;'
        source=name+'$Store.read('+('J'if numeric else'I')+')'+('L'+name+'$Source;'if numeric else'Ljava/lang/Object;')
        plan,_=choose(model,{'entry':entry,'target':target,'path':'/value'if numeric else'/text','source_calls':[source]},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'));save(d/'plan.json',plan)
        baseline=json.loads(command([java,'-cp',cp,name],d/'baseline.log').stdout.splitlines()[-1]);modes={}
        for mode in ('full','selective'):
            cap=d/mode;cap.mkdir();cmd=[java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(d/'plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,name]
            actual=json.loads(command(cmd,cap/'stdout.log').stdout.splitlines()[-1]);assert[{k:v for k,v in r.items()if k not in ('message','members')}for r in actual]==baseline
            rows=[json.loads(x)for x in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows)
            validate(plan,rows);sources=[r for r in rows if r['kind']=='binding-source'and r['callee']==source]
            for s in sources:tf_pair(rows,s)
            if numeric:
                result=infer_execution(plan,rows)
                for i,c in enumerate(actual):
                    assert c['response']==(str(c['input'])if render else(c['input']+2**31)%2**32-2**31)
                    ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==c['message']);answer=next(a for a in result['answers']if a['root_frame']==ret['frame']and a['path']=='/value')
                    if i==9:assert not answer['known'];continue
                    s=next(s for s in sources if s['message']==c['message']);field=next(j for j,f in enumerate(s['fields'])if f['field']==name+'$Source.value');assert answer['known']and answer['origins']==[['field',s['seq'],field]]
                guards=[]
                if render:
                    for fault in ('wrong-long-render-hash','wrong-decimal-render','missing-long-render-proof'):
                        altered=copy.deepcopy(rows);finish=next(r for r in altered if r.get('scalar_contract',{}).get('boxed_long_sha256'))
                        if fault=='wrong-long-render-hash':finish['scalar_contract']['boxed_long_sha256']='wrong'
                        elif fault=='wrong-decimal-render':finish['scalar_contract']['after']='WRONG'
                        else:finish['scalar_contract'].pop('boxed_long_sha256')
                        try:infer_execution(plan,altered)
                        except ValueError:guards.append(fault)
                        else:raise AssertionError(fault)
                else:
                    for fault in ('wrong-narrowed-value','wrong-narrowed-type','wrong-return-class','wrong-long-runtime','missing-unbox-proof'):
                        altered=copy.deepcopy(rows);start=next(r for r in altered if r['kind']=='collection-call-enter'and r['callee']=='java/lang/Long.intValue()I');finish=next(r for r in altered if r['kind']=='collection-call-exit'and r['call_id']==start['call_id'])
                        if fault=='wrong-narrowed-value':finish['result']['value']+=1
                        elif fault=='wrong-narrowed-type':finish['result']['value']=False
                        elif fault=='wrong-return-class':finish['result_type']='java.lang.Long'
                        elif fault=='wrong-long-runtime':finish['sequence_value']['class_sha256']['java/lang/Long']='wrong'
                        else:finish.pop('sequence_value')
                        try:infer_execution(plan,altered)
                        except ValueError:guards.append(fault)
                        else:raise AssertionError(fault)
                modes[mode]={'business_equal':True,'positive_known':9,'necessary_unknown':1,'signed_extremes_and_repeated_value_origins':True,'guards':guards}
            else:
                assert len(sources)==2
                s=next(s for s in sources if s['message']==actual[0]['message']);assert len(s['fields'])==4
                for j,owner in enumerate(actual[0]['members']):
                    fields=[f for f in s['fields']if f['owner']==owner];assert{f['path']for f in fields}=={'/'+str(j)+'/v','/'+str(j)+'/n'}and{f['field']for f in fields}=={'@map:v','@map:n'}
                guards=[]
                for fault in ('missing-proof','duplicate-proof','wrong-member','wrong-class','wrong-call'):
                    altered=copy.deepcopy(rows);src=next(r for r in altered if r['kind']=='binding-source');p=next(r for r in altered if r['kind']=='json-tree-container'and r['seq']in src['json_tree_proofs']and r['class'].endswith('JSONObject'))
                    if fault=='missing-proof':altered.remove(p)
                    elif fault=='duplicate-proof':altered.insert(altered.index(p),copy.deepcopy(p))
                    elif fault=='wrong-member':p['contents'][0]['observed']={'value':'WRONG'}
                    elif fault=='wrong-class':p['class_sha256']='wrong'
                    else:src['source_call_id']=-1
                    try:validate(plan,altered)
                    except ValueError:guards.append(fault)
                    else:raise AssertionError(fault)
                for bad in ('4','5'):
                    badcap=d/(mode+'-unsupported-'+bad);badcap.mkdir();raw=json.loads(command([java,'-cp',cp,name,bad],badcap/'baseline.log').stdout.splitlines()[-1]);badcmd=[('-Dservice.events='+str(badcap/'events.jsonl'))if x.startswith('-Dservice.events=')else x for x in cmd];observed=json.loads(command(badcmd+[bad],badcap/'stdout.log').stdout.splitlines()[-1]);assert[{k:v for k,v in r.items()if k not in ('message','members')}for r in observed]==raw
                    badrows=[json.loads(x)for x in(badcap/'events.jsonl').read_text().splitlines()];assert any(r['kind']=='problem'for r in badrows)and next(r for r in badrows if r['kind']=='metrics')['capture_invalid']
                modes[mode]={'business_equal':True,'same_value_distinct_owners_and_null_leaves':True,'empty_and_null_returns_preserved':True,'no_unknown_override_calls':True,'guards':guards,'unsupported_subclasses_preserve_business_and_invalidate_capture':True}
        reports[name]=modes
    save(out/'results.json',reports);print(reports)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);p.add_argument('--business-jar',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.business_jar.resolve())
