#!/usr/bin/env python3
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,save,load
from infer_distributed_fields import Reconstruction
from infer_uuid_projection import validate_uuid_projection

def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();tools=ROOT/'artifacts/library-gap-revision-20261022/development-06/frozen-base/tools';cp=':'.join(map(str,[tools,*JARS]));command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'UuidProjectionFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'UuidProjectionFixture.root(LUuidProjectionFixture$Box;LUuidProjectionFixture$Box;I)LUuidProjectionFixture$Box;','targets':['UuidProjectionFixture$Box.id'],'response_path':'/id','execution_kernel':True,'application_calls':True}})
    expected={0:0,1:1,2:1,3:1,4:(),5:None,6:None,7:1,8:1};reports={};plan=load(b/'fixture/plan.json')
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'UuidProjectionFixture'],cap/'stdout.json');rows=[json.loads(s)for s in (cap/'fixture/events.jsonl').open()];cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);graph=Reconstruction(b,cap,['fixture']);checks=[]
        for c in cases:
            if c['status']!='normal':continue
            answer=graph.query(c['message'],'/id','fixture',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);want=expected[c['mode']];assert answer['known']==(want is not None),(mode,c,answer)
            if want is not None:
                truth=set()
                if want!=():
                    r=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==c['message'] and r['argument']==want);f=next(f for f in r['fields']if f['field']=='UuidProjectionFixture$Box.id');truth={(r['seq'],f['owner'],f['field'],f['version'])}
                assert {(s['seq'],s['owner'],s['field'],s['version'])for s in answer['sources']}==truth
            checks.append({'mode':c['mode'],'known':answer['known']})
        faults={}
        for label in ['missing-runtime','runtime-hash','missing-wire','serializer-hash','wire-object','malformed-value']:
            altered=copy.deepcopy(rows)
            if label=='missing-runtime':altered.remove(next(r for r in altered if r['kind']=='uuid-runtime'))
            elif label=='runtime-hash':next(r for r in altered if r['kind']=='uuid-runtime')['class_sha256']['java/util/UUID']='bad'
            elif label=='missing-wire':altered.remove(next(r for r in altered if r['kind']=='uuid-wire'))
            elif label=='serializer-hash':next(r for r in altered if r['kind']=='uuid-wire')['serializer_class_sha256']='bad'
            elif label=='wire-object':next(r for r in altered if r['kind']=='uuid-wire')['observed']['object']='same-value-wrong-object'
            else:next(r for r in altered if r['kind']=='uuid-wire')['observed']['value']='not-a-uuid'
            try:validate_uuid_projection(plan,altered)
            except ValueError:faults[label]=True
            else:raise AssertionError('Damaged UUID evidence accepted: '+label)
        reports[mode]={'targets':len(checks),'known_exact':sum(c['known']for c in checks),'expected_unknown':sum(not c['known']for c in checks),'custom_serializer_refused':sum(c['status']=='serialization-refused'for c in cases),'faults':faults};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,reports[mode],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
