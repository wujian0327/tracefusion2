#!/usr/bin/env python3
"""Seal external common tasks before either frozen tool version is planned/run."""
import json,datetime,hashlib,subprocess,tarfile,io,shutil
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
FIRST=ROOT/'artifacts/portability-first-20261028'
ROOT_OUT=ROOT/'artifacts/external-frozen-transfer-20261029'
CURRENT=ROOT/'artifacts/account-semantics-20261028/final-candidate-01'
VERSIONS={'ae7fe8d':FIRST/'protocol-start.json','78a9534':CURRENT/'algorithm-freeze.json'}

def leaves(x,path=''):
 if isinstance(x,dict):return sum((leaves(v,path+'/'+str(k).replace('~','~0').replace('/','~1'))for k,v in x.items()),[])
 if isinstance(x,list):return sum((leaves(v,path+'/*')for v in x),[])
 return [(path or '/',x)]

def discover(model,entry):
 methods=model['methods'];classes=model['classes'];front=[entry];seen=set();calls={};boundaries={};sinks={}
 def sub(a,b,visited=None):
  if a==b:return True
  visited=set()if visited is None else visited
  if a in visited or a not in classes:return False
  visited.add(a);c=classes[a]
  return any(sub(x,b,visited)for x in [c.get('super'),*c.get('interfaces',[])]if x)
 while front:
  key=front.pop()
  if key in seen:continue
  seen.add(key);assert len(seen)<6000,'Do not silently truncate source/sink review'
  for i in methods.get(key,{}).get('instructions',[]):
   if i['op']not in(182,183,184,185):continue
   owner,name,desc=i['owner'],i['name'],i['desc'];callee=owner+'.'+name+desc
   annotations=classes.get(owner,{}).get('annotations',[])
   remote=any('FeignClient;'in v for v in annotations)or owner=='org/springframework/web/client/RestTemplate' and name.startswith(('getFor','exchange'))
   repository='/repository/'in owner or '/mapper/'in owner
   read=repository and name.lower().startswith(('find','select','count','get'))
   write=repository and name.lower().startswith(('save','insert','update','delete','remove'))
   redis='org/springframework/data/redis/core/'in owner
   record={'caller':key,'site':i['index'],'callee':callee,'kind':'rpc-read'if remote else'repository-read'if read else'redis-read'if redis and name in ('get','multiGet')else'domain-write'}
   if remote or read or redis and name in ('get','multiGet'):boundaries[callee]=record
   if write or redis and name in ('set','setIfAbsent','delete','expire','leftPush','convertAndSend')or name in ('convertAndSend','sendMessage'):sinks[(key,i['index'])]=record
   if remote or repository or redis:continue
   if callee in methods:front.append(callee)
   if owner in classes and classes[owner]['access']&512:
    for candidate,m in methods.items():
     if m['name']==name and m['desc']==desc and m.get('instructions')and sub(m['owner'],owner):front.append(candidate)
 return {'visited_methods':sorted(seen),'sources':sorted(boundaries.values(),key=lambda x:x['callee']),'sinks':list(sinks.values())}

def physical(model,owner,prop):
 while owner in model['classes']:
  fields=model['classes'][owner]['fields']
  names={f['name']for f in fields}
  if prop in names:return owner+'.'+prop
  if 'is'+prop[:1].upper()+prop[1:]in names:return owner+'.is'+prop[:1].upper()+prop[1:]
  owner=model['classes'][owner].get('super')
 return None

def target(model,api,path):
 prefix='com/ctrip/framework/apollo/'
 if api.startswith('mall-'):return physical(model,'com/macro/mall/common/api/CommonResult',path.split('/')[1])
 if api in ('apollo-1','apollo-4'):
  p=path.split('/');owner=prefix+'common/dto/NamespaceDTO'if p[1]=='baseInfo'else prefix+'portal/entity/bo/NamespaceBO'
  return physical(model,owner,p[-1])
 if api=='apollo-2':return physical(model,prefix+'common/dto/ReleaseDTO',path.split('/')[-1])
 if api=='apollo-5':
  p=path.split('/');owner=prefix+'common/dto/PageDTO'if p[1]!='content'else prefix+'common/dto/InstanceConfigDTO'if'configs'in p else prefix+'common/dto/InstanceDTO'
  return physical(model,owner,p[-1])
 return None

