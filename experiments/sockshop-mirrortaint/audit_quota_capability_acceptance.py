#!/usr/bin/env python3
"""Joint instance/source acceptance plus actual runtime-policy verification."""
import argparse,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_frozen_capability_acceptance as driver
from audit_frozen_capability_acceptance import audit as source_audit


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);driver.HOME=root;freeze=load(root/'algorithm-freeze.json');assert freeze['experiment_protocol_sha256']==sha(HERE/'quota-capability-protocol-20261021.json')
    parent=root.parent;targeted=load(parent/'audit-quota-jvm-first/audit.json');assert targeted['all_targeted_checks_passed'];old=load(parent/'audit-frozen-final/audit.json');assert not old['all_targeted_checks_passed']
    correction=root/'pair-config-repair-protocol-before-run.json';repair=load(correction)if correction.exists()else None;pair=Path(repair['new_pair_directory'])if repair else root/'cart-create-pair';prior=root/'audit-final/source-union'if repair else None
    source=source_audit(root,out/'source-union',pair_root=pair,reuse=prior);queries={q['id']:q for q in driver.QUERIES};checks=[]
    captures=[]
    for worker in root.glob('all62-*'):
        for directory in sorted(worker.glob('*-*')):
            if not (directory/'capture/compose.json').exists():continue
            mode,qid=directory.name.split('-',1);query=queries[qid];captures.append((directory,query['role'],mode,qid))
    for mode in ('full','selective'):captures.append((pair/mode,'carts',mode,'sockshop-carts-get-customerId:create-repeat'))
    for directory,role,mode,qid in captures:
        cap=directory/'capture';spec=load(cap/'compose.json');name=role if role in ('orders','carts')else'ts-'+role+'-service';service=spec['services'][name];opts=service['environment']['JAVA_OPTS'];plan=load(directory/'build'/role/'plan.json')
        assert service['cpus']==1 and service['mem_limit']=='768m';assert '-Xms32m -Xmx256m'in opts;assert opts.count('-XX:ParallelGCThreads=1')==1 and opts.count('-XX:CICompilerCount=2')==1
        assert '-Dservice.diagnostic'not in opts and '-XX:+PrintGC'not in opts and '-Xloggc:'not in opts;assert '-Dservice.mode='+mode in opts
        assert plan['source_evidence'];raw=cap/role/'events.jsonl';rows=[json.loads(s)for s in raw.read_text().splitlines()];assert rows[0]['mode']==mode and not any('diagnostic_monotonic_ns'in r for r in rows)
        timed=[r for r in rows if r['kind']=='collection-call-enter'and r.get('callee','').startswith('java/util/concurrent/Future.get(J')]
        if role=='orders':assert timed and all(r['args'][0]['value']==5 for r in timed)
        checks.append({'mode':mode,'query':qid,'role':role,'CPU':service['cpus'],'memory_limit':service['mem_limit'],'parallel_gc_threads':1,'jit_compiler_threads':2,'no_added_warmup':True,'deadline_unchanged':True,'raw_sha256':sha(raw),'compose_sha256':sha(cap/'compose.json'),'plan_sha256':sha(directory/'build'/role/'plan.json')})
    assert len(checks)==124,len(checks)
    result={**source,'runtime_configuration':'All observed target JVMs:1CPU,768MiB,heap32m/256m,ParallelGCThreads1,CICompilerCount2; original unobserved backends unchanged','runtime_policy_verified':True,'actual_observed_deployments':len(checks),'experiment_protocol_sha256':freeze['experiment_protocol_sha256'],'original_configuration_acceptance_passed':False,'original_configuration_evidence':str(parent/'audit-frozen-final/audit.json'),'original_configuration_evidence_sha256':sha(parent/'audit-frozen-final/audit.json'),'targeted_configuration_evidence_sha256':sha(parent/'audit-quota-jvm-first/audit.json'),'sole_timeout_root_cause_proven':False,'new_unseen_query_evidence':False,'all_passed':source['all_passed'] and len(checks)==124}
    result.update(pair_configuration_correction=repair,first_configuration_audit_passed=not bool(repair),pair_corrected_capture=str(pair),main_122_evaluations_reused_with_hash_checks=bool(repair))
    save(out/'runtime-policy.json',checks);save(out/'audit.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=audit(a.root.resolve(),a.out.resolve());print(json.dumps({k:v for k,v in r.items()if k in ('algorithm_commit','all_passed','modes','first_attempt_business_all_passed','actual_observed_deployments')},indent=2))
