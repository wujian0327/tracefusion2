#!/usr/bin/env python3
"""Actual-JVM read-effect checks and independently enumerated argument origins."""
import argparse,copy,json,subprocess
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import HERE,ROOT,load,save,sha
from infer_distributed_fields import Reconstruction


def run(out,base):
    out.mkdir();classes=out/'classes';classes.mkdir();target=java8_target()[1];cp=':'.join(map(str,[base/'tools',*JARS]))
    command(['javac',*target,'-cp',cp,'-d',str(classes),str(HERE/'ReadForwardFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    runtime=subprocess.check_output(['java','-cp',str(base/'tools'),'JdkContractProbe'],text=True)
    values=dict(l.split('=',1) for l in runtime.splitlines() if '='in l);profile={'java_runtime_version':values.pop('java.runtime.version'),'class_sha256':values}
    results={};cases={'forward':'forward(Ljava/util/List;Ljava/util/List;Z)LReadForwardFixture$Item;',
        'repeated':'repeated(Ljava/util/List;Ljava/util/List;)LReadForwardFixture$Item;',
        'overlap':'forward(Ljava/util/List;Ljava/util/List;Z)LReadForwardFixture$Item;',
        'empty':'forward(Ljava/util/List;Ljava/util/List;Z)LReadForwardFixture$Item;',
        'custom-list':'forward(Ljava/util/List;Ljava/util/List;Z)LReadForwardFixture$Item;',
        'opaque':'opaque(LReadForwardFixture$Item;)LReadForwardFixture$Item;',
        'async':'async(LReadForwardFixture$Item;)LReadForwardFixture$Item;',
        'constructor':'constructor(LReadForwardFixture$Item;)LReadForwardFixture$Item;',
        'overwritten':'overwritten(LReadForwardFixture$Item;)LReadForwardFixture$Item;'}
    for name,method in cases.items():
        d=out/name;d.mkdir();b=d/'build'
        build(b,{'fixture':{'jar':str(jar),'entry':'ReadForwardFixture.'+method,'targets':['ReadForwardFixture$Item.text'],'response_path':'/text','read_forward_contracts':True}})
        p=load(b/'fixture/plan.json')
        if 'read_forward_contracts' in p:p['read_forward_contracts']['runtime_profiles'].append({**profile,'scope':'Standalone test JVM only; not an application runtime admission.'})
        save(b/'fixture/plan.json',p)
        manifest=load(b/'build.json');manifest['inputs']['fixture']['plan_sha256']=sha(b/'fixture/plan.json');save(b/'build.json',manifest)
        mode_results={}
        for mode in ('full','selective'):
            cap=d/mode;(cap/'fixture').mkdir(parents=True)
            cmd=['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'ReadForwardFixture',name]
            if name=='custom-list':
                proc=subprocess.run(cmd,text=True,capture_output=True);(d/(mode+'.stdout')).write_text(proc.stdout+proc.stderr)
            else:command(cmd,d/(mode+'.stdout'))
            rows=[json.loads(x) for x in (cap/'fixture/events.jsonl').read_text().splitlines()]
            if name=='custom-list':
                assert any(r['kind']=='problem' for r in rows),'Custom List not refused';mode_results[mode]={'refused':True};continue
            assert not any(r['kind']=='problem' for r in rows),name
            graph=Reconstruction(b,cap,['fixture']);wires=[r for r in rows if r['kind']=='http-json'];checks=[]
            for i,w in enumerate(wires):
                answer=graph.query(w['message'],'/text','fixture');expected_known=name in ('forward','repeated','overwritten')
                assert answer['known']==expected_known,(name,answer)
                if name=='overwritten':assert not answer['sources'],'Same-value constant write inherited old source'
                elif expected_known:
                    arg=(0 if i%2==0 else 1) if name=='forward' else 1
                    source=next(r for r in rows if r['kind']=='binding-input' and r['message']==w['message'] and r['argument']==arg)
                    wanted={(f['owner'],f['field'],f['version']) for f in source['fields'] if f['path']=='/0/text'}
                    actual={(f['owner'],f['field'],f['version']) for f in answer['sources']};assert len(wanted)==1 and actual==wanted,(name,wanted,actual)
                checks.append({'message':w['message'],'known':answer['known'],'sources':answer['sources']})
            assert len(checks)==6
            faults={}
            if name=='forward':
                for fault in ('missing-runtime','missing-call-enter','missing-call-exit','missing-summary','wrong-selected-object','missing-source','ambiguous-message'):
                    broken=copy.deepcopy(rows)
                    kind={'missing-runtime':'binding-call-runtime','missing-call-enter':'binding-call-enter','missing-call-exit':'binding-call-exit','missing-summary':'binding-call-summary','missing-source':'binding-input'}.get(fault)
                    if kind:
                        at=next(i for i,r in enumerate(broken) if r['kind']==kind);broken.pop(at)
                    elif fault=='wrong-selected-object':
                        next(r for r in broken if r['kind']=='binding-call-exit' and r['mode']=='stream-first')['detail']['selected_object']='same-value-other-object'
                    else:broken.insert(-1,copy.deepcopy(wires[0]))
                    for seq,r in enumerate(broken,1):r['seq']=seq
                    try:
                        g=Reconstruction(b,cap,['fixture'],decoded_rows={'fixture':broken});assert not g.query(wires[0]['message'],'/text','fixture')['known'],fault
                    except ValueError:pass
                    faults[fault]='refused or unknown'
            mode_results[mode]={'queries':6,'known':sum(c['known'] for c in checks),'checks':checks,'faults':faults}
        results[name]=mode_results;save(out/'results.json',{'all_passed':True,'scope':'Standalone semantic controls, not application or performance evidence.','cases':results})
        print(name,{m:r.get('known',r) for m,r in mode_results.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.base.resolve())
