#!/usr/bin/env python3
"""Experiment audit: raw coordinates define truth independently of tool labels."""
import argparse,collections,csv,hashlib,json,statistics,subprocess,sys,time,resource
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.append(str(ROOT/'scripts'))
from run_frozen_zlt_reuse import load,save,sha

def native(capture,cases,path_rule,selected_paths):
 from run_mirror_capability_probe import read_events,native_answer
 view=capture.parent/'native-view';view.mkdir(exist_ok=False);(view/'role').symlink_to(capture.resolve(),target_is_directory=True)
 error=None
 try:rows=read_events(view,'role')
 except Exception as e:rows=[];error=str(e)
 result=[]
 for case in cases:
  for path,value in selected_paths(case['response']):
   r={'case':case['case'],'path':path,'positive':True,'state':'evidence_invalid'if error else'unknown','error':error,'oracle_adequate':False}
   if not error:
    a=native_answer(rows,case['message'],path);r['answer']=a
    try:
     roots=[s for s in rows if s['kind']=='target'and s['context'].get('message')==case['message']];assert len(roots)==1,'Actual target/root absent or ambiguous'
     sources=[s for s in rows if s['kind']=='source'and s['root']==roots[0]['root']and path_rule['callee']in s['call']];assert len(sources)==1,'Actual source call absent or ambiguous'
     source=sources[0];wanted=path_rule['source_path'](path)
     fields=[f for f in source['fields']if f['path']==wanted];assert len(fields)==1,'Actual source field absent or ambiguous'
     field=fields[0];assert all(k in field for k in ('owner','field','version'))
     want={(source['call'],source['ordinal'],field['path'],field['owner'],field['field'],field['version'])};r.update(expected=sorted(want,key=str),oracle_adequate=True)
     if a['state']=='known':r['state']='known_correct'if {tuple(s)for s in a['sources']}==want else'known_wrong'
     else:r['state']=a['state']
    except (ValueError,AssertionError)as e:r['oracle_gap']=str(e);r['state']='known_unchecked'if a['state']=='known'else a['state']
   result.append(r)
 return result

