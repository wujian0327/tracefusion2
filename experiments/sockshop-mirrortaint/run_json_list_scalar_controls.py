"""Actual Fastjson calls; independent source identity and ineligible conversion controls."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save
from run_query_planner import command,JARS
from build_distributed_plans import build
from contract_applicability import library_inventory
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution

def run(out,agent,business,record_parent=False):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();deps=out/'deps';deps.mkdir()
 with ZipFile(business)as z:
  for n in z.namelist():
   if n.startswith('BOOT-INF/lib/')and '/fastjson2-'in n:(deps/Path(n).name).write_bytes(z.read(n))
 cp=':'.join(map(str,[classes,agent,*JARS,*deps.glob('*.jar')]))
 java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'JsonListScalarFixture.java')],out/'compile.log')
 jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['JsonListScalarFixture$Out.text']}})
 model=load(b/'fixture/model.json');model['library_inventory']=library_inventory(business)
 source='JsonListScalarFixture$Store.read(Ljava/lang/String;)Lcom/alibaba/fastjson2/JSONArray;'
 plan,route=choose(model,{'entry':'JsonListScalarFixture.root(LJsonListScalarFixture$Store;Ljava/lang/String;)LJsonListScalarFixture$Out;','target':'JsonListScalarFixture$Out.text','path':'/text','source_calls':[source]},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'));save(out/'plan.json',plan);save(out/'route.json',route)
 baseline=json.loads(command([java,'-cp',cp,'JsonListScalarFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
 for mode in ('full','selective'):
  cap=out/mode;cap.mkdir();actual=json.loads(command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'JsonListScalarFixture'],cap/'stdout.log').stdout.splitlines()[-1]);assert [{'text':r['text']}for r in actual]==baseline
  rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];replay=infer_execution(plan,rows);checks=[]
  for r in actual:
   source=next(s for s in rows if s['kind']=='binding-source'and s['message']==r['message']);slot=next(i for i,f in enumerate(source['fields'])if f['field']=='@list:0');ret=next(s for s in rows if s['kind']=='binding-return'and s['message']==r['message']);answer=next(a for a in replay['answers']if a['root_frame']==ret['frame']and a['path']=='/text');expected=[['field',source['seq'],slot]]
   checks.append({'known':answer['known'],'expected':expected,'predicted':answer['origins'],'matched':answer['known']and answer['origins']==expected})
  reports[mode]={'business_same':True,'checks':checks}
 save(out/'results.json',reports);print(reports)
 if not record_parent:assert all(c['matched']for m in reports.values()for c in m['checks']),'Scalar/null origins must match the actual source slot'
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);p.add_argument('--business',type=Path,required=True);p.add_argument('--record-parent',action='store_true');a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.business.resolve(),a.record_parent)
