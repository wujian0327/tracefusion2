"""Validate affected RuoYi tasks before the final fresh historical pass."""
import argparse,json,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
HOME=ROOT/'artifacts/ruoyi-zlt-refinement-20261103'


def command(home,name,args):
    with(home/(name+'.log')).open('w')as log:p=subprocess.run([sys.executable,*map(str,args)],stdout=log,stderr=subprocess.STDOUT)
    with(home/'stage-journal.jsonl').open('a')as log:log.write(json.dumps({'stage':name,'returncode':p.returncode})+'\n')
    print(name,p.returncode,flush=True)
    return p.returncode


def run(root,resume=False):
    home=root.parent;base=root/'historical/frozen-base';freeze=load(root/'historical/algorithm-freeze.json')
    from audit_application_call_revision import class_hashes
    control=HOME/'map-controls-16/build/distributed-observer.jar'
    assert class_hashes(control)==class_hashes(base/'distributed-observer.jar')
    save(home/'control-agent-equivalence.json',{'all_class_bytes_equal':True,'control_agent_sha256':sha(control),'candidate_agent_sha256':sha(base/'distributed-observer.jar')})
    def account_prepass():
        if not resume:
            assert command(home,'account-prepass',[HERE/'run_account_semantics_revision.py','--root',root/'historical','--stage','account'])==0
        result=load(root/'historical/account-score-first/summary.json')
        assert result['complete40']and all(v['known_correct']==40 and v['historic_MT_correct_preserved']==36 for v in result['modes'].values())
        save(root/'account-prepass-receipt.json',{'candidate':freeze['commit'],'agent_sha256':sha(base/'distributed-observer.jar'),
            'new_final_Agent_deployments':True,'captures':result['captured_files_sha256'],
            'plans':{str(p):sha(p)for p in(root/'historical/account-final/planning-first').rglob('*-plan.json')},
            'scope':'Same final candidate, fresh Account40 prepass; do not deploy it again during the broad pass.'})
    def ruoyi_matrix():
        for config in('C1','C2'):
            out=home/('ruoyi-'+config)
            if resume:
                assert load(out/'matrix-progress.json')['complete']
                assert (home/('facts-ruoyi-'+config)/'summary.json').exists()
                continue
            for stage in('prepare','run','score'):
                args=[HERE/'run_ruoyi_wrapper_revision.py',stage,'--out',out,'--build',base]
                if config=='C2':
                    args+=['--calibrated']
                    if stage=='run':args+=['--reuse-mt',HOME/'ruoyi-final-C2-v3']
                if stage=='score':args+=['--audit',home/('audit-ruoyi-'+config)]
                assert command(home,config+'-'+stage,args)==0,(config,stage)
            assert command(home,config+'-facts',[HERE/'audit_ruoyi_wrapper_facts.py','--home',out,'--out',home/('facts-ruoyi-'+config)])==0
    with ThreadPoolExecutor(max_workers=2)as pool:
        futures=[pool.submit(account_prepass),pool.submit(ruoyi_matrix)]
        for future in futures:future.result()
    # No compatibility waiver: Map failures or business changes stop the broad
    # pass. Unsupported collections stay invalid, including preparation output.
    for config in('C1','C2'):
        receipts=load(home/('facts-ruoyi-'+config)/'receipts.json')
        for r in receipts:
            assert r['business_preserved']==r['business_requests'],r
            if r['first_problem']:
                message=str(r['first_problem'])
                assert ('List' in message or 'Unmodeled target collection' in message)and 'Map'not in message,r
    save(home/'matrix-review-before-history.json',{'candidate':freeze['commit'],'fresh_TF_matrix_complete':True,
        'remaining_collection_failures_still_invalid':True,'business_preserved':True,
        'captures':{str(p.relative_to(home)):sha(p)for p in home.glob('ruoyi-C*/runs/*/*/capture/events.jsonl')},
        'scope':'Experiment coordinator previously expected only the original List limit; preparation-output collection remains a separate disclosed restriction. No capture or algorithm change.'})
    for p,h in freeze['sources'].items():assert sha(Path(p))==h,p
    assert command(home,'capability',[HERE/'run_ruoyi_zlt_acceptance.py','--root',root])==0
    result=load(home/'capability-pass-01/summary.json')
    save(home/'pipeline-complete.json',{'complete':True,'capability_passed':result['passed'],'candidate':freeze['commit'],'core_sources_unchanged':all(sha(Path(p))==h for p,h in freeze['sources'].items())})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--resume-completed-matrix',action='store_true');a=p.parse_args();run(a.root.resolve(),a.resume_completed_matrix)
