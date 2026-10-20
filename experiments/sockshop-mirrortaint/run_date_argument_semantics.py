#!/usr/bin/env python3
"""Root Date and epoch arguments are actual boundary sources, never constants."""
import argparse,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from infer_distributed_fields import Reconstruction
import run_response_binding_revision as old

def run(out,allow_failure=False,forward=False):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/ticketinfo-wrapper-revision-20261020/final-base-build'
    command(['javac',*java8_target()[1],'-cp',':'.join(map(str,[base/'tools',*JARS])),'-d',str(classes),str(HERE/'DateProjectionFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    entry='DateProjectionFixture.forward(LDateProjectionFixture$Out;I)LDateProjectionFixture$Out;' if forward else 'DateProjectionFixture.direct(Ljava/util/Date;JZ)LDateProjectionFixture$Out;'
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':entry,'targets':['DateProjectionFixture$Out.date'],'response_path':'/date','execution_kernel':not forward,'application_calls':not forward}});reports={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'DateProjectionFixture','forward' if forward else 'direct'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);g=Reconstruction(b,cap,['fixture']);checks=[]
        for c in cases:
            try:
                a=g.query(c['message'],'/date','fixture',boundary=old.BOUNDARY)
                if forward:
                    assert a['known']==(c['mode']==0),(c,a)
                    if a['known']:
                        source=next(r for r in g.rows['fixture'] if r['kind']=='binding-input' and r.get('message')==c['message'] and r['argument']==0);field=next(f for f in source['fields'] if f['path']=='/date');assert {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('fixture',source,field)}
                else:assert a['known'] and len(a['sources'])==1 and a['sources'][0]['kind']=='argument' and a['sources'][0]['field']=='@argument:'+str(c['argument']),(c,a)
                checks.append({'case':c,'status':'correct','answer':a})
            except (ValueError,AssertionError) as error:
                if not allow_failure:raise
                checks.append({'case':c,'status':'failed','error':str(error)})
        reports[mode]={'targets':len(checks),'correct':sum(c['status']=='correct' for c in checks),'known_correct':sum(c.get('answer',{}).get('known',False) for c in checks),'expected_unknown':sum(c.get('answer') is not None and not c['answer']['known'] for c in checks),'checks':checks};save(out/'results.json',{'all_passed':all(r['targets']==r['correct'] for r in reports.values()),'modes':reports,'scope':'Expected-state guards include unknown; correct is not an overall provenance accuracy.'});print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--allow-failure',action='store_true');p.add_argument('--forward',action='store_true');a=p.parse_args();run(a.out.resolve(),a.allow_failure,a.forward)
