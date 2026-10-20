#!/usr/bin/env python3
"""Mixed normal, caught, propagated, pre-body and finally JVM evidence controls."""
import argparse,copy,json,subprocess
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import HERE,load,save,sha
from infer_distributed_fields import Reconstruction


def run(out,base):
    out.mkdir();classes=out/'classes';classes.mkdir()
    command(['javac',*java8_target()[1],'-cp',':'.join(map(str,[base/'tools',*JARS])),'-d',str(classes),str(HERE/'CallLifecycleFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'CallLifecycleFixture.root(LCallLifecycleFixture$Item;I)LCallLifecycleFixture$Item;','targets':['CallLifecycleFixture$Item.text'],'response_path':'/text','read_forward_contracts':True}})
    raw=subprocess.check_output(['java','-cp',str(b/'tools'),'JdkContractProbe'],text=True)
    runtime=dict(l.split('=',1) for l in raw.splitlines() if '=' in l)
    p=load(b/'fixture/plan.json');p['read_forward_contracts']['runtime_profiles'].append({'java_runtime_version':runtime.pop('java.runtime.version'),'class_sha256':runtime,'scope':'Standalone semantic JVM only'})
    save(b/'fixture/plan.json',p);manifest=load(b/'build.json');manifest['inputs']['fixture']['plan_sha256']=sha(b/'fixture/plan.json');save(b/'build.json',manifest)
    results={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'CallLifecycleFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);rows=[json.loads(l) for l in (cap/'fixture/events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='problem' for r in rows)
        g=Reconstruction(b,cap,['fixture']);checks=[]
        for c in cases:
            if c['status']=='aborted':continue
            answer=g.query(c['message'],'/text','fixture');expected=c['mode']==0
            assert answer['known']==expected,(mode,c,answer)
            if expected:
                source=next(r for r in rows if r['kind']=='binding-input' and r['message']==c['message'] and r['argument']==0)
                expected_coords={(f['owner'],f['field'],f['version']) for f in source['fields']}
                assert {(s['owner'],s['field'],s['version']) for s in answer['sources']}==expected_coords
            if c['mode']==7:
                summary=next(r for r in rows if r['kind']=='binding-call-summary' and r['message']==c['message'])
                assert summary['root_effects_verified']
                assert all(r['valid'] for r in rows if r['kind']=='binding-call-exit' and r['message']==c['message']), 'Computed helper must pass effect checks without gaining an origin'
            checks.append({'case':c,'known':answer['known'],'sources':answer['sources']})
        throws=[r for r in rows if r['kind']=='binding-call-throw'];summaries=[r for r in rows if r['kind']=='binding-call-summary']
        assert len(summaries)==13 and sum(r['completion']=='exceptional' for r in summaries)==2 and all(r['unpaired']==0 for r in summaries)
        assert any(r['callee'].endswith('work()LCallLifecycleFixture$Item;') and r['receiver'] is None for r in throws)
        faults={}
        for fault in ('missing-throw','duplicate-throw','wrong-call-id','wrong-exception','wrong-completion','missing-abort-summary','missing-root-abort','truncated-capture'):
            broken=copy.deepcopy(rows);at=next(i for i,r in enumerate(broken) if r['kind']=='binding-call-throw')
            if fault=='missing-throw':broken.pop(at)
            elif fault=='duplicate-throw':broken.insert(at,copy.deepcopy(broken[at]))
            elif fault=='wrong-call-id':broken[at]['call_id']='other-call'
            elif fault=='wrong-exception':broken[at]['detail']['exception_object']=None
            elif fault=='wrong-completion':broken[at]['detail']['completion']='normal'
            elif fault=='missing-abort-summary':broken.pop(next(i for i,r in enumerate(broken) if r['kind']=='binding-call-summary' and r['completion']=='exceptional'))
            elif fault=='missing-root-abort':broken.pop(next(i for i,r in enumerate(broken) if r['kind']=='abort'))
            else:broken=broken[:at+1]
            for i,r in enumerate(broken,1):r['seq']=i
            try:Reconstruction(b,cap,['fixture'],decoded_rows={'fixture':broken})
            except ValueError as e:faults[fault]=str(e)
            else:raise AssertionError('Corrupt lifecycle accepted: '+fault)
        abrupt=out/('abrupt-'+mode);(abrupt/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(abrupt/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'CallLifecycleFixture','halt'],abrupt/'stdout.log')
        try:Reconstruction(b,abrupt,['fixture'])
        except ValueError as e:abrupt_reason=str(e)
        else:raise AssertionError('Runtime.halt incomplete capture accepted')
        results[mode]={'requests':13,'targets':len(checks),'known':sum(c['known'] for c in checks),'expected_unknown':sum(not c['known'] for c in checks),'root_aborts':2,'throw_events':len(throws),'abrupt_process_refused':abrupt_reason,'checks':checks,'business_cases':cases,'faults':faults}
        save(out/'results.json',{'all_passed':True,'scope':'Independent small-program semantic controls, not application coverage','modes':results})
        print(mode,{k:v for k,v in results[mode].items() if k not in ('checks','business_cases','faults')},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.base.resolve())
