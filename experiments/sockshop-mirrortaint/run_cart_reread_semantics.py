#!/usr/bin/env python3
"""Actual JVM allocation/cyclic-call evidence; independent source-read oracle."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,save,load
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
from analysis_status import AnalysisLimit,failure_status
import run_response_binding_revision as old

def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/call-lifecycle-revision-20261020/base-build'
    command(['javac',*java8_target()[1],'-cp',':'.join(map(str,[base/'tools',*JARS])),'-d',str(classes),str(HERE/'CartRereadFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'CartRereadFixture.root(LCartRereadFixture$Item;LCartRereadFixture$Repo;I)LCartRereadFixture$Item;','targets':['CartRereadFixture$Item.text'],'response_path':'/text','source_calls':['CartRereadFixture$Repo.read(LCartRereadFixture$Item;I)LCartRereadFixture$Item;'],'execution_kernel':True,'application_calls':True}})
    p=load(b/'fixture/plan.json');reports={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'CartRereadFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);g=Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];checks=[]
        for c in cases:
            a=g.query(c['message'],'/text','fixture',boundary=old.BOUNDARY);known=c['mode'] in (0,4,6,7);assert a['known']==known,(mode,c,a)
            if known:
                expected=set()
                if c['mode']!=7:
                    source=next(r for r in rows if r['kind']=='binding-source' and r.get('message')==c['message']);f=next(f for f in source['fields'] if f['field']=='CartRereadFixture$Item.text');expected={old.source_coord('fixture',source,f)}
                assert {old.predicted_coord(s) for s in a['sources']}==expected
            checks.append({'case':c,'expected_known':known,'answer':a})
        faults={}
        target=next(c for c in cases if c['mode']==0)
        ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==target['message']);owner=next(f for f in ret['fields'] if f['path']=='/text')['owner']
        for label in ('missing-birth','wrong-birth-owner','wrong-birth-hash','duplicate-birth','wrong-cycle-argument','missing-cycle-return'):
            changed=copy.deepcopy(rows);birth=next(r for r in changed if r['kind']=='execution-object-birth' and r['object']==owner)
            if label=='missing-birth':changed.remove(birth)
            elif label=='wrong-birth-owner':birth['object']='same-value-wrong-object'
            elif label=='wrong-birth-hash':birth['class_sha256']='wrong'
            elif label=='duplicate-birth':changed.insert(changed.index(birth)+1,dict(birth))
            elif label=='wrong-cycle-argument':next(r for r in changed if r['kind']=='enter' and '.cycle(' in r['method'])['args'][0]['object']='wrong-object'
            else:
                frame=next(r['frame'] for r in changed if r['kind']=='enter' and '.cycle(' in r['method']);changed.remove(next(r for r in changed if r['kind']=='exit' and r.get('frame')==frame))
            try:
                answers=infer_execution(p,changed)['answers']
                assert label=='missing-birth' and not next(a for a in answers if a['seq']==ret['seq'] and a['path']=='/text')['known'],label
                faults[label]='unknown'
            except ValueError:faults[label]='refused'
        limited=copy.deepcopy(p);limited['execution_kernel']['call_depth_limit']=2
        try:infer_execution(limited,rows)
        except AnalysisLimit as e:assert failure_status(e)=='analysis_limited'
        else:raise AssertionError('Call depth limit ignored')
        reports[mode]={'targets':16,'known_exact':8,'expected_unknown':8,'faults':faults,'depth_status':'analysis_limited','checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,'8 known exact / 8 conservative unknown',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
