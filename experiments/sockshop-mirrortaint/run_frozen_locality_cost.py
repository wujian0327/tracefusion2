#!/usr/bin/env python3
"""Experiment-only driver. Never rebuilds or modifies the c1a4e5c semantic core."""
import argparse,copy,hashlib,json,random,secrets,statistics,subprocess,sys,time,traceback,urllib.request,urllib.error,resource
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.append(str(ROOT/'scripts'))
from run_planned_service import load,save,sha
from sockshop import Deployment
OLD=ROOT/'artifacts/source-locality-effects-20261030'
BASE=OLD/'final-historical-03/frozen-base'
MALL=OLD/'final-mall-03'
COMMIT='c1a4e5ceb60a276cc3651e4cdb413aa29d7f8d5d'
AGENT='375cdbeb9b1c3b06df488011cf848e4f614ef4de6dbe29d5e8bdcfd18f66f0fa'
PORT=19893
PATH='/data/expiresIn'
CLIENT_DEP=None

def verify():
 f=load(OLD/'final-historical-03/algorithm-freeze.json')
 for p,h in f['sources'].items():
  assert sha(Path(p))==h,p
  relative=str(Path(p).relative_to(ROOT))
  assert hashlib.sha256(subprocess.check_output(['git','show',COMMIT+':'+relative],cwd=ROOT)).hexdigest()==h,relative
 assert sha(BASE/'distributed-observer.jar')==AGENT
 return {str(Path(p).relative_to(ROOT)):h for p,h in f['sources'].items()}

def prepare(home):
 home.mkdir(parents=True,exist_ok=False);sources=verify()
 rng=random.Random(30102026);order=[]
 for i in range(5):
  modes=['original','full','selective'];rng.shuffle(modes);order.append(modes)
 protocol={'algorithm':COMMIT,'agent_sha256':AGENT,'sources':sources,'entry':'com/macro/mall/controller/UmsAdminController.login(Lcom/macro/mall/dto/UmsAdminLoginParam;)Lcom/macro/mall/common/api/CommonResult;',
  'path':PATH,'source_boundary':'Actual AuthService.getAccessToken call return /data/expiresIn; not wire bytes, database status, or value equality.',
  'independent_rule':'Original controller/service returns this actual RPC result unchanged. Pair unique raw source call under root, its object/field/version, and actual response target. No graph/MT tags define truth.',
  'input':{'username':'admin','password':'macro123'},'input_basis':'Unmodified original public SQL auth seed; ordinary application OAuth issuance. No private signing configuration read.',
  'modes':['original','full','selective'],'round_order':order,'rounds':5,'warmup_seconds':30,'measure_seconds':60,'rate':2,'concurrency_limit':2,
  'JVM':['-Xms32m','-Xmx256m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2'],'business_limits':'Each JVM 1CPU/768MiB; MySQL512MiB, Redis128MiB, Mongo384MiB, Rabbit384MiB, each1CPU.',
  'plan':str(MALL/'planning-first/mall-swarm-3/002-plan.json'),'plan_sha256':sha(MALL/'planning-first/mall-swarm-3/002-plan.json'),
  'no_agent_core_contract_change':True,'locality_off':'Derived offline precision ablation only; never a same-answer cost arm.',
  'MT':'Calibration first with fixed native+adapter. Formal inclusion only after task/source/target/dependency equivalence is independently demonstrated; otherwise pending.',
  'online_order':'Sequential deployments; no other experimental online workload concurrently. Existing unrelated containers left untouched.',
  'phases':'Decode, graph validation+reconstruction, query restoration, export, independent scoring separate. Core is reconstruction+query; total process includes all.',
  'request_attribution':'Closed events grouped by root Frame/message and RPC/ownership intervals. Unattributable shared startup/footer costs separately retained.',
  'driver_sources':{str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))}}
 save(home/'protocol-before-calibration.json',protocol)
 save(home/'environment-before.json',{'docker_ps':subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines(),'machine':subprocess.check_output(['uname','-a'],text=True).strip(),'cpu':Path('/proc/cpuinfo').read_text().split('model name\t: ')[1].splitlines()[0]})
 print('Protocol sealed',home,flush=True)

