"""Actual MVC dispatch, before-observation exclusion, and whole-capture guards."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from build_distributed_plans import build
from plan_capability_policy import choose
from contract_applicability import library_inventory
from infer_request_scope import validate


def run(out,agent):
    out.mkdir(parents=True,exist_ok=False);deps=out/'deps';deps.mkdir();classes=out/'classes';classes.mkdir()
    business=ROOT/'artifacts/target-closure-revision-20261103/external-candidates/ruoyi-cloud/ruoyi-modules/ruoyi-system/target/ruoyi-modules-system.jar'
    with ZipFile(business)as z:
        for n in z.namelist():
            if n.startswith('BOOT-INF/lib/')and n.endswith('.jar'):(deps/Path(n).name).write_bytes(z.read(n))
    libs=sorted(deps.glob('*.jar'));cp=':'.join(map(str,[classes,agent,*JARS,*libs]));java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'RequestScopeFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['RequestScopeFixture$DTO.text']}})
    model=load(b/'fixture/model.json');model['library_inventory']=library_inventory(business)
    plan,route=choose(model,{'entry':'RequestScopeFixture.query(LRequestScopeFixture$DTO;)LRequestScopeFixture$Wrap;','target':'RequestScopeFixture$DTO.text','path':'/data/text'},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);save(out/'route.json',route);assert plan.get('query_request_scope')
    result=[]
    for variant in('normal','formal-bad','parented','unverified'):
        baseline=json.loads(command([java,'-cp',cp,'RequestScopeFixture',variant],out/('baseline-'+variant+'.log')).stdout.splitlines()[-1])
        for mode in('full','selective'):
            cap=out/(mode+'-'+variant);cap.mkdir()
            actual=json.loads(command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'events.jsonl'),'-cp',cp,'RequestScopeFixture',variant],cap/'stdout.log').stdout.splitlines()[-1]);assert actual==baseline,(variant,mode,actual,baseline)
            rows=[json.loads(x)for x in(cap/'events.jsonl').read_text().splitlines()];bad=any(r['kind']=='problem'for r in rows)
            assert bad==(variant in('formal-bad','parented')),(mode,variant,[r for r in rows if r['kind']=='problem'])
            excluded=[r for r in rows if r['kind']=='query-scope-output-excluded']
            assert len(excluded)==(2 if variant=='normal'else 0),(variant,excluded)
            if not bad:validate(plan,rows)
            result.append({'mode':mode,'variant':variant,'business_equal':True,'observer_extra_set_iterations':0,'excluded':len(excluded),'invalid':bad,'state_clean':True})
    save(out/'results.json',{'agent_sha256':sha(agent),'cases':result,'scope':'Observation ownership and failure isolation; not a source accuracy experiment.'})
    print(result,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.agent.resolve())
