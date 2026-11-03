"""Prepare exposed Mall/ZLT pilots with one current control Agent, not new apps."""
import argparse
from pathlib import Path
import shutil
from run_planned_service import ROOT,load,save,sha


def prepare(home,base):
    from plan_capability_policy import choose
    import run_plan_applicability_revision as mall
    from run_zlt_path_revision import prepare as zlt
    from contract_applicability import library_inventory
    home.mkdir(parents=True,exist_ok=False)
    mall.HOME=home/'mall';mall.BASE=base;mall.prepare('mall-swarm-3',2)
    shutil.copyfile(home.parent/'development-protocol-before-change.json',mall.HOME/'development-protocol-before-change.json')
    manifest=load(base/'build.json')
    save(mall.HOME/'candidate-code.json',{'sources':{str(Path(p).relative_to(ROOT)):h for p,h in manifest['sources'].items()},
         'agent_sha256':sha(base/'distributed-observer.jar'),'meaning':'Development pilot of field-value demand projection; not a frozen external task.',
         'planning_inputs':{str(p.relative_to(mall.HOME)):sha(p)for d in ('metadata','planning-first')for p in(mall.HOME/d).rglob('*.json')}})
    reference=ROOT/'artifacts/zlt-completion-slice-20261031/final-candidate-01/zlt'
    for q in load(reference/'task-seal.json')['entries']:
        role=q['role'];m=load(reference/'metadata'/role/'model.json')
        m['library_inventory']=library_inventory(reference/'business-jars'/(role+'.jar'))
        dest=home/'zlt-models'/role;dest.mkdir(parents=True);save(dest/'model.json',m)
        p,route=choose(m,{'entry':q['entry'],**q['return_targets'][0],'source_calls':[q['oracle']['source']]})
        dest=home/'zlt-plans'/q['id'];dest.mkdir(parents=True);save(dest/'plan.json',p);save(dest/'route.json',route)
    zlt(home/'zlt',base,home/'zlt-models',home/'zlt-plans')
    save(home/'pilot-before-business.json',{'agent_sha256':sha(base/'distributed-observer.jar'),
         'core_sources':manifest['sources'],'task_scope':'Existing Mall expiresIn and both original ZLT fields only. No external new query planned.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    a=p.parse_args();prepare(a.home.resolve(),a.base.resolve())
