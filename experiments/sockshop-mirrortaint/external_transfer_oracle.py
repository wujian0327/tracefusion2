"""Original-code rules and raw-instance facts only. No TF graph or MT labels."""
from pathlib import Path
import json,datetime

def raw(path):return [json.loads(v)for v in path.read_text().splitlines()]
def at(value,path):
 for p in path.strip('/').split('/'):
  if not p:continue
  value=value[int(p)]if isinstance(value,list)else value[p.replace('~1','/').replace('~0','~')]
 return value
def targets(value,path=''):
 if isinstance(value,dict):return sum((targets(v,path+'/'+str(k).replace('~','~0').replace('/','~1'))for k,v in value.items()),[])
 if isinstance(value,list):return sum((targets(v,path+'/'+str(i))for i,v in enumerate(value)),[])
 return [(path or '/',value)]
def wildcard(path):return '/'.join('*'if v.isdigit()else v for v in path.split('/'))
def original_root_returns(case):
 if case['http_status']!=200:return False
 if case['api']=='mall-swarm-2':
  # The original controller has exactly one normal return: success(null,
  # "注册成功"). Duplicate/captcha errors throw from the void service and
  # GlobalExceptionHandler returns a separate CommonResult over HTTP 200.
  # Preserve those requests as exception cases, not root-return field targets.
  return isinstance(case['response'],dict)and case['response'].get('code')==200
 if case['api']=='mall-swarm-3':
  # @Validated UmsAdminLoginParam has @NotEmpty username/password. The
  # frozen input-04 materialization omits username, so its HTTP-200 handler
  # response is outside the declared controller's return instances.
  body=case.get('body')or{}
  return body.get('username')not in(None,'')and body.get('password')not in(None,'')
 return True
def rule(protocol,api,path):return next(r for r in protocol['rules']if r['api']==api and r['path']==wildcard(path))
def require_complete_raw_capture(rows):
 if not rows or [r['seq']for r in rows]!=list(range(1,len(rows)+1)):raise ValueError('Raw event sequence incomplete')
 metrics=[r for r in rows if r['kind']=='metrics']
 if len(metrics)!=1 or rows[-1]['kind']!='metrics' or metrics[0].get('capture_invalid') or any(r['kind']=='problem'for r in rows):raise ValueError('Raw capture incomplete or explicitly invalid; do not use it to certify instance truth')
def native_expected(rows,root,r,path):
 if r['kind']=='constant':return []
 if r['kind']not in ('rpc-field','repository-field'):raise ValueError('Independent logical rule unresolved')
 sources=[s for s in rows if s['kind']=='source'and s.get('root')==root]
 if r['kind']=='repository-field':sources=[s for s in sources if 'AppNamespaceRepository.findByAppIdAndName'in s['call']]
 elif r['api'].startswith('mall-'):sources=[s for s in sources if 'AuthService.getAccessToken'in s['call']]
 elif r['api']=='apollo-1':sources=[s for s in sources if 'RestTemplate.exchange'in s['call']and any(f.get('field','').startswith('com/ctrip/framework/apollo/common/dto/NamespaceDTO.')for f in s['fields'])]
 else:sources=[s for s in sources if 'RestTemplate.exchange'in s['call']]
 if len(sources)!=1:raise ValueError('Actual declared source occurrence absent/ambiguous: '+str(len(sources)))
 source=sources[0];suffix=path if r['api']not in ('apollo-1',)else path[len('/baseInfo'):]if path.startswith('/baseInfo/')else r['source_path']
 prefix='/body'if r['rpc_owner']=='RestTemplate'else'';wanted=prefix+suffix
 if r['kind']=='repository-field':wanted=r['source_path']
 fields=[f for f in source['fields']if f['path']==wanted]
 if len(fields)!=1:raise ValueError('Physical source field absent/ambiguous '+wanted)
 f=fields[0]
 if not all(k in f for k in ('owner','field','version')):raise ValueError('Raw field instance coordinate incomplete')
 return [[source['call'],source['ordinal'],f['path'],f['owner'],f['field'],f['version']]]

def tf_expected(rows,ret,r,path):
 if r['kind']=='constant':return []
 if r['kind']not in ('rpc-field','repository-field'):raise ValueError('Independent logical rule unresolved')
 frames={ret['frame']}
 changed=True
 while changed:
  changed=False
  for s in rows:
   if s['kind']=='enter'and s.get('parent')in frames and s.get('frame')not in frames:frames.add(s['frame']);changed=True
 sources=[s for s in rows if s['kind']=='binding-source'and s.get('frame')in frames]
 if r['kind']=='repository-field':sources=[s for s in sources if 'AppNamespaceRepository.findByAppIdAndName'in s.get('callee','')]
 elif r['api'].startswith('mall-'):sources=[s for s in sources if 'AuthService.getAccessToken'in s.get('callee','')]
 elif r['api']=='apollo-1':sources=[s for s in sources if 'RestTemplate.exchange'in s.get('callee','')and any(f.get('field','').startswith('com/ctrip/framework/apollo/common/dto/NamespaceDTO.')for f in s['fields'])]
 else:sources=[s for s in sources if 'RestTemplate.exchange'in s.get('callee','')]
 if len(sources)!=1:raise ValueError('TF raw boundary occurrence absent/ambiguous; do not substitute an output snapshot')
 source=sources[0];wanted=path if r['api']!='apollo-1'else path[len('/baseInfo'):]if path.startswith('/baseInfo/')else r['source_path']
 wanted=('/body'if r['rpc_owner']=='RestTemplate'else'')+wanted
 fields=[f for f in source['fields']if f['path']==wanted]
 if len(fields)!=1:raise ValueError('TF raw boundary field absent/ambiguous')
 f=fields[0]
 # Full coordinate representation mirrors a source FACT, without invoking any
 # dependency propagation, alias graph, label decoder, or prediction.
 return [[source.get('callee'),source.get('frame'),source['seq'],f['path'],f['owner'],f['field'],f['version']]]
