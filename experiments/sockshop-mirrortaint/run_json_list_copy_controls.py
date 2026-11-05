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

def run(out,agent,business):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();deps=out/'deps';deps.mkdir()
 with ZipFile(business)as z:
  for n in z.namelist():
   if n.startswith('BOOT-INF/lib/')and '/fastjson2-'in n:(deps/Path(n).name).write_bytes(z.read(n))
 cp=':'.join(map(str,[classes,agent,*JARS,*deps.glob('*.jar')]))
 java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'JsonListCopyFixture.java')],out/'compile.log')
 jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['JsonListCopyFixture$Out.text']}})
 model=load(b/'fixture/model.json');model['library_inventory']=library_inventory(business)
 source='JsonListCopyFixture$Store.read(I)Lcom/alibaba/fastjson2/JSONArray;'
 plan,route=choose(model,{'entry':'JsonListCopyFixture.root(LJsonListCopyFixture$Store;I)LJsonListCopyFixture$Out;','target':'JsonListCopyFixture$Out.text','path':'/text','source_calls':[source]},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'));save(out/'plan.json',plan);save(out/'route.json',route)
 baseline=json.loads(command([java,'-cp',cp,'JsonListCopyFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
 for mode in ('full','selective'):
  cap=out/mode;cap.mkdir();actual=json.loads(command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'JsonListCopyFixture'],cap/'stdout.log').stdout.splitlines()[-1]);assert[{k:v for k,v in r.items()if k!='message'}for r in actual]==baseline
  rows=[json.loads(x)for x in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem']
  replay=infer_execution(plan,rows);checks=[]
  for c in actual:
   ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==c['message']);ans=next(a for a in replay['answers']if a['root_frame']==ret['frame']and a['path']=='/text');known=c['case']in(0,1,2,3,6);assert ans['known']==known,(c,ans)
   if c['case']in(0,1):
    s=next(r for r in rows if r['kind']=='binding-source'and r['message']==c['message']);i=next(i for i,f in enumerate(s['fields'])if f['path']=='/'+str(c['case'])+'/text');assert ans['origins']==[['field',s['seq'],i]],ans
   elif known:assert not ans['origins'],ans
   checks.append({'case':c['case'],'known':ans['known'],'origins':ans['origins']})
  guards=[]
  for fault in ('missing-cache','duplicate-cache','wrong-cache-call','wrong-target-class','wrong-member','wrong-runtime','late-initialization'):
   changed=copy.deepcopy(rows);end=next(r for r in changed if r.get('json_list_copy',{}).get('valid'));proof=end['json_list_copy'];hit=next(r for r in changed if r['seq']==proof['cache_seq'])
   if fault=='missing-cache':hit['kind']='missing-cache'
   elif fault=='duplicate-cache':changed.insert(changed.index(hit),copy.deepcopy(hit))
   elif fault=='wrong-cache-call':hit['call_id']=-1
   elif fault=='wrong-target-class':hit['target_class']='wrong'
   elif fault=='wrong-member':proof['members'][0]={'object':'wrong'}
   elif fault=='wrong-runtime':proof['runtime']['java_runtime_version']='wrong'
   else:proof['initialized_seq']=end['seq']
   try:infer_execution(plan,changed)
   except ValueError:guards.append(fault)
   else:raise AssertionError(fault)
  reports[mode]={'business_same':True,'checks':checks,'guards':guards}
 save(out/'results.json',reports);print(reports)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);p.add_argument('--business',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.business.resolve())
