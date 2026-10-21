#!/usr/bin/env python3
"""Real Date render + Mongo codecs, independent same-time instance oracle."""
import argparse,copy,json,secrets,time
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import HERE,ROOT,load,save
from infer_execution_kernel import infer_execution
import run_response_binding_revision as old

def run(out,libs,base):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();cp=':'.join(map(str,[*JARS,*libs.glob('*.jar')]));command(['javac',*java8_target()[1],'-cp',cp+':'+str(base/'tools'),'-d',str(classes),str(HERE/'DateEffectsFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'DateEffectsFixture.root(Lorg/springframework/data/mongodb/repository/MongoRepository;LDateEffectsFixture$Input;LDateEffectsFixture$Input;I)LDateEffectsFixture$Out;','targets':['DateEffectsFixture$Out.date'],'response_path':'/date','execution_kernel':True,'application_calls':True,'async_dependencies':True}})
 image=load(ROOT/'artifacts/orders-end-to-end-revision-20261021/business-frozen-final/full-sockshop-orders-newOrder-customer-firstName/capture/compose.json')['services']['orders-db']['image'];save(out/'compose.json',{'services':{'mongo':{'image':image,'ports':['127.0.0.1:19827:27017']}}});dep=old.CachedDeployment(argparse.Namespace(project='tf2-date-effects-'+secrets.token_hex(5),ready_timeout=90),out,out/'compose.json');reports={}
 try:
  dep.compose('up','-d','--pull','never',timeout=120)
  for i in range(60):
   if dep.compose('exec','-T','mongo','mongo','--quiet','--eval','db.runCommand({ping:1})',check=False).returncode==0:break
   time.sleep(1)
  else:raise RuntimeError('Mongo readiness')
  for mode in ('full','selective'):
   cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+cp,'DateEffectsFixture','19827'],cap/'stdout.log');g=old.Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];cases=json.loads((cap/'stdout.log').read_text().splitlines()[-1]);checks=[]
   for c in cases:
    want=None if c['mode'] in (3,4,6,7,8,9) else [] if c['mode'] in (2,11) else [2] if c['mode'] in (1,10) else [1];a=g.query(c['message'],'/date','fixture',boundary=old.BOUNDARY);assert a['known']==(want is not None),(c,a)
    truth=set()
    if want is not None:
     for index in want:
      inp=next(r for r in rows if r['kind']=='binding-input'and r.get('message')==c['message'] and r['argument']==index);f=next(f for f in inp['fields']if f['field']=='DateEffectsFixture$Input.date');truth.add(old.source_coord('fixture',inp,f))
     assert {old.predicted_coord(s)for s in a['sources']}==truth,(c,a,truth)
    checks.append({'case':c,'expected_root_arguments':want,'truth':sorted(truth,key=str),'answer':a})
   faults={}
   for label in ('missing-render','render-runtime','same-time-wrong-object','render-epoch','render-zone','missing-codec','codec-class','custom-registry','encoding-hook','codec-count'):
    bad=copy.deepcopy(rows);event=next(r for r in bad if r.get('date_effect',{}).get('valid'));proof=event['date_effect'];savep=next(r for r in bad if r['kind']=='mongo-save-effect'and r.get('date_codecs')and all(c['valid']for c in r['date_codecs']))
    if label=='missing-render':event.pop('date_effect')
    elif label=='render-runtime':proof['render_runtime']['class_sha256']={}
    elif label=='same-time-wrong-object':proof['before']['object']='other-same-date'
    elif label=='render-epoch':proof['after']['date_epoch_ms']+=1
    elif label=='render-zone':proof['zone']='custom-zone'
    elif label=='missing-codec':savep['date_codecs']=[]
    elif label=='codec-class':savep['date_codecs'][0]['class_sha256']={}
    elif label=='custom-registry':savep['date_codecs'][0]['default_registry']=False
    elif label=='encoding-hook':savep['date_codecs'][0]['encoding_hooks']=True
    else:savep['date_codec_calls']+=1
    try:infer_execution(g.plans['fixture'],bad)
    except ValueError:faults[label]=True
    else:raise AssertionError('Accepted '+label)
   reports[mode]={'targets':len(checks),'known_exact':sum(c['answer']['known']for c in checks),'expected_unknown':sum(not c['answer']['known']for c in checks),'faults':faults,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,{k:v for k,v in reports[mode].items()if k!='checks'},flush=True)
 finally:
  v=dep.compose('down','--volumes','--remove-orphans',check=False);save(out/'cleanup.json',{'returncode':v.returncode})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--libs',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.libs.resolve(),a.base_build.resolve())
