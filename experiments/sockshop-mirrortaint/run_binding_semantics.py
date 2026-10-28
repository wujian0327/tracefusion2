#!/usr/bin/env python3
"""Real JVM/serializer controls with independent source-position expectations."""
import argparse
import copy
import json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import HERE,save,load
from infer_distributed_fields import Reconstruction


def run(out,base,only=None,mode='selective'):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    _,target=java8_target();cp=':'.join(map(str,[base/'tools',*JARS]))
    command(['javac',*target,'-cp',cp,'-d',str(classes),str(HERE/'BindingSemanticFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    cases={
      'direct':('direct(LBindingSemanticFixture$Input;)LBindingSemanticFixture$Input;','BindingSemanticFixture$Input.text','/text'),
      'nested':('nested(LBindingSemanticFixture$Input;)LBindingSemanticFixture$Box;','BindingSemanticFixture$Input.text','/data/text'),
      'choose':('choose(LBindingSemanticFixture$Input;LBindingSemanticFixture$Input;Z)LBindingSemanticFixture$Box;','BindingSemanticFixture$Input.text','/data/text'),
      'opaque':('opaque(LBindingSemanticFixture$Input;)LBindingSemanticFixture$Input;','BindingSemanticFixture$Input.text','/text'),
      'overwrite':('overwrite(LBindingSemanticFixture$Input;)LBindingSemanticFixture$Input;','BindingSemanticFixture$Input.text','/text'),
      'map':('map(LBindingSemanticFixture$Input;)LBindingSemanticFixture$Box;','BindingSemanticFixture$Box.data','/data/k'),
      'constant':('constant(LBindingSemanticFixture$Input;)LBindingSemanticFixture$Output;','BindingSemanticFixture$Output.flag','/flag'),
      'overwrite-flag':('overwriteFlag(LBindingSemanticFixture$Input;)LBindingSemanticFixture$Output;','BindingSemanticFixture$Output.flag','/flag'),
      'catch-unused':('catchUnused(LBindingSemanticFixture$Input;Z)LBindingSemanticFixture$Output;','BindingSemanticFixture$Output.flag','/flag')}
    result={}
    for name,(method,field,path) in cases.items():
        if only and name!=only:continue
        dest=out/name;dest.mkdir();config={'fixture':{'jar':str(jar),'entry':'BindingSemanticFixture.'+method,'targets':[field],'response_path':path}}
        build(dest/'build',config);capture=dest/'capture';(capture/'fixture').mkdir(parents=True)
        log=capture/'fixture/events.jsonl'
        command(['java','-javaagent:'+str(dest/'build/distributed-observer.jar'),'-Dservice.plan='+str(dest/'build/fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(log),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'BindingSemanticFixture',name],dest/'stdout.log')
        rows=[json.loads(x) for x in log.read_text().splitlines()]
        assert not any(r['kind']=='problem' for r in rows)
        graph=Reconstruction(dest/'build',capture,['fixture']);wires=[r for r in rows if r['kind']=='http-json'];checks=[]
        for i,wire in enumerate(wires):
            answer=graph.query(wire['message'],path,'fixture')
            assert answer['known']==(name!='opaque'),(name,answer)
            expected=[]
            if name not in ('constant','overwrite','overwrite-flag','catch-unused','opaque'):
                arg=0 if name!='choose' or i%2==0 else 1
                source=next(r for r in rows if r['kind']=='binding-input' and r['message']==wire['message'] and r['argument']==arg)
                expected=[f for f in source['fields'] if f['field']==('@map:k' if name=='map' else 'BindingSemanticFixture$Input.text')]
                assert len(expected)==1
            wanted={(f['owner'],f['field'],f['version']) for f in expected}
            actual={(s['owner'],s['field'],s['version']) for s in answer['sources']}
            assert actual==wanted,(name,actual,wanted)
            checks.append({'message':wire['message'],'known':answer['known'],'expected_sources':sorted(wanted),'predicted_sources':sorted(actual)})
        assert len(checks)==6
        negatives={}
        if name=='nested':
            custom=capture/'custom';custom.mkdir()
            result_custom=command(['java','-javaagent:'+str(dest/'build/distributed-observer.jar'),'-Dservice.plan='+str(dest/'build/fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(custom/'events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'BindingSemanticFixture','custom-serializer'],dest/'custom-serializer.log')
            assert 'CUSTOM_SERIALIZER_BUSINESS_UNCHANGED' in result_custom.stdout
            custom_rows=[json.loads(x)for x in(custom/'events.jsonl').read_text().splitlines()]
            assert any(r['kind']=='problem'for r in custom_rows) and custom_rows[-1]['capture_invalid']
            try:Reconstruction(dest/'build',custom,['fixture'],decoded_rows={'fixture':custom_rows})
            except ValueError as e:assert str(e)=='Collector problem'
            else:raise AssertionError('Custom serializer capture incorrectly certified')
            negatives['custom-equal-value-serializer']='business unchanged; failed capture refused'
            for mutation in ('missing-return','missing-input','ambiguous-return','wrong-return-owner','ambiguous-message'):
                bad=copy.deepcopy(rows)
                if mutation=='missing-return':bad=[r for r in bad if r['kind']!='binding-return']
                if mutation=='missing-input':bad=[r for r in bad if r['kind']!='binding-input']
                if mutation=='ambiguous-return':
                    position=next(i for i,r in enumerate(bad) if r['kind']=='binding-return')
                    bad.insert(position+1,copy.deepcopy(bad[position]))
                if mutation=='wrong-return-owner':
                    for r in bad:
                        if r['kind']=='binding-return':r['fields'][0]['owner']='not-the-returned-field'
                if mutation=='ambiguous-message':bad.insert(-1,copy.deepcopy(wires[0]))
                for seq,r in enumerate(bad,1):r['seq']=seq
                try:
                    broken=Reconstruction(dest/'build',capture,['fixture'],decoded_rows={'fixture':bad})
                    assert not broken.query(wires[0]['message'],path,'fixture')['known'],mutation
                except ValueError:pass
                negatives[mutation]='rejected or unknown'
        result[name]={'queries':6,'known':sum(c['known'] for c in checks),'checks':checks,'negative_controls':negatives}
        save(dest/'checks.json',result[name])
    save(out/'results.json',{'all_passed':True,'cases':result,'scope':'Standalone JVM controls with actual Jackson serialization and explicit W3C fixture contexts; not application HTTP runs or performance results.'})
    print({k:v['known'] for k,v in result.items()},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--only');p.add_argument('--mode',choices=('full','selective'),default='selective');a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.only,a.mode)