def request(endpoint,label,index):
 trace=hashlib.sha256((label+':'+str(index)).encode()).hexdigest();message=trace[:32]+'/'+trace[32:48]
 data=json.dumps({'username':'admin','password':'macro123'}).encode()
 req=urllib.request.Request(endpoint+'/admin/login',data=data,headers={'Content-Type':'application/json','traceparent':'00-'+trace[:32]+'-'+trace[32:48]+'-01'})
 start=time.monotonic_ns();status=0;body=b'';error=None;http_seconds=None
 try:
  if CLIENT_DEP is not None:
   p=CLIENT_DEP.compose('exec','-T','load-client','curl','--noproxy','*','-sS','--max-time','20','-w','\n%{http_code}\n%{time_total}','-H','Content-Type: application/json','-H','traceparent: 00-'+trace[:32]+'-'+trace[32:48]+'-01','--data-binary',data.decode(),'http://admin:8080/admin/login',check=False)
   raw,code,timing=p.stdout.rsplit('\n',2);body=raw.encode();status=int(code);http_seconds=float(timing)
   if p.returncode:error='curl return '+str(p.returncode)
  else:
   try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=20) as r:status=r.status;body=r.read()
   except urllib.error.HTTPError as r:status=r.code;body=r.read()
 except Exception as e:error=str(e)
 end=time.monotonic_ns()
 try:value=json.loads(body)
 except Exception:value=body.decode(errors='replace')
 valid=status==200 and isinstance(value,dict) and value.get('code')==200 and isinstance(value.get('data'),dict) and isinstance(value['data'].get('expiresIn'),int) and bool(value['data'].get('token'))
 return {'case':label+'-%05d'%index,'message':message,'http_status':status,'response':value,'body':json.loads(data),'start_ns':start,'end_ns':end,'http_seconds':http_seconds,'error':error,'business_passed':valid}

def phase(endpoint,label,seconds,rate=2):
 start=time.monotonic_ns();pending=[]
 with ThreadPoolExecutor(max_workers=2)as pool:
  for i in range(round(seconds*rate)):
   delay=start/1e9+i/rate-time.monotonic()
   if delay>0:time.sleep(delay)
   pending.append(pool.submit(request,endpoint,label,i))
  delay=start/1e9+seconds-time.monotonic()
  if delay>0:time.sleep(delay)
  rows=[p.result()for p in pending]
 return {'start_ns':start,'end_ns':time.monotonic_ns(),'requests':rows}

def spec(out,mode):
 original=MALL/'tool-runs/mall-swarm-3/full/query-002';cfg=copy.deepcopy(load(original/'compose.json'))
 images=json.loads(subprocess.check_output(['docker','image','inspect',*[s['image']for s in cfg['services'].values()]],text=True))
 mapping={tag:i['Id']for i in images for tag in i.get('RepoTags',[])}
 for role,s in cfg['services'].items():
  s['image']=mapping.get(s['image'],s['image'])
  if role not in ('admin','auth','portal'):continue
  s['command']=[('-Xmx256m'if x.startswith('-Xmx')else x)for x in s['command']if not x.startswith(('-javaagent:','-Dservice.'))]
  s['volumes']=[v for v in s['volumes']if '/tf2/'not in v.split(':')[1]]
 cfg['services']['admin'].pop('ports',None)
 cfg['services']['load-client']={'image':cfg['services']['admin']['image'],'entrypoint':['sleep','infinity'],'cpus':1,'mem_limit':'128m'}
 if mode!='original':
  import portability_tool_config as pc
  pc.BASE=BASE;pc.verify=lambda root:verify()
  q=next(q for q in load(MALL/'task-seal.json')['entries']if q['id']=='mall-swarm-3')
  pc.configure(MALL,out,cfg['services']['admin'],q,mode,2 if mode!='mirrortaint'else None)
 # Every arm keeps exactly the same business dependencies and fixture.
 save(out/'images.json',images);return cfg

