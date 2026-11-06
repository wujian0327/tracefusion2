"""Compare logical evidence, never JVM object IDs, across short ablation arms."""
import argparse,json,pickle
from pathlib import Path
from run_planned_service import load,save,sha
from infer_distributed_fields import Reconstruction
from infer_response_binding import matches
from run_pruning_cost_audit import ARMS

def run(home,out):
 out.mkdir(parents=True,exist_ok=False);tasks=load(home/'protocol-before-change.json')['order'];checks=[]
 for task in tasks:
  baseline=None
  for arm in ARMS:
   trial=home/'short'/(task+'-'+arm);spec=load(trial/'offline-protocol.json')['tasks'][task]['selective'];cap=Path(spec['capture']);plan=Path(spec['plan']);role=spec['role'];plan_data=load(plan);d=out/(task+'-'+arm);b=d/'build'/role;b.mkdir(parents=True);(b/'plan.json').write_bytes(plan.read_bytes());c=d/'capture'/role;c.mkdir(parents=True);(c/'events.jsonl').symlink_to(cap)
   assert sha(cap)==spec['capture_sha256']and sha(plan)==spec['plan_sha256'];rows=[json.loads(x)for x in cap.read_text().splitlines()];g=Reconstruction(d/'build',d/'capture',[role],decoded_rows={role:rows})
   byseq={r['seq']:r for r in rows};case_index={r['message']:i for i,r in enumerate(load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'])};returns={r['frame']:r for r in rows if r['kind']=='binding-return'};local=g.local_queries[role]
   frames={r['frame']:r for r in rows if r['kind']=='enter'}
   def root(f):
    seen=set()
    while f in frames and f not in seen:
     seen.add(f);r=frames[f]
     if r['method']==plan_data['entry']:return f
     f=r.get('parent')
    return None
   def token(t):
    if t[0]=='field':
     r=byseq[t[1]];f=r['fields'][t[2]]
     kind='source-call-enter'if r.get('source_scope')=='observation-only-call'else'collection-call-enter'
     identity_key='source_call_id'if kind=='source-call-enter'else'call_id'
     starts=[x for x in rows if x['kind']==kind and x.get('callee')==r.get('callee')and root(x.get('frame'))==root(r.get('frame'))]
     matching=[i for i,x in enumerate(starts)if x.get(identity_key)==r.get('source_call_id')]
     assert len(matching)==1,(r.get('callee'),r.get('source_call_id'),matching)
     start=starts[matching[0]]
     return['field',r.get('callee'),start.get('method'),start.get('pc'),matching[0],f['path'],f['field'],f['version']]
    # Non-field selectors have no ad hoc fallback based on equal values.
    raise ValueError('Selector coordinate needs an explicit normalization: '+str(t))
   answers=[]
   for a in local['answers']:
    if not matches(plan_data['response_binding']['path'],a['path']):continue
    ret=returns[a['root_frame']]
    if ret['message']not in case_index:continue
    answers.append({'case':case_index[ret['message']],'path':a['path'],'field':a['field'],'version':a['version'],'known':a['known'],'origins':sorted([token(t)for t in a['origins']],key=str),'selectors':sorted([token(t)for t in a['selectors']],key=str)})
   roots=[]
   for r in local['roots']:
    ret=returns.get(r['frame'])
    if ret and ret['message']in case_index:roots.append({'case':case_index[ret['message']],'completion':r['completion'],'answers':r['answers']})
   normalized={'answers':sorted(answers,key=lambda a:(a['case'],a['path'])),'roots':sorted(roots,key=lambda a:a['case'])}
   save(d/'normalized.json',normalized)
   with(d/'graph-and-root-audits.pkl').open('wb')as f:pickle.dump((g.nodes,g.edges,g.local_queries),f,protocol=4)
   if baseline is None:baseline=normalized
   else:assert normalized==baseline,(task,arm)
   checks.append({'task':task,'arm':arm,'answers':len(answers),'roots':len(roots),'same_status_origin_field_version_selectors_and_root_completion':True,'capture_sha256':sha(cap),'note':'Step counts and opaque effect-body representation may differ by design; full audits are retained. Independent raw instance scoring is separate.'})
 save(out/'checks.json',{'passed':True,'scope':'All predeclared query targets. Unrequested internal response answers are retained in full audit views but are not a claim of target-specific projection.','checks':checks});print('All short arms preserve answers, field versions, origins, selectors and audited completion')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
