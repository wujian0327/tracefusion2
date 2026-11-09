"""Read-only frozen files, library consistency and raw source mismatch controls."""
import copy,json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from run_unrelated_work_scaling import H,ROOT,F,load,save,sha,verify
from audit_zlt_foundation_revision import tf_pair

def run(out):
 verify();out.mkdir(exist_ok=False);checks=[]
 for tier in('low','medium','high'):
  path=H/'pilot-controlled-04'/(tier+'-full');rows=[json.loads(l)for l in(path/'capture/events.jsonl').read_text().splitlines()];source=next(r for r in rows if r['kind']=='binding-source');ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==source['message']);f=next(f for f in source['fields']if f['path']=='/target');target=next(f for f in ret['fields']if f['path']=='/target')
  for fault in('missing-completion','duplicate-start','wrong-PC','wrong-call-id','wrong-source-object','wrong-version','duplicate-field'):
   bad=copy.deepcopy(rows);s=next(r for r in bad if r['seq']==source['seq']);cid=s['source_call_id'];start=next(r for r in bad if r['kind']=='collection-call-enter'and r.get('call_id')==cid)
   if fault=='missing-completion':bad[:]=[r for r in bad if not(r['kind']=='collection-call-exit'and r.get('call_id')==cid)]
   elif fault=='duplicate-start':bad.append(copy.deepcopy(start))
   elif fault=='wrong-PC':s['source_pc']+=1
   elif fault=='wrong-call-id':s['source_call_id']='wrong-instance'
   elif fault=='wrong-source-object':next(v for v in s['fields']if v['path']=='/target')['owner']='same-value-other-object'
   elif fault=='wrong-version':next(v for v in s['fields']if v['path']=='/target')['version']+=1
   else:s['fields'].append(copy.deepcopy(next(v for v in s['fields']if v['path']=='/target')))
   try:
    tf_pair(bad,s);fs=[v for v in s['fields']if v['path']=='/target'];assert len(fs)==1 and all(fs[0][k]==target[k]for k in('owner','field','version'))
   except (ValueError,AssertionError):checks.append({'tier':tier,'fault':fault,'no_raw_oracle_certification':True})
   else:raise AssertionError('Raw source fault accepted '+fault)
  # Same-task Jackson implementation; no native bundled substitute accepted.
  witness=[json.loads(l)for l in(H/'pilot-controlled-04'/(tier+'-mirrortaint')/'capture/native-library.jsonl').read_text().splitlines()];w=[r for r in witness if r.get('class')=='com/fasterxml/jackson/databind/ObjectMapper'];assert len(w)==1
  import hashlib
  with ZipFile(H/'controlled-build-04'/tier/'business.jar')as z,ZipFile(BytesIO(z.read('BOOT-INF/lib/jackson-databind-2.13.3.jar')))as j:digest=hashlib.sha256(j.read('com/fasterxml/jackson/databind/ObjectMapper.class')).hexdigest()
  assert w[0]['sha256']==digest and 'jackson-databind-2.13.3.jar' in w[0]['source'];checks.append({'tier':tier,'MT_actual_Jackson_matches_business':True,'class_sha256':digest})
 # Sticky invalid footer remains active even without a problem row.
 from infer_distributed_fields import Reconstruction
 trial=H/'pilot-controlled-04/low-full';rows=[json.loads(l)for l in(trial/'capture/events.jsonl').read_text().splitlines()];rows[-1]['capture_invalid']=True
 (out/'build/role').mkdir(parents=True);(out/'capture/role').mkdir(parents=True);(out/'build/role/plan.json').write_bytes((H/'controlled-build-04/low/plan.json').read_bytes());(out/'capture/role/events.jsonl').write_text(''.join(json.dumps(r)+'\n'for r in rows))
 try:Reconstruction(out/'build',out/'capture',['role'],decoded_rows={'role':rows})
 except ValueError:checks.append({'sticky_invalid_without_problem':'rejected'})
 else:raise AssertionError('Sticky invalid accepted')
 save(out/'checks.json',{'checks':checks,'passed':True,'core_sources_unchanged':len(load(F/'algorithm-freeze.json')['sources']),'scope':'Raw oracle fault controls plus production sticky failure; not new framework semantics or proof of arbitrary concurrency.'});print('CHECKS',len(checks))

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
