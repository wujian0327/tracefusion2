"""Re-extract unchanged dependency bytecode; preserve original task metadata."""
import argparse
from pathlib import Path
from run_planned_service import ROOT,load,save
from build_distributed_plans import build
from plan_capability_policy import choose


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    prior=ROOT/'artifacts/frozen-zlt-reuse-20261030'
    tasks=load(prior/'task-seal.json')['entries']
    # This list imports code, not propagation summaries or new source calls.
    dependencies=['com/baomidou/mybatisplus/extension/plugins/pagination/Page',
        'com/baomidou/mybatisplus/core/metadata/IPage',
        'com/baomidou/mybatisplus/extension/activerecord/Model',
        'com/central/common/model/SuperEntity','com/central/common/model/SysRole',
        'com/central/common/model/PageResult','com/central/common/model/PageResult$PageResultBuilder']
    build(out/'build',{q['role']:{'jar':str(prior/'business-jars'/(q['role']+'.jar')),
        'targets':[q['return_targets'][0]['target']], 'bytecode_dependencies':dependencies} for q in tasks})
    for q in tasks:
        role=q['role'];model=load(prior/'metadata'/role/'model.json')
        fresh=load(out/'build'/role/'model.json')
        for part in ('classes','methods'):model[part].update(fresh[part])
        model['library_inventory']=fresh['library_inventory']
        dest=out/'models'/role;dest.mkdir(parents=True);save(dest/'model.json',model)
        plan,route=choose(model,{'entry':q['entry'],**q['return_targets'][0],
            'source_calls':[q['oracle']['source']]})
        dest=out/'plans'/q['id'];dest.mkdir(parents=True);save(dest/'plan.json',plan);save(dest/'route.json',route)
        print(q['id'],len(plan['execution_kernel']['methods']),
              'SQL proof candidate',bool(plan['execution_kernel'].get('sql_result_locality')),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out.resolve())
