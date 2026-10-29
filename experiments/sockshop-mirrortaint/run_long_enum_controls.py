"""Actual Java long boundaries and literal enum proof guards; no cost tests."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from build_distributed_plans import build
from infer_execution_kernel import infer_execution
from plan_literal_enums import prove

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
 cp=':'.join(map(str,[ROOT/'artifacts/communication-identity-revision-20261029/build-04/distributed-observer.jar',*JARS]))
 command(['/usr/lib/jvm/java-8-openjdk-amd64/bin/javac','-cp',cp,'-d',str(classes),str(HERE/'LongEnumFixture.java')],out/'compile.log')
 jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for p in classes.glob('LongEnumFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
 reports={}
 for target in ('number','text','chosen'):
  home=out/target;home.mkdir();b=home/'build';build(b,{'fixture':{'jar':str(jar),'entry':'LongEnumFixture.root(LLongEnumFixture$Input;)LLongEnumFixture$Result;','targets':['LongEnumFixture$Result.'+target],'response_path':'/'+target,'execution_kernel':True,'application_calls':True}})
  model=load(b/'fixture/model.json');plan=load(b/'fixture/plan.json');cfg=plan['execution_kernel'];assert 'LongEnumFixture$Code'in cfg['plain_enum_classes'];assert {'LongEnumFixture$Mutable','LongEnumFixture$Callback'}<=set(cfg['unproved_enum_classes'])
  classpath=':'.join(map(str,[classes,b/'distributed-observer.jar',*JARS]));java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
  original=command([java,'-cp',classpath,'LongEnumFixture'],home/'original.log');expected=json.loads(original.stdout.splitlines()[-1]);reports[target]={}
  for mode in ('full','selective'):
   cap=home/mode;cap.mkdir();command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-cp',classpath,'LongEnumFixture'],cap/'stdout.log')
   assert json.loads((cap/'stdout.log').read_text().splitlines()[-1])==expected
   rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem']
   answers=infer_execution(plan,rows)['answers'];assert len(answers)==len(expected)
   for case in expected:
    returned=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message']);a=next(a for a in answers if a['root_frame']==returned['frame']and a['path']=='/'+target);assert a['known'],(mode,target,case,a)
    want=set()
    if target=='chosen':
     arg=next(r for r in rows if r['kind']=='binding-input'and r['frame']==returned['frame']);field='LongEnumFixture$Input.'+('a'if case['left']>case['right']else'b');i=next(i for i,f in enumerate(arg['fields'])if f['field']==field);want={('field',arg['seq'],i)}
    assert set(map(tuple,a['origins']))==want,(a,want)
   guards={}
   for fault in ('missing-field','wrong-field-owner','wrong-initial-version','wrong-literal','wrong-enum-hash','contradict-branch'):
    bad=copy.deepcopy(rows);fact=next(r for r in bad if r.get('foundation_enum'))
    if fault=='missing-field':fact['foundation_enum']['literal_fields'].pop()
    elif fault=='wrong-field-owner':fact['foundation_enum']['literal_fields'][0]['owner']='foreign'
    elif fault=='wrong-initial-version':fact['foundation_enum']['literal_fields'][0]['version']=2
    elif fault=='wrong-literal':fact['foundation_enum']['literal_fields'][0]['observed']['value']=77
    elif fault=='wrong-enum-hash':fact['foundation_enum']['class_sha256']='wrong'
    else:next(r for r in bad if r['kind']=='branch')['taken']^=True
    try:infer_execution(plan,bad)
    except ValueError:guards[fault]=True
    else:raise AssertionError('Bad literal/LCMP evidence accepted: '+fault)
   reports[target][mode]={'known_correct':len(answers),'positive':len(answers)if target=='chosen'else 0,'guards':guards,'business_equal':True,'agent_sha256':sha(b/'distributed-observer.jar')};save(cap/'checks.json',reports[target][mode]);print(target,mode,reports[target][mode],flush=True)
 save(out/'results.json',reports)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
