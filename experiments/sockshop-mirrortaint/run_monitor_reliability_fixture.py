#!/usr/bin/env python3
import argparse,json,subprocess,hashlib
from pathlib import Path
from run_planned_service import HERE,ROOT,load,save,sha

def run(out,build):
 out.mkdir(parents=True);classes=out/'classes';classes.mkdir();subprocess.run(['javac','-cp',str(build/'distributed-observer.jar'),'-d',str(classes),str(HERE/'MonitorReliabilityFixture.java'),str(HERE/'MonitorFrameworkReliabilityFixture.java')],check=True)
 owner='MonitorReliabilityFixture';entry=owner+'.root(L'+owner+'$Input;)L'+owner+'$Input;';plan={'profile':'identity-return','entry':entry,'frame_methods':[entry]+[owner+'.'+m+'(L'+owner+'$Input;)L'+owner+'$Input;'for m in('child','deeper')],'class_sha256':{p.stem:sha(p)for p in classes.glob('*.class')},'target':owner+'$Input.text','input_argument':0,'input_owner':owner+'$Input','snapshot_fields':[owner+'$Input.text'],'mapper_fields':[],'full_snapshot_fields':[],'reduction':{},'selected_read_sites':[],'binding_callsites':[],'producer_method':None,'writer_method':None,'json_schema':{}}
 save(out/'plan.json',plan);expected=None;expected_parents=0;checks=[]
 for mode in('original','full','selective'):
  cap=out/mode;cap.mkdir();cmd=['java'];
  if mode!='original':cmd+=['-javaagent:'+str(build/'distributed-observer.jar'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.plan='+str(out/'plan.json'),'-Dservice.mode='+mode]
  cmd+=['-cp',str(classes),owner];p=subprocess.run(cmd,capture_output=True,text=True,timeout=45);(cap/'stdout.log').write_text(p.stdout);(cap/'stderr.log').write_text(p.stderr);save(cap/'command.json',cmd);assert p.returncode==0,p.stderr
  business=[l for l in p.stdout.splitlines()if l.startswith('BUSINESS|')]
  if mode=='original':expected=business;expected_parents=sum(l.startswith('PARENT|')for l in p.stdout.splitlines())
  else:
   assert business==expected,(mode,business,expected)
   states=[l for l in p.stdout.splitlines()if l.startswith('STATE|')];assert len(states)==len(expected)
   for s in states:
    assert 'frames=0'in s and 'scopes=0'in s and 'calls=0'in s and 'effects=0'in s and 'pending=null'in s and 'active=0'in s and 'constructors=0'in s and 'save=0'in s and 'conversions=0'in s,s
   parents=[l for l in p.stdout.splitlines()if l.startswith('PARENT|')];assert len(parents)==expected_parents
   assert all('frames=1'in s and 'scopes=1'in s and 'active=1'in s for s in parents),parents
   rows=[json.loads(l)for l in(cap/'events.jsonl').open()];assert any(r['kind']=='problem'for r in rows)and rows[-1]['capture_invalid']
   assert(cap/'events.jsonl.invalid').exists();checks.append({'mode':mode,'business_rows_equal':len(expected),'parent_scope_checks':len(parents),'no_residual_state_after_each_root':True,'original_exception_identity_and_finally_preserved':True,'damaged_capture_has_problem_sidecar_and_footer':True})
 framework=[];baseline=None
 for mode in('original','full','selective'):
  cap=out/('framework-'+mode);cap.mkdir();cmd=['java']
  if mode!='original':cmd+=['-javaagent:'+str(build/'distributed-observer.jar'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.plan='+str(out/'plan.json'),'-Dservice.mode='+mode]
  cmd+=['-cp',str(classes)+':'+str(build/'distributed-observer.jar'),'MonitorFrameworkReliabilityFixture'];p=subprocess.run(cmd,capture_output=True,text=True,timeout=45);(cap/'stdout.log').write_text(p.stdout);(cap/'stderr.log').write_text(p.stderr);save(cap/'command.json',cmd);assert p.returncode==0,p.stderr
  business=[l for l in p.stdout.splitlines()if l.startswith('BUSINESS|')]
  if mode=='original':baseline=business
  else:
   assert business==baseline
   rpc=[l for l in p.stdout.splitlines()if l.startswith('RPC|')];assert len(rpc)==4;assert 'SOURCE|failed-scope-owned-cleanup' in p.stdout
   final=next(l for l in p.stdout.splitlines()if l.startswith('FINAL|'));assert 'frames=0'in final and 'scopes=0'in final and 'calls=0'in final and 'active=0'in final
   rows=[json.loads(l)for l in(cap/'events.jsonl').open()];assert rows[-1]['capture_invalid']
   framework.append({'mode':mode,'business_rows_equal':len(business),'RPC_parent_and_idempotent_completion':len(rpc),'source_capture_cleanup_in_failed_scope':True,'task_exception_identity_and_parent_preserved':True,'invalid_capture_stays_invalid':True})
 save(out/'framework-checks.json',framework)
 save(out/'checks.json',{'checks':checks,'fixture':'Independent control only; real Recipient separate','agent_sha256':sha(build/'distributed-observer.jar')});print(checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.build.resolve())
