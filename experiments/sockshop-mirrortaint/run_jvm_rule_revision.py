"""Fixed original workloads; new shared offline rules, unchanged observer binary."""
import argparse,copy,json,random,subprocess,sys,time,os,resource
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import run_unrelated_work_scaling as old

H=ROOT/'artifacts/jvm-rule-evidence-20261110'
OLD=ROOT/'artifacts/unrelated-work-scaling-20261109'

def verify():
    path=H/'candidate-after-identity-fix.json' if (H/'candidate-after-identity-fix.json').exists() else H/'candidate-before-pilot.json'
    f=load(path)
    for p,h in f['core_sources'].items():assert sha(Path(p))==h,p
    for p,h in load(H/'protocol-before-change.json')['binaries_and_protocols'].items():assert sha(Path(p))==h,p
    return f

def install():
    old.H=H;old.verify=verify
    import audit_unrelated_work_scaling as audit
    audit.H=H;audit.verify=verify
    if not hasattr(audit,'unrelated_original_run'):audit.unrelated_original_run=audit.run
    def scored(out,task,tier,mode):
        if tier=='related-high'and mode in ('full','selective'):return related_tf(out,mode)
        return audit.unrelated_original_run(out,task,tier,mode)
    audit.run=scored
    return audit

def related_tf(out,mode):
    """Literal original sum: all 257 raw field occurrences, never graph truth."""
    from raw_source_call_facts import RawSourceCallFacts
    from audit_zlt_foundation_revision import tf_pair
    from infer_distributed_fields import Reconstruction
    dest=out/'audit-related-257';dest.mkdir(exist_ok=False)
    rows=[json.loads(s)for s in(out/'capture/events.jsonl').read_text().splitlines()]
    cases=load(out/'warmup.json')['requests']+load(out/'measure.json')['requests'];facts=RawSourceCallFacts(rows);truth=[]
    for case in cases:
        sources=[r for r in rows if r['kind']=='binding-source'and r.get('message')==case['message']and r.get('callee')=='bench/Store.read()Lbench/Payload;'];assert len(sources)==1;s=sources[0];tf_pair(facts.matching(rows,s),s)
        fields=[f for f in s['fields']if f['path']=='/target'or f['path'].startswith('/f')];assert len(fields)==257
        want={(s['callee'],s['frame'],s['seq'],f['path'],f['owner'],f['field'],f['version'])for f in fields};assert len(want)==257
        truth.append(want)
    save(dest/'raw-truth-before-prediction.json',[{'message':c['message'],'expected':sorted(t,key=str)}for c,t in zip(cases,truth)])
    (dest/'build/role').mkdir(parents=True);(dest/'capture/role').mkdir(parents=True);(dest/'build/role/plan.json').write_bytes((H/'controlled-build-04/related-high/plan.json').read_bytes());(dest/'capture/role/events.jsonl').symlink_to((out/'capture/events.jsonl').resolve())
    graph=Reconstruction(dest/'build',dest/'capture',['role']);scores=[]
    for c,want in zip(cases,truth):
        a=graph.query(c['message'],'/target','role',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']}
        scores.append({'message':c['message'],'correct':a['known']and got==want,'known':a['known'],'expected_count':257,'actual_count':len(got),'answer':a})
    save(dest/'scores.json',scores);summary={'mode':mode,'correct':sum(s['correct']for s in scores),'targets':len(cases),'expected_origins_each':257,'actual_origin_counts':[s['actual_count']for s in scores],'actual_scalar_omissions':sum(sum(r.get('target_observation',{}).get('scalar_fields',{}).values())for r in rows)}
    save(dest/'summary.json',summary);return summary

def prepare():
    import shutil
    from plan_capability_policy import choose
    from jvm_semantic_rules import specification
    sealed=load(H/'protocol-before-change.json');paths=list(sealed['baseline_sources'])
    for name in ('jvm_semantic_rules.py',):paths.append(str(HERE/name))
    save(H/'candidate-before-pilot.json',{'core_sources':{p:sha(Path(p))for p in paths},'semantic_rules':specification(),'agent_unchanged':True,'agent_sha256':sha(old.AGENT),'attribution':'No new omission shape: existing boundary projection and existing scalar write omission now consume shared static demand. Do not claim old savings as a new mechanism.'})
    protocol=load(OLD/'protocol-before-tools.json');save(H/'protocol-before-tools.json',protocol);shutil.copyfile(OLD/'images-before.json',H/'images-before.json')
    dest=H/'controlled-build-04';dest.mkdir(exist_ok=False)
    for tier in old.TIERS:
        d=dest/tier;d.mkdir();previous=OLD/'controlled-build-04'/tier
        for name in ('business.jar','model.json','schema.json','mt-config.json'):shutil.copyfile(previous/name,d/name)
        q=protocol['controlled'];target,path=q['target'].split('@')
        try:
            p,r=choose(load(d/'model.json'),{'entry':q['entry'],'target':target,'path':path,'source_calls':q['source_calls']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'));save(d/'plan.json',p);save(d/'route.json',r);save(d/'planning.json',{'state':'planned','profile':p['profile']})
        except ValueError as e:save(d/'planning.json',{'state':'planning_rejected','error':str(e)})
    save(H/'plans-before-pilot.json',{str(p):sha(p)for p in dest.rglob('*')if p.is_file()})

def pilot():
    audit=install();results={};root=H/'pilot';root.mkdir(exist_ok=False)
    for tier in old.TIERS:
        results[tier]={}
        for mode in old.MODES:
            if mode in ('full','selective')and not(H/'controlled-build-04'/tier/'plan.json').exists():
                results[tier][mode]={'passed':False,'planning':load(H/'controlled-build-04'/tier/'planning.json')};continue
            out=root/(tier+'-'+mode);r=old.controlled_trial(out,tier,mode,0,3,2);a=audit.run(out,'controlled',tier,mode)
            good=r.get('state')=='captured'and r.get('requests')==r.get('business_passed')and (mode=='original' or a.get('correct')==6)
            results[tier][mode]={'passed':good,'run':r,'audit':a};save(H/'pilot-progress.json',results)
    omissions={t:results[t]['selective'].get('audit',{}).get('actual_scalar_omissions',0)for t in ('low','medium','high')}
    gate=all(c['passed']for group in results.values()for c in group.values())and 0<omissions['low']<omissions['medium']<omissions['high']
    save(H/'pilot-results.json',results);save(H/'gate.json',{'passed':gate,'actual_boundary_omissions':omissions,'related_requires_257_each':True,'no_formal_if_false':True})
    print('GATE',gate,flush=True)

def formal():
    gate=H/'gate-calibrated.json' if (H/'gate-calibrated.json').exists() else H/'gate.json'
    assert load(gate)['passed'];audit=install();verify()
    rng=random.Random(load(H/'protocol-before-tools.json')['formal']['order_seed']);jobs=[]
    for round_ in range(1,6):
        for tier in ('low','medium','high'):
            modes=old.MODES[:];rng.shuffle(modes)
            jobs += [{'round':round_,'tier':tier,'mode':mode}for mode in modes]
    save(H/'formal-order-before-timing.json',{'jobs':jobs,'core_sources':verify()['core_sources'],'warm':30,'measure':60,'rps':2,'driver_sha256':sha(Path(__file__)),'helper_hashes':{str(HERE/n):sha(HERE/n)for n in ('run_unrelated_work_scaling.py','audit_unrelated_work_scaling.py','measure_unrelated_work_offline.py')},'no_new_pruning_attribution':True})
    for j in jobs:
        name='%02d-%s-%s'%(j['round'],j['tier'],j['mode']);out=H/'formal'/name
        print('START',name,flush=True);r=old.controlled_trial(out,j['tier'],j['mode'],30,60,2);a=audit.run(out,'controlled',j['tier'],j['mode'])
        good=r.get('state')=='captured'and r.get('requests')==180 and r.get('business_passed')==180 and(j['mode']=='original' or a.get('correct')==180)
        save(out/'formal-job.json',{**j,'passed':good})
        if not good:raise RuntimeError('Formal failure retained '+name)
        if j['mode']!='original':
            cmd=['taskset','-c',str(min(os.sched_getaffinity(0))),sys.executable,str(Path(__file__).resolve()),'--stage','offline','--trial',str(out),'--tier',j['tier'],'--mode',j['mode']]
            start=time.perf_counter();before=resource.getrusage(resource.RUSAGE_CHILDREN)
            with(out/'normal-offline.log').open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
            after=resource.getrusage(resource.RUSAGE_CHILDREN);save(out/'normal-offline-process.json',{'wall_seconds':time.perf_counter()-start,'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,'fresh_exec':True})

def offline(trial,tier,mode):
    install()
    import measure_unrelated_work_offline as m
    m.H=H;m.verify=verify
    original_save=m.save
    def measured_save(path,data):
        if Path(path).name=='summary.json':
            data['resource_ru_maxrss_KiB']=data['VmHWM_KiB']
            data['VmHWM_KiB']=int(next(s.split()[1]for s in Path('/proc/self/status').read_text().splitlines()if s.startswith('VmHWM:')))
        return original_save(path,data)
    m.save=measured_save
    m.run(trial,'controlled',tier,mode)

def rescore():
    # Preserve the original scorer result. Its unrelated-field equality rule
    # cannot score a sum with a new target version; the task itself is unchanged.
    results=load(H/'pilot-results.json')
    for mode in ('full','selective'):
        out=H/'pilot'/('related-high-'+mode);a=related_tf(out,mode)
        results['related-high'][mode]['audit']=a
        results['related-high'][mode]['passed']=a['correct']==6 and results['related-high'][mode]['run']['business_passed']==6
    save(H/'pilot-results-calibrated.json',results)
    initial=load(H/'gate.json');save(H/'gate-calibrated.json',{**initial,'passed':all(v.get('passed',False)for group in results.values()for v in group.values()),'calibration':'Raw 257-field sum oracle replaces unrelated-case source/target version equality; original results preserved. No core or source-boundary change.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','pilot','formal','offline','rescore'],required=True);p.add_argument('--trial',type=Path);p.add_argument('--tier');p.add_argument('--mode');a=p.parse_args()
    if a.stage=='offline':offline(a.trial.resolve(),a.tier,a.mode)
    else:{'prepare':prepare,'pilot':pilot,'formal':formal,'rescore':rescore}[a.stage]()
