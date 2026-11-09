"""Strict post-run byte accounting; no grouping by trace ID alone or time.
Only explicit message parentage, validated concrete spans, recorded Frame ancestry
and native root identities establish ownership. Every line stays in batch totals.
"""
import collections,json
from pathlib import Path
from run_unrelated_work_scaling import H,load,save,verify
from transport_context import validate_protocol

def run():
 verify();assert load(H/'formal-complete.json')['passed'];checks=[]
 for job in load(H/'formal-order-before-timing.json')['jobs']:
  if job['mode']=='original':continue
  trial=H/'formal'/('%02d-%s-%s-%s'%(job['round'],job['task'],job['tier'],job['mode']));dest=trial/'attribution-strict.json';assert not dest.exists()
  phases={c['message']:phase for phase in('warmup','measure')for c in load(trial/(phase+'.json'))['requests']};seed=set(phases)
  files=['events.jsonl']if job['mode'] in('full','selective')else['native-capability.jsonl','instances.jsonl','native-library.jsonl'];lines=[]
  for name in files:
   for line in(trial/'capture'/name).read_bytes().splitlines(keepends=True):lines.append((line,json.loads(line),name))
  rows=[r for _,r,_ in lines];wire=[r for r in rows if r['kind']in('http-json','http-rpc-enter','http-rpc-exit','http-rpc-abort')or r.get('communication_version')==2 or r['kind'].startswith('communication-')]
  plan=load(H/'mall-plan.json');contract=plan.get('communication_identity')if job['mode']!='mirrortaint'else None
  validate_protocol(rows,contract.get('version',1)if contract else 1,contract)
  parents=collections.defaultdict(set);spans=collections.defaultdict(set)
  for r in wire:
   if r.get('trace_id')and r.get('span_id')and r.get('message'):spans[(r['trace_id'],r['span_id'])].add(r['message'])
   if r['kind']=='http-rpc-enter'and r.get('parent_message')and r.get('message')!=r['parent_message']:parents[r['message']].add(r['parent_message'])
  # Exact concrete span parent, never a trace-prefix collapse. Unobserved
  # remote spans do not become local parents merely because the trace matches.
  for r in wire:
   if r['kind']!='http-rpc-enter':continue
   candidates=spans.get((r.get('trace_id'),r.get('parent_span_id')),set())
   if len(candidates)==1:
    p=next(iter(candidates))
    if p!=r['message']:parents[r['message']].add(p)
  memo={}
  def owners(message,seen=None):
   if message in seed:return {message}
   if message is None:return set()
   if message in memo:return memo[message]
   seen=set()if seen is None else seen
   if message in seen:raise ValueError('Metric message parent cycle')
   result=set()
   for p in parents.get(message,()):result|=owners(p,seen|{message})
   memo[message]=result;return result
  frames={r['frame']:r for r in rows if r['kind']=='enter'};frame_seed=collections.defaultdict(set);native_roots=collections.defaultdict(set)
  for r in rows:
   if r['kind']=='binding-return':frame_seed[r['frame']]|=owners(r.get('message'))
   if r['kind']=='target':native_roots[r['root']]|=owners(r.get('context',{}).get('message'))
  frame_memo={}
  def frame_owners(f,seen=None):
   if f is None:return set()
   if f in frame_memo:return frame_memo[f]
   seen=set()if seen is None else seen
   if f in seen:raise ValueError('Metric Frame parent cycle')
   result=set(frame_seed.get(f,()))
   if f in frames:result|=frame_owners(frames[f].get('parent'),seen|{f})
   frame_memo[f]=result;return result
  calls={r['call_id']:frame_owners(r.get('frame'))for r in rows if r['kind']=='collection-call-enter'}
  counts={name:{'events':0,'bytes':0}for name in('batch','measure','warmup','unattributed_or_shared')};ambiguous=0
  for line,r,name in lines:
   counts['batch']['events']+=1;counts['batch']['bytes']+=len(line)
   possible=set();possible|=owners(r.get('message'));possible|=owners(r.get('context',{}).get('message'))
   for key in('frame','root_frame','caller_frame'):possible|=frame_owners(r.get(key))
   possible|=native_roots.get(r.get('root'),set())
   if r['kind'].startswith('collection-call-'):possible|=calls.get(r.get('call_id'),set())
   category=phases[next(iter(possible))]if len(possible)==1 else'unattributed_or_shared'
   if len(possible)>1:ambiguous+=1
   counts[category]['events']+=1;counts[category]['bytes']+=len(line)
  assert sum(counts[k]['bytes']for k in('measure','warmup','unattributed_or_shared'))==counts['batch']['bytes']
  old=load(trial/'audit/summary.json');assert counts['batch']['bytes']==old['batch_bytes']and counts['batch']['events']==old['batch_events']
  result={'counts':counts,'ambiguous_owner_records':ambiguous,'explicit_message_parents':{k:sorted(v)for k,v in parents.items()},'trace_id_alone_used':False,'time_or_values_used':False,'old_audit_measure_bytes_not_used':old.get('measure_bytes'),'rules':'Validated actual RPC parent_message or exact recorded parent span; actual Frame ancestry/native root; all other bytes remain in batch shared/unattributed.'}
  save(dest,result);checks.append({'trial':str(trial),'measure_bytes':counts['measure']['bytes'],'batch_bytes':counts['batch']['bytes'],'unattributed_or_shared_bytes':counts['unattributed_or_shared']['bytes'],'ambiguous':ambiguous})
 save(H/'strict-attribution-complete.json',{'captures':len(checks),'checks':checks,'all_batch_totals_identical':True,'no_trace_prefix_assignment':True});print('ATTRIBUTION COMPLETE',len(checks))

if __name__=='__main__':run()
