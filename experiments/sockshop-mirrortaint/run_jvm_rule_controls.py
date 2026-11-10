"""Real JVM extremes/alias/write controls with literal raw-field oracle."""
import argparse,json,copy
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save
from run_query_planner import JARS,command
from run_generic_observation_rules import metadata_build,AGENT,JAVA
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution

def run(out,guard_off=False):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();cp=':'.join(map(str,[classes,AGENT,*JARS]))
 command([JAVA[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'JvmRuleFixture.java')],out/'compile.log')
 jar=out/'fixture.jar'
 with ZipFile(jar,'w')as z:
  for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
 metadata_build(out/'build',{'fixture':{'jar':str(jar),'targets':['JvmRuleFixture$Out.result']}})
 p,r=choose(load(out/'build/fixture/model.json'),{'entry':'JvmRuleFixture.root(LJvmRuleFixture$Store;I)LJvmRuleFixture$Out;','target':'JvmRuleFixture$Out.result','path':'/result','source_calls':['JvmRuleFixture$Store.read(I)LJvmRuleFixture$Data;']});save(out/'plan.json',p);p=load(out/'plan.json')
 baseline=json.loads(command([JAVA,'-cp',cp,'JvmRuleFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
 expected_values=[-2**63,2**63-1,14,-2**31,7,7,7,7]
 expected_fields=[['a','b'],['a','b'],['a','b'],['x','y'],[],[],['b'],['b']]
 for mode in('full','selective'):
  d=out/mode;d.mkdir();flags=['-Dservice.write.observation=false']if guard_off else[]
  actual=json.loads(command([JAVA,*flags,'-javaagent:'+str(AGENT),'-Dservice.plan='+str(out/'plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(d/'events.jsonl'),'-cp',cp,'JvmRuleFixture'],d/'stdout.log').stdout.splitlines()[-1]);assert actual==baseline
  rows=[json.loads(s)for s in(d/'events.jsonl').read_text().splitlines()];answers=infer_execution(p,rows)['answers'];assert len(answers)==8;checks=[]
  for c,a,fields,value in zip(actual,answers,expected_fields,expected_values):
   assert c['value']==value
   s=next(r for r in rows if r['kind']=='binding-source'and r.get('message')==c['message']);want={('field',s['seq'],i)for i,f in enumerate(s['fields'])if f['field']in{'JvmRuleFixture$Data.'+k for k in fields}}
   assert len(want)==len(fields)and a['known']and set(map(tuple,a['origins']))==want,(c,a,want)
   checks.append({'case':c['case'],'value':value,'expected':sorted(want),'answer':a})
  guards=[]
  for fault in('i2l-result','wrong-read-owner','decreasing-write-version','missing-write'):
   changed=copy.deepcopy(rows)
   if fault=='i2l-result':next(r for r in changed if r['kind']=='execution-i2l')['result']+=1
   elif fault=='wrong-read-owner':next(r for r in changed if r['kind']=='read')['owner']='same-value-other-object'
   elif fault=='missing-write':changed.remove(next(r for r in changed if r['kind']=='write'and '.root('in r['site']))
   else:next(r for r in changed if r['kind']=='write'and '.root('in r['site'])['version']=0
   try:infer_execution(p,changed)
   except (ValueError,KeyError):guards.append(fault)
   else:raise AssertionError(fault)
  versions=[r for r in rows if r['kind']=='write-version'];assert len(versions)==(1 if mode=='selective'and not guard_off else 0)
  reports[mode]={'business_equal':True,'checks':checks,'guards':guards,'actual_version_only':len(versions)}
 save(out/'results.json',reports)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--guard-off',action='store_true');a=p.parse_args();run(a.out.resolve(),a.guard_off)
