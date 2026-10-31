"""Independent raw source/target coordinates; prediction never defines truth."""
import argparse,collections,copy,csv,json
from pathlib import Path
from run_planned_service import load,save,sha
from query_observation_planner import require

def ancestor(frame,root,frames):
 seen=set()
 while frame in frames and frame not in seen:
  if frame==root:return True
  seen.add(frame);frame=frames[frame].get('parent')
 return False

def fields_equal(source_fields,target_fields,source_path,path):
 source=[f for f in source_fields if f['path']==source_path];target=[f for f in target_fields if f['path']==path]
 require(len(source)==len(target)==1,'Raw source/target field missing or ambiguous')
 a,b=source[0],target[0]
 require(all(a.get(k)is not None and a.get(k)==b.get(k)for k in ('owner','field','version')),'Raw source/target object-field-version differs')
 return a

def tf_pair(rows,source):
 cid=source.get('source_call_id')
 require(cid is not None,'Source snapshot has no actual invocation')
 if source.get('source_scope')=='observation-only-call':
  starts=[r for r in rows if r['kind']=='source-call-enter'and r.get('source_call_id')==cid];ends=[r for r in rows if r['kind']=='source-call-exit'and r.get('source_call_id')==cid]
  require(len(starts)==len(ends)==1,'Observation-only source completion missing/ambiguous');start,end=starts[0],ends[0]
  require(source.get('source_observation_frame')==start['observation_frame']==end['observation_frame'],'Observation-only caller invocation differs')
  method=start['caller_method']
 else:
  starts=[r for r in rows if r['kind']=='collection-call-enter'and r.get('call_id')==cid];ends=[r for r in rows if r['kind']=='collection-call-exit'and r.get('call_id')==cid]
  require(len(starts)==len(ends)==1,'Planned source completion missing/ambiguous');start,end=starts[0],ends[0];method=start['method']
 require(start['seq']<source['seq']<end['seq'] and source['frame']==start['frame']==end['frame']and source['callee']==start['callee'],'Raw source call interval/parent differs')
 require(source.get('source_caller_method')==method and source.get('source_pc')==start['pc'],'Raw source caller/PC differs')
 return {'call_id':cid,'caller':method,'pc':start['pc'],'frame':source['frame'],'start':start['seq'],'completion':end['seq'],'scope':source['source_scope']}

