"""Sequential pilot gate, original-only load preflight, then randomized rounds."""
import argparse,copy,json,math,os,random,resource,subprocess,sys,time,traceback
from pathlib import Path
from run_unrelated_work_scaling import H,HERE,ROOT,F,MALL,AGENT,BUNDLE,MODES,TIERS,load,save,sha,verify,controlled_trial

def audit(out,task,tier,mode):
 cmd=[sys.executable,str(HERE/'audit_unrelated_work_scaling.py'),'--trial',str(out),'--task',task,'--tier',tier,'--mode',mode]
 with(out/'audit-process.log').open('w')as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 if r.returncode:return {'correct':0,'targets':-1,'error':'audit process failed'}
 return load(out/'audit/summary.json')

def mall_trial(out,mode,warm,seconds,rate):
 import run_frozen_locality_cost as mall
 import run_sockshop_cost as cost
 import portability_tool_config as pc
 mall.BASE=F/'frozen-base';mall.MALL=MALL;mall.COMMIT=load(H/'protocol-before-tools.json')['TF_commit'];mall.verify=verify;pc.BUNDLE=BUNDLE
 realphase=mall.phase;realSampler=cost.Sampler;current={}
 class Sampler(realSampler):
  def __enter__(self):current['containers']=self.containers;return super().__enter__()
 def phase(endpoint,label,seconds):
  if label.endswith('-measure'):
   save(out/'measure-cpu-before.json',cost.resource_snapshot(current['containers']))
  result=realphase(endpoint,label,seconds,rate=rate)
  if label.endswith('-measure'):save(out/'measure-cpu-after.json',cost.resource_snapshot(current['containers']))
  return result
 mall.phase=phase;cost.Sampler=Sampler
 try:r=mall.trial(out.parent,out.name,mode,warm,seconds)
 finally:mall.phase=realphase;cost.Sampler=realSampler
 r.update(task='mall',tier=str(rate),rate=rate);save(out/'result.json',r)
 cases=load(out/'warmup.json')['requests']+load(out/'measure.json')['requests']if(out/'measure.json').exists()else[]
 if cases:
  for c in cases:
   v=copy.deepcopy(c['response']);assert c['business_passed']
   for key in('token','refreshToken'):assert isinstance(v['data'][key],str)and v['data'][key];v['data'][key]='<generated>'
   ttl=v['data']['expiresIn'];assert 86400-math.ceil(c['http_seconds'])-1<=ttl<=86400;v['data']['expiresIn']='<bounded-TTL>'
   assert v=={'code':200,'message':'操作成功','data':{'token': '<generated>','refreshToken':'<generated>','tokenHead':'Bearer ','expiresIn':'<bounded-TTL>'}},v
  lines=(out/'database-after.txt').read_text().splitlines();assert int(lines[lines.index('login_log_count')+1])==len(cases)
  save(out/'business-check.json',{'requests':len(cases),'response_normalization':'only generated token strings and bounded clock TTL; all other keys/values exact','login_log_count':len(cases),'own_database':True})
 return r

def passes(r,a):return r.get('state')=='captured'and r.get('cleanup_returncode')==0 and r['requests']==r['business_passed']and a.get('correct')==a.get('targets')and a.get('targets',0)>0

def pilot_controlled():
 results={};outroot=H/'pilot-controlled-04';outroot.mkdir(exist_ok=False)
 for tier in TIERS:
  results[tier]={}
  for mode in MODES:
   out=outroot/(tier+'-'+mode)
   if mode in('full','selective')and not(H/'controlled-build-04'/tier/'plan.json').exists():
    results[tier][mode]={'state':'planning_rejected','planning':load(H/'controlled-build-04'/tier/'planning.json'),'correct':0,'actual_business_deployment':False};continue
   r=controlled_trial(out,tier,mode,0,3,2);a=audit(out,'controlled',tier,mode);results[tier][mode]={'run':r,'audit':a,'passed':(r.get('requests')==r.get('business_passed')and r.get('state')=='captured')if mode=='original'else passes(r,a)}
 save(H/'controlled-pilot-results.json',results)
 # The related-high necessary-observation control is a hard gate, not an
 # alternative task to replace when the frozen core lacks its semantics.
 gate=all(v.get('passed',False)for group in results.values()for v in group.values())
 omissions={t:results[t].get('selective',{}).get('audit',{}).get('actual_scalar_omissions',0)for t in('low','medium','high')};gate=gate and omissions['low']>0 and omissions['low']<omissions['medium']<omissions['high']
 save(H/'controlled-gate.json',{'passed':gate,'omissions':omissions,'requires_related_control':True,'no_formal_cost_if_false':True,'no_replacement_or_model_fix':True});print('CONTROLLED GATE',gate,flush=True)

