"""Freeze stronger guards, reuse only unchanged Agent/plan captures.

An incompatible plan is explicitly excluded and must be newly collected. This
does not relabel the previous complete capability pass as a final new deployment.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from run_planned_service import ROOT,HERE,load,save,sha

HOME=ROOT/'artifacts/target-closure-revision-20261103'
FIRST=HOME/'final-candidate-01'
FINAL=HOME/'final-candidate-02'


def prepare():
    assert load(HOME/'capability-pass-01/summary.json')['passed']
    from run_zlt_slice_revision import prepare as build
    from audit_application_call_revision import class_hashes
    build(FINAL)
    oldbase=FIRST/'historical/frozen-base';base=FINAL/'historical/frozen-base'
    assert class_hashes(oldbase/'distributed-observer.jar')==class_hashes(base/'distributed-observer.jar')
    fresh_sha=sha(base/'distributed-observer.jar')
    shutil.copyfile(oldbase/'distributed-observer.jar',base/'distributed-observer.jar')
    manifest=load(base/'build.json');manifest['agent_sha256']=sha(base/'distributed-observer.jar');save(base/'build.json',manifest)
    lock=load(FINAL/'zlt/run-source-lock.json');lock['agent_sha256']=sha(base/'distributed-observer.jar');save(FINAL/'zlt/run-source-lock.json',lock)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();assert commit!=load(FIRST/'target-closure-candidate.json')['commit']
    freeze=load(FINAL/'historical/algorithm-freeze.json')
    freeze.update(commit=commit,algorithm_commit=commit,parent_algorithm='7e4ad0b900a64871259a5fac008968128cc5ec28',
        scope='Target snapshot value demands, future-state and constructor-transfer guards. Existing public contracts unchanged.')
    save(FINAL/'historical/algorithm-freeze.json',freeze)
    p=load(FINAL/'mall/candidate-code.json');p['agent_sha256']=sha(base/'distributed-observer.jar');save(FINAL/'mall/candidate-code.json',p)
    protocol=load(FINAL/'final-protocol-before-business.json')
    protocol.update(reference='7e4ad0b900a64871259a5fac008968128cc5ec28',agent_sha256=sha(base/'distributed-observer.jar'),
        no_new_applications=False,external_queries_not_yet_planned=True,external_seal_sha256=sha(HOME/'external-query-seal-v3-before-tools.json'))
    save(FINAL/'final-protocol-before-business.json',protocol)
    same=[];changed=[]
    for relative in protocol['plans']:
        a=FIRST/relative;b=FINAL/relative
        if not a.exists():continue
        (same if sha(a)==sha(b)else changed).append(relative)
    changes={k:[]for k in('62','29')}
    for folder,key in [('frozen-plans','62'),('regression29-plans','29')]:
        for p in(FINAL/'historical'/folder).glob('*.json'):
            if p.name=='planning.json':continue
            if sha(p)!=sha(FIRST/'historical'/folder/p.name):changes[key].append(p.stem)
    # Copy directory shells but never overwrite a first capture or its score.
    for category in ('all62-orders-serial','all62-reads','all62-route','all62-travel','all62-cart',
                     'regression29-orders','regression29-train','development-route-frozen','development-price-frozen'):
        source=FIRST/'historical'/category;dest=FINAL/'historical'/category;dest.mkdir()
        for p in source.iterdir():
            if p.is_dir()and(p/'evaluation.json').exists():
                ev=load(p/'evaluation.json');kind='29'if category.startswith('regression29')else'62'
                if isinstance(ev,dict)and ev.get('query')in changes[kind]:continue
            (dest/p.name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
    for name in ('cart-create-pair','account-runtime-status.json'):
        p=FIRST/'historical'/name
        if p.exists():(FINAL/'historical'/name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
    (FINAL/'historical/account-final/diagnostics').symlink_to((FIRST/'historical/account-final/diagnostics').resolve(),target_is_directory=True)
    for name in('tool-runs','matrix-progress.json','matrix-protocol-before-business.json'):
        p=FIRST/'mall'/name;(FINAL/'mall'/name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
    for api in('ZLT-MP-1','ZLT-MP-4'):
        for mode in('full','selective'):
            (FINAL/'zlt/runs'/api/mode).symlink_to((FIRST/'zlt/runs'/api/mode).resolve(),target_is_directory=True)
    receipt={'first_candidate':str(FIRST),'first_full_pass_sha256':sha(HOME/'capability-pass-01/summary.json'),
        'final_candidate':commit,'same_Agent_class_hashes':True,'actual_Agent_JAR_reused_exactly':sha(base/'distributed-observer.jar'),
        'new_packaging_sha_before_canonical_copy':fresh_sha,'identical_planning_artifacts':same,'changed_planning_artifacts':changed,
        'changed_query_ids':changes,'new_Agent_deployment_claim':False,
        'reuse_condition':'Unchanged original JAR, actual Agent bytes and complete execution plan; normal offline validation under the final code. Changed plans get new captures, no hash/proof substitution.',
        'public_contract_changes':False,'external_query_run_before_final_freeze':False}
    save(FINAL/'capture-reuse-receipt.json',receipt)
    save(FINAL/'target-closure-candidate.json',{'commit':commit,'agent_sha256':sha(base/'distributed-observer.jar'),
        'source_files':freeze['sources'],'plans':protocol['plans'],'first_new_app_query_planned':False})
    print({'candidate':commit,'same_artifacts':len(same),'changed_queries':changes},flush=True)


def changed(stage):
    import os
    import run_frozen_capability_acceptance as driver
    import run_quota_capability_acceptance as quota
    root=FINAL/'historical';changes=load(FINAL/'capture-reuse-receipt.json')['changed_query_ids'];key='62'if stage=='changed62'else'29'
    if not changes[key]:return
    if key=='62':
        driver.QUERIES=[q for q in driver.QUERIES if q['id']in changes[key]];assert len(driver.QUERIES)==len(changes[key])
        quota.install(root);os.environ.update(TF2_CAPABILITY_ROLES='basic,ticketinfo',TF2_CAPABILITY_PORT='19020')
        driver.train(root/'changed62-captures',root/'frozen-base')
        temp=root/'changed62-captures';dest=root/'all62-travel'
    else:
        import run_execution_closure_revision as revision
        real_train=driver.train
        def partial(out,base):
            driver.QUERIES=[q for q in driver.QUERIES if q['id']in changes[key]];assert len(driver.QUERIES)==len(changes[key])
            return real_train(root/'changed29-captures',base)
        driver.train=partial;revision.regression29(root,'train');temp=root/'changed29-captures';dest=root/'regression29-train'
    new=load(temp/'results.json');assert new['complete']and not any('failure'in r for r in new['results'])
    for p in temp.iterdir():
        if p.is_dir()and(p/'capture/run.json').exists():assert not(dest/p.name).exists();shutil.move(str(p),str(dest/p.name))
    old=load(dest/'results.json');old['results']=[r for r in old['results']if r.get('query')not in changes[key]]+new['results']
    old['capture_provenance']='Unchanged captures reused from candidate01; changed plans freshly collected in candidate02.'
    (dest/'results.json').unlink();save(dest/'results.json',old)


def audits():
    out=HOME/'final-compatibility-pass-02';out.mkdir(exist_ok=False)
    def command(label,args):
        with(out/(label+'.log')).open('w')as f:subprocess.run([sys.executable,*map(str,args)],stdout=f,stderr=subprocess.STDOUT,check=True)
    # Re-score every Mall root with the final normal reconstruction and the
    # unchanged independent raw-fact oracle; do not reuse prior predictions.
    for record in load(FINAL/'mall/matrix-progress.json')['results']:
        api,mode,index=record['api'],record['mode'],record['index']
        command(api+'-'+mode+'-%03d'%index,[HERE/'audit_plan_applicability_revision.py','--home',FINAL/'mall','--api',api,'--mode',mode,'--index',index,
            '--out',FINAL/'mall/evaluation'/api/mode/('%03d'%index)])
    command('account',[HERE/'audit_account_candidate.py','--root',FINAL/'historical/account-final','--out',FINAL/'historical/account-score-first','--require-complete'])
    command('compatible-replay',[HERE/'replay_target_compatible.py','--root',FINAL,'--reference',FIRST,'--out',out/'compatible-replay'])
    for stage in('mall','historical'):
        command('audit-'+stage,[HERE/'audit_zlt_body_candidate.py',stage,'--root',FINAL,'--out',out/('audit-'+stage)])
    command('audit-zlt',[HERE/'audit_zlt_slice_completion.py','--root',FINAL,'--out',out/'audit-zlt'])
    save(FINAL/'capability-compatibility-receipt.json',{'passed':True,'final_candidate':load(FINAL/'target-closure-candidate.json')['commit'],
        'Mall_known':98,'Mall_MT_preserved':88,'ZLT_positive_per_mode':15,'Account':40,'old62':428,'old29':232,'write15':96,
        'new_apps_not_yet_planned':True,'capture_provenance':load(FINAL/'capture-reuse-receipt.json'),
        'validation':'Normal final-code reconstruction and independent oracle scoring. Reused first captures stay in their original directories, changed plans newly collected.'})
    print('Final compatibility gate passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','changed62','changed29','audits']);a=p.parse_args()
    prepare()if a.stage=='prepare'else audits()if a.stage=='audits'else changed(a.stage)
