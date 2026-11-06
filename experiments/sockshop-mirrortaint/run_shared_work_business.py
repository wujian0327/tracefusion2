"""Fixed ZLT User / RuoYi dictionary: shared-work diagnostics and paired online costs.

The additional counter Agent is used only by diagnostic jobs, never by timing.
No task, source boundary, runtime model or pruning policy is changed here.
"""
import argparse,copy,hashlib,json,random,resource,secrets,subprocess,sys,time,traceback,yaml
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from run_planned_service import ROOT,HERE,load,save,sha
from sockshop import Deployment
from run_sockshop_cost import Sampler
OLD=ROOT/'artifacts/ruoyi-tolist-20261105/final-candidate'


def phase(request,label,seconds):
 start=time.monotonic_ns()
 with ThreadPoolExecutor(max_workers=2)as pool:
  jobs=[]
  for i in range(round(seconds*2)):
   delay=start/1e9+i/2-time.monotonic()
   if delay>0:time.sleep(delay)
   jobs.append(pool.submit(request,label,i))
  delay=start/1e9+seconds-time.monotonic()
  if delay>0:time.sleep(delay)
  rows=[j.result()for j in jobs]
 return {'start_ns':start,'end_ns':time.monotonic_ns(),'requests':rows}


def add_probe(cfg,role,home,cap):
 s=cfg['services'][role];s['volumes'].append(str(home/'snapshot-probe/snapshot-probe.jar')+':/tf2/work-probe.jar:ro')
 at=next(i for i,a in enumerate(s['command'])if a.startswith('-javaagent:'))
 s['command'].insert(at,'-javaagent:/tf2/work-probe.jar=/tf2/capture/snapshot-work.json')