def mt_cost(home):
 trial=home/'calibration-v2-mirrortaint';cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests']
 records=native(trial/'capture',cases,{'callee':'AuthService.getAccessToken','source_path':lambda p:p},lambda response:[('/data/expiresIn',response['data']['expiresIn'])]if isinstance(response,dict)and isinstance(response.get('data'),dict)else[])
 # A correct exported field alone is insufficient for formal cross-tool costs:
 # dependency origin/configuration equivalence must also be positively audited.
 witness=trial/'capture/native-library.jsonl';libraries=[json.loads(s)for s in witness.read_text().splitlines()]if witness.exists()else[]
 summary={'targets':len(records),'states':dict(collections.Counter(r['state']for r in records)),'positive_correct':sum(r['state']=='known_correct'for r in records),'native_jar_sha256':sha(ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'),
  'library_witness_rows':len(libraries),'formal_cost_inclusion':'pending_dependency_and_scope_calibration','reason':'Fixed B0 exporter observes multiple fields and native instrumentation scope exceeds selected task. Same single target can be scored, but matched dependency/configuration and measurement-scope audit is not yet established; no forced ranking.'}
 save(home/'mt-calibration-instances.json',records);save(home/'mt-calibration-summary.json',summary);print(summary)

def mt_offline(trial):
 from run_mirror_capability_probe import read_events,native_answer
 import external_transfer_oracle as oracle
 start=time.perf_counter();cpu=time.process_time();out=trial/'offline-native';out.mkdir(exist_ok=False);view=out/'view';view.mkdir();(view/'role').symlink_to((trial/'capture').resolve(),target_is_directory=True)
 t=time.perf_counter();rows=read_events(view,'role');phases={'decode_validate_bind':time.perf_counter()-t};cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'];answers=[]
 t=time.perf_counter()
 for c in cases:answers.append((c,native_answer(rows,c['message'],'/data/expiresIn')))
 phases['native_tag_decode']=time.perf_counter()-t;t=time.perf_counter();save(out/'answers.json',[{'case':c['case'],'answer':a}for c,a in answers]);phases['export']=time.perf_counter()-t;t=time.perf_counter();scored=[]
 for c,a in answers:
  roots=[r for r in rows if r['kind']=='target'and r['context'].get('message')==c['message']];assert len(roots)==1
  want={tuple(s)for s in oracle.native_expected(rows,roots[0]['root'],{'kind':'rpc-field','api':'mall-swarm-3','rpc_owner':'AuthService'},'/data/expiresIn')};got={tuple(s)for s in a.get('sources',[])}
  scored.append({'case':c['case'],'known':a['state']=='known','exact':a['state']=='known'and bool(want)and want==got,'expected':sorted(want,key=str),'actual':sorted(got,key=str)})
 phases['independent_score']=time.perf_counter()-t;save(out/'scores.json',scored)
 measured={c['message']for c in load(trial/'measure.json')['requests']};bytrace={c['message'].split('/')[0]:c['message']for c in cases};counts={'measure_events':0,'measure_bytes':0,'batch_events':0,'batch_bytes':0,'shared_events':0,'shared_bytes':0}
 roots={r['root']:r['context']['message']for r in rows if r['kind']=='target'}
 for name in('native-capability.jsonl','instances.jsonl','native-library.jsonl'):
  for line in(trial/'capture'/name).read_bytes().splitlines(keepends=True):
   r=json.loads(line);msg=r.get('context',{}).get('message')or r.get('message')or roots.get(r.get('root'));msg=bytrace.get(msg.split('/')[0],msg)if msg else None
   counts['batch_events']+=1;counts['batch_bytes']+=len(line)
   if msg in measured:counts['measure_events']+=1;counts['measure_bytes']+=len(line)
   elif msg not in bytrace.values():counts['shared_events']+=1;counts['shared_bytes']+=len(line)
 files={str(f.relative_to(trial/'capture')):f.stat().st_size for f in(trial/'capture').rglob('*')if f.is_file()}
 result={'targets':len(scored),'correct':sum(r['exact']for r in scored),'positive':len(scored),'phases_seconds':phases,'core_seconds':phases['native_tag_decode'],'decode_validate_bind_seconds':phases['decode_validate_bind'],'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'VmHWM_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'capture_files_bytes':files,'all_capture_bytes':sum(files.values()),**counts}
 save(out/'summary.json',result);assert result['correct']==result['targets'];print({k:v for k,v in result.items()if k not in('capture_files_bytes','phases_seconds')})

def zlt(home):
 import external_transfer_oracle as oracle
 from infer_distributed_fields import Reconstruction
 records=[];apis=[]
 for q in load(home/'task-seal.json')['entries']:
  api=q['id'];original=load(home/'runs'/api/'original/selected-requests.json');planning=load(home/'planning-first'/api/'000.json');target=q['return_targets'][0];leaf=target['path'].split('/')[-1]
  def paths(response):return [('/data/%d/'%i+leaf,row[leaf])for i,row in enumerate(response.get('data',[]))if leaf in row]if isinstance(response,dict)else[]
  # Original database snapshot and unmodified query establish value/row truth;
  # instance truth still requires each tool's own raw mapper call coordinates.
  db=(home/'runs'/api/'original/independent-database.tsv').read_text();assert db and leaf in('clientId','username')
  for case in original:
   assert case['http_status']==200 and isinstance(case['response'],dict)and isinstance(case['response'].get('data'),list)
   for _,value in paths(case['response']):assert str(value)in db.splitlines()[0]or any(str(value)in line.split('\t')for line in db.splitlines()[1:]),'Original value missing from raw SQL'
  for mode in ('full','selective','mirrortaint'):
   folder=home/'runs'/api/mode
   if not(folder/'selected-requests.json').exists():
    for c in original:
     for path,value in paths(c['response']):records.append({'api':api,'mode':mode,'case':c['case'],'path':path,'state':'planning_rejected','positive':True,'oracle_adequate':False,'error':planning.get('reason')})
    continue
   current=load(folder/'selected-requests.json');bycase={c['case']:c for c in current};error=None;graph=None;raw=[]
   if mode=='mirrortaint':
    rr=native(folder/'capture',current,{'callee':q['oracle']['source'],'source_path':lambda p:p[len('/data'):]},paths)
    for r in rr:r.update(api=api,mode=mode)
    records.extend(rr);continue
   try:
    raw=oracle.raw(folder/'capture/events.jsonl');oracle.require_complete_raw_capture(raw)
    b=folder/'audit-build'/q['role'];b.mkdir(parents=True,exist_ok=False);(b/'plan.json').write_bytes((home/'planning-first'/api/'000-plan.json').read_bytes())
    c=folder/'audit-capture'/q['role'];c.mkdir(parents=True);(c/'events.jsonl').symlink_to((folder/'capture/events.jsonl').resolve())
    graph=Reconstruction(folder/'audit-build',folder/'audit-capture',[q['role']])
   except Exception as e:error=str(e)
   for before in original:
    c=bycase.get(before['case'])
    for path,value in paths(before['response']):
     r={'api':api,'mode':mode,'case':before['case'],'path':path,'state':'unknown','positive':True,'oracle_adequate':False}
     if c is None:r.update(state='environment_failure',error='No corresponding request')
     elif c['http_status']!=before['http_status']or c['response']!=before['response']:r.update(state='instrumented_business_failure',error='Original response differs')
     elif error:r.update(state='evidence_invalid',error=error)
     else:
      try:
       a=graph.query(c['message'],path,q['role'],boundary=[{'kind':'binding-source'},{'kind':'argument'}]);r['answer']=a
       roots=[s for s in raw if s['kind']=='binding-return'and s.get('message')==c['message']];assert len(roots)==1
       sources=[s for s in raw if s['kind']=='binding-source'and s.get('callee')==q['oracle']['source']and s.get('frame')==roots[0]['frame']];assert len(sources)==1,'Source occurrence absent/ambiguous; do not substitute helper return'
       source=sources[0];fs=[f for f in source['fields']if f['path']==path[len('/data'):]];assert len(fs)==1,'Source field absent/ambiguous'
       f=fs[0];want={(source['callee'],source['frame'],source['seq'],f['path'],f['owner'],f['field'],f['version'])};r.update(expected=sorted(want,key=str),oracle_adequate=True)
       got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']}
       r['state']='known_correct'if a['known']and got==want else'known_wrong'if a['known']else'unknown'
      except Exception as e:r.update(oracle_gap=str(e),state='known_unchecked'if r.get('answer',{}).get('known')else'unknown')
     records.append(r)
  apis.append({'api':api,'planning_status':planning['status'],'original_requests':len(original),'actual_positive_targets':sum(len(paths(c['response']))for c in original),'nonempty_requests':sum(bool(paths(c['response']))for c in original)})
 summary={'algorithm':'c1a4e5ceb60a276cc3651e4cdb413aa29d7f8d5d','pool_APIs':5,'selected_APIs':2,'all40_retained':True,'complete40_acceptance':False,'apis':apis,'states':{m:dict(collections.Counter(r['state']for r in records if r['mode']==m))for m in('full','selective','mirrortaint')},'oracle_adequate':dict(collections.Counter(r['mode']for r in records if r['oracle_adequate']))}
 save(home/'audit/instances.json',records);save(home/'audit/summary.json',summary)
 with(home/'audit/instances.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=['api','mode','case','path','state','positive','oracle_adequate','error','oracle_gap'],extrasaction='ignore');w.writeheader();w.writerows(records)
 print(summary)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['mt-cost','mt-offline','zlt']);p.add_argument('--home',type=Path,required=True);a=p.parse_args();{'mt-cost':mt_cost,'mt-offline':mt_offline,'zlt':zlt}[a.stage](a.home.resolve())