def trial(home,name,mode,warmup,measure):
 global CLIENT_DEP
 import run_sockshop_cost as cost
 verify();out=home/name;out.mkdir(parents=True,exist_ok=False);cfg=spec(out,mode);save(out/'compose.json',cfg)
 dep=Deployment(argparse.Namespace(project='tf2-frozen-cost-'+secrets.token_hex(5)),out,out/'compose.json');result={'mode':mode,'state':'environment_failed'}
 try:
  dep.compose('up','-d','mysql','redis','mongo','rabbitmq','--pull','never',timeout=180)
  deadline=time.monotonic()+120
  while time.monotonic()<deadline:
   p=dep.compose('exec','-T','mysql','mysql','-uroot','-ptf2-portability-fixture-only','mall','-e','SELECT COUNT(*) FROM ums_admin',check=False)
   if p.returncode==0:break
   time.sleep(2)
  else:raise ValueError('Original SQL not ready')
  dep.compose('up','-d','--pull','never',timeout=180);deadline=time.monotonic()+200
  while time.monotonic()<deadline:
   logs=dep.compose('logs','--no-color',check=False).stdout
   if 'APPLICATION FAILED TO START'in logs or 'Application run failed'in logs:raise ValueError('Application startup failed')
   if all('Started 'in dep.compose('logs','--no-color',role,check=False).stdout for role in ('admin','auth','portal')):break
   time.sleep(3)
  else:raise ValueError('Readiness timeout')
  CLIENT_DEP=dep
  containers={r:dep.compose('ps','-q',r).stdout.strip()for r in cfg['services']if r!='load-client'}
  endpoint='http://127.0.0.1:%d'%PORT
  with cost.Sampler(containers,2,out/'resources.jsonl',observed_roles=('admin','auth','portal'))as sampler:
   a=phase(endpoint,name+'-warmup',warmup);save(out/'warmup.json',a)
   b=phase(endpoint,name+'-measure',measure);save(out/'measure.json',b)
  save(out/'resource-summary.json',sampler.summary(b['start_ns'],b['end_ns']))
  result.update(state='captured',requests=len(a['requests'])+len(b['requests']),business_passed=sum(r['business_passed']for r in a['requests']+b['requests']))
  p=dep.compose('exec','-T','mysql','mysql','-uroot','-ptf2-portability-fixture-only','mall','-e','SELECT COUNT(*) AS login_log_count FROM ums_admin_login_log; SELECT id,username,status FROM ums_admin ORDER BY id;',check=False)
  (out/'database-after.txt').write_text((p.stdout or'')+(p.stderr or''))
 except Exception as e:result.update(error=str(e));(out/'failure.log').write_text(traceback.format_exc())
 finally:
  try:
   dep.compose('stop','-t','30','admin','auth','portal',check=False,timeout=120);dep.diagnostics()
  finally:
   p=dep.compose('down','--volumes','--remove-orphans',check=False,timeout=120);result['cleanup_returncode']=p.returncode;save(out/'result.json',result)
 CLIENT_DEP=None;verify();print(name,result,flush=True);return result

