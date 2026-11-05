"""Exact JDK8 ArrayList compaction, with interpreted actual predicate calls."""
from query_observation_planner import require
from execution_dependency_state import Value
from infer_sequence_callbacks import callback_arguments

KEYS={'java/util/List.removeIf(Ljava/util/function/Predicate;)Z','java/util/ArrayList.removeIf(Ljava/util/function/Predicate;)Z'}


def replay(call,args,cfg,state,container,actual,identity,take,execute,methods,parent,site,next_enter,poisoned_at):
    fact=call.get('remove_if_start')
    if fact is None:return None
    require(cfg['remove_if']['version']==1 and call['receiver_type']=='java.util.ArrayList'and fact['version']==1 and fact['runtime']in cfg['remove_if']['profiles'],'removeIf implementation/runtime differs')
    c=container(call);before=fact['before'];require(fact['receiver']==c.owner and fact['predicate']==call['args'][0]and before['elements']==[actual(v)for v in c.elements]and before['epoch']==c.epoch,'removeIf source/predicate/membership differs')
    require(type(before['mod_count'])is int and type(before['epoch'])is int,'removeIf modCount/epoch absent')
    base={'poison_seq':poisoned_at.get(c.owner,-1),'source':c,'proof':fact,'before':list(c.elements),'decisions':[],'error':None,'structural':False,'null':args[0].observed.get('value','not-null')is None}
    if base['null']:require(not next_enter(),'Null predicate executed callback');return base
    pair=state.lambdas.get(identity(args[0]))
    if not pair or pair[0]['bootstrap_args'][1]['handle']not in methods:return None
    declaration,captures=pair;require(declaration['name']=='test','removeIf SAM is not Predicate.test')
    for index in range(len(base['before'])):
        member=c.elements[index];impl,recv,bound=callback_arguments(declaration,captures,member)
        begin=take('enter',check_frame=False)
        require(begin['method']==impl and begin['parent']==parent and begin.get('callback_call_id')==call['call_id']and begin['callsite']==site,'removeIf callback order/method/call differs')
        if recv is not None:require(begin['receiver']==identity(recv),'removeIf captured receiver differs')
        result,error=execute(begin,bound,recv)
        if error is not None:base['error']=error;break
        require(result is not None and result.observed.get('value')in(0,1,False,True),'removeIf predicate did not return boolean')
        if poisoned_at.get(c.owner,-1)>base['poison_seq']:return None
        base['decisions'].append(result)
        if c.epoch!=before['epoch']:base['structural']=True;break
    require(not next_enter(),'removeIf extra predicate invocation')
    return base


def complete(replayed,call,finish,actual,identity,member_choices):
    fact=finish.get('remove_if');require(fact and all(fact.get(k)==v for k,v in replayed['proof'].items()),'removeIf completion proof missing/different')
    c=replayed['source'];before=replayed['proof']['before'];after=fact['after'];require(type(after['mod_count'])is int and type(after['epoch'])is int,'removeIf completion count/epoch absent');error=finish['kind']=='collection-call-throw'
    if error:
        require(fact['exception']==finish['exception']and fact['exception_type']==finish['exception_type'],'removeIf original exception differs')
        if replayed['error']is not None:require(replayed['error']['object']==finish['exception']['object'],'removeIf predicate exception replaced')
        elif replayed['null']:require(finish['exception_type']=='java.lang.NullPointerException','Null predicate failure differs')
        else:require(replayed['structural']and finish['exception_type']=='java.util.ConcurrentModificationException','Unexplained removeIf exception')
        # ArrayList has not compacted; callback effects have already executed.
        require(after['elements']==[actual(v)for v in c.elements]and after['epoch']==c.epoch,'removeIf exception lost callback effects or committed removals')
        require((after['mod_count']!=before['mod_count'])==replayed['structural']if replayed['error']is None else True,'removeIf concurrent modification proof differs')
    else:
        require(not replayed['null']and not replayed['structural']and replayed['error']is None,'removeIf returned after failure')
        decisions=replayed['decisions'];require(len(decisions)==len(replayed['before']),'removeIf callback count differs')
        kept=[];selection=frozenset().union(*(test.origins|test.selectors for test in decisions));uncertain=any(test.unknown for test in decisions)
        for member,test in zip(c.elements,decisions):
            if not bool(test.observed['value']):kept.append(Value(member.observed,member.origins,member.selectors|selection,member.unknown or uncertain,member.allocation))
        removed=len(kept)!=len(c.elements);require(type(finish['result'].get('value'))is bool and finish['result'].get('value')==removed and fact['result']==finish['result'],'removeIf result differs')
        require(after['elements']==[actual(v)for v in kept],'removeIf compacted wrong members/order')
        wrap=lambda n:(n+2**31)%2**32-2**31
        require(after['mod_count']==wrap(before['mod_count']+int(removed))and after['epoch']==wrap(before['epoch']+int(removed)),'removeIf modification/version differs')
        c.elements=kept;c.epoch=after['epoch']
        for member in kept:
            if identity(member) is not None:
                old=member_choices.get(identity(member),(frozenset(),False));member_choices[identity(member)]=(old[0]|member.selectors,old[1]or member.unknown)
    return Value(finish.get('result',{'value':None}))