def ruoyi_trial(home,out,base,mode,warm,measure,diagnostic):
 original=ROOT/'artifacts/target-closure-revision-20261103/ruoyi-original-03';cfg=yaml.safe_load((original/'compose.yml').read_text())
 old=ROOT/'artifacts/ruoyi-tolist-20261105/final-C1';q=next(q for q in load(old/'task-seal.json')['tasks']['ruoyi']if q['id']=='ruoyi-3')
 cap=out/'capture';cap.mkdir();cap.chmod(0o777);s=cfg['services']['system'];plan=old/'plans/ruoyi-3/plan.json';agent=base/'distributed-observer.jar'
 s['volumes'] += [str(agent)+':/tf2/observer.jar:ro',str(plan)+':/tf2/plan.json:ro',str(cap)+':/tf2/capture:rw']
 at=s['command'].index('-jar');s['command'][at:at]=['-javaagent:/tf2/observer.jar','-Dservice.plan=/tf2/plan.json','-Dservice.events=/tf2/capture/events.jsonl','-Dservice.mode='+mode]
 for service in cfg['services'].values():service['image']=json.loads(subprocess.check_output(['docker','image','inspect',service['image']],text=True))[0]['Id']
 if diagnostic:add_probe(cfg,'system',home,cap)
 save(out/'compose.json',cfg);save(out/'binary-receipt.json',{'agent':str(agent),'sha256':sha(agent),'plan':str(plan),'plan_sha256':sha(plan),'additional_probe':diagnostic})
 dep=Deployment(argparse.Namespace(project='tf2-shared-work-'+secrets.token_hex(5)),out,out/'compose.json');result={'state':'environment_failed','task':'ruoyi-dictionary','mode':mode}
 try:
  dep.compose('up','-d','mysql','redis','client','--pull','never',timeout=180)
  for _ in range(100):
   r=dep.compose('exec','-T','mysql','mysql','-uroot','-ptf2-disposable-fixture','-e','SELECT COUNT(*) FROM `ry-cloud`.sys_config;',check=False)
   if r.returncode==0:break
   time.sleep(2)
  else:raise RuntimeError('Original SQL readiness failed')
  dep.compose('up','-d','--pull','never',timeout=180)
  token=None
  for _ in range(100):
   r=dep.compose('exec','-T','client','curl','-sS','--max-time','5','-H','Content-Type: application/json','--data-binary','{"username":"admin","password":"admin123"}','http://auth:9200/login',check=False)
   try:token=json.loads(r.stdout)['data']['access_token']
   except(ValueError,KeyError,TypeError):token=None
   if token:break
   time.sleep(3)
  else:raise RuntimeError('Original normal authentication failed')
  def request(label,i):
   template=i%len(q['inputs']);body=q['inputs'][template];path=q['http'].split(' ',1)[1].replace('{dictType}',quote(body,safe=''));digest=hashlib.sha256((out.name+'|'+label+'|'+str(i)).encode()).hexdigest();start=time.monotonic_ns()
   p=dep.compose('exec','-T','client','curl','-sS','--max-time','25','-w','\n%{http_code}\n%{time_total}','-H','Authorization: Bearer '+token,'-H','traceparent: 00-'+digest[:32]+'-'+digest[32:48]+'-01','http://system:9201'+path,check=False)
   end=time.monotonic_ns();raw,status,timing=p.stdout.rsplit('\n',2);value=json.loads(raw)
   return {'case':label+'-%05d'%i,'template':template,'message':digest[:32]+'/'+digest[32:48],'response':value,'http_status':int(status),'http_seconds':float(timing),'start_ns':start,'end_ns':end,'business_passed':p.returncode==0 and int(status)==200 and value.get('code')==200}
  ids={r:dep.compose('ps','-q',r).stdout.strip()for r in cfg['services']if r!='client'}
  if diagnostic:
   a=phase(request,'warmup',warm);save(out/'warmup.json',a);b=phase(request,'measure',measure);save(out/'measure.json',b)
  else:
   with Sampler(ids,2,out/'resources.jsonl',observed_roles=('system','auth'))as sampler:
    a=phase(request,'warmup',warm);save(out/'warmup.json',a);b=phase(request,'measure',measure);save(out/'measure.json',b)
   save(out/'resource-summary.json',sampler.summary(b['start_ns'],b['end_ns']))
  cases=a['requests']+b['requests'];result.update(state='captured',requests=len(cases),business_passed=sum(c['business_passed']for c in cases))
  sql="SELECT dict_code,dict_label,dict_type,DATE_FORMAT(create_time,'%Y-%m-%d %H:%i:%s') AS createTime FROM sys_dict_data ORDER BY dict_code;"
  r=dep.compose('exec','-T','mysql','mysql','-uroot','-ptf2-disposable-fixture','--default-character-set=utf8mb4','--batch','-D','ry-cloud','-e',sql,check=False);(out/'independent-database.tsv').write_text((r.stdout or'')+(r.stderr or''));assert r.returncode==0
 except Exception as error:result['error']=str(error);(out/'failure.log').write_text(traceback.format_exc())
 finally:
  try:dep.compose('stop','-t','30','system','auth',check=False,timeout=120);dep.diagnostics()
  finally:result['cleanup_returncode']=dep.compose('down','--volumes','--remove-orphans',check=False,timeout=120).returncode;save(out/'result.json',result)
 assert result['state']=='captured'and result['requests']==result['business_passed']and result['cleanup_returncode']==0,result
 return q,plan,'role'


def trial(home,out,task,version,mode,warm,measure,diagnostic):
 out.mkdir(parents=True,exist_ok=False);base=(OLD if version=='old'else home/'final-candidate')/'historical/frozen-base'
 if task=='ruoyi-dictionary':q,plan,role=ruoyi_trial(home,out,base,mode,warm,measure,diagnostic)
 else:
  import run_target_closure_cost as cost
  cost.FINAL=OLD;cost.BASE=base;cost.verify=lambda:{};cost.fresh=lambda *args:None
  original=cost.zlt_spec
  def spec(*args,**kwargs):
   cfg,q=original(*args,**kwargs)
   if diagnostic:add_probe(cfg,q['role'],home,args[1]/'capture')
   return cfg,q
  cost.zlt_spec=spec
  # Existing workload owns creation of its output directory.
  out.rmdir();cost.zlt_trial(out.parent,out.name,'zlt-user',mode,warm,measure,sample=not diagnostic)
  plan=OLD/'zlt/planning-first/ZLT-MP-4/000-plan.json';role='zlt-user'
 protocol={'tasks':{task:{mode:{'capture':str(out/'capture/events.jsonl'),'capture_sha256':sha(out/'capture/events.jsonl'),'plan':str(plan),'plan_sha256':sha(plan),'role':role}}}}
 save(out/'offline-protocol.json',protocol)
 from measure_shared_work_revision import worker
 # Fresh Python process: code selection and memory scopes do not leak between runs.
 verify_business(out,task)
 cmd=[sys.executable,str(HERE/'measure_shared_work_revision.py'),'worker','--home',str(home),'--protocol',str(out/'offline-protocol.json'),'--out',str(out/'offline'),'--task',task,'--mode',mode,'--repo',str(home/'old-repository'if version=='old'else ROOT)]
 start=time.perf_counter();before=resource.getrusage(resource.RUSAGE_CHILDREN)
 with(out/'offline.log').open('w')as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
 after=resource.getrusage(resource.RUSAGE_CHILDREN);save(out/'offline-process.json',{'wall_seconds':time.perf_counter()-start,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,'profiler':False,'fresh_exec':True})


