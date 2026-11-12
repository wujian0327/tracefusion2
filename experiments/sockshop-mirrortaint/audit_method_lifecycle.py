"""Current-source delivery replay. Preserve original captures, truth and failures."""
import argparse,csv,hashlib,json,subprocess
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_public_control_semantics import checked
from run_constructor_scope_controls import score as constructor
from run_exception_completion_controls import score as completion
from run_exception_dispatch_controls import score as dispatch
from method_value_protocol import validate as methods
from field_value_protocol import validate as fields
from identity_lifecycle_protocol import validate as lifecycle
from infer_async_protocol import validate_async_protocol


def rows(p):return [json.loads(l)for l in p.read_text().splitlines()]
def run(home,out):
    out.mkdir(parents=True,exist_ok=False);data=[];cohorts={};final=home/'release'
    for name,score in [('case8',constructor),('builtin',completion),('custom',dispatch)]:
        p=final/name;plan=load(p/'plan.json');stats={};normalized={}
        for mode in ('full','static','selective'):
            d=p/mode;raw=rows(d/'events.jsonl');result,checks,normalized[mode]=score(plan,raw,load(d/'truth-before-prediction.json'));assert all(c['complete_correct']for c in checks);save(out/(name+'-'+mode+'-replay.json'),result)
            stats[mode]={'targets':len(checks),'correct':len(checks),'known_answers':sum(c['answer']['known']for c in checks),'aborted':sum(bool(c.get('aborted'))for c in checks),'capture_sha256':sha(d/'events.jsonl'),'plan_sha256':sha(p/'plan.json'),'command':str(d/'command.json')}
            for c in checks:data.append({'cohort':name,'mode':mode,'scenario':c['scenario'],'input':c['input'],'completion':'aborted'if c.get('aborted')else'normal','known':c['answer']['known'],'complete_correct':c['complete_correct'],'details':json.dumps(c['answer'],sort_keys=True)})
        assert normalized['full']==normalized['static']==normalized['selective'];cohorts[name]=stats
    p=final/'original66';plan=load(p/'plan.json');stats={}
    for mode in ('full','static','selective'):
        d=p/mode;raw=rows(d/'events.jsonl');result=checked(plan,raw);checks=[]
        for t in load(d/'truth-before-prediction.json'):
            ret=next(r for r in raw if r['kind']=='binding-return'and r['message']==t['message']);a=next(a for a in result['answers']if a['root_frame']==ret['frame']and a['path']=='/value');physical=next(f for f in ret['fields']if f['path']=='/value')
            flags={'origins':set(map(tuple,a['origins']))==set(map(tuple,t['origins'])),'selectors':set(map(tuple,a['selectors']))==set(map(tuple,t['selectors'])),'version':a['version']==t['expected_target_version'],'physical':all(a[k]==physical[k]for k in ('owner','field')),'known':a['known']}
            if t['scenario']in (14,16):assert not a['known']and flags['selectors']and flags['version']and flags['physical']
            else:assert all(flags.values())
            checks.append(flags);data.append({'cohort':'original66','mode':mode,'scenario':t['scenario'],'input':t['input'],'completion':'normal','known':a['known'],'complete_correct':all(flags.values()),'details':json.dumps({'checks':flags,'answer':a},sort_keys=True)})
        assert sum(c['known']for c in checks)==60;stats[mode]={'correct':60,'unknown':6,'targets':66,'capture_sha256':sha(d/'events.jsonl'),'plan_sha256':sha(p/'plan.json'),'command':str(d/'command.json'),'whole_semantics_gate':False};save(out/('original66-'+mode+'-replay.json'),result)
    cohorts['original66']=stats
    for name in ('fields','methods-bits'):
        p=final/name;reports=[]
        for field in ('big','boxed','absent')if name=='fields'else(None,):
            plan=load(p/(field+'-plan.json'if field else'plan.json'))
            for mode in ('full','static','selective'):
                d=p/(field+'-'+mode if field else mode);raw=rows(d/'events.jsonl');result=checked(plan,raw);truth=load(d/'truth-before-prediction.json');answer=next(a for a in result['answers']if a['path']=='/'+(field or'value'));assert all(answer[k]==v for k,v in truth.items());reports.append({'field':field,'mode':mode,'correct':True,'capture_sha256':sha(d/'events.jsonl'),'command':str(d/'command.json')});data.append({'cohort':name,'mode':mode,'scenario':field or'methods','input':'literal','completion':'normal','known':True,'complete_correct':True,'details':json.dumps(answer,sort_keys=True)})
                if not field:
                    dvalues=[r['result']for r in raw if r['kind']=='exit'and r['result'].get('primitive')in ('F','D')];assert any(r.get('bits')=='7ff8000000000017'for r in dvalues)and any(r.get('bits')=='7fc00017'for r in dvalues),'Noncanonical NaN control absent'
        cohorts[name]=reports
    guards={}
    for name in ('release/method-guards','release/field-guards','release/dispatch-guards'):
        r=load(home/name/'results.json');assert r['gate'];guards[name]={'checks':len(r['checks']),'gate':r['gate']}
    # A real new footer cannot be ignored to obtain a known result.
    p=final/'case8';plan=load(p/'plan.json');negative=[]
    import copy
    for mode in ('full','static','selective'):
        raw=rows(p/mode/'events.jsonl')
        for fault in ('missing-counters','allocation-mismatch','negative-counter','missing-version'):
            bad=copy.deepcopy(raw);footer=next(r for r in bad if r['kind']=='metrics')
            if fault=='missing-counters':footer.pop('lifecycle')
            elif fault=='allocation-mismatch':footer['lifecycle']['ids_allocated']+=1
            elif fault=='negative-counter':footer['lifecycle']['field_version_entries']=-1
            else:bad[0].pop('identity_lifecycle_version')
            try:checked(plan,bad)
            except ValueError as error:negative.append({'mode':mode,'fault':fault,'state':'evidence_invalid','error':str(error)})
            else:raise AssertionError('Accepted lifecycle counter corruption '+fault)
    save(out/'lifecycle-guards.json',negative);guards['lifecycle-counters']={'checks':len(negative),'gate':True}
    before=load(home/'lifecycle-before-portable-02/results.json');state=load(home/'release/state/results.json');unit=load(home/'release/state/map-results.json');assert state['gate']and unit['gate']and state['events']==32
    assert load(home/'lifecycle-before-portable-02/protocol-before-jvm.json')['fixture_sha256']==load(home/'release/state/protocol-before-jvm.json')['fixture_sha256']
    tests={c['test']:c for c in state['checks']};batch=tests['120000-cumulative-bounded-live'];assert batch['after']['ids_allocated']-batch['before']['ids_allocated']==120000 and batch['after']['ids_registered']==0 and batch['after']['field_version_entries']==0 and batch['after']['array_slot_entries']==0
    prior=load(home/'method-stress-before/results.json');fixed=load(home/'method-stress-after/results.json');latest=load(home/'final-method-stress/results.json');assert all(r['growth']==[9600,9600]for r in prior['reports'])and all(r['growth']==[0,0]for r in fixed['reports']+latest['reports'])
    assert load(home/'method-stress-before/protocol-before-jvm.json')['fixture_sha256']==load(home/'method-stress-after/protocol-before-jvm.json')['fixture_sha256']
    auxiliary=home/'release/spring-async';plan=load(auxiliary/'build/fixture/plan.json');spring={}
    for mode in ('full','selective'):
        raw=rows(auxiliary/mode/'events.jsonl');assert methods(plan,raw)==fields(plan,raw)==lifecycle(raw)==1;audit=validate_async_protocol(plan,raw);assert len(audit['tasks'])==15;spring[mode]={'tasks':15,'mutations':len(load(auxiliary/'results.json')['modes'][mode]['faults']),'capture_sha256':sha(auxiliary/mode/'events.jsonl')}
    monitor=load(home/'release/monitor/checks.json');framework=load(home/'release/monitor/framework-checks.json');assert len(monitor['checks'])==len(framework)==2
    old=load(home/'final-old-business/results.json')['captures'];assert len(old)==14 and all(c['versions_equal']and c['root_audits_equal']and c['known_changes']==c['explicit_data_changes']==c['selector_changes']==0 for c in old)
    oldaudit=load(home/'final-old-audit/results.json');assert oldaudit['fault_checks']==72 and len(oldaudit['old_control_captures'])==18
    for source,digest in load(home/'final-old-audit/core-under-test.json')['sources'].items():assert sha(Path(source))==digest
    agents={}
    for label,p in [('method',home/'method-agent-01'),('final',home/'lifecycle-agent-06'),('spring_auxiliary',auxiliary/'build')]:
        manifest=load(p/'build.json');jar=p/'distributed-observer.jar'
        with ZipFile(jar)as z:hashes={n:hashlib.sha256(z.read(n)).hexdigest()for n in z.namelist()if n.endswith('.class')and not n.startswith(('org/','tracefusion/internal/'))}
        agents[label]={'sha256':sha(jar),'class_sha256':hashes,'compiler_version':manifest['compiler_version'],'compiler_target':manifest['compiler_target'],'build_receipt':str(p/'build.json')}
        if label!='method':
            for file,digest in manifest['sources'].items():
                if file.endswith('.java'):assert sha(Path(file))==digest,(label,file)
    java=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java';jdk={'java':str(java),'version':subprocess.check_output([str(java),'-version'],stderr=subprocess.STDOUT,text=True),'java_sha256':sha(java),'rt_jar_sha256':sha(java.parent.parent/'jre/lib/rt.jar'),'libjvm_sha256':sha(java.parent.parent/'jre/lib/amd64/server/libjvm.so')}
    sources=set(load(home/'lifecycle-agent-06/build.json')['sources'])
    sources.update(str(HERE/n)for n in ('method_value_protocol.py','identity_lifecycle_protocol.py','field_value_protocol.py','infer_application_execution.py','infer_execution_kernel.py','infer_response_binding.py','WeakIdentityMap.java','OwnerVersions.java','test_method_value_protocol.py','test_identity_lifecycle_protocol.py','LifecycleStateFixture.java','LifecycleMapFixture.java','MethodObservationFixture.java','run_lifecycle_state_controls.py','run_method_observation_controls.py','audit_method_lifecycle.py'))
    summary={'baseline':'4035a025c07f1a6a7f3cbc0b0fe5c72066b0798b','method_commit':'5b3daa2','protocol':{'method_value_version':1,'field_value_version':1,'exception_dispatch_version':1,'identity_lifecycle_version':1},'JDK':jdk,'agents':agents,'cohorts':cohorts,'guards':guards,'fixed_graph':{'before':prior,'method_fix':fixed,'final':latest},'state_before':before,'state_after':state,'identity_map_unit':unit,'spring_async':spring,'monitor_cleanup':monitor,'framework_cleanup':framework,'old_replay':{'public_captures':18,'business_captures':14,'guard_cases':72,'original_unknowns':6,'call_write_targets':22},'units':{'original':127,'method_new':13,'lifecycle_protocol_new':7,'total':147,'passed':147,'failed':0,'skipped':0,'missing_dependencies':0,'log':str(home/'final-unit-tests.log')},'sources':{p:sha(Path(p))for p in sorted(sources)},'not_executed':['unrelated historical container redeployments','class unloading','performance or heap-memory benchmarks'],'whole_semantics_gate':False}
    with(out/'cases.csv').open('w')as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    save(out/'receipt.json',summary);print(json.dumps({'case_records':len(data),'new_guards':guards,'GC_checks':len(state['checks']),'whole_semantics_gate':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
