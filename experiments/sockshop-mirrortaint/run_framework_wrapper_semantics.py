#!/usr/bin/env python3
"""Actual pinned Spring HTTP wrapper controls with independent target-source oracle."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,save,load,sha
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution

def run(out):
    out.mkdir(parents=True,exist_ok=False);libs=out/'libs';libs.mkdir();original=ROOT/'artifacts/constructor-effect-revision-20261020/business-frozen-base-build/ticketinfo/original.jar'
    with ZipFile(original) as z:
        for name in z.namelist():
            if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):(libs/Path(name).name).write_bytes(z.read(name))
    classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/ticketinfo-wrapper-revision-20261020/development-base-build';cp=':'.join(map(str,[base/'tools',*JARS,*sorted(libs.glob('*.jar'))]))
    command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'FrameworkWrapperFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'FrameworkWrapperFixture.root(LFrameworkWrapperFixture$Input;Ljava/lang/String;I)LFrameworkWrapperFixture$Reply;','targets':['FrameworkWrapperFixture$Reply.data'],'response_path':'/data/text','execution_kernel':True,'application_calls':True}})
    plan=load(b/'fixture/plan.json');reports={}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True)
        command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+cp,'FrameworkWrapperFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);rows=[json.loads(s) for s in (cap/'fixture/events.jsonl').read_text().splitlines()];graph=Reconstruction(b,cap,['fixture']);checks=[]
        for case in cases:
            if case['status']=='aborted' or case['mode']==6:continue
            answer=graph.query(case['message'],'/data/text','fixture',boundary=[{'kind':'http-json','phase':'read','direction':'response'}]);known=case['mode'] in (0,1,7);assert answer['known']==known,(case,answer)
            reads=[r for r in rows if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and r.get('parent_message')==case['message']]
            if known:
                assert len(reads)==(2 if case['mode']==1 else 1);source=reads[-1];field=next(f for f in source['fields'] if f['path']=='/data/text')
                expected={(source['message'],source['seq'],field['owner'],field['field'],field['version'])};actual={(s['message'],s['seq'],s['owner'],s['field'],s['version']) for s in answer['sources']};assert actual==expected,(case,answer,expected)
            checks.append({'case':case,'known':known,'answer':answer})
        faults={}
        for label in ('missing-class-literal','wrong-class-literal','wrong-class-hash','missing-entity-witness','wrong-entity-body','wrong-library-hash','wrong-rpc-body','changed-rpc-fields','wrong-rpc-parent','missing-rpc-read','ambiguous-rpc-read','wrong-getbody-result'):
            altered=copy.deepcopy(rows);event=next(r for r in altered if r['kind']=='execution-class-literal');ctor=next(r for r in altered if r['kind']=='execution-constructed' and r.get('framework_contract',{}).get('kind')=='http-entity-null-headers');ret=next(r for r in altered if r['kind']=='collection-call-exit' and r.get('framework_contract',{}).get('kind')=='rest-exchange');read=next(r for r in altered if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response')
            if label=='missing-class-literal':altered.remove(event)
            elif label=='wrong-class-literal':event['descriptor']='Ljava/lang/Object;'
            elif label=='wrong-class-hash':event['class_sha256']='bad'
            elif label=='missing-entity-witness':ctor.pop('framework_contract')
            elif label=='wrong-entity-body':ctor['framework_contract']['body']['object']='another-same-value-input'
            elif label=='wrong-library-hash':ret['framework_contract']['class_sha256']={}
            elif label=='wrong-rpc-body':ret['framework_contract']['body']['object']='another-same-value-response'
            elif label=='changed-rpc-fields':ret['framework_contract']['fields'][0]['version']+=1
            elif label=='wrong-rpc-parent':read['parent_message']='wrong-request'
            elif label=='missing-rpc-read':altered.remove(read)
            elif label=='ambiguous-rpc-read':altered.insert(altered.index(read),copy.deepcopy(read))
            elif label=='wrong-getbody-result':next(r for r in altered if r.get('framework_contract',{}).get('kind')=='http-entity-body')['framework_contract']['body']['object']='wrong-body'
            try:infer_execution(plan,altered)
            except (ValueError,KeyError):faults[label]=True
            else:raise AssertionError('Bad framework evidence accepted: '+label)
        reports[mode]={'targets':len(checks),'known':sum(c['known'] for c in checks),'expected_unknown':sum(not c['known'] for c in checks),'aborted':sum(c['status']=='aborted' for c in cases),'N/A_requests':sum(c['mode']==6 for c in cases),'faults':faults,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
