import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from build_distributed_plans import build
from infer_execution_kernel import infer_execution
from plan_capability_policy import choose

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';agent=ROOT/'artifacts/zlt-completion-slice-20261031/page-controls-01/build/distributed-observer.jar';cp=':'.join(map(str,[agent,*JARS]));command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'SequenceCallbackFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('SequenceCallbackFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
 b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['SequenceCallbackFixture$Row.text']}});model=load(b/'fixture/model.json');plan,route=choose(model,{'entry':'SequenceCallbackFixture.root(I)LSequenceCallbackFixture$Result;','target':'SequenceCallbackFixture$Row.text','path':'/rows/*/text','source_calls':['SequenceCallbackFixture$Store.read()Ljava/util/List;']});save(b/'fixture/plan.json',plan);save(out/'route.json',route);cp=str(classes)+':'+str(b/'distributed-observer.jar')+':'+':'.join(map(str,JARS));baseline=json.loads(command([java,'-cp',cp,'SequenceCallbackFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
 for mode in('full','selective'):
  cap=out/mode;cap.mkdir();observed=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'SequenceCallbackFixture'],cap/'stdout.log');assert json.loads(observed.stdout.splitlines()[-1])==baseline;rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem'];a=infer_execution(plan,rows)['answers'];assert len(a)==4 and all(x['known']for x in a),a
  for answer in a:
   source=next(r for r in rows if r['kind']=='binding-source'and r['frame']==answer['root_frame']or r['kind']=='binding-source'and r.get('message')==next(e['message']for e in rows if e['kind']=='binding-return'and e['frame']==answer['root_frame']));index=int(answer['path'].split('/')[2]);selected=[(i,f)for i,f in enumerate(source['fields'])if f['path']=='/'+str(index)+'/text'];assert len(selected)==1 and set(map(tuple,answer['origins']))=={('field',source['seq'],selected[0][0])}
  guards={}
  for fault in('capture','callback-parent','terminal-id','collector-config','result-members','missing-init'):
   bad=copy.deepcopy(rows)
   if fault=='capture':next(r for r in bad if r['kind']=='execution-lambda'and r['captures'])['captures'][0]={'object':'wrong'}
   elif fault=='callback-parent':next(r for r in bad if r['kind']=='enter'and r.get('callback_call_id'))['parent']='wrong'
   elif fault=='terminal-id':next(r for r in bad if r['kind']=='enter'and r.get('callback_call_id'))['callback_call_id']=-1
   elif fault=='collector-config':next(r for r in bad if r.get('sequence_start',{}).get('collector_configuration'))['sequence_start']['collector_configuration']['accumulator']='wrong'
   elif fault=='result-members':next(r for r in bad if r.get('sequence_contract',{}).get('result_elements')and'value'not in r['sequence_contract']['result_elements'][0])['sequence_contract']['result_elements'].reverse()
   else:bad.remove(next(r for r in bad if r['kind']=='execution-initialized-class'))
   try:infer_execution(plan,bad)
   except ValueError:guards[fault]=True
   else:raise AssertionError(fault)
  reports[mode]={'business_equal':True,'known_positive':4,'exception_then_normal_same_thread_clean':True,'guards':guards}
 save(out/'results.json',reports);print(reports)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
