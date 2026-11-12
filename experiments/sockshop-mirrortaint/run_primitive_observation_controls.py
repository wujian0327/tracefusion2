"""Field observation stress and provenance, independent raw field expectations."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,save,load,sha
from run_query_planner import command,JARS
from run_generic_observation_rules import metadata_build
from tf_static_baseline import configure
from plan_capability_policy import choose
from run_public_control_semantics import checked
from raw_source_call_facts import RawSourceCallFacts
from audit_zlt_foundation_revision import tf_pair


def run(out,agent,stress_only=False):
    out.mkdir(parents=True,exist_ok=False)
    save(out/'protocol-before-jvm.json',{'fixture_sha256':sha(HERE/'PrimitiveObservationFixture.java'),'agent_sha256':sha(agent),'expectation':'big/boxed/absent copy corresponding source field, selectors empty, version1; real boxed identity retained; all eight primitive descriptors and null/ordinary refs distinct; after warmup no field-box IDS growth','stress':{'phases':2,'observations_per_phase':1000}})
    java=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java'
    classes=out/'classes';classes.mkdir();deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'));cp=':'.join(map(str,[classes,agent,*JARS,*deps]))
    command([str(java.with_name('javac')),'-cp',cp,'-d',str(classes),str(HERE/'PrimitiveObservationFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    metadata_build(out/'build',{'fixture':{'jar':str(jar),'targets':['PrimitiveObservationFixture$Out.big']}})
    model=load(out/'build/fixture/model.json');entry='PrimitiveObservationFixture.root(LPrimitiveObservationFixture$Store;)LPrimitiveObservationFixture$Out;'
    deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json')
    plans={}
    for field in ('big','boxed','absent'):
        plan,route=choose(model,{'entry':entry,'target':'PrimitiveObservationFixture$Out.'+field,'path':'/'+field,'source_calls':['PrimitiveObservationFixture$Store.read()LPrimitiveObservationFixture$Datum;']},deployment=deployment)
        save(out/(field+'-plan.json'),plan);plans[field]=load(out/(field+'-plan.json'))
    stress=copy.deepcopy(plans['big']);scan='PrimitiveObservationFixture.scan(LPrimitiveObservationFixture$Datum;)V';stress['frame_methods'].append(scan);stress['execution_kernel']['methods'][scan]=model['methods'][scan];save(out/'stress-plan.json',stress)
    cmd=[str(java),'-javaagent:'+str(agent),'-Dservice.plan='+str(out/'stress-plan.json'),'-Dservice.events='+str(out/'stress-events.jsonl'),'-Dservice.mode=full','-cp',cp,'PrimitiveObservationFixture','stress'];save(out/'stress-command.json',cmd)
    stats=json.loads(command(cmd,out/'stress.log').stdout.splitlines()[-1]);save(out/'stress-results.json',stats)
    rows=[json.loads(l)for l in(out/'stress-events.jsonl').read_text().splitlines()];reads=[r for r in rows if r['kind']=='read'];assert len(reads)==2001*12
    for field,key in (('boxed','boxed'),('boxedLong','boxedLong'),('ref','ref')):
        assert {r['observed']['object']for r in reads if r['field'].endswith('.'+field)}=={stats[key]}
    assert all(r['observed']=={'object':None,'value':None}for r in reads if r['field'].endswith('.absent'))
    protocol=rows[0].get('field_value_version',0);growth=[stats['stats'][i]['IDS']-stats['stats'][i-1]['IDS']for i in (1,2)]
    if protocol:
        from field_value_protocol import validate
        validate(stress,rows)
        assert growth==[0,0],growth
        primitive={r['descriptor']for r in reads if 'primitive'in r['observed']};assert primitive==set('ZBCSIJFD')
    if stress_only:return
    baseline=command([str(java),'-cp',cp,'PrimitiveObservationFixture'],out/'original.log').stdout.splitlines()[-1];reports=[]
    for field,plan in plans.items():
        norms={}
        for mode in ('full','static','selective'):
            d=out/(field+'-'+mode);d.mkdir();policy=configure(plan,mode);save(d/'policy.json',policy)
            cmd=[str(java),'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/(field+'-plan.json')),'-Dservice.events='+str(d/'events.jsonl'),*policy['jvm_options'],'-cp',cp,'PrimitiveObservationFixture'];save(d/'command.json',cmd)
            actual=command(cmd,d/'stdout.log').stdout.splitlines()[-1];assert json.loads(actual)==json.loads(baseline)
            rows=[json.loads(l)for l in(d/'events.jsonl').read_text().splitlines()];source=next(r for r in rows if r['kind']=='binding-source');tf_pair(RawSourceCallFacts(rows).matching(rows,source),source)
            indices=[i for i,f in enumerate(source['fields'])if f['field']=='PrimitiveObservationFixture$Datum.'+field];assert len(indices)==1;index=indices[0];src=source['fields'][index]
            ret=next(r for r in rows if r['kind']=='binding-return');physical=next(f for f in ret['fields']if f['path']=='/'+field)
            truth={'origins':[['field',source['seq'],index]],'selectors':[],'owner':physical['owner'],'field':physical['field'],'version':1,'known':True};save(d/'truth-before-prediction.json',truth)
            result=checked(plan,rows);save(d/'prediction.json',result);a=next(a for a in result['answers']if a['path']=='/'+field)
            assert all(a[k]==v for k,v in truth.items()),(field,mode,a,truth)
            if field in ('boxed','absent'):assert src['observed']['object']==physical['observed']['object']
            norms[mode]={'known':a['known'],'origins':['source.'+field],'selectors':a['selectors'],'version':a['version']};reports.append({'field':field,'mode':mode,'passed':True})
        assert norms['full']==norms['static']==norms['selective']
    save(out/'results.json',{'checks':reports,'gate':all(r['passed']for r in reports),'IDS_growth':growth,'protocol':protocol,'new_Agent':True,'JDK':str(java)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);p.add_argument('--stress-only',action='store_true');a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.stress_only)