def preflight():
 results=[]
 for rate in(4,8):
  out=H/'mall-preflight'/('original-rate-%d'%rate);r=mall_trial(out,'original',0,12,rate);cases=load(out/'measure.json');successful=[c for c in cases['requests']if c['business_passed']];lats=sorted(c['http_seconds']for c in successful);achieved=len(successful)/((cases['end_ns']-cases['start_ns'])/1e9);p95=lats[min(len(lats)-1,math.ceil(.95*len(lats))-1)]if lats else None
  results.append({'rate':rate,'run':r,'completed':len(successful),'achieved_rate':achieved,'p95_seconds':p95,'qualified':r.get('state')=='captured'and len(successful)==len(cases['requests'])and achieved>=rate*.98 and p95<.5})
 higher=[r['rate']for r in results if r['qualified']];rates=[2]+([max(higher)]if higher else[])
 save(H/'mall-rate-lock-before-tool-timing.json',{'preflight':results,'rates':rates,'rule':load(H/'protocol-before-tools.json')['mall']['higher_selection'],'no_tool_formal_timing_yet':True});print('LOCKED',rates,flush=True)

def pilot_mall():
 results={};root=H/'pilot-mall';root.mkdir(exist_ok=False)
 for rate in load(H/'mall-rate-lock-before-tool-timing.json')['rates']:
  results[str(rate)]={}
  for mode in MODES:
   out=root/('rate-%d-'%rate+mode);r=mall_trial(out,mode,0,8,rate);a=audit(out,'mall',str(rate),mode);results[str(rate)][mode]={'run':r,'audit':a,'passed':r.get('state')=='captured'and r.get('requests')==r.get('business_passed')if mode=='original'else passes(r,a)}
 save(H/'mall-pilot-results.json',results);gate=all(v['passed']for row in results.values()for v in row.values());save(H/'mall-gate.json',{'passed':gate,'no_controlled_growth_claim':True});print('MALL GATE',gate,flush=True)

def formal():
 verify()
 from datetime import datetime,timezone
 seal_files=[HERE/n for n in('run_unrelated_work_scaling.py','execute_unrelated_work_scaling.py','audit_unrelated_work_scaling.py','measure_unrelated_work_offline.py')]+[H/'mall-plan.json']+[H/'controlled-build-04'/t/'plan.json'for t in('low','medium','high')]
 assert not(H/'formal-code-seal-before-timing.json').exists()
 save(H/'formal-code-seal-before-timing.json',{'files':{str(f):sha(f)for f in seal_files},'experiment_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'created_utc':datetime.now(timezone.utc).isoformat(),'core_unchanged':True})
 verify();rng=random.Random(load(H/'protocol-before-tools.json')['formal']['order_seed']);jobs=[]
 for round_ in range(1,6):
  if load(H/'controlled-gate.json')['passed']:
   for tier in('low','medium','high'):
    modes=MODES[:];rng.shuffle(modes)
    for m in modes:jobs.append({'round':round_,'task':'controlled','tier':tier,'mode':m,'rate':2})
  if load(H/'mall-gate.json')['passed']:
   for rate in load(H/'mall-rate-lock-before-tool-timing.json')['rates']:
    modes=MODES[:];rng.shuffle(modes)
    for m in modes:jobs.append({'round':round_,'task':'mall','tier':str(rate),'mode':m,'rate':rate})
 save(H/'formal-order-before-timing.json',{'jobs':jobs,'seed':2026110917,'rounds':5,'pilot_qualification_only':True})
 for job in jobs:
  name='%02d-%s-%s-%s'%(job['round'],job['task'],job['tier'],job['mode']);out=H/'formal'/name
  print('START',name,flush=True)
  if job['task']=='mall':r=mall_trial(out,job['mode'],30,60,job['rate'])
  else:r=controlled_trial(out,job['tier'],job['mode'],30,60,2)
  a=audit(out,job['task'],job['tier'],job['mode'])
  good=r.get('state')=='captured'and r.get('requests')==r.get('business_passed')if job['mode']=='original'else passes(r,a)
  save(out/'formal-job.json',{**job,'passed':good})
  if not good:raise RuntimeError('Formal task stopped; retained failure '+name)
  if job['mode']!='original':
   cmd=['taskset','-c',str(min(os.sched_getaffinity(0))),sys.executable,str(HERE/'measure_unrelated_work_offline.py'),'--trial',str(out),'--task',job['task'],'--tier',job['tier'],'--mode',job['mode']]
   before=resource.getrusage(resource.RUSAGE_CHILDREN);started=time.perf_counter()
   with(out/'normal-offline-process.log').open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
   after=resource.getrusage(resource.RUSAGE_CHILDREN);save(out/'normal-offline-process.json',{'wall_seconds':time.perf_counter()-started,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,'fresh_exec':True,'includes_process_start_and_imports':True,'logical_cpu':min(os.sched_getaffinity(0))})
 save(H/'formal-complete.json',{'jobs':len(jobs),'passed':True});print('FORMAL COMPLETE',len(jobs),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['pilot-controlled','preflight','pilot-mall','formal']);a=p.parse_args();verify()
 {'pilot-controlled':pilot_controlled,'preflight':preflight,'pilot-mall':pilot_mall,'formal':formal}[a.stage]()
