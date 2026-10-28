"""Check finite local input preservation certificates; never creates origins."""
from query_observation_planner import require
from infer_execution_kernel import coordinate

_PHASES=('command','join-enter','future','worker-enter','encoder-enter','converter','serialization-enter','serialization-exit','encoder-exit','worker-exit','join-exit')

def validate(cfg,rows):
 contract=cfg.get('feign_input_effects')
 facts=[r for r in rows if r['kind'].startswith('feign-')]
 if not contract:
  require(not facts,'Unexpected Feign protocol evidence');return {}
 runtime=[r for r in facts if r['kind']=='feign-runtime']
 if not runtime:
  require(not any(r['kind']=='feign-call-begin'for r in facts),'Feign runtime missing');return {}
 require(len(runtime)==1,'Feign runtime repeated');supported=runtime[0]['class_sha256']==contract['class_sha256'];require(runtime[0]['approved']==supported,'Feign runtime approval differs')
 starts={};ends={};result={}
 for r in facts:
  if r['kind']=='feign-call-begin':
   require(type(r['task'])is int and r['task']not in starts,'Feign task ID absent/repeated');starts[r['task']]=r
  if r['kind']=='feign-call-end':
   require(r['task']not in ends,'Feign completion repeated');ends[r['task']]=r
 require(set(starts)==set(ends),'Feign lifecycle incomplete')
 calls={r.get('call_id'):r for r in rows if r['kind']=='collection-call-enter'}
 completions={r.get('call_id'):r for r in rows if r['kind']in('collection-call-exit','collection-call-throw')}
 for task,start in starts.items():
  end=ends[task];cid=start['parent_call_id'];call=calls.get(cid);ret=completions.get(cid)
  require(call and ret and cid not in result,'Feign call missing/repeated')
  require(start['callee']in contract['potential_calls']and start['callee']==call['callee']and start['caller_frame']==call['frame'],'Feign method/caller differs')
  require(call['seq']<start['seq']<end['seq']<ret['seq'],'Feign lifecycle outside parent call')
  require(len(call['args'])==1 and call['args'][0]==start['input'],'Feign input not actual argument')
  for key in ('parent_call_id','caller_frame','callee','input','before'):require(start[key]==end[key],'Feign completion binding differs: '+key)
  certificate=ret.get('feign_effect');require(certificate and all(certificate.get(k)==end.get(k)for k in ('task','parent_call_id','caller_frame','callee','input','command','future','before','after','valid','counts','eligible','reason')),'Feign completion certificate missing/different')
  events=[r for r in facts if r.get('task')==task and r['kind']not in('feign-call-begin','feign-call-end')]
  for r in events:
   require(start['seq']<r['seq']<end['seq'],'Feign phase outside lifecycle')
   require(all(r[k]==end[k]for k in ('parent_call_id','caller_frame','callee','input','command')),'Feign phase command/input/caller differs')
  if end['valid']:
   require(supported and start['eligible']and end['eligible']and not end['reason']and ret['kind']=='collection-call-exit','Feign valid without preconditions')
   require(end['counts']==[1]*9 and end['command'].get('object')and end['future'].get('object'),'Feign task/completion cardinality differs')
   by={}
   for phase in _PHASES:
    matches=[r for r in events if r['kind']=='feign-'+phase];require(len(matches)==1,'Required Feign phase missing/repeated: '+phase);by[phase]=matches[0]
   for a,b in (('command','join-enter'),('join-enter','future'),('command','worker-enter'),('worker-enter','encoder-enter'),('encoder-enter','converter'),('converter','serialization-enter'),('serialization-enter','serialization-exit'),('serialization-exit','encoder-exit'),('encoder-exit','worker-exit'),('worker-exit','join-exit'),('future','join-exit')):require(by[a]['seq']<by[b]['seq'],'Feign phase order differs')
   for phase in ('serialization-exit','encoder-exit','worker-exit','join-exit'):require(by[phase]['normal'],'Feign valid after exceptional phase')
   require(by['converter']['valid'],'Unproved actual converter');require(by['serialization-enter']['valid'],'Unproved actual serializer')
   require(by['future']['future']==end['future'],'Feign Future identity differs')
   require(by['worker-enter']['thread']==by['worker-exit']['thread']==by['encoder-enter']['thread']==by['encoder-exit']['thread']==by['serialization-enter']['thread']==by['serialization-exit']['thread'],'Feign worker phases cross threads')
   before=end['before'];after=end['after'];require(before and before==after,'Feign input fields/versions changed')
   require(len({coordinate(f)for f in before})==len(before)and all(f['owner']==end['input']['object']and f.get('descriptor')=='Ljava/lang/String;'for f in before),'Feign field coverage/owner/shape differs')
  result[cid]=end
 return result
