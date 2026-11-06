"""Presealed existing tasks; independent omission switches and diagnosis-before-timing."""
import argparse,copy,json,os,random,resource,subprocess,sys,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
ARMS={'none':(False,False,False),'boundary_only':(True,False,False),'write_only':(False,True,False),'body_only':(False,False,True),'all':(True,True,True)}
REF=ROOT/'artifacts/shared-transfer-optimization-20261106/final-candidate'

def verify_current(home):
 freeze=load(home/'final-candidate/historical/algorithm-freeze.json')
 for path,digest in freeze['sources'].items():assert sha(Path(path))==digest,path
 receipt=load(home/'agent-content-equivalence.json');assert receipt['all_members_equal']
 assert sha(home/'build/distributed-observer.jar')==receipt['JAR_files'][0]['sha256']
 return freeze


def trial(home,out,task,arm,diagnostic,warm=None,seconds=None,coarse=False):
 verify_current(home)
 import sockshop
 actual=sockshop.Deployment;flags=ARMS[arm];protocol=load(home/'protocol-before-change.json');planned=protocol['tasks'][task];role={'mall':'mall-admin','zlt-user':'zlt-user','ruoyi-dictionary':'role'}[task]
 agent=home/'build/distributed-observer.jar';plan=Path(planned['plan']);assert sha(plan)==planned['sha256']
 def deployment(args,dest,compose):
  cfg=load(compose);modified=[]
  for name,s in cfg['services'].items():
   if not any(x.startswith('-javaagent:')for x in s.get('command',[])):continue
   # All five arms use the same selective persistence projection and plan.
   # These switches change only the three permitted pre-omission gates.
   cmd=s['command'];at=cmd.index('-jar');cmd[at:at]=['-Dservice.target.observation='+str(flags[0]).lower(),'-Dservice.write.observation='+str(flags[1]).lower(),'-Dservice.body.observation='+str(flags[2]).lower()]
   if diagnostic:
    probe=home/'probe'/('probe-v4-coarse.jar'if coarse else'probe-v2.jar');s['volumes'].append(str(probe)+':/tf2/cost-probe.jar:ro')
    pos=next(i for i,x in enumerate(cmd)if x.startswith('-javaagent:'));cmd[pos:pos]=['-javaagent:/tf2/cost-probe.jar=/tf2/capture/monitor-cost.json']+(['-Dprobe.coarse=true']if coarse else['-Dservice.diagnostic.timing=true'])
   modified.append(name)
  assert len(modified)==1,modified
  save(compose,cfg);save(dest/'ablation-options.json',{'arm':arm,'flags':flags,'service_mode':'selective','same_plan':str(plan),'plan_sha256':sha(plan),'Agent_sha256':sha(agent),'diagnostic_only':diagnostic,'coarse_probe':coarse,'modified_services':modified})
  return actual(args,dest,compose)
 sockshop.Deployment=deployment
 warm=0 if diagnostic and warm is None else 30 if warm is None else warm
 seconds=8 if diagnostic and seconds is None else 60 if seconds is None else seconds
 try:
  if task=='ruoyi-dictionary':
   import run_shared_work_business as business
   business.Deployment=deployment;business.add_probe=lambda *a:None
   out.mkdir(parents=True,exist_ok=False)
   business.ruoyi_trial(home,out,home/'build','selective',warm,seconds,diagnostic)
   business.verify_business(out,task)
  elif task=='zlt-user':
   import run_target_closure_cost as cost
   cost.FINAL=REF;cost.BASE=home/'build';cost.verify=lambda:verify_current(home);cost.fresh=lambda *a:None
   cost.zlt_trial(out.parent,out.name,task,'selective',warm,seconds,sample=not diagnostic)
   from run_shared_work_business import verify_business
   verify_business(out,task)
  else:
   import run_frozen_locality_cost as mall
   mall.BASE=home/'build';mall.MALL=REF/'mall';mall.COMMIT=verify_current(home)['commit'];mall.verify=lambda:verify_current(home)
   r=mall.trial(out.parent,out.name,'selective',warm,seconds)
   assert r['state']=='captured'and r['requests']==r['business_passed']and r['cleanup_returncode']==0,r
   # Original comparator keeps response structure; token/clock normalization is
   # independent of physical source scoring below.
   import math
   def normalized(c):
    value=copy.deepcopy(c['response'])
    for key in ('token','refreshToken'):
     assert isinstance(value['data'][key],str)and value['data'][key];value['data'][key]='<fresh-token>'
    ttl=value['data']['expiresIn'];assert type(ttl)is int and 86400-math.ceil(c['http_seconds'])-1<=ttl<=86400
    value['data']['expiresIn']='<clock-rounded-TTL>';return value
   reference=ROOT/'artifacts/target-closure-revision-20261103/common-cost-01/cal-mall-original'
   originals=load(reference/'warmup.json')['requests']+load(reference/'measure.json')['requests']
   cases=load(out/'warmup.json')['requests']+load(out/'measure.json')['requests']
   assert all(normalized(c)==normalized(originals[0])for c in cases)
   lines=(out/'database-after.txt').read_text().splitlines();assert int(lines[lines.index('login_log_count')+1])==len(cases)
   save(out/'business-comparison.json',{'requests':len(cases),'passed':len(cases),'reference':str(reference),'login_log_rows':len(cases),'token_and_TTL_normalization_only':True,'source_truth_independent':True})
 finally:sockshop.Deployment=actual
 from check_pruning_target_completeness import run as complete_targets
 expected_targets=complete_targets(out,plan);save(out/'target-completeness.json',expected_targets)
 cap=out/'capture/events.jsonl';save(out/'offline-protocol.json',{'tasks':{task:{'selective':{'capture':str(cap),'capture_sha256':sha(cap),'plan':str(plan),'plan_sha256':sha(plan),'role':role}}}})
 script=HERE/'measure_pruning_cost_offline.py'
 for stage in ('trace','oracle'):
  cmd=['taskset','-c',str(min(os.sched_getaffinity(0))),sys.executable,str(script),'--protocol',str(out/'offline-protocol.json'),'--task',task,'--out',str(out/stage)]
  if stage=='oracle':cmd+=['--score',str(out/'trace')]
  before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
  with(out/(stage+'.log')).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
  after=resource.getrusage(resource.RUSAGE_CHILDREN);save(out/(stage+'-process.json'),{'wall_seconds':time.perf_counter()-start,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,'fresh_exec':True,'profiler':False,'logical_cpu':min(os.sched_getaffinity(0))})
 summary=load(out/'oracle/summary.json');assert summary['correct']==summary['targets']and summary['targets']>0 and summary['targets']==expected_targets['expected_targets']
 verify_current(home)
 save(out/'complete.json',{'complete':True,'task':task,'arm':arm,'diagnostic_only':diagnostic,'targets':summary['targets'],'correct':summary['correct']})

