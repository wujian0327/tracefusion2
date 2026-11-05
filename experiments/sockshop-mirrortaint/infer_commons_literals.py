"""Literal tokenization and String-only membership; retain all dependency/choice inputs."""
from query_observation_planner import require
from execution_dependency_state import Value

def transfer(cfg,index,root,call,ret,args,state,actual):
    proof=ret.get('commons_literal');contract=cfg.get('commons_literals')
    if not proof or not proof['valid']:return None
    require(contract and contract['version']==proof['version']==2 and proof['callee']==call['callee'] and contract['class_sha256'].get(proof['declaring'])==proof['class_sha256']and proof['runtime']in contract['profiles'],'Commons call/runtime differs')
    require(contract.get('resolved_calls',{}).get(call['callee'],{}).get('declaring')==proof['declaring'],'Unproved inherited static resolution')
    inits=index[('commons-initialized',proof['initialized_seq'])]
    require(len(inits)==1 and inits[0]['class']==proof['declaring']and inits[0]['class_sha256']==proof['class_sha256']and inits[0]['class_object']==proof['initialized_class'],'Commons initialization evidence differs')
    loaded=index[('commons-framework',proof['declaring'])]
    require(len(loaded)==1 and loaded[0]['class_sha256']==proof['class_sha256']and loaded[0]['seq']<inits[0]['seq'],'Commons loaded bytes differ')
    deps=proof['initializations']
    require(len(deps)==len(contract['class_sha256']) and {d['class']for d in deps}==set(contract['class_sha256']),'Commons transitive initialization proof incomplete')
    for dependency in deps:
        observed=index[('commons-initialized',dependency['seq'])]
        require(observed==[dependency]and dependency['class_sha256']==contract['class_sha256'][dependency['class']],'Commons transitive initializer identity differs')
    if not all(d['seq']<root['seq']for d in deps):return None  # ordinary ineligibility: original opaque effect remains
    array=proof['array'];owner=array['array']['object'];observed=ret['result']
    if '.split('in call['callee']:
        text,sep=(a.observed.get('value')for a in args)
        require(type(text)is str and type(sep)is str and len(sep)==1 and ord(sep)<65536 and not 0xD800<=ord(sep)<=0xDFFF,'Commons split argument shape differs')
        expected=[part for part in text.split(sep)if part]
        require(ret['result_type']=='[Ljava.lang.String;'and [v.get('value')for v in array['elements']]==expected and owner==observed['object']and owner not in state.arrays and array['version']==0 and array['element_versions']==[0]*len(expected)and array['component']=='java.lang.String','Commons split fresh array/value differs')
        origins=args[0].origins|args[1].origins;selectors=args[0].selectors|args[1].selectors;unknown=any(a.unknown for a in args)
        state.arrays[owner]={'elements':[Value(v,origins,selectors,unknown)for v in array['elements']],'version':0,'versions':[0]*len(expected)}
        return Value(observed)
    require(ret['result_type']=='java.lang.Boolean'and call.get('argument_types',[None])[0]=='[Ljava.lang.String;'and array['component']=='java.lang.String'and args[0].observed.get('object')==owner,'Commons contains array identity/type differs')
    array_state=state.arrays.get(owner)
    if array_state is None:return None
    require(array['version']==array_state['version']and array['element_versions']==array_state['versions']and array['elements']==[actual(v)for v in array_state['elements']],'Commons contains array stage differs')
    needle=args[1].observed.get('value');values=array_state['elements'];require(needle is None or type(needle)is str,'Commons contains arbitrary equals callback')
    require(all(v.observed.get('value')is None or type(v.observed.get('value'))is str for v in values),'Commons contains mutable element')
    require(type(observed.get('value'))is bool and observed['value']==any(v.observed.get('value')==needle for v in values),'Commons membership result differs')
    operands=values+args
    return Value(observed,frozenset().union(*(v.origins for v in operands)),frozenset().union(*(v.selectors for v in operands)),any(v.unknown for v in operands))
