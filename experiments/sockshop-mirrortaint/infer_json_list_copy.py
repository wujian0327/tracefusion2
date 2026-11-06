"""Copy already typed element identities; never introduce a decoding/source edge."""
from query_observation_planner import require
from execution_dependency_state import Value
from member_state_transfer import read_members,copy_member,install_members

def transfer(plan,index,root,call,ret,recv,args,state,actual,origin=None):
    proof=ret.get('json_list_copy')
    if not proof or not proof.get('valid'):return None
    cfg=plan.get('json_list_copy')
    require(cfg and cfg['version']==proof['version']==1 and proof['class_sha256']==cfg['class_sha256']and proof['runtime']in cfg['profiles'],'JSON list contract/runtime differs')
    init=index[('json-list-initialized',proof['initialized_seq'])]
    require(len(init)==1 and init[0]['loader']==proof['loader']and init[0]['class']=='com/alibaba/fastjson2/JSONFactory','JSON list initialization missing/ambiguous')
    for name,digest in cfg['class_sha256'].items():
        loaded=index[('json-list-class',name)]
        candidates=[r for r in loaded if r['loader']==proof['loader']]
        require(len(candidates)==1 and candidates[0]['class_sha256']==digest and candidates[0]['seq']<call['seq'],'JSON list loaded implementation missing/ambiguous')
        if name=='com/alibaba/fastjson2/JSONFactory':require(candidates[0]['seq']<init[0]['seq'],'JSON list initializer precedes loaded implementation')
    if init[0]['seq']>=root['seq']:return None
    hits=index[('json-list-cache',call['call_id'])]
    require(len(hits)==1 and hits[0]['seq']==proof['cache_seq'],'JSON list actual cache lookup missing/ambiguous')
    hit=hits[0]
    require(call['seq']<hit['seq']<ret['seq']and hit['frame']==call['frame']and hit['thread']==call['thread']and hit.get('message')==call.get('message')and hit['cache_hit']is True and hit['field_based']is False and hit['cache_type']=='java.util.concurrent.ConcurrentHashMap'and hit['provider']==proof['provider']and hit['target_class']==proof['target_class']==args[0].observed['object'],'JSON list reader lookup/call differs')
    require(call['receiver_type']=='com.alibaba.fastjson2.JSONArray'and ret['result_type']=='java.util.ArrayList'and call['collection_epoch']==ret['collection_epoch']and call['collection']==ret['collection_after']==proof['members'],'JSON list members/identity stage differs')
    owner=ret['result']['object'];require(owner!=recv.observed['object']and owner not in state.containers and proof['result_epoch']==0,'JSON list result is not fresh')
    previous=state.containers.get(recv.observed['object'])
    if previous is not None:
        require(previous.epoch==call['collection_epoch']and [actual(v)for v in previous.elements]==proof['members'],'JSON list input dependency state differs')
        values=[copy_member(v,item)for v,item in zip(previous.elements,proof['members'])]
    else:values=read_members(recv.observed['object'],call['collection_epoch'],proof['members'],call['seq'],origin,recv.selectors,recv.unknown)
    install_members(state,owner,values,0)
    return Value(ret['result'])