def count_trial(home,trial,task):
 planned=load(home/'protocol-before-change.json')['tasks'][task];rows=[json.loads(x)for x in(trial/'capture/events.jsonl').read_text().splitlines()];messages={r['message']for phase in ('warmup','measure')for r in load(trial/(phase+'.json'))['requests']};frames={r['frame']:r for r in rows if r['kind']=='enter'}
 def root(f):
  seen=set()
  while f in frames and f not in seen:
   seen.add(f);r=frames[f]
   if r['method']==planned['entry']:return f
   f=r.get('parent')
  return None
 request_roots={root(r.get('frame'))for r in rows if r.get('message')in messages};request_roots.discard(None)
 selected=[r for r in rows if r.get('message')in messages or root(r.get('frame'))in request_roots]
 # Preparation is retained in batch counts but never mixed into request counts.
 def counts(events):
  scalar=container=ctor=write=body_reads=body_branches=body_eligible=body_selected=body_fallback=0;reasons={};boundary_decisions=boundary_selected=0
  for r in events:
   policy=r.get('target_observation')
   if policy:
    boundary_decisions+=1;boundary_selected+=bool(policy.get('selected'));scalar+=sum(policy.get('scalar_fields',{}).values());container+=sum(policy.get('container_values',{}).values())
   ctor+=sum(r.get('execution_closure',{}).get('elided_writes',{}).values())
   write+=r['kind']=='write-version'
   b=r.get('body_observation')
   if b:
    body_eligible+=bool(b['guard_eligible']);body_selected+=bool(b['selected']);body_fallback+=not b['guard_eligible'];reason=b.get('reason')or('eligible'if b['guard_eligible']else'unspecified');reasons[reason]=reasons.get(reason,0)+1
   b=r.get('body_observation_omissions',{});body_reads+=b.get('field_reads',0);body_branches+=b.get('branches',0)
  return {'boundary_scope_checks':boundary_decisions,'boundary_selected_scopes':boundary_selected,'boundary_scalar_values_omitted':scalar,'boundary_container_values_omitted':container,'constructor_write_values_omitted':ctor,'application_write_values_omitted':write,'body_guard_eligible_calls':body_eligible,'body_selected_calls':body_selected,'body_ineligible_calls':body_fallback,'body_reasons':reasons,'body_field_reads_omitted':body_reads,'body_branches_omitted':body_branches,'events':len(events),'kinds':{k:sum(r['kind']==k for r in events)for k in sorted({r['kind']for r in events})}}
 return {'task':task,'trial':str(trial),'plan_sha256':planned['sha256'],'static_candidates':{k:len(planned[k])for k in ('boundary_scalar_candidates','boundary_container_candidates','constructor_write_candidates','application_write_candidates','body_candidates')},'batch':counts(rows),'requests':counts(selected),'request_messages':len(messages),'note':'Snapshot selection is not omission. Actual value/field/branch omission counts come from retained completion certificates; zero means no omission, not failure.'}

