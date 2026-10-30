"""Real JVM constructor chains, independent argument/source-occurrence truth."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save,sha
from build_distributed_plans import build
from infer_execution_kernel import infer_execution

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';javac='/usr/lib/jvm/java-8-openjdk-amd64/bin/javac';old=ROOT/'artifacts/communication-identity-revision-20261029/final-historical-02/frozen-base/distributed-observer.jar'
 command([javac,'-cp',':'.join(map(str,[old,*JARS])),'-d',str(classes),str(HERE/'ConstructorChainFixture.java')],out/'compile.log');jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('ConstructorChainFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
 entry='ConstructorChainFixture.root(LConstructorChainFixture$Input;)LConstructorChainFixture$Result;';source='ConstructorChainFixture$Reader.read()LConstructorChainFixture$Box;';b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':entry,'targets':['ConstructorChainFixture$Result.text'],'response_path':'/text','execution_kernel':True,'application_calls':True,'source_calls':[source]}})
 plan=load(b/'fixture/plan.json');cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*JARS]));baseline=command([java,'-cp',cp,'ConstructorChainFixture'],out/'baseline.log');expected=json.loads(baseline.stdout.splitlines()[-1]);assert all(c['finallyCount']==1 for c in expected)
 oracle={0:'left',1:'right',2:'left',3:'right',4:(),5:(),6:None,7:None,8:'remote',9:'right',10:(),11:'left',12:'right',13:'left',14:'left'};reports={}
 for mode in ('full','selective'):
  cap=out/mode;cap.mkdir();command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'ConstructorChainFixture'],cap/'stdout.log');assert json.loads((cap/'stdout.log').read_text().splitlines()[-1])==expected
  rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem'];answers=infer_execution(plan,rows)['answers'];checks=[]
  for case in expected:
   ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message']);a=next(x for x in answers if x['root_frame']==ret['frame']and x['path']=='/text');want=oracle[case['mode']];assert a['known']==(want is not None),(mode,case,a)
   wanted=set()
   if want not in (None,()):
    if want=='remote':provider=next(r for r in rows if r['kind']=='binding-source'and r['frame']==ret['frame']);field='ConstructorChainFixture$Box.text'
    else:provider=next(r for r in rows if r['kind']=='binding-input'and r['frame']==ret['frame']and r['argument']==0);field='ConstructorChainFixture$Input.'+want
    index=next(i for i,f in enumerate(provider['fields'])if f['field']==field);wanted={('field',provider['seq'],index)}
   if want is not None:assert set(map(tuple,a['origins']))==wanted,(mode,case,a,wanted)
   checks.append({'case':case,'known':a['known'],'expected':list(wanted),'actual':a['origins']})
  guards={}
  for fault in ('missing-parent','wrong-allocation','wrong-chain-id','wrong-parent-args','wrong-default-version','wrong-default-frame','missing-child-write','missing-completion','missing-type-test','wrong-type-result','wrong-type-object','disconnected-type-hierarchy','missing-accessor-implementation'):
   bad=copy.deepcopy(rows);base=next(r for r in bad if r['kind']=='enter'and r['method'].startswith('ConstructorChainFixture$Base.<init>'))
   if fault=='missing-parent':bad.remove(base)
   elif fault=='wrong-allocation':base['receiver']='different-object'
   elif fault=='wrong-chain-id':base['constructor_id']=-1
   elif fault=='wrong-parent-args':base['args'][0]['object']='same-valued-other-input'
   elif fault=='wrong-default-version':next(r for r in bad if r['kind']=='execution-defaults')['fields'][0]['version']=1
   elif fault=='wrong-default-frame':next(r for r in bad if r['kind']=='execution-defaults')['frame']='other-frame'
   elif fault=='missing-child-write':bad.remove(next(r for r in bad if r['kind']=='write'and r['site'].startswith('ConstructorChainFixture$Child.<init>')))
   elif fault=='missing-completion':bad.remove(next(r for r in bad if r['kind']=='execution-constructed'))
   elif fault=='missing-type-test':bad.remove(next(r for r in bad if r['kind']=='execution-type-test'))
   elif fault=='wrong-type-result':next(r for r in bad if r['kind']=='execution-type-test')['result']^=1
   elif fault=='wrong-type-object':next(r for r in bad if r['kind']=='execution-type-test'and r['hierarchy'])['input']['object']='other'
   elif fault=='disconnected-type-hierarchy':next(r for r in bad if r['kind']=='execution-type-test'and r['hierarchy'])['actual_class']='other'
   else:next(r for r in bad if r['kind']=='collection-call-enter'and r.get('accessor_implementation')and r['callee']not in plan['response_binding']['source_calls']).pop('accessor_implementation')
   try:infer_execution(plan,bad)
   except ValueError:guards[fault]=True
   else:raise AssertionError('Damaged constructor evidence accepted: '+fault)
  from diagnose_source_loss import run as diagnose
  diagnose(b/'fixture/plan.json',cap/'events.jsonl',cap/'first-loss')
  losses=load(cap/'first-loss/source-first-loss.json')['first_losses']
  source_by_message={r['message']:r['seq']for r in rows if r['kind']=='binding-source'}
  for case in expected:
   actual=[r for r in losses if r['source_seq']==source_by_message[case['message']]]
   if case['mode']==6:assert actual and all('OpaqueConstructorEffects.touch('in r['callee']for r in actual),actual
   elif case['mode']==7:assert actual and all('$Published.<init>'in r['callee']and r.get('constructor_id')for r in actual),actual
   else:assert not actual,(case,actual)
  reports[mode]={'targets':len(checks),'known_correct':sum(x['known']for x in checks),'necessary_unknown':sum(not x['known']for x in checks),'business_equal':True,'diagnostic_constructor_and_callback_guards':True,'guards':guards,'checks':checks};save(cap/'checks.json',reports[mode]);print(mode,{k:v for k,v in reports[mode].items()if k!='checks'},flush=True)
 save(out/'results.json',{'all_passed':True,'modes':reports,'agent_sha256':sha(b/'distributed-observer.jar')})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