def prepare(out=ROOT_OUT):
 out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();(out/'sources').mkdir()
 for version,where in VERSIONS.items():
  p=load(where);sources=p.get('core_sources',p.get('sources'));frozen=out/'sources'/version
  data=subprocess.check_output(['git','archive',version,'experiments/sockshop-mirrortaint'])
  with tarfile.open(fileobj=io.BytesIO(data))as t:t.extractall(frozen)
  (frozen/'artifacts').symlink_to(ROOT/'artifacts',target_is_directory=True)
  for old,h in sources.items():assert sha(frozen/Path(old).relative_to(ROOT))==h,(version,old)
 tasks=load(FIRST/'task-seal.json');entries=[];oracles=[]
 for api in [*(f'apollo-{n}'for n in range(1,6)),*(f'mall-swarm-{n}'for n in range(1,6))]:
  old=next(q for q in tasks['entries']if q['id']==api);model=load(FIRST/'metadata'/old['role']/'model.json');original=FIRST/'original'/old['application']/'attempt04/results.json';cases=[c for c in load(original)['cases']if c['api']==api];assert len(cases)==6
  paths=sorted({p for c in cases if c['http_status']==200 and not(api=='apollo-4'and c['response']=='')for p,v in leaves(c['response'])})
  if api=='apollo-4':paths=['/']
  review=discover(model,old['entry']);entry={**old,'legacy_return_targets':old['return_targets'],'return_targets':[{'path':p,'target':target(model,api,p),'type':'actual-original-scalar-or-null','binding':'original-source-DTO-field'if target(model,api,p)else'unsupported-root-or-dynamic-target'}for p in paths],
   'read_source_candidates':review['sources'],'effect_sink_candidates':review['sinks'],'reviewed_reachable_methods':review['visited_methods'],'original_reference':str(original),'original_reference_sha256':sha(original),'input_cases':cases,'task_review_before_new_tools':True}
  entries.append(entry)
  for p in paths:
   rule={'api':api,'path':p,'kind':'unresolved','reason':'Explicit truth gap; never fill with tool graph, labels or equal values'}
   if api in ('mall-swarm-1','mall-swarm-3'):rule.update(kind='rpc-field',rpc_owner='AuthService',source_path=p,reason='Original login returns the actual AuthService.getAccessToken result; select by actual call occurrence, not matching token values.')
   if api=='mall-swarm-2':rule.update(kind='constant',sources=[],reason='register returns CommonResult.success(null, 注册成功); failure handler output is excluded unless actual root returns')
   if api=='mall-swarm-4':rule.update(kind='constant',sources=[],reason='updatePassword returns literal status 1/-1/-2/-3; control conditions are selection evidence, not data sources')
   if api=='mall-swarm-5'and p in ('/code','/message'):rule.update(kind='constant',sources=[],reason='Success/failure wrapper code and message are constants; row count remains separately unresolved')
   if api=='apollo-2':rule.update(kind='rpc-field',source_path=p,rpc_owner='RestTemplate',reason='Actual ReleaseDTO list read and corresponding member/field; order from original service, no index guessing across filtering')
   if api=='apollo-5':rule.update(kind='rpc-field',source_path=p,rpc_owner='RestTemplate',reason='Original service returns actual remote PageDTO directly, including its paging fields')
   if api=='apollo-1'and p.startswith('/baseInfo/'):rule.update(kind='rpc-field',source_path=p[len('/baseInfo'):],rpc_owner='RestTemplate',reason='NamespaceBO.baseInfo is the actual NamespaceDTO returned by the namespace HTTP read')
   if api=='apollo-1'and p in ('/format','/isPublic','/parentAppId','/comment'):rule.update(kind='repository-field',source_path={'/format':'/format','/isPublic':'/isPublic','/parentAppId':'/appId','/comment':'/comment'}[p],rpc_owner='AppNamespaceRepository',reason='Original fillAppNamespaceProperties reads actual AppNamespace repository object; missing-row fallback must be checked separately')
   if api=='apollo-1'and p=='/itemModifiedCnt':rule.update(kind='constant',sources=[],reason='Presealed empty Item fixture; loop executes zero iterations; initial literal 0. Nonempty inputs require new oracle rule.')
   if api=='apollo-4':rule.update(kind='constant',sources=[],reason='No branch fixture, original method returns literal null; empty HTTP body is not JSON null and does not certify a wire-field answer')
   oracles.append(rule)
 root_sources={str(p):sha(p)for name in ('apollo','mall-swarm')for p in(FIRST/'upstream'/name).rglob('*.java')if'/src/main/java/'in str(p)}
 save(out/'task-seal.json',{'entries':entries,'all40_retained':load(FIRST/'task-original.json')['methods'],'order':[q['id']for q in entries],'legacy_static_candidates_preserved':True,'not_a_third_party_blind_test':True,'prior_exposure':'Source inspection, prior static ae7 planning and original environment attempts already occurred. No original tool run for these ten APIs before this new seal.'})
 save(out/'oracle-before-tools.json',{'rules':oracles,'source_files_sha256':root_sources,'selection_dependencies':'Separate from data sources','root_clock_rules':'Check dates within each deployment, not cross-JVM epoch equality','coordinate_rule':'Require own message, root/call occurrence, actual object, physical field and version. Values only check consistency.','missing_raw_facts':'oracle_unavailable; TP/FP/FN null, never 0','sinks':'Review all application domain persistence/message sites and runtime occurrences; framework token/cache internals remain explicit unresolved obligations, not omitted success.'})
 save(out/'protocol-before-tools.json',{'sealed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'versions':{v:sha(p)for v,p in VERSIONS.items()},'scope':'All 40 APIs retained; first execute Apollo1..5 then Mall1..5, no replacement. Two frozen TF algorithms, original MT propagation and fixed B0 exporter; any exporter extension separate B1/version/result.',
  'no_core_agent_contract_changes':True,'no_performance':True,'input_rule':'Original six fixed cases and fixture recipes. Captcha, clocks and OAuth tokens materialize from legitimate own services; retain request before execution. No answer-driven input adjustment.',
  'task_seal_sha256':sha(out/'task-seal.json'),'oracle_sha256':sha(out/'oracle-before-tools.json'),'native_jar_sha256':sha(ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'),
  'missing_original_path_rule':'Legacy candidate with no actual original leaf stays a structural/N/A obligation. It is not an answered query or a new tool execution.',
  'migration_levels':['query declaration only','implementation/version/configuration revalidation','new public model','core or collector change'],
  'first_results':'Retain business changes, startup failure, reject, unknown, evidence_invalid, analysis_limited, oracle gaps and N/A separately. No FP/FN or complete-API accuracy for missing truth/sinks.'})
 for version in VERSIONS:
  home=out/version;home.mkdir()
  for name in ('business-jars','upstream','method-metadata'):(home/name).symlink_to(FIRST/name,target_is_directory=True)
  shutil.copyfile(out/'task-seal.json',home/'task-seal.json');shutil.copyfile(FIRST/'protocol-start.json',home/'protocol-start.json');shutil.copyfile(FIRST/'task-original.json',home/'task-original.json')
 print({'sealed':str(out),'APIs':len(entries),'actual_return_queries':sum(len(q['return_targets'])for q in entries),'sink_sites':sum(len(q['effect_sink_candidates'])for q in entries)},flush=True)
if __name__=='__main__':prepare()
