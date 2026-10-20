#!/usr/bin/env python3
"""Actual Date/Jackson controls, independent source-position and ISO/epoch oracle."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
from infer_date_projection import validate_date_serialization
import run_response_binding_revision as old

def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/ticketinfo-wrapper-revision-20261020/final-base-build'
    command(['javac',*java8_target()[1],'-cp',':'.join(map(str,[base/'tools',*JARS])),'-d',str(classes),str(HERE/'DateProjectionFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'DateProjectionFixture.root(LDateProjectionFixture$Input;LDateProjectionFixture$Input;I)LDateProjectionFixture$Out;','targets':['DateProjectionFixture$Out.date'],'response_path':'/date','execution_kernel':True,'application_calls':True}})
    plan=load(b/'fixture/plan.json');reports={};expected={0:(0,'date'),1:(1,'date'),2:(0,'millis'),3:(),4:(),5:(0,'date'),6:(0,'date'),7:None,8:None,9:None,10:None,11:(1,'millis'),13:(),14:(),15:None,16:()}
    for mode in ('full','selective'):
        for encoding in ('iso','timestamp'):
            cap=out/(mode+'-'+encoding);(cap/'fixture').mkdir(parents=True)
            command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'DateProjectionFixture',*(['timestamp'] if encoding=='timestamp' else [])],cap/'stdout.json')
            cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);g=Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];checks=[]
            for case in cases:
                if case['status']=='aborted':continue
                want=expected[case['mode']];a=g.query(case['message'],'/date','fixture',boundary=old.BOUNDARY);assert a['known']==(want is not None),(case,a)
                if want is not None:
                    truth=set()
                    if want:
                        source=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==case['message'] and r['argument']==want[0]);f=next(f for f in source['fields'] if f['field']=='DateProjectionFixture$Input.'+want[1]);truth={old.source_coord('fixture',source,f)}
                    assert {old.predicted_coord(s) for s in a['sources']}==truth,(case,a,truth)
                if case['response']['date'] is not None:assert a['target']['wire_value']==case['response']['date']
                if case['mode'] in (3,4):
                    root=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']);assert next(v for v in g.local_queries['fixture']['roots'] if v['frame']==root['frame'])['environment_facts']
                checks.append({'case':case,'known':a['known'],'expected':want,'answer':a})
            faults={}
            for label in ('runtime-hash','missing-runtime','date-input-object','date-input-epoch','missing-clock','calendar-provider','serialization-object','serialization-epoch','serialization-library','wire-value','missing-serialization'):
                bad=copy.deepcopy(rows)
                if label=='runtime-hash':next(r for r in bad if r['kind']=='date-runtime')['class_sha256']={}
                elif label=='missing-runtime':bad.remove(next(r for r in bad if r['kind']=='date-runtime'))
                elif label.startswith('date-input'):
                    f=next(f for r in bad if r['kind']=='binding-input' for f in r['fields'] if f['field'].endswith('.date'))
                    if label=='date-input-object':f['observed']['object']='same-time-other-date'
                    else:f['observed']['date_epoch_ms']+=1
                elif label=='missing-clock':next(r for r in bad if r['kind']=='collection-call-exit' and r.get('date_contract',{}).get('kind')=='calendar-environment').pop('date_contract')
                elif label=='calendar-provider':next(r for r in bad if r['kind']=='collection-call-exit' and r.get('date_contract',{}).get('kind')=='calendar-environment')['date_contract']['provider_type']='unmodeled-provider'
                else:
                    proof=next(r for r in bad if r['kind']=='date-serialization')
                    if label=='serialization-object':proof['date']['object']='wrong-same-time-date'
                    elif label=='serialization-epoch':proof['date']['date_epoch_ms']+=1
                    elif label=='serialization-library':proof['class_sha256']={}
                    elif label=='wire-value':proof['wire_value']='1970-01-01T00:00:00.000+0000'
                    else:bad.remove(proof)
                try:
                    validate_date_serialization(plan,bad);infer_execution(plan,bad)
                except (ValueError,KeyError):faults[label]=True
                else:raise AssertionError('Date evidence not protected: '+label)
            reports[mode+'-'+encoding]={'targets':len(checks),'known':sum(c['known'] for c in checks),'expected_unknown':sum(not c['known'] for c in checks),'root_aborts':sum(c['status']=='aborted' for c in cases),'faults':faults,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,encoding,{k:v for k,v in reports[mode+'-'+encoding].items() if k!='checks'},flush=True)
    refused={}
    for kind in ('custom-serializer','custom-format'):
        cap=out/kind;(cap/'fixture').mkdir(parents=True);r=command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode=selective','-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'DateProjectionFixture',kind],cap/'stdout.log');assert 'DATE_SERIALIZER_REJECTED=' in r.stdout;refused[kind]=True
    save(out/'results.json',{'all_passed':True,'modes':reports,'custom_serialization_refused':refused})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