def verify_business(out,task):
 cases=load(out/'warmup.json')['requests']+load(out/'measure.json')['requests']
 if task=='zlt-user':
  ref=ROOT/'artifacts/target-closure-revision-20261103/common-cost-01/round-01-zlt-user-original'
  original=load(ref/'warmup.json')['requests']+load(ref/'measure.json')['requests']
  by_template={}
  for r in original:by_template.setdefault(r['template'],[]).append(r['response'])
  checks=[r['http_status']==200 and all(r['response']==b for b in by_template[r['template']])for r in cases]
 else:
  from audit_target_external_first import business_comparison
  original=load(ROOT/'artifacts/target-closure-revision-20261103/ruoyi-original-03/sealed-original-requests/results.json')['cases']
  original=[r for r in original if r['query']=='ruoyi-3']
  checks=[r['http_status']==original[r['template']]['http_status'] and business_comparison('ruoyi',original[r['template']]['response'],r['response'])['task_response_equal_except_original_SQL_initialization_clock']for r in cases]
  own_clock={}
  for line in(out/'independent-database.tsv').read_text().splitlines():
   cols=line.split('\t')
   if len(cols)==4 and cols[0].isdigit():own_clock[int(cols[0])]=cols[3]
  for r in cases:
   for v in r['response']['data']:
    assert v['createTime']==own_clock[v['dictCode']],'Returned seed clock differs from its own DB'
 save(out/'business-comparison.json',{'requests':len(cases),'passed':sum(checks),'original_reference':str(ref)if task=='zlt-user'else'Original sealed six RuoYi cases; SQL initialization clock handled by unchanged comparator.','graph_or_labels_used_as_truth':False})
 assert all(checks),'Business differs from original'

def run(home,diagnostic):
 folder=home/('business-work-diagnostics-02'if diagnostic else'online-paired');folder.mkdir(exist_ok=False);jobs=[];rng=random.Random(61106)
 for repeat in range(1,2 if diagnostic else 6):
  for task in('zlt-user','ruoyi-dictionary'):
   arms=[(v,m)for v in('old','new')for m in('full','selective')];rng.shuffle(arms)
   jobs.extend((repeat,task,v,m)for v,m in arms)
 save(folder/'order-before-runs.json',{'jobs':jobs,'warmup_seconds':0 if diagnostic else 30,'measurement_seconds':3 if diagnostic else 60,'rps':2,'concurrency':2,'profiler':False,'counter_agent':diagnostic})
 for repeat,task,version,mode in jobs:
  d=folder/('%02d-%s-%s-%s'%(repeat,task,version,mode));args=[sys.executable,__file__,'trial','--home',str(home),'--out',str(d),'--task',task,'--version',version,'--mode',mode]
  if diagnostic:args.append('--diagnostic')
  with(folder/(d.name+'.log')).open('w')as log:r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT)
  save(folder/(d.name+'-receipt.json'),{'returncode':r.returncode});assert r.returncode==0,d
 save(folder/'complete.json',{'complete':True,'deployments':len(jobs),'no_pruning_change':True})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=('run','trial','score'));p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path);p.add_argument('--task');p.add_argument('--version');p.add_argument('--mode');p.add_argument('--diagnostic',action='store_true');a=p.parse_args();h=a.home.resolve()
 if a.stage=='run':run(h,a.diagnostic)
 elif a.stage=='trial':trial(h,a.out.resolve(),a.task,a.version,a.mode,0 if a.diagnostic else 30,3 if a.diagnostic else 60,a.diagnostic)
 else:
  from measure_shared_work_revision import worker
  verify_business(a.out,a.task)
  worker(a.out/'offline-protocol.json',a.task,a.mode,h/'old-repository'if a.version=='old'else ROOT,a.out/'offline',False)
