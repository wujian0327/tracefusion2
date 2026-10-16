#!/usr/bin/env python3
"""Execute original JVM library operations and audit generic collection replay."""
import argparse
import copy
import json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from run_query_planner import command, JARS
from run_planned_service import HERE, save, load, sha
from experiment_environment import java8_target
from infer_collection_service import infer_collection


def run(out):
    out.mkdir(parents=True,exist_ok=False); app=out/'classes';app.mkdir()
    _,target=java8_target()
    command(['javac',*target,'-d',str(app),str(HERE/'CollectionServiceFixture.java')],out/'fixture-compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in app.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    entry='CollectionServiceFixture.transform(LCollectionServiceFixture$Input;Ljava/lang/String;Ljava/lang/String;Z)LCollectionServiceFixture$Output;'
    build(out/'build',{'fixture':{'jar':str(jar),'entry':entry,'targets':['CollectionServiceFixture$Output.cells'],'profile':'collection-computation'}})
    p=load(out/'build/fixture/plan.json');reports={};all_answers={}
    for mode in ('full','selective'):
        log=out/(mode+'.events.jsonl')
        command(['java','-javaagent:'+str(out/'build/distributed-observer.jar'),'-Dservice.plan='+str(out/'build/fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(log),'-cp',str(app),'CollectionServiceFixture'],out/(mode+'.stdout.log'))
        rows=[json.loads(s) for s in log.read_text().splitlines()]
        if any(r['kind']=='problem' for r in rows):raise ValueError('Collector failed')
        result=infer_collection(p,rows);save(out/(mode+'.answers.json'),result)
        grouped={f:sorted([a for a in result['answers'] if a['root_frame']==f],key=lambda a:a['field']) for f in result['completed_roots']}
        if len(grouped)!=5 or any(len(v)!=2 for v in grouped.values()):raise ValueError('Fixture population differs')
        expected=[({'@list:0','@list:2'},True),({'@list:1','@list:2'},True),(set(),False),(set(),True),({'@list:0','@list:2'},True)]
        semantic=[]
        for i,answers in enumerate(grouped.values()):
            for a in answers:
                fields={s[1] for s in a['sources']};wanted=set(expected[i][0])
                if expected[i][1]:wanted.add('CollectionServiceFixture$Input.scale')
                if i==3 and a['field']=='@map:other':wanted=set()
                if not a['known'] or fields!=wanted or len(a['sources'])!=len(wanted):raise ValueError('Independent source-position/overwrite oracle differs: '+str(a))
                semantic.append({'case':i,'field':a['field'],'sources':sorted(fields),'value':a['observed'].get('value')})
        # Equal cached Integer identity at three positions must remain three
        # separate source coordinates, and repeated roots must not merge maps.
        if len({a['owner'] for a in result['answers']})!=5:raise ValueError('Repeated invocation targets merged')
        mutated=copy.deepcopy(rows);victim=next(r for r in mutated if r['kind']=='collection-call-exit' and r['result'].get('value')==2 and p['collection_method']['instructions'][r['pc']].get('name')=='indexOf')
        victim['result']['value']=0
        try:infer_collection(p,mutated)
        except ValueError:pass
        else:raise ValueError('Tampered indexOf result accepted')
        reports[mode]={'queries':len(result['answers']),'exact':10,'events':len(rows),'bytes':log.stat().st_size,'tamper_rejected':True};all_answers[mode]=semantic
    if all_answers['full']!=all_answers['selective']:raise ValueError('Policies disagree')
    negative={}
    for case,marker in [('mutation','MUTATION_REJECTED'),('virtual','DISPATCH_REJECTED')]:
        log=out/(case+'.events.jsonl')
        result=command(['java','-javaagent:'+str(out/'build/distributed-observer.jar'),'-Dservice.plan='+str(out/'build/fixture/plan.json'),'-Dservice.mode=selective','-Dservice.events='+str(log),'-cp',str(app),'CollectionServiceFixture',case],out/(case+'.stdout.log'))
        rows=[json.loads(s) for s in log.read_text().splitlines()]
        if marker not in result.stdout or not any(r['kind']=='problem' for r in rows):raise ValueError('Negative runtime contract accepted: '+case)
        negative[case]={'rejected':True,'problem_events':[r['message'] for r in rows if r['kind']=='problem']}
    save(out/'results.json',{'all_passed':True,'profiles':reports,'negative_contracts':negative,'planning':p['planning_stats'],'cases':['equal boxed values at distinct positions','different positions/values','failed List.get and original catch fallback','branch zero and overwritten Map entry','repeated invocation with same input objects'],'scope':'Controlled generic JVM semantic tests, not original Train Ticket or a performance benchmark'})
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
