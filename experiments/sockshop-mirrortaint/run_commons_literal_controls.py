import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save
from run_query_planner import JARS,command
from build_distributed_plans import build
from plan_capability_policy import choose
from contract_applicability import library_inventory
from infer_execution_kernel import infer_execution

def run(out,agent,business):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();deps=out/'deps';deps.mkdir()
    with ZipFile(business)as z:
        for n in z.namelist():
            if n.startswith('BOOT-INF/lib/')and '/commons-lang3-'in n:(deps/Path(n).name).write_bytes(z.read(n))
    cp=':'.join(map(str,[classes,agent,*JARS,*deps.glob('*.jar')]));java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'CommonsLiteralFixture.java')],out/'compile.log');jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['CommonsLiteralFixture$Out.flag']}});model=load(b/'fixture/model.json');model['library_inventory']=library_inventory(business)
    plan,_=choose(model,{'entry':'CommonsLiteralFixture.root(LCommonsLiteralFixture$Store;I)LCommonsLiteralFixture$Out;','target':'CommonsLiteralFixture$Out.flag','path':'/flag','source_calls':['CommonsLiteralFixture$Store.read(I)LCommonsLiteralFixture$Source;']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'));save(out/'plan.json',plan);reports=[]
    for late in (False,True):
        base=json.loads(command([java,'-Dfixture.late='+str(late).lower(),'-cp',cp,'CommonsLiteralFixture'],out/('baseline-'+str(late)+'.log')).stdout.splitlines()[-1]);assert not any(r['alias_initialized']for r in base)
        for mode in ('full','selective'):
            d=out/(mode+'-'+str(late));d.mkdir();actual=json.loads(command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dfixture.late='+str(late).lower(),'-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'CommonsLiteralFixture'],d/'stdout.log').stdout.splitlines()[-1]);assert[{k:v for k,v in r.items()if k!='message'}for r in actual]==base
            rows=[json.loads(x)for x in(d/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows);result=infer_execution(plan,rows);checks=[]
            for case in actual:
                ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message']);answer=next(a for a in result['answers']if a['root_frame']==ret['frame']and a['path']=='/flag');known=case['case']not in (3,6,7)and not(late and case['case']==0);assert answer['known']==known,(late,mode,case['case'],answer)
                if known:
                    source=next(r for r in rows if r['kind']=='binding-source'and r['message']==case['message']);i=next(i for i,f in enumerate(source['fields'])if f['field']=='CommonsLiteralFixture$Source.text');assert answer['origins']==[['field',source['seq'],i]]
                checks.append({'case':case['case'],'known':known})
            guards=[]
            for fault in ('missing-init','duplicate-init','wrong-array','wrong-runtime','wrong-declaring'):
                changed=copy.deepcopy(rows);call=next(r for r in changed if r.get('commons_literal',{}).get('valid')and '.split('in r['commons_literal']['callee']);fact=call['commons_literal'];init=next(r for r in changed if r['seq']==fact['initialized_seq'])
                if fault=='missing-init':changed.remove(init)
                elif fault=='duplicate-init':changed.insert(changed.index(init),copy.deepcopy(init))
                elif fault=='wrong-array':fact['array']['elements']=[{'value':'WRONG'}]
                elif fault=='wrong-runtime':fact['runtime']['java_runtime_version']='wrong'
                else:fact['declaring']='wrong'
                try:infer_execution(plan,changed)
                except ValueError:guards.append(fault)
                else:assert late and fault=='wrong-array'  # first split ordinarily ineligible, later calls retain independent proofs
            reports.append({'mode':mode,'late_init':late,'business_and_callback_counts_equal':True,'alias_not_initialized':True,'checks':checks,'guards':guards})
    save(out/'results.json',reports);print(reports)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);p.add_argument('--business-jar',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.business_jar.resolve())
