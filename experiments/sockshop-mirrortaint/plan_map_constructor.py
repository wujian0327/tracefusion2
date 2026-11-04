"""Finite effect proof: fresh wrapper, literal String keys, no argument writes.

This preserves existing dependencies only. It does not manufacture Map entries
or sources, and is not a general constructor/read-only summary.
"""
from plan_collection_service import analyze
from plan_service_observations import callee
from query_observation_planner import require


def prove(model,key,candidates):
    m=model['methods'][key];code=m['instructions'];owner=m['owner'];helpers={};active=set()
    require(owner in candidates and model['classes'][owner]['super']=='java/util/HashMap','Not a directly supported wrapper')
    require(owner+'.<clinit>()V'not in model['methods'],'Wrapper initialization effects unsupported')
    require(not m['exception_handlers']and code[:2]==[{'index':0,'op':25,'var':0},{'index':1,'op':183,'owner':'java/util/HashMap','name':'<init>','desc':'()V'}],'Wrapper must first initialize only its fresh HashMap')
    def pure(k):
        require(k not in active,'Recursive pure helper');body=model['methods'][k]
        require(body['access']&8 and not body['access']&(32|256|1024)and not body['exception_handlers'],'Helper must be ordinary static bytecode')
        active.add(k)
        for i in body['instructions']:
            if i['op']==184:pure(callee(i))
            else:require(i['op']in {0,1,2,3,4,5,6,7,8,16,17,18,21,25,54,58,87,89,153,154,159,160,165,166,167,172,176,177,198,199}and i.get('constant_type')!='Type','Helper has heap, initialization, callback or unsupported effects')
        analyze(body);helpers[k]=body['owner'];active.remove(k)
    deps,operands,_,_=analyze(m)
    def leaves(defs,seen=None):
        seen=set()if seen is None else seen;result=set()
        for d in defs:
            if d<0:result.add(('argument',d));continue
            require(d not in seen,'Cyclic constructor definitions');i=code[d]
            if i['op']in(21,25,54,58,89):result|=leaves(deps[d],seen|{d})
            elif i['op']==18 and i.get('constant_type')=='String':result.add(('string',i['constant']))
            else:result.add(('other',d))
        return result
    puts=[]
    for i in code[2:]:
        op=i['op'];k=callee(i)if op in(182,183,184,185)else None
        if op==183 and k=='java/util/HashMap.put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;':
            used=operands[i['index']];require(leaves(used[2])=={('argument',-1)},'Map write does not target fresh this')
            keys=leaves(used[1]);require(keys and all(t=='string'for t,_ in keys),'Map key may execute unknown hashCode/equals');puts.append(i['index'])
        elif op==184 and k=='java/lang/Integer.valueOf(I)Ljava/lang/Integer;':pass
        elif op==184:pure(k)
        else:require(op in {0,1,2,3,4,5,6,7,8,16,17,18,21,25,54,58,87,89,153,154,159,160,165,166,167,177,198,199}and i.get('constant_type')!='Type','Constructor has external writes/calls/unsupported effects')
    require(puts,'No local Map writes')
    return {'kind':'fresh-map-arguments-preserved','constructor':key,'helpers':helpers,'literal_put_sites':puts,'class_sha256':{c:model['classes'][c]['sha256']for c in sorted({owner,*helpers.values()})},'proof':'Fresh direct HashMap initialization; all possible writes are invokespecial HashMap.put(this,literal String,value); static predicates cannot access heap; helper initialization must precede the query root; otherwise preserve no argument dependency.'}


def attach(plan,model):
    cfg=plan.get('execution_kernel');policy=plan.get('map_wrapper_observation')
    if not cfg or not policy:return
    helpers=set()
    for key,effect in list(cfg['constructors'].items()):
        if effect.get('kind')!='opaque'or key not in model['methods']:continue
        try:proof=prove(model,key,policy['candidates'])
        except (ValueError,KeyError):continue
        cfg['constructors'][key]=proof;helpers.update(proof['helpers'].values())
    cfg['initialized_effect_owners']=sorted(helpers)
