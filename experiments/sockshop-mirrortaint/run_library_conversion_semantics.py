#!/usr/bin/env python3
"""Original JsonUtils binary; independent instance oracle and damaged evidence."""
import argparse,json,copy,shutil
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,save,load,sha
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution

def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/library-gap-revision-20261022/development-04/frozen-base'
    libraries=sorted((ROOT/'artifacts/library-gap-revision-20261022/control-libs').glob('*.jar'));cp=':'.join(map(str,[base/'tools',base/'basic/app',*JARS,*libraries]))
    command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'LibraryConversionFixture.java')],out/'compile.log')
    summary=Path('edu/fudan/common/util/JsonUtils.class');(classes/summary).parent.mkdir(parents=True);shutil.copyfile(base/'basic/app'/summary,classes/summary)
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.rglob('*.class'):z.write(f,'BOOT-INF/classes/'+str(f.relative_to(classes)))
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'LibraryConversionFixture.root(LLibraryConversionFixture$Input;LLibraryConversionFixture$Input;I)LLibraryConversionFixture$Box;','targets':['LibraryConversionFixture$Box.text'],'response_path':'/text','execution_kernel':True,'application_calls':True}})
    plan=load(b/'fixture/plan.json');reports={};want={0:0,1:1,2:1,3:(),4:None,5:(),6:0,7:None}
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,[*JARS,*libraries])),'LibraryConversionFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);rows=[json.loads(s)for s in (cap/'fixture/events.jsonl').open()];graph=Reconstruction(b,cap,['fixture']);checks=[]
        for c in cases:
            a=graph.query(c['message'],'/text','fixture',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);expected=want[c['mode']];assert a['known']==(expected is not None),(mode,c,a)
            if expected is not None:
                truth=set()
                if expected!=():
                    r=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==c['message'] and r['argument']==expected);f=next(f for f in r['fields']if f['field']=='LibraryConversionFixture$Input.text');truth={(r['seq'],f['owner'],f['field'],f['version'])}
                assert {(s['seq'],s['owner'],s['field'],s['version'])for s in a['sources']}==truth,(c,a,truth)
            checks.append({'mode':c['mode'],'known':a['known'],'expected_argument':expected})
        faults={}
        for name in ('missing-conversion','call-instance','source-object','output-object','field-version','source-pointer','wrong-class-hash','missing-birth'):
            altered=copy.deepcopy(rows);conversion=next(r for r in altered if r['kind']=='json-conversion' and r.get('conversion_contract',{}).get('valid'))
            if name=='missing-conversion':altered.remove(conversion)
            elif name=='call-instance':conversion['conversion_contract']['call_id']=-1
            elif name=='source-object':conversion['conversion_contract']['source']['object']='same-value-wrong-source'
            elif name=='output-object':conversion['conversion_contract']['target']['object']='same-value-wrong-target'
            elif name=='field-version':conversion['output'][0]['version']+=1
            elif name=='source-pointer':conversion['input'][0]['path']='/wrong'
            elif name=='wrong-class-hash':conversion['conversion_contract']['summary_class_sha256']['edu/fudan/common/util/JsonUtils']='wrong'
            else:altered.remove(next(r for r in altered if r['kind']=='execution-decoder-birth'))
            try:infer_execution(plan,altered)
            except ValueError:faults[name]=True
            else:raise AssertionError('Bad conversion evidence accepted: '+name)
        reports[mode]={'targets':len(checks),'known_exact':sum(c['known']for c in checks),'expected_unknown':sum(not c['known']for c in checks),'faults':faults,'checks':checks}
        save(out/'results.json',{'all_passed':True,'modes':reports,'original_JsonUtils_class_sha256':sha(classes/summary)});print(mode,{k:v for k,v in reports[mode].items()if k!='checks'},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