def matrix(home):
 from verify_pruning_short_answers import run as verify_answers
 verify_answers(home,home/'short-evidence-comparison-02')
 out=home/'short';data={};jobs=[]
 for task in load(home/'protocol-before-change.json')['order']:
  observations={}
  for arm in ARMS:
   trialpath=out/(task+'-'+arm);assert load(trialpath/'complete.json')['complete'];observations[arm]=count_trial(home,trialpath,task)
  def vector(arm):
   c=observations[arm]['requests'];return(c['boundary_scalar_values_omitted']+c['boundary_container_values_omitted'],c['constructor_write_values_omitted']+c['application_write_values_omitted'],c['body_field_reads_omitted']+c['body_branches_omitted'])
  arms=['none'];vectors=[vector('none')]
  assert vectors[0]==(0,0,0),vectors[0]
  for arm in ('boundary_only','write_only','body_only','all'):
   v=vector(arm)
   if any(v)and v not in vectors:arms.append(arm);vectors.append(v)
  data[task]={'observations':observations,'selected_arms':arms if len(arms)>1 else [],'omission_vectors':dict(zip(arms,vectors)),'zero_trigger_task_not_timed':len(arms)==1}
 rng=random.Random(6110617)
 for repeat in range(1,6):
  for task,v in data.items():
   arms=v['selected_arms'][:];rng.shuffle(arms);jobs.extend([repeat,task,a]for a in arms)
 save(home/'formal-matrix-after-diagnosis.json',{'tasks':data,'jobs':jobs,'rule':load(home/'protocol-before-change.json')['matrix_rule'],'no_selection_by_speed':True})
 print('Formal unique triggered arms:',{k:v['selected_arms']for k,v in data.items()},flush=True)

def run(home,stage):
 if stage=='matrix':return matrix(home)
 if stage=='formal':
  if not(home/'coarse/complete.json').exists():run(home,'coarse')
  from seal_pruning_cost_environment import run as seal_environment
  seal_environment(home)
 if stage=='coarse':
  out=home/'coarse';out.mkdir(exist_ok=False);jobs=[(task,'none')for task in load(home/'protocol-before-change.json')['order']]
 elif stage=='short':
  out=home/'short';out.mkdir(exist_ok=False);jobs=[(task,arm)for task in load(home/'protocol-before-change.json')['order']for arm in ARMS]
 else:
  out=home/'formal';out.mkdir(exist_ok=False);jobs=[(task,arm,repeat)for repeat,task,arm in load(home/'formal-matrix-after-diagnosis.json')['jobs']]
 for job in jobs:
  task,arm=job[:2];name=task+'-'+arm if stage in('short','coarse')else'%02d-%s-%s'%(job[2],task,arm)
  if stage=='short'and name=='mall-none'and(home/'pilot-mall-none/complete.json').exists():
   prior=home/'pilot-mall-none';receipt=load(prior/'ablation-options.json');assert receipt['Agent_sha256']==sha(home/'build/distributed-observer.jar')and receipt['flags']==list(ARMS['none'])and receipt['plan_sha256']==load(home/'protocol-before-change.json')['tasks']['mall']['sha256']
   (out/name).symlink_to(prior,target_is_directory=True);save(out/(name+'-reuse.json'),{'valid_same_Agent_plan_and_switches':True,'original':str(prior),'original_capture_sha256':sha(prior/'capture/events.jsonl')});continue
  cmd=[sys.executable,__file__,'trial','--home',str(home),'--out',str(out/name),'--task',task,'--arm',arm]
  if stage in('short','coarse'):cmd.append('--diagnostic')
  if stage=='coarse':cmd.append('--coarse-probe')
  with(out/(name+'.log')).open('w')as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
  save(out/(name+'-returncode.json'),{'returncode':r.returncode})
  if r.returncode:raise RuntimeError('Retained failure: '+name)
 save(out/'complete.json',{'complete':True,'deployments':len(jobs),'diagnostic_only':stage!='formal'})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=('short','coarse','matrix','formal','trial'));p.add_argument('--home',required=True,type=Path);p.add_argument('--out',type=Path);p.add_argument('--task');p.add_argument('--arm',choices=list(ARMS));p.add_argument('--diagnostic',action='store_true');p.add_argument('--coarse-probe',action='store_true');a=p.parse_args()
 if a.stage=='trial':trial(a.home.resolve(),a.out.resolve(),a.task,a.arm,a.diagnostic,coarse=a.coarse_probe)
 else:run(a.home.resolve(),a.stage)
