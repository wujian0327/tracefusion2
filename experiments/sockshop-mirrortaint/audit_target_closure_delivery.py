"""Final content checks after all timed deployments, without re-running them."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
import subprocess
from run_planned_service import ROOT,HERE,load,save,sha


def audit(home,out):
    out.mkdir(parents=True,exist_ok=False)
    frozen=load(home/'final-candidate-02/historical/algorithm-freeze.json')
    for name,digest in frozen['sources'].items():
        assert sha(Path(name))==digest,('Frozen core changed',name)
    builder=HERE/'build_distributed_plans.py'
    assert sha(builder)==frozen['builder_sha256']
    contracts=[Path(p)for p in frozen['sources']if p.endswith('.json')]
    for path in contracts:
        original=subprocess.check_output(['git','show','7e4ad0b:'+str(path.relative_to(ROOT))])
        assert original==path.read_bytes(),('Public contract changed',path)
    lock=load(home/'common-cost-01/driver-lock-before-formal.json')
    assert sha(home/'common-cost-01/protocol-before-calibration.json')==lock['protocol_sha256']
    for name,digest in lock['files'].items():assert sha(Path(name))==digest,('Cost driver changed',name)
    guard=load(home/'final-guard-receipt-02/summary.json')
    for name,digest in guard['control_results'].items():assert sha(home/name)==digest
    first=home/'external-before-read-permission.sha256';first_count=0
    for line in first.read_text().splitlines():
        digest,name=line.split('  ',1)
        path=home/'external-first-01/runs'/Path(name).relative_to('/work')
        assert sha(path)==digest,('First capture changed',path)
        first_count+=1
    # These are the SAME first-candidate Mall captures, not new deployments.
    manifest=load(home/'final-compatibility-pass-02/audit-mall/captures-manifest.json')['files']
    for name,digest in manifest.items():
        assert sha(home/'final-candidate-02/mall'/name)==digest,('Compatible capture changed',name)
    cost=load(home/'common-cost-01/audit-01/summary.json')
    assert cost['all_trials_completed']and len(cost['formal_rows'])==80
    assert all(r['correct']==r['targets']for r in cost['formal_rows']if r['mode']!='original')
    resources=load(home/'common-cost-01/audit-01/resource-receipts.json')
    assert len(resources)==80 and all(r['exact']for r in resources)
    images=defaultdict(list);business_jars={};file_hashes={}
    for row in cost['formal_rows']:
        trial=home/'common-cost-01'/row['trial'];task=row['task']
        cfg=load(trial/('sockshop/compose.json'if task=='orders'else'compose.json'))
        spec={r:{k:v[k]for k in('image','cpus','mem_limit')if k in v}for r,v in cfg['services'].items()}
        assert all(v['image'].startswith('sha256:')or'@sha256:'in v['image']for v in spec.values())
        images[task].append(spec)
        jars={}
        for role,service in cfg['services'].items():
            for mount in service.get('volumes',[]):
                if not isinstance(mount,str):continue
                parts=mount.rsplit(':',2)
                if len(parts)!=3 or parts[1]not in('/app.jar','/tf2/app.jar'):continue
                path=Path(parts[0])
                if path not in file_hashes:file_hashes[path]=sha(path)
                jars[role]=file_hashes[path]
        assert jars,('Missing actual business JAR',row['trial'])
        if task in business_jars:assert business_jars[task]==jars,('Business JAR differs',row['trial'])
        else:business_jars[task]=jars
    assert all(all(spec==group[0]for spec in group)for group in images.values())
    before=load(home/'common-cost-01/environment-before-formal.json')['docker_ps']
    after=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
    assert set(after)==set(before),'Experiment containers left running or unrelated container list changed'
    save(out/'environment-after.json',{'docker_ps':after,'unrelated_list_unchanged':True})
    reports=['TARGET-OBSERVATION-ALGORITHM-20261103.md','TARGET-OBSERVATION-DEVELOPMENT-20261103.md',
             'FROZEN-EXTERNAL-FIRST-20261103.md','TARGET-OBSERVATION-COMMON-COST-20261103.md']
    drivers=['run_target_closure_cost.py','audit_target_closure_cost.py','audit_target_closure_delivery.py',
             'run_target_external_first.py','audit_target_external_first.py','write_target_closure_reports.py',
             'backup_target_closure_revision.py','prepare_target_closure_guarded_final.py','replay_target_compatible.py']
    dest=out/'delivery-sources';dest.mkdir()
    files={}
    for name in reports+drivers:
        shutil.copyfile(HERE/name,dest/name);files[name]=sha(HERE/name)
    external=load(home/'external-first-audit-03/summary.json')
    receipt={'algorithm':frozen['commit'],'reference':'7e4ad0b900a64871259a5fac008968128cc5ec28',
        'passed':True,'core_sources':len(frozen['sources']),'builder_unchanged':True,
        'public_contracts_unchanged':len(contracts),'cost_locked_files':len(lock['files']),
        'first_external_files_unchanged':first_count,'same_Mall_capture_files_unchanged':len(manifest),
        'formal_deployments':80,'resource_summaries_exact':80,'pinned_image_and_limit_specs_equal_within_task':True,
        'same_business_JAR_hashes_all_80_trials':business_jars,
        'all_common_task_sources_correct':True,'internal_joint_tasks_passed':cost['task_wins'],
        'external_first_summary_sha256':sha(home/'external-first-audit-03/summary.json'),
        'external_selected_original_targets':sum(r['selected_original_targets']for r in external['APIs']),
        'delivery_sources':files,'unrelated_container_list_unchanged':True,
        'provenance':'First candidate full business pass plus compatible same-Agent/same-plan reuse and four changed plans in both modes re-collected. Formal costs and external first runs are new deployments.',
        'no_push':True}
    save(out/'summary.json',receipt);save(HERE/'target-observation-delivery-integrity-20261103.json',receipt)
    print({k:v for k,v in receipt.items()if k!='delivery_sources'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.home.resolve(),a.out.resolve())
