#!/usr/bin/env python3
"""Unknown mutable constructor effects are unknown, never invented evidence errors."""
import argparse,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from infer_distributed_fields import Reconstruction
import run_response_binding_revision as old

def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/call-lifecycle-revision-20261020/base-build';command(['javac',*java8_target()[1],'-cp',':'.join(map(str,[base/'tools',*JARS])),'-d',str(classes),str(HERE/'OpaqueDateConstructorFixture.java')],out/'compile.log');jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'OpaqueDateConstructorFixture.root(Ljava/util/Date;I)LOpaqueDateConstructorFixture$Out;','targets':['OpaqueDateConstructorFixture$Out.date'],'response_path':'/date','execution_kernel':True,'application_calls':True}});reports={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'OpaqueDateConstructorFixture'],cap/'stdout.json');cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);g=Reconstruction(b,cap,['fixture']);checks=[]
        for c in cases:
            if c['status']=='aborted':continue
            a=g.query(c['message'],'/date','fixture',boundary=old.BOUNDARY);want=c['mode'] in (0,2);assert a['known']==want,(mode,c,a)
            if want:assert len(a['sources'])==1 and a['sources'][0]['field']=='@argument:0' and a['sources'][0]['observed']['date_epoch_ms']==1000
            checks.append({'case':c,'expected_known':want,'answer':a})
        reports[mode]={'targets':len(checks),'known_exact':sum(c['answer']['known'] for c in checks),'expected_unknown':sum(not c['answer']['known'] for c in checks),'aborted':sum(c['status']=='aborted' for c in cases),'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
