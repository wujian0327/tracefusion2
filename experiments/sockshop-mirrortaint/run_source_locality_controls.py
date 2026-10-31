"""Actual default decoder ownership, effects and independent source coordinates."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from build_distributed_plans import build
from infer_execution_kernel import infer_execution
from plan_capability_policy import choose

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();libs=out/'libs';libs.mkdir();fat=ROOT/'artifacts/constructor-chain-effects-20261030/final-mall-01/business-jars/mall-admin.jar'
 with ZipFile(fat)as z:
  for n in z.namelist():
   if n.startswith('BOOT-INF/lib/')and n.endswith('.jar'):(libs/Path(n).name).write_bytes(z.read(n))
 old=ROOT/'artifacts/constructor-chain-effects-20261030/final-historical-01/frozen-base/distributed-observer.jar';cp=':'.join(map(str,[old,*sorted(libs.glob('*.jar')),*JARS]));javac='/usr/lib/jvm/java-8-openjdk-amd64/bin/javac';java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
 command([javac,'-cp',cp,'-d',str(classes),str(HERE/'SourceLocalityFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('SourceLocalityFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
  for p in libs.glob('*.jar'):z.write(p,'BOOT-INF/lib/'+p.name)
 entry='SourceLocalityFixture.root(I)LSourceLocalityFixture$Result;';source='SourceLocalityFixture$API.fetch()LSourceLocalityFixture$Result;';query={'entry':entry,'target':'SourceLocalityFixture$Result.message','path':'/message','source_calls':[source]};b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':entry,'targets':[query['target']],'response_path':query['path'],'execution_kernel':True,'application_calls':True,'source_calls':[source]}});model=load(b/'fixture/model.json');from contract_applicability import library_inventory;model['library_inventory']=library_inventory(jar);plan,policy=choose(model,query);assert plan['execution_kernel'].get('source_locality');plan.pop('communication_identity',None);save(b/'fixture/plan.json',plan);save(out/'policy.json',policy)
 cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*sorted(libs.glob('*.jar')),*JARS]));native=command([java,'-cp',cp,'SourceLocalityFixture'],out/'original.log');expected=json.loads(next(x for x in native.stdout.splitlines()if x.startswith('[{')));reports={}
 for mode in ('full','selective'):
  dest=out/mode;dest.mkdir();command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(dest/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'SourceLocalityFixture'],dest/'stdout.log');assert json.loads(next(x for x in (dest/'stdout.log').read_text().splitlines()if x.startswith('[{')))==expected
  rows=[json.loads(s)for s in(dest/'events.jsonl').read_text().splitlines()];problems=[r for r in rows if r['kind']=='problem'];assert not problems,problems;answers=infer_execution(plan,rows)['answers'];checks=[]
  for case in expected:
   ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message']);answer=next(a for a in answers if a['root_frame']==ret['frame']);want=case['mode']in(0,4,9,12,15,18,20,22,25);assert answer['known']==want,(mode,case,answer,[r for r in rows if r['kind']=='locality-end'])
   if want and case['mode']==18:assert not answer['origins']
   elif want:
    source_row=next(r for r in rows if r['kind']=='binding-source'and r['message']==case['message']);i=next(i for i,f in enumerate(source_row['fields'])if f['field']=='SourceLocalityFixture$Result.message');truth=set()if case['mode']==4 else{('field',source_row['seq'],i)};assert set(map(tuple,answer['origins']))==truth,(case,answer,truth)
   if case['mode']==24:
    source_row=next(r for r in rows if r['kind']=='binding-source'and r['message']==case['message']);field=next(f for f in source_row['fields']if f['field']=='SourceLocalityFixture$Result.message');assert answer['owner']==field['owner']and answer['version']==field['version']and answer['observed']==field['observed']and not answer['known'],'Unobserved same-object/same-value overwrite certified'
   checks.append({'mode':case['mode'],'known':answer['known'],'actual':answer['origins']})
  guards={}
  for fault in ('missing-birth','missing-reader','missing-corridor','wrong-call','external-mutable-reference','wrong-return','duplicate-completion'):
   bad=copy.deepcopy(rows);end=next(r for r in bad if r['kind']=='locality-end'and r['valid']);oid=end['ownership_id']
   if fault=='missing-birth':bad.remove(next(r for r in bad if r['kind']=='locality-birth'and r['ownership_id']==oid))
   elif fault=='missing-reader':bad.remove(next(r for r in bad if r['kind']=='locality-reader'and r['ownership_id']==oid))
   elif fault=='missing-corridor':bad.remove(next(r for r in bad if r['kind']=='locality-client-return'and r['ownership_id']==oid))
   elif fault=='wrong-call':end['call_id']=-1
   elif fault=='external-mutable-reference':end['objects'][0]['references'].append('other')
   elif fault=='wrong-return':end['body']='other'
   else:bad.insert(bad.index(end),copy.deepcopy(end))
   try:infer_execution(plan,bad)
   except ValueError:guards[fault]=True
   else:raise AssertionError('Missing ownership evidence accepted: '+fault)
  reports[mode]={'targets':len(checks),'known_correct':sum(x['known']for x in checks),'expected_unknown':sum(not x['known']for x in checks),'business_and_side_effects_preserved':True,'guards':guards,'checks':checks};save(dest/'checks.json',reports[mode]);print(mode,{k:v for k,v in reports[mode].items()if k!='checks'},flush=True)
 save(out/'results.json',{'all_passed':True,'modes':reports,'agent_sha256':sha(b/'distributed-observer.jar')})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
