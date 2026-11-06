"""Pruning ablation accounting: timing and evidence counts remain separate."""
import argparse,collections,csv,json,pstats,statistics
from pathlib import Path
from run_planned_service import load,save,sha
from run_pruning_cost_audit import ARMS,count_trial

def diagnostic(folder):
 report=load(folder/'capture/monitor-cost.json');groups=collections.defaultdict(lambda:[0,0,0,0,0]);methods=[]
 for key,v in report['methods'].items():
  group=key.split(':',1)[0]
  for i,n in enumerate(v):groups[group][i]+=n
  methods.append({'method':key,'calls':v[0],'inclusive_wall_seconds':v[1]/1e9,'inclusive_cpu_seconds':v[2]/1e9,'self_wall_seconds':v[3]/1e9,'self_cpu_seconds':v[4]/1e9})
 samples=collections.Counter();file=folder/'capture/events.jsonl.diagnostic.jsonl'
 if file.exists():
  for line in file.read_text().splitlines():
   for t in json.loads(line)['threads']:
    if t['name'].startswith('tf2-diagnostic'):continue
    stack=t['stack'];probe=any('PruningCostProbeAgent'in f for f in stack);observer=any(any(n in f for n in('PlannedServiceAgent','ResponseBindingHooks','JsonTreeObservationHooks','CollectionServiceHooks','SourceLocalityHooks','BodyObservationHooks','tracefusion.internal.jackson'))for f in stack)
    bucket='probe_blocked'if probe and t['state']=='BLOCKED'and stack and 'PruningCostProbeAgent'in stack[0]else'observer_blocked'if observer and t['state']=='BLOCKED'else'observer_stack'if observer else'business_framework_or_idle'
    samples[bucket]+=1
 return {'groups':{k:{'calls':v[0],'inclusive_wall_seconds':v[1]/1e9,'inclusive_cpu_seconds':v[2]/1e9,'self_wall_seconds':v[3]/1e9,'self_cpu_seconds':v[4]/1e9}for k,v in groups.items()},'methods':methods,'thread_state_samples':dict(samples),'boundary':'Selected observer methods and original JDK operations called from them; never application invoke/predicate execution. Self times additive only within this probe coverage. Includes probe overhead, startup and preparation; synchronized-entry waiting is excluded from method timers. Stack samples are counts, not duration/CPU attribution. Shutdown timer snapshot may exclude final footer work. Not formal speed data.'}

def profile(folder):
 s=pstats.Stats(str(folder/'profile.pstats'));groups=collections.defaultdict(lambda:{'calls':0,'self_profile_seconds':0.0});top=[]
 evidence=('infer_source_locality.py','infer_body_observation.py','infer_execution_closure.py','infer_communication_identity.py','infer_request_scope.py','infer_map_wrapper.py','infer_json_tree_observation.py','infer_before_advice.py','infer_scalar_projection.py','infer_json_list_copy.py')
 for (file,line,name),v in s.stats.items():
  leaf=Path(file).name
  group='required_evidence_modules'if leaf in evidence else'interpreter_and_dependency_state'if leaf in('infer_application_execution.py','execution_dependency_state.py','member_state_transfer.py','infer_sequence_kernel.py','infer_remove_if.py')else'decode'if leaf in('decoder.py','__init__.py')and('/json/'in file or leaf=='decoder.py')else'binding_graph_query'if leaf in('infer_response_binding.py','infer_distributed_fields.py')else'other_including_imports'
  groups[group]['calls']+=v[1];groups[group]['self_profile_seconds']+=v[2];top.append({'file':file,'line':line,'function':name,'primitive_calls':v[0],'total_calls':v[1],'self_seconds':v[2],'cumulative_seconds':v[3]})
 return {'groups':dict(groups),'top_self_functions':sorted(top,key=lambda r:-r['self_seconds'])[:25],'all_profiled_self_seconds':sum(v[2]for v in s.stats.values()),'warning':'cProfile wall-clock diagnosis only, not formal CPU attribution; module groups are an explicit lower-bound partition. Necessary checks embedded in interpreter are not removed or separately timed. Never sum cumulative times.'}

