#!/usr/bin/env python3
"""Native library bytes, private packaging, same-core controls and instance truth."""
import argparse,json,hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from isolate_agent_jackson import symbolic_types,OLD
from audit_application_call_revision import class_hashes
from audit_frozen_capability_acceptance import audit as source_audit
import run_frozen_capability_acceptance as driver


def mapper_hash(original):
    with ZipFile(original)as z:
        matches=[]
        for n in z.namelist():
            if n.startswith('BOOT-INF/lib/')and n.endswith('.jar'):
                with ZipFile(BytesIO(z.read(n)))as dep:
                    if 'com/fasterxml/jackson/databind/ObjectMapper.class'in dep.namelist():matches.append((n,hashlib.sha256(dep.read('com/fasterxml/jackson/databind/ObjectMapper.class')).hexdigest()))
    assert len(matches)==1;return matches[0]


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);driver.HOME=root;driver.check();freeze=load(root/'algorithm-freeze.json')
    assert freeze['jackson_isolation_required'] and freeze['experiment_protocol_sha256']==sha(HERE/'jackson-isolation-protocol-20261022.json')
    for p,h in freeze['oracle_sources'].items():assert sha(Path(p))==h
    assert not (root/'business-repeats').exists()
    source=source_audit(root,out/'source-union');agent=root/'frozen-base/distributed-observer.jar';classes=class_hashes(agent)
    with ZipFile(agent)as z:
        assert not any(n.startswith('com/fasterxml/jackson/')for n in z.namelist())
        for n in z.namelist():
            if n.endswith('.class'):assert not any(OLD in t for t in symbolic_types(z.read(n))),n
    expected={role:mapper_hash(root/'frozen-base'/role/'original.jar')for role in freeze['original_jars']}
    controls={};control_root=root.parent/'frozen-controls'
    for group in ('kernel','application','date','received','legacy','conversion-native','conversion-286','uuid-native','uuid-286'):
        p=control_root/group;d=load(p/'results.json');assert d['all_passed'];assert class_hashes(p/'build/distributed-observer.jar')==classes;controls[group]={'all_passed':True,'results_sha256':sha(p/'results.json')}
    loader=load(control_root/'loader/results.json');assert loader['all_passed'] and loader['agent_sha256']==sha(control_root/'conversion-native/build/distributed-observer.jar')
    purity=load(control_root/'observer-purity/results.json');assert purity['all_passed'] and purity['user_override_calls']==0 and purity['agent_sha256']==loader['agent_sha256']
    # ZIP timestamps can differ across builds; all class definitions and manifest must agree.
    with ZipFile(agent)as a,ZipFile(control_root/'conversion-native/build/distributed-observer.jar')as b:
        assert set(a.namelist())==set(b.namelist()) and a.read('META-INF/MANIFEST.MF')==b.read('META-INF/MANIFEST.MF')
    queries={q['id']:q for q in driver.QUERIES};captures=[]
    for worker in sorted(root.glob('all62-*')):
        for d in sorted(worker.glob('*-*')):
            if (d/'capture/compose.json').exists():
                mode,qid=d.name.split('-',1);captures.append((d,queries[qid]['role'],mode,qid))
    for mode in ('full','selective'):captures.append((root/'cart-create-pair'/mode,'carts',mode,'supplemental-create-read'))
    receipts=[]
    for d,role,mode,qid in captures:
        cap=d/'capture';rows=[json.loads(s)for s in (cap/role/'events.jsonl').read_text().splitlines()];proofs=[r for r in rows if r['kind']=='jackson-isolation'];assert proofs,(mode,qid,'native mapper proof missing')
        for r in proofs:
            assert r['business_class']=='com.fasterxml.jackson.databind.ObjectMapper' and r['business_class_sha256']==expected[role][1],(role,r)
            assert r['agent_class']=='tracefusion.internal.jackson.databind.ObjectMapper'
            assert r['agent_class_sha256']==classes['tracefusion/internal/jackson/databind/ObjectMapper.class']
        name=role if role in ('orders','carts')else'ts-'+role+'-service';service=load(cap/'compose.json')['services'][name];opts=service['environment']['JAVA_OPTS']
        assert service['cpus']==1 and service['mem_limit']=='768m' and '-Xms32m -Xmx256m'in opts
        assert opts.count('-XX:ParallelGCThreads=1')==opts.count('-XX:CICompilerCount=2')==1
        assert '-Dservice.mode='+mode in opts and '-Dservice.diagnostic'not in opts
        if role=='orders':
            timed=[r for r in rows if r['kind']=='collection-call-enter'and r.get('callee','').startswith('java/util/concurrent/Future.get(J')];assert timed and all(r['args'][0]['value']==5 for r in timed)
        receipts.append({'query':qid,'mode':mode,'role':role,'native_library':expected[role][0],'mapper_sha256':expected[role][1],'proofs':proofs,'raw_sha256':sha(cap/role/'events.jsonl'),'compose_sha256':sha(cap/'compose.json')})
    assert len(receipts)==126
    save(out/'native-runtime-receipts.json',receipts);save(out/'controls.json',controls)
    legacy=root.parent/'legacy-live-first';historical=load(legacy/'capture/comparison.json')
    assert class_hashes(legacy/'build/distributed-observer.jar')==classes
    for name,count in [('sockshop',198),('trainticket',31)]:
        result=historical['results'][name];assert result['queries']==result['exact']==count and result['unknown']==result['fp']==result['fn']==0
    for role in load(legacy/'build/build.json')['inputs']:
        for path in (legacy/'capture').rglob(role+'/events.jsonl'):
            proof=[json.loads(s)for s in path.read_text().splitlines()if json.loads(s)['kind']=='jackson-isolation'];assert proof
            assert all(r['business_class_sha256']==expected[role][1]for r in proof)
    result={**source,'jackson_isolation_verified':True,'agent_original_jackson_classes':0,'native_runtime_configurations_verified':len(receipts),'original_native_mapper_hashes':expected,'controls':controls,'loader_probe_sha256':sha(control_root/'loader/results.json'),'loader_probe_all_class_definitions_identical':True,'historical_correctness':historical['results'],'historical_comparison_sha256':sha(legacy/'capture/comparison.json'),'all_passed':source['all_passed']}
    save(out/'audit.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=audit(a.root.resolve(),a.out.resolve());print(json.dumps({k:r[k]for k in ('algorithm_commit','all_passed','modes','jackson_isolation_verified','native_runtime_configurations_verified')},indent=2))