def audit(home,out):
 from infer_distributed_fields import Reconstruction
 from infer_source_observation import validate as validate_observation
 from run_mirror_capability_probe import read_events,native_answer
 from native_source_protocol import validate as validate_native
 import external_transfer_oracle as oracle
 out.mkdir(parents=True,exist_ok=False);records=[];receipts=[];guards={}
 for q in load(home/'task-seal.json')['entries']:
  api=q['id'];original=load(home/'runs'/api/'original/selected-requests.json');plan=load(home/'planning-first'/api/'000-plan.json');leaf=q['return_targets'][0]['path'].split('/')[-1]
  def leaves(case):return [('/data/%d/'%i+leaf,x[leaf])for i,x in enumerate(case['response']['data'])]
  for mode in ('full','selective','mirrortaint'):
   folder=home/'runs'/api/mode;cases=load(folder/'selected-requests.json');before={c['case']:c for c in original};raw_path=folder/'capture'/('native-capability.jsonl'if mode=='mirrortaint'else'events.jsonl');rows=[json.loads(s)for s in raw_path.read_text().splitlines()];frames={r['frame']:r for r in rows if r['kind']=='enter'};error=None;graph=None;native=[];protocol=None
   try:
    if mode=='mirrortaint':
     view=out/(api+'-native-view');view.mkdir();(view/'role').symlink_to((folder/'capture').resolve(),target_is_directory=True);native=read_events(view,'role');protocol=validate_native(native)
    else:
     oracle.require_complete_raw_capture(rows);protocol=validate_observation(plan,rows);b=out/(api+'-'+mode)/'build'/q['role'];b.mkdir(parents=True);(b/'plan.json').write_bytes((home/'planning-first'/api/'000-plan.json').read_bytes());c=b.parents[1]/'capture'/q['role'];c.mkdir(parents=True);(c/'events.jsonl').symlink_to(raw_path.resolve());graph=Reconstruction(b.parents[1]/'build',b.parents[1]/'capture',[q['role']])
   except Exception as e:error=type(e).__name__+': '+str(e)
   business_equal=all(c['http_status']==before[c['case']]['http_status']and c['response']==before[c['case']]['response']for c in cases)
   receipts.append({'api':api,'mode':mode,'requests':len(cases),'business_equal':business_equal,'selected_task_equal':all(c['http_status']==before[c['case']]['http_status']and leaves(c)==leaves(before[c['case']])for c in cases),'protocol':protocol,'error':error,'raw_sha256':sha(raw_path),'source_fields':sum(r['kind']in('binding-source','source')and(r.get('callee')or r.get('call'))==q['oracle']['source']for r in rows)})
   for case in cases:
    for path,value in leaves(before[case['case']]):
     r={'api':api,'mode':mode,'case':case['case'],'path':path,'positive':True,'business_equal':case['response']==before[case['case']]['response']and case['http_status']==200,'target_bound':False,'source_paired':False,'oracle_adequate':False,'state':'evidence_invalid'if error else'unknown','error':error}
     r['selected_task_equal']=case['http_status']==before[case['case']]['http_status']and leaves(case)==leaves(before[case['case']])
     try:
      require(r['selected_task_equal'],'Selected declared task response differs')
      if mode=='mirrortaint':
       targets=[s for s in rows if s['kind']=='target'and s['context'].get('message')==case['message']];require(len(targets)==1,'Actual native target/root absent/ambiguous');target=targets[0]
       wire=[f for e in [json.loads(s)for s in(folder/'capture/instances.jsonl').read_text().splitlines()]if e['kind']=='http-json'and e.get('direction')=='response'and e.get('phase')=='write'and e.get('message')==case['message']for f in e['fields']]
       selected=[f for f in wire if f['path']==path];require(len(selected)==1,'Native wire target absent/ambiguous');r['target_bound']=True
       sources=[s for s in rows if s['kind']=='source'and s.get('root')==target['root']and s.get('call')==q['oracle']['source']];require(len(sources)==1,'Actual native mapper occurrence absent/ambiguous');source=sources[0]
       validate_native(rows);r['source_paired']=True;r['source_call_id']=source['source_call_id'];r['source_caller']=source['caller_method'];r['source_pc']=source['instrumented_instruction_index']
       field=fields_equal(source['fields'],wire,path[len('/data'):],path);require(field['value']==value,'Native raw source value differs');r['expected']=[source['call'],source['ordinal'],field['path'],field['owner'],field['field'],field['version']];r['oracle_adequate']=not error
       if not error:
        a=native_answer(native,case['message'],path);r['answer']=a;r['state']='known_correct'if a['state']=='known'and set(map(tuple,a['sources']))=={tuple(r['expected'])}else'known_wrong'if a['state']=='known'else a['state']
      else:
       targets=[s for s in rows if s['kind']=='binding-return'and s.get('message')==case['message']];require(len(targets)==1,'Actual TF target/root absent/ambiguous');target=targets[0];r['target_bound']=len([f for f in target['fields']if f['path']==path])==1
       sources=[s for s in rows if s['kind']=='binding-source'and s.get('callee')==q['oracle']['source']and ancestor(s.get('frame'),target['frame'],frames)];require(len(sources)==1,'Actual mapper occurrence absent/ambiguous');source=sources[0];pair=tf_pair(rows,source);r['source_paired']=True;r['pair']=pair
       field=fields_equal(source['fields'],target['fields'],path[len('/data'):],path);require(field['observed']['value']==value,'Raw mapper field differs from original business value');r['expected']=[source['callee'],source['frame'],source['seq'],field['path'],field['owner'],field['field'],field['version']];r['oracle_adequate']=not error
       if not error:
        a=graph.query(case['message'],path,q['role'],boundary=[{'kind':'binding-source'},{'kind':'argument'}]);r['answer']=a;got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']};r['state']='known_correct'if a['known']and got=={tuple(r['expected'])}else'known_wrong'if a['known']else'unknown'
     except Exception as e:r['gap']=str(e)
     records.append(r)
   if not error and mode=='mirrortaint':
    for fault in ('missing-tag','missing-completion','wrong-object','ambiguous-source','problem'):
     bad=copy.deepcopy(native);target=next(r for r in bad if r['kind']=='target'and r.get('wire_fields'));field=next(f for f in target['fields']if f.get('path','').endswith('/'+leaf))
     if fault=='missing-tag':
      coord={k:field[k]for k in('owner','field','version')}
      for e in bad:
       if e['kind']in('target','native-observation'):
        for f in e['fields']:
         if all(f.get(k)==v for k,v in coord.items()):f['tag_present']=False
      assert native_answer(bad,target['context']['message'],field['path'])['state']!='known';guards[api+'-'+fault]=True;continue
     if fault=='missing-completion':bad.remove(next(r for r in bad if r['kind']=='source-call-exit'))
     elif fault=='wrong-object':next(r for r in bad if r['kind']=='source-call-exit')['result_identity']='other'
     elif fault=='ambiguous-source':bad.insert(-1,copy.deepcopy(next(r for r in bad if r['kind']=='source'and not r['call'].startswith('@argument:'))))
     else:
      # Main decoder rejects problems; protocol also retains the fact separately.
      bad.insert(-1,{'kind':'problem','error':'injected exporter failure'})
     try:validate_native(bad)
     except ValueError:guards[api+'-'+fault]=True
     else:raise AssertionError('Damaged native protocol accepted: '+fault)
 summary={'development_regression':True,'same_two_tasks':True,'all40_retained':True,'no_new_framework_contract':True,'receipts':receipts,'states':{m:dict(collections.Counter(r['state']for r in records if r['mode']==m))for m in('full','selective','mirrortaint')},'adequate_oracles':{m:sum(r['oracle_adequate']for r in records if r['mode']==m)for m in('full','selective','mirrortaint')},'guards':guards}
 save(out/'instances.json',records);save(out/'summary.json',summary)
 with(out/'instances.csv').open('w')as f:
  w=csv.DictWriter(f,fieldnames=['api','mode','case','path','business_equal','selected_task_equal','target_bound','source_paired','oracle_adequate','state','error','gap'],extrasaction='ignore');w.writeheader();w.writerows(records)
 print(summary)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.home.resolve(),a.out.resolve())