def formal_row(home,repeat,task,arm):
 from run_sockshop_cost import Sampler,percentiles
 from audit_zlt_body_cost import attributable
 folder=home/'formal'/('%02d-%s-%s'%(repeat,task,arm));assert load(folder/'complete.json')['complete'];assert not(folder/'capture/monitor-cost.json').exists()and not(folder/'capture/events.jsonl.diagnostic.jsonl').exists()
 a=load(folder/'warmup.json')['requests'];b=load(folder/'measure.json');cases=b['requests'];assert len(a)==60 and len(cases)==120
 summary=load(folder/'oracle/summary.json');assert summary['correct']==summary['targets']and summary['correct']>0
 samples=[json.loads(x)for x in(folder/'resources.jsonl').read_text().splitlines()];roles=('admin','auth','portal')if task=='mall'else('zlt-user','zlt-uaa')if task=='zlt-user'else('system','auth');sampler=Sampler({r:None for r in samples[0]},2,folder/'unused-audit.jsonl',observed_roles=roles);sampler.rows=samples;resources=sampler.summary(b['start_ns'],b['end_ns']);assert resources==load(folder/'resource-summary.json')
 lines=(folder/'capture/events.jsonl').read_bytes().splitlines(keepends=True);events=[json.loads(x)for x in lines];parents={}
 for r in events:
  if r.get('message')and r.get('parent_message'):
   assert parents.get(r['message'],r['parent_message'])==r['parent_message'];parents[r['message']]=r['parent_message']
 counts=attributable(events,lines,{c['message']for c in cases},{c['message']for c in cases+a},parents);p=percentiles([c['http_seconds']*1000 for c in cases]);trace=load(folder/'trace/summary.json');oracle=load(folder/'oracle/summary.json')
 row={'repeat':repeat,'task':task,'arm':arm,'targets':summary['targets'],'correct':summary['correct'],'business_CPU':resources['observed_jvms']['cpu_one_core_percent_mean'],'business_RSS_MiB':resources['observed_jvms']['rss_bytes_mean']/2**20,'business_peak_RSS_MiB':resources['observed_jvms']['rss_bytes_peak']/2**20,'p50_ms':p['p50'],'p95_ms':p['p95'],'p99_ms':p['p99'],**counts,'trace_VmHWM_KiB':trace['VmHWM_KiB'],'oracle_VmHWM_KiB':oracle['VmHWM_KiB']}
 for kind,value in [('trace',trace),('oracle',oracle)]:
  for k,v in load(folder/(kind+'-process.json')).items():
   if k.endswith('_seconds'):row[kind+'_process_'+k]=v
  for k,v in value['phases_seconds'].items():row[kind+'_'+k+'_wall_seconds']=v
  for k,v in value['cpu_phases_seconds'].items():row[kind+'_'+k+'_cpu_seconds']=v
 return row

def paired(rows):
 result={};metrics=[k for k in rows[0]if k not in('repeat','task','arm','targets','correct')]if rows else[]
 for task,arm in sorted({(r['task'],r['arm'])for r in rows if r['arm']!='none'}):
  data={}
  for metric in metrics:
   old=[];new=[];ratios=[]
   for repeat in range(1,6):
    a=next(r for r in rows if r['repeat']==repeat and r['task']==task and r['arm']=='none')[metric];b=next(r for r in rows if r['repeat']==repeat and r['task']==task and r['arm']==arm)[metric];old.append(a);new.append(b)
    if a:ratios.append(b/a)
   data[metric]={'baseline_median':statistics.median(old),'arm_median':statistics.median(new),'median_ratio':statistics.median(ratios)if ratios else None,'min_ratio':min(ratios)if ratios else None,'max_ratio':max(ratios)if ratios else None}
  result[task+'-'+arm]=data
 return result

def run(home,out,formal=False):
 out.mkdir(parents=True,exist_ok=False);protocol=load(home/'protocol-before-change.json');data={'protocol_sha256':sha(home/'protocol-before-change.json'),'core_reference':'4cb5943','score_reference':'df977b7','diagnosis':{},'old_complete_capture_profiles':{}}
 for task in protocol['order']:
  data['diagnosis'][task]={}
  for arm in ARMS:
   folder=home/'short'/(task+'-'+arm);assert load(folder/'complete.json')['complete'];data['diagnosis'][task][arm]={'counts':count_trial(home,folder,task),'observer_cost':diagnostic(folder)}
  data['old_complete_capture_profiles'][task]=profile(home/'offline-diagnostics'/(task+'-trace'))
 if(home/'coarse/complete.json').exists():
  data['coarse_baseline_diagnosis']={task:diagnostic(home/'coarse'/(task+'-none'))for task in protocol['order']}
 if formal:
  assert load(home/'pipeline-complete.json')['complete'];jobs=load(home/'formal-matrix-after-diagnosis.json')['jobs'];rows=[formal_row(home,*job)for job in jobs];data['formal']={'rows':rows,'paired':paired(rows),'independent_oracle_is_excluded_from_trace':True,'resource_recomputed_exact':True}
  with(out/'rounds.csv').open('w')as f:
   w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 save(out/'summary.json',data);print('Pruning contribution accounting validated')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--formal',action='store_true');a=p.parse_args();run(a.home.resolve(),a.out.resolve(),a.formal)
