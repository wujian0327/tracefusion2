#!/usr/bin/env python3
"""Check real JVM numeric execution against independent literal source fields."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import HERE,save,load
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
from analysis_status import AnalysisLimit

def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    tools=HERE.parents[1]/'artifacts/call-lifecycle-revision-20261020/base-build/tools'
    cp=':'.join(map(str,[tools,*JARS]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'NumericKernelFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'NumericKernelFixture.root(LNumericKernelFixture$Input;LNumericKernelFixture$Input;)LNumericKernelFixture$Result;','targets':['NumericKernelFixture$Result.value'],'response_path':'/value','execution_kernel':True,'application_calls':True}})
    reports={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'NumericKernelFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);rows=[json.loads(x) for x in (cap/'fixture/events.jsonl').read_text().splitlines()];g=Reconstruction(b,cap,['fixture']);checks=[]
        for c in cases:
            assert c['response']==c['expected']
            a=g.query(c['message'],'/value','fixture',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);truth=set()
            for arg,field in [(0,'count'),(1,'rate')]:
                r=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==c['message'] and r.get('argument')==arg)
                f=next(f for f in r['fields'] if f['field']=='NumericKernelFixture$Input.'+field)
                truth.add((r['seq'],f['owner'],f['field'],f['version']))
            assert a['known'] and {(s['seq'],s['owner'],s['field'],s['version']) for s in a['sources']}==truth,(mode,c,a,truth)
            checks.append({'message':c['message'],'known_correct':True,'sources':sorted(truth)})
        # A valid capture with an intentionally reduced model cannot claim a
        # completed analysis. Nonfinite values also remain outside the model.
        plan=load(b/'fixture/plan.json');mutated=copy.deepcopy(rows)
        for r in mutated:
            if r['kind']=='binding-input' and r.get('argument')==1:
                for f in r['fields']:
                    if f['field'].endswith('.rate'):f['observed']['value']=float('inf')
            if r['kind']=='read' and r['field'].endswith('.rate'):r['observed']['value']=float('inf')
        try:infer_execution(plan,mutated)
        except AnalysisLimit:pass
        else:raise AssertionError('Nonfinite arithmetic received a definite answer')
        reports[mode]={'known_correct':len(checks),'tp':2*len(checks),'checks':checks,'nonfinite_analysis_limited':True}
    save(out/'results.json',{'all_passed':True,'modes':reports});print({k:v['known_correct'] for k,v in reports.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
