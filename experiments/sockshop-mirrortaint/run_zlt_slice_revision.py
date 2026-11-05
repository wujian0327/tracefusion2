"""One final candidate; reuse original tasks, not earlier deployment outcomes."""
import argparse,json,shutil,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def prepare(root,extra_inputs=None):
    import run_account_semantics_revision as history
    import run_plan_applicability_revision as mall
    from plan_capability_policy import choose
    from contract_applicability import library_inventory
    from run_zlt_path_revision import prepare as prepare_zlt
    root.mkdir(parents=True,exist_ok=False)
    history.prepare(root/'historical',extra_inputs=extra_inputs)
    base=root/'historical/frozen-base';manifest=load(base/'build.json')
    freeze=load(root/'historical/algorithm-freeze.json')
    freeze.update(parent_algorithm='c1a4e5ceb60a276cc3651e4cdb413aa29d7f8d5d',
        scope='Bounded ZLT Page/SAM/default SELECT locality and guarded effect-only body observations; exposed tasks, no new application/sink/Gson.')
    save(root/'historical/algorithm-freeze.json',freeze)
    mall.HOME=root/'mall';mall.BASE=base;mall.prepare()
    shutil.copyfile(ROOT/'artifacts/zlt-completion-slice-20261031/development-protocol-before-change.json',mall.HOME/'development-protocol-before-change.json')
    sources={str(Path(p).relative_to(ROOT)):digest for p,digest in manifest['sources'].items()}
    planning={str(p.relative_to(mall.HOME)):sha(p) for folder in ('metadata','planning-first') for p in(mall.HOME/folder).rglob('*.json')}
    planning['deployment-environment.json']=sha(mall.HOME/'deployment-environment.json')
    save(mall.HOME/'candidate-code.json',{'sources':sources,'agent_sha256':sha(base/'distributed-observer.jar'),
        'meaning':'Final developed candidate; same Agent across all cohorts, original tasks and independent rules.',
        'planning_inputs':planning})
    oldmodels=ROOT/'artifacts/zlt-completion-slice-20261031/sql-models-03/models'
    task=load(ROOT/'artifacts/frozen-zlt-reuse-20261030/task-seal.json')
    for q in task['entries']:
        model=load(oldmodels/q['role']/'model.json')
        model['library_inventory']=library_inventory(ROOT/'artifacts/portability-first-20261028/business-jars'/(q['role']+'.jar'))
        dest=root/'zlt-models'/q['role'];dest.mkdir(parents=True);save(dest/'model.json',model)
        plan,route=choose(model,{'entry':q['entry'],**q['return_targets'][0],'source_calls':[q['oracle']['source']]})
        dest=root/'zlt-plans'/q['id'];dest.mkdir(parents=True);save(dest/'plan.json',plan);save(dest/'route.json',route)
    prepare_zlt(root/'zlt',base,root/'zlt-models',root/'zlt-plans')
    for api in ('ZLT-MP-1','ZLT-MP-4'):
        directory=root/'zlt/runs'/api;directory.mkdir(parents=True)
        original=ROOT/'artifacts/offline-zlt-revision-20261031/final-zlt-MT-isolated-01/runs'/api
        for mode in ('original','mirrortaint'):(directory/mode).symlink_to((original/mode).resolve(),target_is_directory=True)
    protocol={'reference':'c1a4e5c','candidate_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'agent_sha256':sha(base/'distributed-observer.jar'),'same_binary_all_cohorts':True,
        'ZLT':{'per_mode':15,'positive':15,'fresh_TF':True,'MT':'Unchanged B2.2/native and original task; retained prior captures, not a new MT deployment'},
        'Mall':{'per_mode':103,'known_required':98,'oracle_unavailable_unknown':5,'MT_correct_required':88},
        'Account':{'per_mode':40,'positive':4,'known_empty':36},
        'historical':{'development62_known':428,'fields29_known':232,'writes15_known':96},
        'no_new_applications':True,'cost_gate':'All capability/state/signature gates before any formal timing',
        'plans':{str(p.relative_to(root)):sha(p) for folder in ('historical/frozen-plans','historical/regression29-plans','historical/write-plans','historical/account-final/planning-first','mall/planning-first','zlt-plans')for p in(root/folder).rglob('*.json')},
        'driver_sources':{str(HERE/name):sha(HERE/name)for name in ('run_zlt_slice_revision.py','run_zlt_path_revision.py','prepare_zlt_path_models.py')}}
    save(root/'final-protocol-before-business.json',protocol)
    print('Prepared final candidate',protocol['candidate_commit'],protocol['agent_sha256'],flush=True)


def zlt(root):
    logs=root/'zlt-logs';logs.mkdir(exist_ok=True)
    for mode in ('full','selective'):
        for api in ('ZLT-MP-1','ZLT-MP-4'):
            with(logs/(api+'-'+mode+'.log')).open('w') as log:
                subprocess.run(['python3',str(HERE/'run_zlt_path_revision.py'),'run','--home',str(root/'zlt'),'--api',api,'--mode',mode],stdout=log,stderr=subprocess.STDOUT,check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','zlt']);p.add_argument('--root',type=Path,required=True)
    args=p.parse_args()
    if args.stage=='prepare':prepare(args.root.resolve())
    else:zlt(args.root.resolve())
