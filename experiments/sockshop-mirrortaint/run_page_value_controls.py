import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_query_planner import JARS,command
from run_planned_service import ROOT,HERE,load,save
from build_distributed_plans import build
from infer_execution_kernel import infer_execution

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();deps=list((ROOT/'artifacts/zlt-completion-slice-20261031/review/zlt-user/deps').glob('mybatis-plus-*.jar'));agent=ROOT/'artifacts/zlt-completion-slice-20261031/model-build-02/distributed-observer.jar';cp=':'.join(map(str,[agent,*deps,*JARS]));java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
 command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'PageValueFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
  for p in deps:z.write(p,'BOOT-INF/lib/'+p.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'PageValueFixture.root(I)LPageValueFixture$Result;','targets':['PageValueFixture$Row.text'],'response_path':'/data/*/text','execution_kernel':True,'application_calls':True,'source_calls':['PageValueFixture$Store.read(Lcom/baomidou/mybatisplus/extension/plugins/pagination/Page;)Ljava/util/List;'],'bytecode_dependencies':['com/baomidou/mybatisplus/extension/plugins/pagination/Page','com/baomidou/mybatisplus/core/metadata/IPage']}});plan=load(b/'fixture/plan.json');cp=str(classes)+':'+str(b/'distributed-observer.jar')+':'+':'.join(map(str,[*deps,*JARS]));expected=json.loads(command([java,'-cp',cp,'PageValueFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
 for mode in('full','selective'):
  cap=out/mode;cap.mkdir();value=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'PageValueFixture'],cap/'stdout.log');assert json.loads(value.stdout.splitlines()[-1])==expected;rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem'];answers=infer_execution(plan,rows)['answers'];assert len(answers)==2 and all(a['known']for a in answers),answers
  for a in answers:
   root=next(r for r in rows if r['kind']=='enter'and r['frame']==a['root_frame']);source=next(r for r in rows if r['kind']=='binding-source'and r['frame']==root['frame']);i=next(i for i,f in enumerate(source['fields'])if f['field']=='PageValueFixture$Row.text');assert set(map(tuple,a['origins']))=={('field',source['seq'],i)}
  guards={}
  for fault in('missing-Long-proof','wrong-Long-value','wrong-Page-write'):
   bad=copy.deepcopy(rows)
   if fault=='missing-Long-proof':next(r for r in bad if r.get('sequence_value')and r['sequence_value']['callee'].startswith('java/lang/Long.')).pop('sequence_value')
   elif fault=='wrong-Long-value':next(r for r in bad if r.get('sequence_value')and r['sequence_value']['callee'].startswith('java/lang/Long.'))['result']['value']=-1
   else:next(r for r in bad if r['kind']=='write'and r.get('field','').endswith('.records'))['version']+=1
   try:infer_execution(plan,bad)
   except ValueError:guards[fault]=True
   else:raise AssertionError(fault)
  reports[mode]={'business_equal':True,'source_targets':2,'known_correct':2,'real_Page_total_changed':True,'guards':guards}
 save(out/'results.json',reports);print(reports)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
