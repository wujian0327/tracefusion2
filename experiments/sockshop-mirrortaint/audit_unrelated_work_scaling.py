"""Raw source truth first, prediction second; normal provenance and scoring separate."""
import argparse,json,time,resource,traceback
from pathlib import Path
from run_unrelated_work_scaling import H,F,HERE,load,save,sha,verify,TIERS

def run(out,task,tier,mode):
 verify();dest=out/'audit';dest.mkdir(exist_ok=False);cases=load(out/'warmup.json')['requests']+load(out/'measure.json')['requests'];summary={'task':task,'tier':tier,'mode':mode,'requests':len(cases),'business_passed':sum(c['business_passed']for c in cases),'correct':0,'targets':len(cases),'stages':{},'normal_trace_seconds':None};scores=[]
 if mode=='original':save(dest/'summary.json',summary);return summary
 path='/target'if task=='controlled'else'/data/expiresIn';callee='bench/Store.read()Lbench/Payload;'if task=='controlled'else'AuthService.getAccessToken'
 start=time.perf_counter();cpu=time.process_time()
 try:
  if mode in('full','selective'):
   from infer_distributed_fields import Reconstruction
   import external_transfer_oracle as oracle
   from audit_zlt_foundation_revision import tf_pair
   from raw_source_call_facts import RawSourceCallFacts
   t=time.perf_counter();rows=oracle.raw(out/'capture/events.jsonl');oracle.require_complete_raw_capture(rows);summary['stages']['decode_integrity']=time.perf_counter()-t
   planfile=H/'controlled-build-04'/tier/'plan.json'if task=='controlled'else H/'mall-plan.json'
   # Raw invocation facts are computed independently before any graph exists.
   t=time.perf_counter();facts=RawSourceCallFacts(rows);index=oracle.RawFactIndex(rows);expected=[];coordinates=[]
   for c in cases:
    ret=[r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']];assert len(ret)==1,'target absent/ambiguous';ret=ret[0]
    if task=='mall':
     src=[r for r in index.source_family(ret['frame'])if callee in r.get('callee','')];assert len(src)==1,'RPC source absent/ambiguous';tf_pair(facts.matching(rows,src[0]),src[0])
     want={tuple(x)for x in oracle.tf_expected(rows,ret,{'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'},path,raw_index=index)}
     sf=[f for f in src[0]['fields']if f['path']==path];tf=[f for f in ret['fields']if f['path']==path];assert len(sf)==len(tf)==1 and all(sf[0][k]==tf[0][k]for k in('owner','field','version')),'Raw RPC return target coordinates differ'
    else:
     src=[r for r in index.source_family(ret['frame'])if r.get('callee')==callee];assert len(src)==1,'source absent/ambiguous';src=src[0];tf_pair(facts.matching(rows,src),src)
     field=[f for f in src['fields']if f['path']==path];assert len(field)==1;field=field[0]
     target=[f for f in ret['fields']if f['path']==path];assert len(target)==1;assert all(target[0][k]==field[k]for k in('owner','field','version'))
     want={(src['callee'],src['frame'],src['seq'],field['path'],field['owner'],field['field'],field['version'])}
    assert want;expected.append(want);coordinates.append({'message':c['message'],'expected':sorted(want,key=str)})
   save(dest/'raw-truth-before-prediction.json',coordinates);summary['stages']['independent_raw_oracle']=time.perf_counter()-t
   t=time.perf_counter();(dest/'build/role').mkdir(parents=True);(dest/'capture/role').mkdir(parents=True);(dest/'build/role/plan.json').write_bytes(planfile.read_bytes());(dest/'capture/role/events.jsonl').symlink_to((out/'capture/events.jsonl').resolve())
   g=Reconstruction(dest/'build',dest/'capture',['role'],decoded_rows={'role':rows});summary['stages']['reconstruct_all_required_checks']=time.perf_counter()-t
   t=time.perf_counter();answers=[g.query(c['message'],path,'role',boundary=[{'kind':'binding-source'},{'kind':'argument'}])for c in cases];summary['stages']['query']=time.perf_counter()-t
   t=time.perf_counter();save(dest/'answers.json',answers);summary['stages']['export']=time.perf_counter()-t
   t=time.perf_counter()
   for c,want,a in zip(cases,expected,answers):
    got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']};scores.append({'message':c['message'],'known':a['known'],'correct':a['known']and got==want,'expected':sorted(want,key=str),'actual':sorted(got,key=str),'version':a['target'].get('version'),'selectors':a.get('selectors'), 'state':'known_correct'if a['known']and got==want else'known_wrong'if a['known']else'unknown'})
   summary['stages']['independent_score']=time.perf_counter()-t
   policies=[r['target_observation']for r in rows if r.get('target_observation')];summary['actual_scalar_omissions']=sum(sum(p.get('scalar_fields',{}).values())for p in policies);summary['actual_container_value_omissions']=sum(sum(p.get('container_values',{}).values())for p in policies)
   summary['batch_bytes']=(out/'capture/events.jsonl').stat().st_size;summary['batch_events']=len(rows)
   frame_message={r['frame']:r.get('message')for r in rows if r['kind']=='binding-return'};enters={r['frame']:r for r in rows if r['kind']=='enter'}
   def fm(f):
    seen=set()
    while f not in seen:
     seen.add(f)
     if frame_message.get(f):return frame_message[f]
     if f not in enters:return None
     f=enters[f].get('parent')
   bytrace={c['message'].split('/')[0]:c['message']for c in cases};measured={c['message']for c in load(out/'measure.json')['requests']};bytecount=events=0
   for line,r in zip((out/'capture/events.jsonl').read_bytes().splitlines(keepends=True),rows):
    msg=r.get('message')or fm(r.get('frame'))or fm(r.get('caller_frame'));msg=bytrace.get(msg.split('/')[0],msg)if msg else None
    if msg in measured:events+=1;bytecount+=len(line)
   summary.update(measure_bytes=bytecount,measure_events=events,attribution='actual message/root ancestry; unpaired/shared retained in batch')
  else:
   from run_mirror_capability_probe import read_events,native_answer
   import external_transfer_oracle as oracle
   t=time.perf_counter();view=dest/'native-view';view.mkdir();(view/'role').symlink_to((out/'capture').resolve(),target_is_directory=True);rows=read_events(view,'role');summary['stages']['decode_integrity_bind']=time.perf_counter()-t
   t=time.perf_counter();expected=[];coordinates=[]
   for c in cases:
    roots=[r for r in rows if r['kind']=='target'and r['context'].get('message')==c['message']];assert len(roots)==1,'native target absent/ambiguous';root=roots[0]
    if task=='mall':
     want={tuple(s)for s in oracle.native_expected(rows,root['root'],{'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'},path)}
     src=[s for s in rows if s['kind']=='source'and s['root']==root['root']and callee in s['call']];assert len(src)==1;sf=[f for f in src[0]['fields']if f['path']==path];tf=[f for f in root['fields']if f['path']==path];assert len(sf)==len(tf)==1 and all(sf[0][k]==tf[0][k]for k in('owner','field','version')),'Raw RPC return target coordinates differ'
    else:
     src=[r for r in rows if r['kind']=='source'and r['root']==root['root']and r['call']==callee];assert len(src)==1,'native source absent/ambiguous';src=src[0]
     selected=[f for f in src['fields']if f['path']==path or tier=='related-high'and f['path'].startswith('/f')];assert len(selected)==(257 if tier=='related-high'else 1)
     target=[f for f in root['fields']if f['path']==path];assert len(target)==1
     if tier!='related-high':assert all(target[0].get(k)==selected[0].get(k)for k in('owner','field','version'))
     want={(src['call'],src['ordinal'],f['path'],f['owner'],f['field'],f['version'])for f in selected}
    expected.append(want);coordinates.append({'message':c['message'],'expected':sorted(want,key=str)})
   save(dest/'raw-truth-before-prediction.json',coordinates);summary['stages']['independent_raw_oracle']=time.perf_counter()-t
   t=time.perf_counter();answers=[native_answer(rows,c['message'],path)for c in cases];summary['stages']['native_decode_query']=time.perf_counter()-t
   t=time.perf_counter();save(dest/'answers.json',answers);summary['stages']['export']=time.perf_counter()-t
   t=time.perf_counter()
   for c,want,a in zip(cases,expected,answers):
    got=set(map(tuple,a.get('sources',[])));scores.append({'message':c['message'],'known':a['state']=='known','correct':a['state']=='known'and got==want,'expected':sorted(want,key=str),'actual':sorted(got,key=str),'state':'known_correct'if a['state']=='known'and got==want else'known_wrong'if a['state']=='known'else a['state']})
   summary['stages']['independent_score']=time.perf_counter()-t
   bytrace={c['message'].split('/')[0]:c['message']for c in cases};measured={c['message']for c in load(out/'measure.json')['requests']};roots={r['root']:r['context']['message']for r in rows if r['kind']=='target'};counts={'batch_bytes':0,'batch_events':0,'measure_bytes':0,'measure_events':0}
   for name in('native-capability.jsonl','instances.jsonl','native-library.jsonl'):
    for line in(out/'capture'/name).read_bytes().splitlines(keepends=True):
     r=json.loads(line);msg=r.get('context',{}).get('message')or r.get('message')or roots.get(r.get('root'));msg=bytrace.get(msg.split('/')[0],msg)if msg else None
     counts['batch_bytes']+=len(line);counts['batch_events']+=1
     if msg in measured:counts['measure_bytes']+=len(line);counts['measure_events']+=1
   summary.update(counts)
  summary['correct']=sum(s['correct']for s in scores);summary['states']={state:sum(s['state']==state for s in scores)for state in sorted({s['state']for s in scores})}
  normal=[v for k,v in summary['stages'].items()if not k.startswith('independent')];summary.update(normal_trace_seconds=sum(normal),independent_validation_seconds=sum(v for k,v in summary['stages'].items()if k.startswith('independent')),process_wall_seconds=time.perf_counter()-start,process_cpu_seconds=time.process_time()-cpu,VmHWM_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,all_capture_file_bytes=sum(f.stat().st_size for f in(out/'capture').rglob('*')if f.is_file()))
 except Exception as e:
  summary.update(error=type(e).__name__+': '+str(e));(dest/'failure.log').write_text(traceback.format_exc())
 save(dest/'scores.json',scores);save(dest/'summary.json',summary);print(summary,flush=True);return summary

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--trial',type=Path,required=True);p.add_argument('--task',choices=['mall','controlled'],required=True);p.add_argument('--tier',default='low');p.add_argument('--mode',required=True);a=p.parse_args();run(a.trial.resolve(),a.task,a.tier,a.mode)
