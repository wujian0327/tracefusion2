"""Normal provenance execution excludes independent experiment-oracle scoring.

Required capture/certificate checks remain in decoding/reconstruction. A second
fresh process scores raw physical instances; it is never algorithm core time.
"""
import argparse,cProfile,json,pickle,time
from pathlib import Path
from run_planned_service import ROOT,load,save,sha

def run(protocol,task,out,score=None,profile=False,graph=False):
 spec=load(protocol)['tasks'][task]['selective'];cap=Path(spec['capture']);planfile=Path(spec['plan']);role=spec['role']
 assert sha(cap)==spec['capture_sha256']and sha(planfile)==spec['plan_sha256']
 out.mkdir(parents=True,exist_ok=False);phases={};cpus={};started=time.perf_counter();started_cpu=time.process_time()
 def timed(key,fn):
  t=time.perf_counter();c=time.process_time();v=fn();phases[key]=time.perf_counter()-t;cpus[key]=time.process_time()-c;return v
 def execute():
  import external_transfer_oracle as oracle
  def decode():
   rows=oracle.raw(cap);oracle.require_complete_raw_capture(rows);return rows
  rows=timed('decode_and_capture_integrity',decode);plan=load(planfile)
  from infer_response_binding import matches
  returns=[r for r in rows if r['kind']=='binding-return'];targets=[(r,f)for r in returns for f in r['fields']if matches(plan['response_binding']['path'],f['path'])]
  if score is None:
   from infer_distributed_fields import Reconstruction
   b=out/'build'/role;b.mkdir(parents=True);(b/'plan.json').write_bytes(planfile.read_bytes());c=out/'capture'/role;c.mkdir(parents=True);(c/'events.jsonl').symlink_to(cap)
   g=timed('reconstruction_including_all_required_certificates',lambda:Reconstruction(out/'build',out/'capture',[role],decoded_rows={role:rows}))
   answers=timed('query',lambda:[g.query(ret['message'],f['path'],role,boundary=[{'kind':'binding-source'},{'kind':'argument'}])for ret,f in targets])
   def export():
    save(out/'answers.json',answers)
    # Root evidence preserves origins, selectors, unknown and field versions.
    # Full graph export is an explicit compatibility-only mode, never timing.
    if graph:
     with(out/'graph.pkl').open('wb')as f:pickle.dump((g.nodes,g.edges,g.local_queries),f,protocol=4)
   timed('export',export)
   return {'targets':len(targets),'known':sum(a['known']for a in answers),'graph_compatibility_export':graph,'independent_score_excluded':True}
  from raw_source_call_facts import RawSourceCallFacts
  from audit_zlt_foundation_revision import tf_pair
  answers=load(score/'answers.json');assert len(answers)==len(targets)
  def independent():
   facts=RawSourceCallFacts(rows);index=oracle.RawFactIndex(rows);paired=set();scored=[]
   for (ret,f),a in zip(targets,answers):
    sources=[s for s in index.source_family(ret['frame'])if s.get('callee')in plan['response_binding']['source_calls']];want=[]
    for s in sources:
     if s['seq']not in paired:tf_pair(facts.matching(rows,s),s);paired.add(s['seq'])
     want.extend((s['callee'],s['frame'],s['seq'],v['path'],v['owner'],v['field'],v['version'])for v in s['fields']if all(v.get(k)==f.get(k)for k in('owner','field','version')))
    got=[(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']]
    assert len(want)==1 and a['known']and set(want)==set(got),(ret['message'],f['path'],want,got,a['known'])
    scored.append({'message':ret['message'],'path':f['path'],'known':True,'expected':want,'actual':got,'target_version':f['version']})
   return scored
  scores=timed('independent_raw_oracle_and_score',independent);timed('score_export',lambda:save(out/'scores.json',scores));return {'targets':len(scores),'correct':len(scores),'independent_validation_only':True}
 if profile:
  p=cProfile.Profile();r=p.runcall(execute);p.dump_stats(str(out/'profile.pstats'))
 else:r=execute()
 r.update(phases_seconds=phases,cpu_phases_seconds=cpus,normal_workflow_wall_seconds=time.perf_counter()-started,normal_workflow_cpu_seconds=time.process_time()-started_cpu,VmHWM_KiB=int(next(x.split()[1]for x in Path('/proc/self/status').read_text().splitlines()if x.startswith('VmHWM:'))),profile=profile,complete_capture_sha256=sha(cap),plan_sha256=sha(planfile))
 save(out/'summary.json',r);print({k:v for k,v in r.items()if k not in('phases_seconds','cpu_phases_seconds')})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--protocol',required=True,type=Path);p.add_argument('--task',required=True);p.add_argument('--out',required=True,type=Path);p.add_argument('--score',type=Path);p.add_argument('--profile',action='store_true');p.add_argument('--graph',action='store_true');a=p.parse_args();run(a.protocol.resolve(),a.task,a.out.resolve(),a.score.resolve()if a.score else None,a.profile,a.graph)
