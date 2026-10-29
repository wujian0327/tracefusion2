#!/usr/bin/env python3
"""Dispatch planning/reconstruction through the selected immutable source tree.
Only experiment environment/configuration code is shared. No core monkeypatch.
"""
import argparse,sys,json,hashlib,shutil,copy,subprocess,datetime
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
OUT=REPO/'artifacts/external-frozen-transfer-20261029'
FIRST=REPO/'artifacts/portability-first-20261028'
CUR=REPO/'artifacts/account-semantics-20261028/final-candidate-01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

def setup(version):
 frozen=OUT/'sources'/version;here=frozen/'experiments/sockshop-mirrortaint';sys.path.insert(0,str(here))
 sys.path.append(str(REPO/'scripts'))
 import run_planned_service
 run_planned_service.ROOT=REPO
 expected=load(FIRST/'protocol-start.json')['core_sources']if version=='ae7fe8d'else load(CUR/'algorithm-freeze.json')['sources']
 for p,h in expected.items():assert sha(frozen/Path(p).relative_to(REPO))==h,(version,p)
 base=REPO/'artifacts/contract-routing-revision-20261023/final-v2/frozen-base'if version=='ae7fe8d'else CUR/'frozen-base'
 assert sha(base/'distributed-observer.jar')==load(base/'build.json')['agent_sha256']
 return here,base,expected

def source_calibrated_plan(model,query,source_calls):
 """Use the frozen low-level source_calls API after answer-free routing.

 The high-level frozen choose API does not pass query source declarations.
 This adapter changes configuration only; every semantic/planning operation
 below is the selected snapshot's existing implementation.
 """
 from plan_capability_policy import choose,specialize_transport,CONVERSION
 from plan_response_binding import plan_response
 from contract_obligations import features as api_obligations
 from plan_async_dependencies import attach_async_dependencies
 from plan_execution_closure import attach_execution_closure
 initial,route=choose(model,query);kernel=initial['profile']=='execution-dependency'
 p=plan_response(model,query['entry'],query['target'],query['path'],source_calls=source_calls,read_forward_contracts=not kernel,execution_kernel=kernel,application_calls=kernel)
 features=set()
 if kernel:
  features=api_obligations(p,model)
  if features:p=attach_async_dependencies(p,features,model.get('library_inventory'))
  import plan_capability_policy
  if Path(plan_capability_policy.__file__).with_name('plan_feign_effects.py').exists():
   from plan_feign_effects import attach as attach_feign_effects
   attach_feign_effects(p,model)
  p['contract_applicability']={'version':1,'features':sorted(features),'selection':'Actual planned APIs; library implementation/hash and runtime preconditions remain mandatory. Save is not a task or decoder contract.'}
 if CONVERSION in model['methods'] and any(i['op']in(182,183,184,185)and i.get('owner','')+'.'+i.get('name','')+i.get('desc','')==CONVERSION for m in p.get('execution_kernel',{}).get('methods',{}).values()for i in m['instructions']):
  p['json_conversion_methods']=[CONVERSION];p['json_conversion_contract']='Existing pinned default Jackson relative-path conversion contract; not a business formula.'
 p['source_evidence']=True
 if kernel:specialize_transport(p);attach_execution_closure(p,model)
 assert set(source_calls)<=set(p['response_binding']['source_calls'])
 route={**route,'source_configuration_calibration':'Forward sealed boundaries through frozen plan_response source_calls API; original route selected before new runtime. No field propagation or library model added.','original_profile':initial['profile']}
 return p,route

def calibrated_home(version):
 return OUT/'source-config-C1'/version

def calibrated_plan(version,api,index):
 setup(version);home=calibrated_home(version);q=next(t for t in load(OUT/'task-seal.json')['entries']if t['id']==api);old=load(OUT/version/'planning-first'/api/('%03d.json'%index));dest=home/'planning-first'/api;dest.mkdir(parents=True,exist_ok=True)
 if old['status']!='accepted':save(dest/('%03d.json'%index),old);return
 model=load(OUT/version/'metadata'/q['role']/'model.json')
 try:
  p,route=source_calibrated_plan(model,old['query'],[s['callee']for s in q['read_source_candidates']]);save(dest/('%03d-plan.json'%index),p);old={**old,'status':'accepted','profile':p['profile'],'route':route,'plan_sha256':sha(dest/('%03d-plan.json'%index)),'configuration_revision':'C1'}
 except (ValueError,KeyError)as e:old={**old,'status':'planning_rejected','reason':str(e),'configuration_revision':'C1'}
 save(dest/('%03d.json'%index),old)