def offline(home,trialpath,precision=True,folder='offline'):
 from infer_distributed_fields import Reconstruction
 from infer_execution_kernel import infer_execution
 from infer_source_locality import validate
 import external_transfer_oracle as oracle
 start=time.perf_counter();cpu=time.process_time();dest=trialpath/folder;dest.mkdir(exist_ok=False);phases={};t=time.perf_counter()
 rows=oracle.raw(trialpath/'capture/events.jsonl');phases['decode']=time.perf_counter()-t
 t=time.perf_counter();oracle.require_complete_raw_capture(rows);cert=validate(load(MALL/'planning-first/mall-swarm-3/002-plan.json'),rows);phases['independent_capture_validation']=time.perf_counter()-t
 build=dest/'build/mall-admin';build.mkdir(parents=True);(build/'plan.json').write_bytes((MALL/'planning-first/mall-swarm-3/002-plan.json').read_bytes())
 capture=dest/'capture/mall-admin';capture.mkdir(parents=True);(capture/'events.jsonl').symlink_to((trialpath/'capture/events.jsonl').resolve())
 t=time.perf_counter();g=Reconstruction(dest/'build',dest/'capture',['mall-admin'],decoded_rows={'mall-admin':rows});phases['graph_reconstruction']=time.perf_counter()-t
 cases=load(trialpath/'warmup.json')['requests']+load(trialpath/'measure.json')['requests'];answers=[];t=time.perf_counter()
 for c in cases:
  answer=g.query(c['message'],PATH,'mall-admin',boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}]);answers.append((c,answer))
 phases['query_restore']=time.perf_counter()-t;t=time.perf_counter();save(dest/'answers.json',[{'case':c['case'],'answer':a}for c,a in answers]);phases['export']=time.perf_counter()-t
 t=time.perf_counter();scored=[];rule={'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'}
 for c,a in answers:
  ret=[r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']];assert len(ret)==1
  want={tuple(v)for v in oracle.tf_expected(rows,ret[0],rule,PATH)}
  got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']}
  assert want and c['business_passed'];assert a['target']['observed']['value']==c['response']['data']['expiresIn']
  scored.append({'case':c['case'],'message':c['message'],'positive':True,'known':a['known'],'exact':a['known']and want==got,'expected':sorted(want,key=str),'actual':sorted(got,key=str)})
 phases['independent_score']=time.perf_counter()-t
 save(dest/'scores.json',scored)
 measured_wall=time.perf_counter()-start;measured_cpu=time.process_time()-cpu;measured_hwm=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
 # Both ablative executions consume the identical complete capture. Off is precision only.
 disabled=[]
 if precision:
  t=time.perf_counter();p=load(build/'plan.json');off=copy.deepcopy(p);off['execution_kernel'].pop('source_locality',None);without=infer_execution(off,rows);phases['precision_ablation_excluded_from_timed_total']=time.perf_counter()-t
  disabled=[a for a in without['answers']if a['path']==PATH]
 # Attribute by actual message/Frame/call lineage, never event file visibility windows.
 frame_message={r['frame']:None for r in rows if r['kind']=='enter'}
 for r in rows:
  if r['kind']in('binding-input','binding-return','binding-source','binding-opaque-touch')and r.get('frame')and r.get('message'):
   if frame_message.get(r['frame'])not in(None,r['message']):raise ValueError('Frame rebound to another message')
   frame_message[r['frame']]=r['message']
 for _ in range(len(frame_message)+1):
  changed=False
  for r in rows:
   if r['kind']=='enter'and not frame_message.get(r['frame'])and frame_message.get(r.get('parent')):frame_message[r['frame']]=frame_message[r['parent']];changed=True
  if not changed:break
 calls={r['call_id']:frame_message.get(r.get('frame'))for r in rows if r['kind']=='collection-call-enter'}
 measured={c['message']for c in load(trialpath/'measure.json')['requests']};bytrace={c['message'].split('/')[0]:c['message']for c in cases};events=0;bytecount=0;shared_events=0;shared_bytes=0
 for line,r in zip((trialpath/'capture/events.jsonl').read_bytes().splitlines(keepends=True),rows):
  msg=r.get('message')or frame_message.get(r.get('frame'))or frame_message.get(r.get('caller_frame'))or calls.get(r.get('call_id'))
  msg=bytrace.get(msg.split('/')[0],msg)if msg else None
  if msg in measured:events+=1;bytecount+=len(line)
  elif msg not in bytrace.values():shared_events+=1;shared_bytes+=len(line)
 result={'targets':len(scored),'correct':sum(r['exact']for r in scored),'positive':len(scored),'without_certificate_known':sum(a['known']for a in disabled),'valid_certificates':len(cert),'phases_seconds':phases,
  'core_seconds':phases['graph_reconstruction']+phases['query_restore'],'wall_seconds_excluding_ablation':measured_wall,'cpu_seconds_excluding_ablation':measured_cpu,'VmHWM_KiB_before_ablation':measured_hwm,
  'measure_events':events,'measure_bytes':bytecount,'shared_unattributed_events':shared_events,'shared_unattributed_bytes':shared_bytes,'batch_events':len(rows),'batch_bytes':(trialpath/'capture/events.jsonl').stat().st_size}
 save(dest/'summary.json',result);assert result['correct']==result['targets']and (not precision or result['without_certificate_known']==0),result
 if precision:save(trialpath/'offline-complete.json',{'summary':str((dest/'summary.json').relative_to(trialpath))})
 print({k:v for k,v in result.items()if k!='phases_seconds'},flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','trial','offline','memory','formal']);p.add_argument('--home',type=Path,required=True);p.add_argument('--name');p.add_argument('--mode',choices=['original','full','selective','mirrortaint']);p.add_argument('--warmup',type=int,default=4);p.add_argument('--measure',type=int,default=8);p.add_argument('--folder',default='offline');a=p.parse_args();home=a.home.resolve()
 if a.stage=='prepare':prepare(home)
 elif a.stage=='trial':trial(home,a.name,a.mode,a.warmup,a.measure)
 elif a.stage=='offline':offline(home,home/a.name,folder=a.folder)
 elif a.stage=='memory':offline(home,home/a.name,precision=False,folder='offline-fresh')
 else:
  protocol=load(home/'protocol-before-calibration.json')
  for m in ('original','full','selective'):
   assert load(home/('calibration-v2-'+m)/'result.json')['state']=='captured'
   if m!='original':
    root=home/('calibration-v2-'+m);s=load(root/load(root/'offline-complete.json')['summary']);assert s['correct']==s['targets']and s['without_certificate_known']==0
  acceptance=load(home/'common-task-calibration-final.json');assert acceptance['passed']
  for i,modes in enumerate(load(home/'formal-order-before-measurement.json')['round_order']):
   for mode in modes:
    name='round-%02d-%s'%(i+1,mode);r=trial(home,name,mode,30,60);assert r['state']=='captured'and r['business_passed']==180
    if mode=='mirrortaint':
     before=resource.getrusage(resource.RUSAGE_CHILDREN);started=time.perf_counter()
     subprocess.run([sys.executable,str(HERE/'audit_frozen_transfer_cost.py'),'mt-offline','--home',str(home/name)],check=True,stdout=(home/name/'offline-native-process.log').open('w'),stderr=subprocess.STDOUT)
     after=resource.getrusage(resource.RUSAGE_CHILDREN);save(home/name/'offline-native-process.json',{'wall_seconds':time.perf_counter()-started,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,'fresh_exec':True})
    elif mode!='original':
     subprocess.run([sys.executable,__file__,'offline','--home',str(home),'--name',name],check=True,stdout=(home/name/'offline-process.log').open('w'),stderr=subprocess.STDOUT)
     before=resource.getrusage(resource.RUSAGE_CHILDREN);started=time.perf_counter()
     subprocess.run([sys.executable,__file__,'memory','--home',str(home),'--name',name],check=True,stdout=(home/name/'offline-fresh-process.log').open('w'),stderr=subprocess.STDOUT)
     after=resource.getrusage(resource.RUSAGE_CHILDREN);save(home/name/'offline-fresh-process.json',{'wall_seconds':time.perf_counter()-started,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,'fresh_exec':True,'excludes_precision_ablation':True})
if __name__=='__main__':main()
