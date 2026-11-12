"""Final current-source replay receipt; raw captures and old expectations stay intact."""
import argparse,csv,json,hashlib,subprocess
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,save,load,sha
from run_public_control_semantics import checked
from run_exception_completion_controls import score as completion
from run_constructor_scope_controls import score as constructor
from run_exception_dispatch_controls import score as dispatch
from field_value_protocol import validate


def rows(path):return [json.loads(l)for l in path.read_text().splitlines()]

def run(home,out):
    out.mkdir(parents=True,exist_ok=False);records=[];cohorts={}
    for name,score in [('final-original-case8',constructor),('task3-builtin',completion),('task3-custom-verified',dispatch)]:
        p=home/name;plan=load(p/'plan.json');counts={}
        for mode in ('full','static','selective'):
            d=p/mode;raw=rows(d/'events.jsonl');prediction,checks,norm=score(plan,raw,load(d/'truth-before-prediction.json'));save(out/(name+'-'+mode+'-prediction.json'),prediction)
            assert all(c['complete_correct']for c in checks)
            counts[mode]={'correct':len(checks),'targets':len(checks),'known':sum(c['answer']['known']for c in checks),'aborted':sum(bool(c.get('aborted'))for c in checks),'capture_sha256':sha(d/'events.jsonl'),'plan_sha256':sha(p/'plan.json'),'command':str(d/'command.json')}
            for c in checks:records.append({'cohort':name,'mode':mode,'scenario':c['scenario'],'input':c['input'],'evidence':'completed','independent_correct':True,'known':c['answer']['known'],'aborted':bool(c.get('aborted')),'answer':json.dumps(c['answer'],sort_keys=True)})
        cohorts[name]=counts
    p=home/'final-original66';plan=load(p/'plan.json');counts={}
    for mode in ('full','static','selective'):
        d=p/mode;raw=rows(d/'events.jsonl');prediction=checked(plan,raw);save(out/('original66-'+mode+'-prediction.json'),prediction);checks=[]
        for t in load(d/'truth-before-prediction.json'):
            ret=next(r for r in raw if r['kind']=='binding-return'and r['message']==t['message']);a=next(a for a in prediction['answers']if a['root_frame']==ret['frame']and a['path']=='/value');physical=next(f for f in ret['fields']if f['path']=='/value')
            flags={'origins':set(map(tuple,a['origins']))==set(map(tuple,t['origins'])),'selectors':set(map(tuple,a['selectors']))==set(map(tuple,t['selectors'])),'version':a['version']==t['expected_target_version'],'owner_field':all(a[k]==physical[k]for k in ('owner','field')),'known':a['known']}
            expected_unknown=t['scenario']in (14,16)
            assert (not a['known'] and flags['selectors']and flags['version']and flags['owner_field'])if expected_unknown else all(flags.values())
            checks.append({'scenario':t['scenario'],'input':t['input'],'flags':flags,'answer':a})
            records.append({'cohort':'original66','mode':mode,'scenario':t['scenario'],'input':t['input'],'evidence':'completed','independent_correct':all(flags.values()),'known':a['known'],'aborted':False,'answer':json.dumps({'checks':flags,**a},sort_keys=True)})
        assert sum(not c['answer']['known']for c in checks)==6
        save(out/('original66-'+mode+'-checks.json'),checks);counts[mode]={'correct':60,'unknown':6,'targets':66,'capture_sha256':sha(d/'events.jsonl'),'all_semantics_gate':False}
    cohorts['original66']=counts
    p=home/'task3-final';primitive=[]
    for field in ('big','boxed','absent'):
        plan=load(p/(field+'-plan.json'))
        for mode in ('full','static','selective'):
            d=p/(field+'-'+mode);raw=rows(d/'events.jsonl');r=checked(plan,raw);a=next(a for a in r['answers']if a['path']=='/'+field);truth=load(d/'truth-before-prediction.json');assert all(a[k]==v for k,v in truth.items());primitive.append({'field':field,'mode':mode,'correct':True,'capture_sha256':sha(d/'events.jsonl')});records.append({'cohort':'primitive-'+field,'mode':mode,'scenario':'copy','input':'same-value','evidence':'completed','independent_correct':True,'known':True,'aborted':False,'answer':json.dumps(a,sort_keys=True)})
    validate(load(p/'stress-plan.json'),rows(p/'stress-events.jsonl'))
    before=load(home/'task3-before-final/stress-results.json');after=load(p/'stress-results.json');assert [r['IDS']for r in before['stats']]==[13,6013,12013]and [r['IDS']for r in after['stats']]==[5,5,5]
    assert load(home/'task3-before-final/protocol-before-jvm.json')['fixture_sha256']==load(p/'protocol-before-jvm.json')['fixture_sha256']
    agents={}
    for task in ('task2','task3'):
        agent=home/(task+'-agent/distributed-observer.jar');build=load(home/(task+'-agent/build.json'))
        with ZipFile(agent)as z:hashes={n:hashlib.sha256(z.read(n)).hexdigest()for n in z.namelist()if n.endswith('.class')and n.startswith(('PlannedServiceAgent','ExecutionKernelHooks','CollectionServiceHooks','FoundationValueHooks','ResponseBindingHooks','SpringTransportAgent'))}
        agents[task]={'sha256':sha(agent),'class_sha256':hashes,'compiler_version':build['compiler_version'],'compiler_target':build['compiler_target'],'build':str(home/(task+'-agent/build.json'))}
    java=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java';jdk={'java':str(java),'version':subprocess.check_output([str(java),'-version'],stderr=subprocess.STDOUT,text=True),'java_sha256':sha(java),'rt_jar_sha256':sha(java.parent.parent/'jre/lib/rt.jar'),'libjvm_sha256':sha(java.parent.parent/'jre/lib/amd64/server/libjvm.so')}
    paths=['control_dependencies.py','exception_completion.py','execution_dependency_state.py','exception_dispatch.py','field_value_protocol.py','infer_application_execution.py','infer_execution_kernel.py','infer_planned_service.py','infer_response_binding.py','audit_review_request.py','run_primitive_observation_controls.py','PrimitiveObservationFixture.java']
    paths+=['test_exception_completion.py','test_exception_dispatch.py','test_field_value_protocol.py']
    paths+=['PlannedServiceAgent.java','ExecutionKernelHooks.java','CollectionServiceHooks.java','FoundationValueHooks.java','ResponseBindingHooks.java','SpringTransportAgent.java']
    guards={name:{'checks':len(load(home/name/'results.json')['checks']),'gate':load(home/name/'results.json')['gate']}for name in ('task3-final-guards','task3-dispatch-guards-verified')};assert all(g['gate']for g in guards.values())
    old=load(home/'final-old-business-02/results.json');assert len(old['captures'])==14 and all(c['versions_equal']and c['root_audits_equal']and c['known_changes']==c['explicit_data_changes']==c['selector_changes']==0 for c in old['captures'])
    result={'jdk':jdk,'agents':agents,'protocol':{'exception_dispatch_version':1,'field_value_version':1},'cohorts':cohorts,'primitive_checks':primitive,'stress':{'before':before,'after':after,'field_observations':24012,'same_fixture_hash':True},'guards':guards,'old_capture_replay':{'public':18,'business':14,'faults':72,'original_unknowns':6,'historical_write_address_limits':2,'historical_override_rejections':2},'sources':{str(HERE/p):sha(HERE/p)for p in paths},'unit_log':str(home/'final-units.log'),'not_run':['unrelated historical application container redeployments','native construction closure','performance benchmarks'],'whole_semantics_gate':False}
    with(out/'cases.csv').open('w')as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    save(out/'receipt.json',result);print(json.dumps({'case_records':len(records),'guards':guards,'whole_semantics_gate':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