def plan(version,only_api=None,only_index=None):
 here,base,expected=setup(version)
 from plan_capability_policy import choose
 from contract_applicability import library_inventory
 from plan_distributed_fields import json_schema
 home=OUT/version;metadata=home/'metadata';metadata.mkdir(exist_ok=True);rows=[]
 for q in load(OUT/'task-seal.json')['entries']:
  if only_api and q['id']!=only_api:continue
  role=q['role'];d=metadata/role
  if not d.exists():
   d.mkdir();m=load(FIRST/'metadata'/role/'model.json');m['library_inventory']=library_inventory(FIRST/'business-jars'/(role+'.jar'));save(d/'model.json',m)
  m=load(d/'model.json');dest=home/'planning-first'/q['id'];dest.mkdir(parents=True,exist_ok=True)
  for i,t in enumerate(q['return_targets']):
   if only_index is not None and i!=only_index:continue
   path=dest/('%03d.json'%i)
   if path.exists():rows.append(load(path));continue
   r={'api':q['id'],'index':i,'query':{'id':q['id']+'-'+str(i),'entry':q['entry'],'target':t['target'],'path':t['path'],'role':role,'application':q['application']},'target_metadata':t,'sealed_protocol_sha256':sha(OUT/'protocol-before-tools.json')}
   if only_api is None:
    started=datetime.datetime.now(datetime.timezone.utc)
    with (dest/('%03d-planning.log'%i)).open('w')as log:
     try:
      subprocess.run([sys.executable,str(Path(__file__).resolve()),'--version',version,'--stage','query-plan','--api',q['id'],'--index',str(i)],stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
      r=load(path)
     except subprocess.TimeoutExpired:r.update(status='analysis_limited',reason='External planner process budget 180 seconds; no partial plan accepted')
     except subprocess.CalledProcessError as e:r.update(status='planning_environment_failure',reason=str(e))
    r['planning_subprocess_wall_seconds']=(datetime.datetime.now(datetime.timezone.utc)-started).total_seconds();save(path,r);rows.append(r);continue
   if not t['target']:r.update(status='target_binding_unsupported',reason=t['binding'])
   else:
    try:p,route=choose(m,r['query']);save(dest/('%03d-plan.json'%i),p);r.update(status='accepted',profile=p['profile'],route=route,plan_sha256=sha(dest/('%03d-plan.json'%i)))
    except (ValueError,KeyError)as e:r.update(status='planning_rejected',reason=str(e))
   save(dest/('%03d.json'%i),r);rows.append(r)
  save(dest/'summary.json',{'rows':[r for r in rows if r['api']==q['id']]})
 save(home/'planning.json',rows);print(version,{s:sum(r['status']==s for r in rows)for s in {r['status']for r in rows}},flush=True)

def environment(version,api,mode,index,attempt,addon=False,observer_home=None,source_calibrated=False):
 here,base,expected=setup(version);home=calibrated_home(version)if source_calibrated else OUT/((observer_home or'MT-B1')if addon else version)
 # Environment runners are experiment scripts from main, not algorithm modules.
 import importlib.util
 own=REPO/'experiments/sockshop-mirrortaint'
 name='run_external_apollo'if api.startswith('apollo')else'run_portability_mall'
 spec=importlib.util.spec_from_file_location(name,own/(name+'.py'));env=importlib.util.module_from_spec(spec);spec.loader.exec_module(env)
 import portability_tool_config as config
 def verify(_):
  frozen=OUT/'sources'/version
  for p,h in expected.items():assert sha(frozen/Path(p).relative_to(REPO))==h
  assert sha(base/'distributed-observer.jar')==load(base/'build.json')['agent_sha256']
  assert sha(OUT/'task-seal.json')==load(OUT/'protocol-before-tools.json')['task_seal_sha256']
  assert sha(REPO/'artifacts/external-tools/mirrortaint/mirrorTaint.jar')==load(OUT/'protocol-before-tools.json')['native_jar_sha256']
 config.BASE=base;config.verify=verify
 original=config.configure
 def configure(root,out,cfg,q,mode,index=None):
  # This verifier precedes the unchanged configuration machinery.
  setup_receipt={'algorithm':version,'agent_sha256':sha(base/'distributed-observer.jar'),'core_sources':expected,'source_snapshot':str(OUT/'sources'/version),'no_core_agent_contract_changes':True,'task_seal_sha256':sha(OUT/'task-seal.json'),'adapter':'B0 unchanged native/adapter binaries; reviewed DB/RPC source configuration v2'}
  save(out/'version-before-business.json',setup_receipt)
  original(root,out,cfg,q,mode,index)
  if mode=='mirrortaint':
   prefix='com/ctrip/framework/apollo/'if api.startswith('apollo-')else'com/macro/mall/'
   mc=load(out/'mt-config.json');mc['prefix']=prefix;save(out/'mt-config.json',mc)
   cfg['command']=[('-Dtaint.app='+prefix.rstrip('/').replace('/','.'))if x.startswith('-Dtaint.app=')else x for x in cfg['command']]
   if addon:
    addition=OUT/'native-observation-B1-04';observer=addition/'native-boundary-facts.jar';receipt=load(addition/'results.json');assert sha(observer)==receipt['addon_sha256']
    boundary=out/'boundary-config.json';save(boundary,{'prefix':prefix,'source_calls':[s['callee']for s in q['read_source_candidates']],'sink_calls':sorted({s['callee']for s in q['effect_sink_candidates']})})
    cfg['volumes'] += [str(observer)+':/tf2/boundary.jar:ro',str(boundary)+':/tf2/boundary-config.json:ro']
    pos=cfg['command'].index('-jar');cfg['command'][pos:pos]=['-javaagent:/tf2/boundary.jar','-Dboundary.config=/tf2/boundary-config.json','-Dboundary.events=/tf2/capture/boundary-facts.jsonl']
    save(out/'B1-before-business.json',{'observation_addon_sha256':sha(observer),'config_sha256':sha(boundary),'original_native_sha256':sha(REPO/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'),'propagation_or_TF_contracts_modified':False,'raw_facts_not_certified_projection':True})
  receipt=load(out/'tool-binaries.json');receipt['fixed_core']=version;receipt['source_configuration_revision']='Reviewed concrete repository/RPC boundaries; not business helpers';save(out/'tool-binaries.json',receipt)
  if mode=='mirrortaint':
   receipt['files'][str(out/'mt-config.json')]=sha(out/'mt-config.json');save(out/'tool-binaries.json',receipt)
 config.configure=configure
 env.verify=verify
 # Add request-instance coordinates and read-only DB facts in the environment
 # wrapper; original invokes/arguments and response bodies are not modified.
 from sockshop import Deployment
 native_compose=Deployment.compose
 latest={}
 original_save=env.save
 def witnessed_save(path,data):
  if isinstance(data,dict)and'http_status'in data and'response'in data and latest:data['message']=latest['message']
  return original_save(path,data)
 env.save=witnessed_save
 def compose(self,*args,**kwargs):
  values=list(args)
  if 'curl'in values and '--max-time'in values:
   import inspect
   caller=inspect.currentframe().f_back;label=caller.f_locals.get('label','unknown-request')
   url=values[-1];seed=api+'|'+version+'|'+mode+'|'+str(index)+'|'+url+'|'+str(getattr(self,'_request_seq',0));self._request_seq=getattr(self,'_request_seq',0)+1
   digest=hashlib.sha256(seed.encode()).hexdigest();values[-1:-1]=['-H','traceparent: 00-'+digest[:32]+'-'+digest[32:48]+'-01','-H','tracestate: research=frozen-transfer'];self._last_message=digest[:32]+'/'+digest[32:48]
   latest['message']=self._last_message
   if label.startswith(api+'-input-'):
    save(self.out/(label+'-before-request.json'),{'message':self._last_message,'argv':values,'no_answer_based_materialization':True})
    databases=['ApolloConfigDB','ApolloPortalDB']if api.startswith('apollo-')else['mall']
    dump=native_compose(self,'exec','-T','mysql','mysqldump','-uroot','-ptf2-portability-fixture-only','--skip-comments','--skip-extended-insert','--no-create-info','--databases',*databases,check=False)
    (self.out/(label+'-database-before.sql')).write_text(dump.stdout);save(self.out/(label+'-database-before-status.json'),{'returncode':dump.returncode})
    result=native_compose(self,*values,**kwargs)
    dump=native_compose(self,'exec','-T','mysql','mysqldump','-uroot','-ptf2-portability-fixture-only','--skip-comments','--skip-extended-insert','--no-create-info','--databases',*databases,check=False)
    (self.out/(label+'-database-after.sql')).write_text(dump.stdout);save(self.out/(label+'-database-after-status.json'),{'returncode':dump.returncode})
    return result
  return native_compose(self,*values,**kwargs)
 Deployment.compose=compose
 # No API is replaced on failure; the runner's exception/status receipt is kept.
 if api.startswith('apollo'):env.run(home,attempt,mode,api,index)
 else:env.run(home,mode,api,index,attempt)

def preparation_failure_state(source):
 for name in ('instrumented-business-probe-failure.json','ready-portal-admin-path.json'):
  p=source/name
  if p.exists() and any(reason in p.read_text(errors='replace') for reason in ('Map implementation outside explicit summary','Unmodeled JDK read-effect runtime','Only String map keys admitted')):
   return 'not_executed_after_instrumented_preparation_failure'
 return 'not_executed_after_environment_failure'

def evaluate(version,api,mode,index,evaluation_label="evaluation-frozen-v3",source_calibrated=False):
 here,base,expected=setup(version)
 from infer_distributed_fields import Reconstruction
 import importlib.util
 spec=importlib.util.spec_from_file_location('independent_external_oracle',REPO/'experiments/sockshop-mirrortaint/external_transfer_oracle.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
 home=calibrated_home(version)if source_calibrated else OUT/version;source=home/'tool-runs'/api/mode/('query-%03d'%index);out=source/evaluation_label;out.mkdir()
 q=load(home/'planning-first'/api/('%03d.json'%index))['query'];records=[]
 work=out/'view';(work/'build'/q['role']).mkdir(parents=True);(work/'capture'/q['role']).mkdir(parents=True)
 shutil.copyfile(home/'planning-first'/api/('%03d-plan.json'%index),work/'build'/q['role']/'plan.json')
 (work/'capture'/q['role']/'events.jsonl').symlink_to(source/'capture/events.jsonl')
 g=None;error=None
 try:g=Reconstruction(work/'build',work/'capture',[q['role']])
 except Exception as e:error=str(e)
 raw_path=source/'capture/events.jsonl';rows=oracle.raw(raw_path)if raw_path.exists()else[]
 task=next(t for t in load(OUT/'task-seal.json')['entries']if t['id']==api);control=load(OUT/'ae7fe8d/original'/task['application']/('sealed-'+api)/'results.json');run=load(source/'results.json');protocol=load(OUT/'oracle-before-tools.json')
 for before in control['cases']:
  if not oracle.original_root_returns(before) or api=='apollo-4':continue
  case=next((c for c in run['cases']if c['case']==before['case']),None)
  for path,value in oracle.targets(before['response']):
   if oracle.wildcard(path)!=q['path']:continue
   record={'api':api,'case':before['case'],'path':path,'tool':mode,'version':version,'oracle_adequate':False,'TP':None,'FP':None,'FN':None}
   # Determine raw-fact truth independently of graph construction/query success.
   want=None
   if case is not None and case['http_status']==200:
    try:
     oracle.require_complete_raw_capture(rows)
     ret=[r for r in rows if r['kind']=='binding-return'and r.get('message')==case['message']]
     if len(ret)!=1:raise ValueError('Actual root return absent/ambiguous')
     want=oracle.tf_expected(rows,ret[0],oracle.rule(protocol,api,path),path)
     record.update(expected=want,oracle_adequate=True,TP=0,FP=0,FN=len(want))
    except ValueError as e:record['oracle_gap']=str(e)
   if case is None:record.update(state=preparation_failure_state(source),error=run.get('error'))
   elif case['http_status']!=before['http_status']:record.update(state='instrumented_business_failure',error=error)
   elif error:record.update(state='evidence_invalid',error=error,semantic_limit_or_evidence_failure_needs_diagnosis=True)
   else:
    try:
     a=g.query(case['message'],path,q['role'],boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}]);record['answer']=a;record['state']='known_unchecked'if a['known']else'unknown'
     if want is not None:
      # Preserve actual call occurrence as well as object/field/version.
      w={tuple(v) for v in want}
      actual={(v.get('callee'),v.get('root_frame'),v['seq'],v.get('path'),v['owner'],v['field'],v['version']) for v in a['sources']}
      if a['known']:record['state']='known_correct'if actual==w else'known_wrong'
      record.update(TP=len(actual&w)if a['known']else 0,FP=len(actual-w)if a['known']else 0,FN=len(w-actual)if a['known']else len(w))
    except Exception as e:record.update(state='evidence_invalid',error=str(e),semantic_limit_or_evidence_failure_needs_diagnosis=True)
   records.append(record)
 save(out/'instances.json',records);save(out/'graph-construction.json',{'state':'constructed'if g is not None else'evidence_invalid','error':error,'states':{s:sum(r['state']==s for r in records)for s in {r['state']for r in records}},'raw_events_sha256':sha(raw_path)if raw_path.exists()else None})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--version',required=True,choices=['ae7fe8d','78a9534']);p.add_argument('--stage',choices=['plan','query-plan','run','evaluate','source-calibrated-plan'],required=True);p.add_argument('--api');p.add_argument('--mode',default='original');p.add_argument('--index',type=int);p.add_argument('--attempt',default='sealed-original');p.add_argument('--observer-addon',action='store_true');p.add_argument('--observer-home');p.add_argument('--evaluation-label',default='evaluation-frozen-v3');p.add_argument('--source-calibrated',action='store_true');a=p.parse_args()
 if a.stage=='plan':plan(a.version)
 elif a.stage=='query-plan':plan(a.version,a.api,a.index)
 elif a.stage=='source-calibrated-plan':calibrated_plan(a.version,a.api,a.index)
 elif a.stage=='run':environment(a.version,a.api,a.mode,a.index,a.attempt,a.observer_addon,a.observer_home,a.source_calibrated)
 else:evaluate(a.version,a.api,a.mode,a.index,a.evaluation_label,a.source_calibrated)
