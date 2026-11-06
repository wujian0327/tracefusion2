"""Transfer helpers for callback plans; no fixture/business-field rules."""
from query_observation_planner import require
from member_state_transfer import copy_member


def validate_fact(cfg, runtime, fact, kind):
    require(fact and fact.get('kind')==kind,'Sequential callback contract absent/different')
    require(any(p['java_runtime_version']==runtime['java_runtime_version']==fact.get('java_runtime_version')and all(p['class_sha256'].get(k)==v for k,v in fact.get('class_sha256',{}).items())and set(fact.get('class_sha256',{}))=={k for k in p['class_sha256']if k.startswith('java/')}for p in cfg['sequence_values']['profiles']),'Sequential callback runtime pins incomplete/different')


def callback_arguments(declaration, captured, member):
    spec=declaration['bootstrap_args'][1];values=list(captured)+[member]
    receiver=None if spec['tag']==6 else values.pop(0)
    return spec['handle'],receiver,values


def replay(kind,call,args,recv,cfg,runtime,state,pipes,take,execute,identity,actual,container,methods,parent,site,next_is_enter):
    from execution_dependency_state import Value
    proof=call.get('sequence_start');validate_fact(cfg,runtime,proof,kind)
    sequence=pipes.get(identity(recv));source=container(call)if kind=='for-each'else state.containers[sequence['owner']]
    stages=[{'operation':'accept','callback':identity(args[0])}]if kind=='for-each'else sequence['stages']
    require(proof['source']==source.owner and proof['epoch']==source.epoch and proof['elements']==[actual(v)for v in source.elements],'Sequential callback membership/phase differs')
    require(proof['callback']==identity(args[0])if kind=='for-each'else proof['stages']==stages,'Sequential callback identities/stages differ')
    declarations=[state.lambdas.get(stage['callback'])for stage in stages]
    if not all(d and d[0]['bootstrap_args'][1]['handle']in methods for d in declarations):return None
    output=[];error=None
    for member in list(source.elements):
        current=member;selected=True
        for stage,(declaration,captures)in zip(stages,declarations):
            impl,receiver,arguments=callback_arguments(declaration,captures,current)
            require(declaration['name']=={'map':'apply','filter':'test','accept':'accept'}[stage['operation']],'Pipeline SAM differs')
            begin=take('enter',check_frame=False)
            require(begin['method']==impl and begin['parent']==parent and begin.get('callback_call_id')==call['call_id']and begin.get('callsite')==site,'Pipeline callback method/parent/terminal differs')
            if receiver is not None:require(begin['receiver']==identity(receiver),'Pipeline callback receiver differs')
            result,error=execute(begin,arguments,receiver)
            if error is not None:break
            if stage['operation']=='map':require(result is not None,'Map returned void');current=result
            elif stage['operation']=='filter':
                require(result is not None and result.observed.get('value')in (0,1,False,True),'Filter result differs');selected=bool(result.observed['value'])
                # Uncertain selection is not evidence of a heap modification.
                current=copy_member(current,selectors=result.origins|result.selectors,uncertain=result.unknown)
                if not selected:break
        if error is not None:break
        if selected:output.append(current)
    require(not next_is_enter(),'Extra pipeline callback')
    return {'output':output,'error':error,'source':source,'proof':proof,'kind':kind}


def transfer(replay,call,ret,observed,cfg,runtime,state,actual):
    from execution_dependency_state import Value,Container
    proof=ret.get('sequence_contract');validate_fact(cfg,runtime,proof,replay['kind'])
    require(all(proof.get(k)==v for k,v in replay['proof'].items()),'Sequence completion changed start obligations')
    if replay['kind']=='for-each':
        source=replay['source'];require(proof['after']==[actual(v)for v in source.elements]and proof['after_epoch']==source.epoch,'forEach changed membership/phase')
    else:
        require(proof['result']==observed.get('object')and proof['result_elements']==[actual(v)for v in replay['output']]and ret['result_type']=='java.util.ArrayList','Collected result order/membership differs')
        state.containers[observed['object']]=Container(observed['object'],replay['output'],0,True)
    return Value(observed)
