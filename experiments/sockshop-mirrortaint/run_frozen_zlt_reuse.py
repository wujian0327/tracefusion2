#!/usr/bin/env python3
"""Presealed ZLT read-only transfer; configuration/observations, no new semantics."""
import argparse,copy,hashlib,json,subprocess,sys,time,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.append(str(ROOT/'scripts'))
from run_planned_service import load,sha
from run_frozen_locality_cost import verify,BASE,COMMIT
FIRST=ROOT/'artifacts/portability-first-20261028';ENV=ROOT/'artifacts/external-frozen-transfer-20261029'
def save(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def prepare(home):
 home.mkdir(parents=True,exist_ok=False);sources=verify();entries=load(FIRST/'task-seal.json')['entries'];pool=[copy.deepcopy(q)for q in entries if q['id'].startswith('ZLT-MP-')]
 for folder in ('business-jars','upstream','metadata'):(home/folder).symlink_to((FIRST/folder).resolve(),target_is_directory=True)
 (home/'environment-images-before-tools.json').write_bytes((ENV/'environment-images-before-tools.json').read_bytes())
 qout=[]
 for q in pool:
  q['selected']=q['id']in('ZLT-MP-1','ZLT-MP-4')
  q['selection_reason']='Previously nonempty original list response; distinct untested controller entry; fixed ascending API order.'if q['selected']else'Write endpoint / absent-row-only mobile preflight / authenticated context unprepared. Retained; not replaced after TF planning.'
  if not q['selected']:continue
  model=load(FIRST/'metadata'/q['role']/'model.json');owner='com/central/oauth/mapper/ClientMapper'if q['id']=='ZLT-MP-1'else'com/central/user/mapper/SysUserMapper'
  methods=[m for m in model['methods']if m.startswith(owner+'.findList(')];assert len(methods)==1
  q['read_source_candidates']=[{'callee':methods[0],'basis':'Actual original mapper DB-read return, not service/helper parameter.'}]
  q['return_targets']=[{'path':'/data/*/'+('clientId'if q['id']=='ZLT-MP-1'else'username'),'target':('com/central/oauth/model/Client.clientId'if q['id']=='ZLT-MP-1'else'com/central/common/model/SysUser.username')}]
  q['inputs']=[{'case':'input-%02d'%i,'path':('/clients/list'if q['id']=='ZLT-MP-1'else'/users')+'?page=%d&limit=%d'%(1+i//2,1+i%2)}for i in range(6)]
  q['oracle']={'source':methods[0],'rule':'For each returned data element, the selected scalar is copied from the unique mapper return occurrence. Match original SQL primary key and value; source identity must additionally have raw call/ordinal/object/field/version. JSON values alone never certify instance origin. No implicit selection dependencies.', 'positive':True,'sql_table':'oauth_client_details'if q['id']=='ZLT-MP-1'else'sys_user','column':'client_id'if q['id']=='ZLT-MP-1'else'username','source_path':'/*/'+('clientId'if q['id']=='ZLT-MP-1'else'username')}
  qout.append(q)
 save(home/'candidate-pool-before-planning.json',{'all40_retained':True,'original40_sha256':sha(ROOT/'MIRRORTAINT-PORTABILITY-PLAN-20261028.json'),'pool':pool,'selection_rule':'All five original ZLT APIs retained. Select exactly the two already-ready nonempty list GET entries (1,4); no outcome-based replacement. Static/source/environment previously exposed, not blind.', 'algorithm':COMMIT,'sources':sources,'driver_sha256':sha(Path(__file__))})
 save(home/'task-seal.json',{'entries':qout});save(home/'protocol-start.json',{'TF_commit':COMMIT})
 save(home/'oracle-before-tools.json',{'entries':{q['id']:q['oracle']for q in qout},'truth_is_not_labels_or_graph':True,'inputs_sealed_before_any_tool':True})
 print('Sealed',[(q['id'],q['inputs'])for q in qout],flush=True)

def plan(home):
 from plan_capability_policy import choose
 environment=load(ROOT/'artifacts/source-locality-effects-20261030/final-mall-03/deployment-environment.json')
 # This is an unverified ZLT converter deployment, never borrow Mall's binding eligibility.
 environment.pop('response_converter',None)
 reports=[]
 for q in load(home/'task-seal.json')['entries']:
  target=q['return_targets'][0];query={'id':q['id']+'-positive','entry':q['entry'],'target':target['target'],'path':target['path'],'role':q['role'],'source_calls':[s['callee']for s in q['read_source_candidates']]};receipt={'api':q['id'],'query':query}
  try:
   p,r=choose(load(home/'metadata'/q['role']/'model.json'),query,deployment=environment);save(home/'planning-first'/q['id']/'000-plan.json',p);receipt.update(status='conditional',route=r,plan_sha256=sha(home/'planning-first'/q['id']/'000-plan.json'))
  except Exception as e:receipt.update(status='planning_rejected',reason=str(e))
  save(home/'planning-first'/q['id']/'000.json',receipt);reports.append(receipt)
 save(home/'planning-summary.json',reports);print(reports,flush=True)

def run(home,api,mode):
 import run_external_zlt_environment as env
 import portability_tool_config as pc
 from sockshop import Deployment
 verify();q=next(q for q in load(home/'task-seal.json')['entries']if q['id']==api)
 if mode in('full','selective')and load(home/'planning-first'/api/'000.json')['status']=='planning_rejected':
  save(home/'refusals'/api/(mode+'.json'),{'state':'planning_rejected','not_deployed':True,'proof':load(home/'planning-first'/api/'000.json')});return
 out=home/'runs'/api/mode;out.parent.mkdir(parents=True,exist_ok=True)
 # env.run expects images in its parent. Exact old pinned image inventory is reused.
 (out.parent/'environment-images-before-tools.json').write_bytes((home/'environment-images-before-tools.json').read_bytes())
 native_save=env.save;native_compose=Deployment.compose;records=[];configured=False
 pc.BASE=BASE;pc.verify=lambda root:verify()
 def save_hook(path,data):
  nonlocal configured
  if path.name=='compose.json'and not configured:
   configured=True
   if mode!='original':pc.configure(home,out,data['services'][q['role']],q,mode,0 if mode!='mirrortaint'else None)
  return native_save(path,data)
 def compose(self,*args,**kw):
  vals=list(args)
  if 'curl'in vals and isinstance(vals[-1],str)and vals[-1].startswith('http://127.0.0.1:')and '/actuator/'not in vals[-1]:
   url=vals[-1];selected=(api=='ZLT-MP-1'and '/clients/list?'in url)or(api=='ZLT-MP-4'and '/users?'in url)
   if selected:
    (out/'requests').mkdir(exist_ok=True)
    first_result=None
    for item in q['inputs']:
     call=vals.copy();digest=hashlib.sha256((api+'|'+mode+'|'+item['case']).encode()).hexdigest();message=digest[:32]+'/'+digest[32:48]
     call[-1]=url.split('/',3)[0]+'//'+url.split('/',3)[2]+item['path'];call[-1:-1]=['-H','traceparent: 00-'+digest[:32]+'-'+digest[32:48]+'-01']
     p=native_compose(self,*call,**kw);first_result=first_result or p
     raw,status=p.stdout.rsplit('\n',1)if'\n'in(p.stdout or'')else(p.stdout,'0')
     try:body=json.loads(raw)
     except Exception:body=raw
     record={**item,'api':api,'mode':mode,'message':message,'http_status':int(status or'0'),'response':body,'curl_returncode':p.returncode};records.append(record);native_save(out/'requests'/str(item['case']+'.json'),record)
    # DB content is independent of propagation. It does not fill physical source coordinates.
    table=q['oracle']['sql_table'];database='oauth-center'if api=='ZLT-MP-1'else'user-center'
    p=native_compose(self,'exec','-T','mysql','mysql','-uroot','-ptf2-portability-fixture-only','-e','SELECT * FROM `'+database+'`.`'+table+'` ORDER BY id;',check=False);(out/'independent-database.tsv').write_text((p.stdout or'')+(p.stderr or''))
    return first_result
  if vals[:2]==['down','--volumes']:
   native_compose(self,'stop','-t','30',q['role'],check=False,timeout=90)
  return native_compose(self,*vals,**kw)
 env.save=save_hook;Deployment.compose=compose
 try:env.run(out,nacos_image=load(ENV/'zlt-original-environment-03/compose.json')['services']['nacos']['image'],redis_cluster=True)
 finally:save(out/'selected-requests.json',records);verify()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','plan','run']);p.add_argument('--home',type=Path,required=True);p.add_argument('--api');p.add_argument('--mode',choices=['original','full','selective','mirrortaint']);a=p.parse_args();h=a.home.resolve()
 if a.stage=='prepare':prepare(h)
 elif a.stage=='plan':plan(h)
 else:run(h,a.api,a.mode)
