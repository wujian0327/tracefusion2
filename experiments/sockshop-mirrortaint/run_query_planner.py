#!/usr/bin/env python3
"""Build/run a bounded query-planner experiment; all inference is query-independent code."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import time
from zipfile import ZipFile,ZIP_DEFLATED

from query_observation_planner import plan,verify,digest
from infer_query_observations import infer

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
JARS=[ROOT/'artifacts/java-collection-deps'/n for n in ('asm-9.7.1.jar','asm-tree-9.7.1.jar')]
JARS += [ROOT/'artifacts/flowdist-orders-static-lambda-v3-20261013/work/lib'/n for n in ('jackson-core-2.8.6.jar','jackson-databind-2.8.6.jar','jackson-annotations-2.8.6.jar')]
QUERY_SETS={'total':['Orders.total'],'name':['Shipment.name'],'payload':['Noise.payload'],
            'total-name':['Orders.total','Shipment.name'],'all':['Orders.total','Shipment.name','Noise.payload']}


def load(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def command(cmd,log):
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=90);log.write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(str(cmd[:2])+': '+r.stdout+r.stderr)
    return r


def build(out,extra_work=0,helper_depth=0):
    out.mkdir(parents=True,exist_ok=False);tools=out/'tools';app=out/'app';tools.mkdir();app.mkdir()
    require=["8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281","9929881f59eb6b840e86d54570c77b59ce721d104e6dfd7a40978991c2d3b41f"]
    if [sha(p) for p in JARS[:2]]!=require:raise ValueError('ASM dependency changed')
    cp=':'.join(map(str,JARS))
    sources=[HERE/n for n in ('QueryObservationAgent.java','QueryBytecodeModel.java')]
    command(['javac','--release','8','-cp',cp,'-d',str(tools),*map(str,sources)],out/'compile-tools.log')
    text=(HERE/'QueryPlannerFixture.java').read_text()
    text=text.replace('// EXTRA_WORK: generated variants insert irrelevant field work here.',
                      '\n'.join('noise.marker=noise.marker+a.quantity;' for _ in range(extra_work)))
    if helper_depth:
        chain='public static String copy(String name){return layer0(name);}'
        for i in range(helper_depth):chain+='public static String layer'+str(i)+'(String value){return '+('layer'+str(i+1)+'(value)' if i+1<helper_depth else 'value')+';}'
        text=text.replace('public static String copy(String name){return name;}',chain)
        text=text.replace('calculate(', 'renamedCalculation(')
    fixture=out/'QueryPlannerFixture.java';fixture.write_text(text)
    command(['javac','--release','8','-cp',cp,'-d',str(app),str(fixture)],out/'compile-app.log')
    command(['java','-cp',str(tools)+':'+cp,'QueryBytecodeModel',str(app),str(out/'model.json')],out/'model.log')
    model=load(out/'model.json');entries=[k for k,m in model['methods'].items() if m['name']=='process']
    if len(entries)!=1:raise ValueError('Entry boundary is ambiguous')
    plans={}
    for name,targets in QUERY_SETS.items():
        started=time.perf_counter();p=plan(model,entries[0],targets);elapsed=time.perf_counter()-started
        save(out/(name+'.plan.json'),p);plans[name]={'plan_sha256':sha(out/(name+'.plan.json')),'planning_seconds':elapsed,
          'selected_branches':len(p['selected_branch_sites']),'selected_sites':len(p['selected_sites']),'full_sites':len(p['full_sites']),
          'snapshot_fields':len(p['snapshot_fields']),'full_snapshot_fields':len(p['full_snapshot_fields']),
          'certificate':p['certificate']}
    agent=out/'query-observer.jar'
    with ZipFile(agent,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: QueryObservationAgent\n\n')
        for p in tools.glob('QueryObservationAgent*.class'):z.write(p,p.name)
        for dependency in JARS[:2]:
            with ZipFile(dependency) as dep:
                for name in dep.namelist():
                    if name.startswith('org/objectweb/asm/') and name.endswith('.class'):z.writestr(name,dep.read(name))
    save(out/'build.json',{'sources':{str(p):sha(p) for p in sources+[HERE/'QueryPlannerFixture.java']},
         'generated_source_sha256':sha(fixture),'class_sha256':{p.name:sha(p) for p in app.glob('*.class')},
         'model_sha256':digest(model),'agent_sha256':sha(agent),'dependencies':{str(p):sha(p) for p in JARS},
         'entry':entries[0],'extra_work':extra_work,'helper_depth':helper_depth,'plans':plans})
    print(json.dumps(plans,indent=2),flush=True)


def freeze(out,build_dir,seed):
    out.mkdir(parents=True,exist_ok=False)
    manifest=load(build_dir/'build.json')
    for name,r in manifest['plans'].items():
        if sha(build_dir/(name+'.plan.json'))!=r['plan_sha256']:raise ValueError('Plan changed before freeze')
    rng=random.Random(seed);cases=[]
    for name,pick,noise,equal,alias in [('different-left',True,False,False,False),('different-right',False,True,False,False),
          ('equal-left',True,True,True,False),('equal-right',False,False,True,False),
          ('repeat-left',True,True,True,False),('repeat-right',False,False,True,False),
          ('alias-left',True,False,True,True),('alias-right',False,True,True,True)]:
        aq=rng.randint(1,9);bq=aq if equal else aq+10
        cases.append(dict(id=name,aq=aq,bq=bq,price=rng.choice([1.25,2.5,3.75]),an='SAME' if equal else 'LEFT-'+name,
                          bn='SAME' if equal else 'RIGHT-'+name,ap='SAME' if equal else 'PUBLIC-A',bp='SAME' if equal else 'PUBLIC-B',pick=pick,noise=noise,alias=alias))
    for i in range(12):cases.append(dict(id='parallel-'+str(i),aq=4,bq=4,price=2.5,an='SAME',bn='SAME',ap='SAME',bp='SAME',pick=i%2==0,noise=i%3==0,alias=False))
    # New randomized inputs are generated only after code/model/plan freeze.
    for i in range(24):
        aq=rng.randint(1,30);bq=aq if i%2 else rng.randint(1,30)
        cases.append(dict(id='heldout-'+str(i),aq=aq,bq=bq,price=rng.choice([.5,1.25,2.5,7.75]),an='A-'+str(rng.randrange(1000)),
                          bn='B-'+str(rng.randrange(1000)),ap='P'+str(i),bp='P'+str(i),pick=bool(rng.getrandbits(1)),noise=bool(rng.getrandbits(1)),alias=False))
    save(out/'cases.json',cases);save(out/'freeze.json',{'seed':seed,'cases_sha256':sha(out/'cases.json'),
         'build_sha256':sha(build_dir/'build.json'),'plans':manifest['plans'],
         'inference_sources':{str(HERE/n):sha(HERE/n) for n in ('query_observation_planner.py','infer_query_observations.py')},
         'scope':'New generated inputs after code/model/plan freeze; not an independently authored blind benchmark.'})


def run(out,build_dir):
    frozen=load(out/'freeze.json');build_info=load(build_dir/'build.json')
    if sha(build_dir/'build.json')!=frozen['build_sha256'] or sha(out/'cases.json')!=frozen['cases_sha256']:raise ValueError('Frozen inputs changed')
    for file,expected in {**build_info['dependencies'],**build_info['sources'],**frozen['inference_sources']}.items():
        if sha(Path(file))!=expected:raise ValueError('Frozen input changed: '+file)
    if sha(build_dir/'query-observer.jar')!=build_info['agent_sha256']:raise ValueError('Collector changed')
    for name,r in build_info['plans'].items():
        p=build_dir/(name+'.plan.json')
        if sha(p)!=r['plan_sha256']:raise ValueError('Plan changed')
        verify(load(p),load(build_dir/'model.json'))
        for mode in ('full','selective','fixed'):
            dest=out/(name+'-'+mode);dest.mkdir(exist_ok=False)
            cmd=['java','-Xms32m','-Xmx256m','-javaagent:'+str(build_dir/'query-observer.jar'),'-Dquery.plan='+str(p),
                 '-Dquery.mode='+mode,'-Dquery.events='+str(dest/'events.jsonl'),'-Dquery.test.barrier=true',
                 '-cp',str(build_dir/'app')+':'+':'.join(map(str,JARS)),'QueryPlannerFixture',str(out/'cases.json'),str(dest/'business.json')]
            started=time.perf_counter();command(cmd,dest/'console.log');save(dest/'run.json',{'command':cmd,'whole_process_seconds':time.perf_counter()-started,
                     'includes_startup':True,'performance_eligible':False,'exit_code':0})
            print(name,mode,'completed',flush=True)


def f32(value):return struct.unpack('f',struct.pack('f',value))[0]


def evaluate(out,build_dir):
    cases=load(out/'cases.json');results={};model=load(build_dir/'model.json')
    for name in QUERY_SETS:
        p=load(build_dir/(name+'.plan.json'));verify(p,model);results[name]={}
        for mode in ('full','selective','fixed'):
            run_dir=out/(name+'-'+mode);business=load(run_dir/'business.json');indexed={r['id']:r for r in business}
            if len(business)!=len(cases) or set(indexed)!={c['id'] for c in cases}:raise ValueError('Business coverage differs')
            for c in cases:
                expected_total=f32(f32((c['aq'] if c['pick'] or c['alias'] else c['bq'])*f32(c['price']))+f32(4.99))
                expected_payload=c['ap'] if c['noise'] or c['alias'] else c['bp']
                expected_marker=c['aq']+(c['aq'] if c['alias'] else c['bq'])+load(build_dir/'build.json')['extra_work']*c['aq']
                if abs(indexed[c['id']]['total']-expected_total)>1e-4 or indexed[c['id']]['name']!=c['an'] or indexed[c['id']]['payload']!=expected_payload or indexed[c['id']]['marker']!=expected_marker:
                    raise ValueError('Independent business oracle failed')
            r=infer(p,run_dir/'events.jsonl');raw=[json.loads(l) for l in (run_dir/'events.jsonl').read_text().splitlines()]
            expected_queries=len(cases)*sum(p['root_arguments'].count('L'+field.rsplit('.',1)[0]+';') for field in p['targets'])
            if r['frames']!=len(cases) or len(r['answers'])!=expected_queries or {a['request_id'] for a in r['answers']}!={c['id'] for c in cases}:
                raise ValueError('Captured query coverage differs from frozen workload')
            entries={v['frame']:v for v in raw if v['kind']=='enter'};queries=[]
            for a in r['answers']:
                c=next(c for c in cases if c['id']==a['request_id']);args=entries[a['frame']]['arguments']
                field=a['field'].rsplit('.',1)[1]
                if field=='total':expected={(0 if c['pick'] or c['alias'] else 1,'quantity'),(0,'unitPrice')}
                elif field=='name':expected={(0,'name')}
                else:expected={(0 if c['noise'] or c['alias'] else 1,'publicValue')}
                actual=set();source_instances=[]
                for _,owner,source_field,version in a['sources'] or []:
                    arg=min(v['argument'] for v in args if v['object']==owner)
                    actual.add((arg,source_field.rsplit('.',1)[1]))
                    source_instances.append([arg,source_field,version])
                target_arg=min(v['argument'] for v in args if v['object']==a['owner'])
                expected_target_arg=2 if field=='total' else 3 if field=='name' else 4
                expected_source_version=2 if c['id']=='repeat-right' else 1
                expected_target_version=(2 if field in ('total','name') else 1)*(2 if c['id']=='repeat-right' else 1)
                versions_exact=(all(v[3]==expected_source_version for v in a['sources'] or [])
                                and a['version']==expected_target_version and target_arg==expected_target_arg)
                queries.append(dict(a,expected=[list(v) for v in sorted(expected)],actual=[list(v) for v in sorted(actual)],
                                    source_instances=sorted(source_instances),target_instance=[target_arg,a['field'],a['version']],
                                    expected_source_version=expected_source_version,expected_target_version=expected_target_version,
                                    exact=a['known'] and actual==expected and versions_exact))
            answered=sum(q['known'] for q in queries);exact=sum(q['exact'] for q in queries)
            active=set();parallel=set();peak=0;parallel_peak=0
            for row in raw:
                if row['kind']=='enter':
                    active.add(row['frame']);peak=max(peak,len(active))
                    if row['request_id'].startswith('parallel-'):parallel.add(row['frame']);parallel_peak=max(parallel_peak,len(parallel))
                elif row['kind']=='exit':active.remove(row['frame']);parallel.discard(row['frame'])
            if parallel_peak!=12:raise ValueError('Concurrent frames did not overlap')
            save(run_dir/'predictions.json',r)
            results[name][mode]={'queries':len(queries),'answered':answered,'exact':exact,'unknown':len(queries)-answered,
               'coverage':answered/len(queries),'field_events':r['field_events'],'branch_events':r['branch_events'],
               'data_events':r['data_event_count'],'log_bytes':r['log_bytes'],'field_hook_calls':r['hook_metrics']['field_hook_calls'],
               'branch_hook_calls':r['hook_metrics']['branch_hook_calls'],'peak_overlapping_frames':peak,
               'peak_parallel_test_frames':parallel_peak,'query_results':queries}
        full,selected=results[name]['full'],results[name]['selective']
        if full['exact']!=full['queries'] or selected['exact']!=full['exact']:raise ValueError('Full/selected answers differ')
        normalize=lambda rows:{(r['request_id'],r['field']):(r['target_instance'],r['source_instances']) for r in rows}
        if normalize(full['query_results'])!=normalize(selected['query_results']):raise ValueError('Full/selected instance/version answers differ')
    report={'kind':'query-driven-observation-selection','results':results,'build':load(build_dir/'build.json'),
            'freeze':load(out/'freeze.json'),'baseline_note':'fixed retains entry/exit and mandatory target writes; it is stronger than pure boundary-only capture.',
            'performance_eligible':False,'new_input_cases':len(cases),'business_calls':len(cases)*len(QUERY_SETS)*3}
    save(out/'results.json',report)
    print(json.dumps({name:{mode:{k:v for k,v in r.items() if k!='query_results'} for mode,r in modes.items()} for name,modes in results.items()},indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('build','freeze','run','evaluate'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path);p.add_argument('--extra-work',type=int,default=0);p.add_argument('--helper-depth',type=int,default=0);p.add_argument('--seed',type=int,default=241015);a=p.parse_args();out=a.out.resolve()
    if a.stage=='build':build(out,a.extra_work,a.helper_depth)
    elif a.stage=='freeze':freeze(out,a.build.resolve(),a.seed)
    elif a.stage=='run':run(out,a.build.resolve())
    else:evaluate(out,a.build.resolve())
