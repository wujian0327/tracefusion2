"""Existing observer-internal counter probe; diagnosis only, no speed claim."""
from run_unrelated_work_scaling import H,ROOT,load,save,sha,controlled_trial
from execute_unrelated_work_scaling import audit
p=H/'diagnostic-protocol-before-runs.json'
assert not p.exists()
save(p,{'probe_sha256':sha(ROOT/'artifacts/pruning-contribution-audit-20261106/probe/probe-v2.jar'),'jobs':[[t,m]for t in('low','high')for m in('full','selective')],'requests':6,'unchanged_frozen_TF_Agent':True,'runtime_probe':'Wrap only observer internals/Field.get/metadata lookup; no original business invoke in timing; counts only reported, never diagnostic latency or CPU in formal table.'})
results=[]
for tier,mode in load(p)['jobs']:
 out=H/'diagnostic-counts'/(tier+'-'+mode);r=controlled_trial(out,tier,mode,0,3,2,diagnostic=True);a=audit(out,'controlled',tier,mode)
 assert r['business_passed']==6 and a.get('correct')==6
 probe=load(out/'capture/monitor-cost.json');counts={}
 for key,v in probe['methods'].items():
  group=key.split(':',1)[0];counts[group]=counts.get(group,0)+v[0]
 results.append({'tier':tier,'mode':mode,'method_calls':counts,'actual_scalar_omissions':a['actual_scalar_omissions'],'correct':a['correct'],'diagnostic_only':True})
save(H/'diagnostic-count-results.json',results)
