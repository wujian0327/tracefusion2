"""Bytecode-only constructor selection: original narrow shortcut or shared Frame."""
from query_observation_planner import require,descriptors
from plan_service_observations import callee


def assignment_effects(model,key,active=None):
    """Flatten only bounded same-class constructor delegation and exact assignments."""
    from plan_execution_kernel import constructor_writes
    active=set() if active is None else active
    require(key not in active,'Recursive constructor delegation');m=model['methods'][key]
    for ins in m['instructions']:
        if ins['op']==183 and ins['name']=='<init>':break
        require(ins['op']!=181,'Pre-initialization field assignment lacks initialized-receiver write evidence')
    try:return {f:{'argument':i} for f,i in constructor_writes(m).items()}
    except ValueError:pass
    active=active|{key};stack=[];fields={};args={};slot=1
    for index,desc in enumerate(descriptors(m['desc'])):args[slot]=index;slot+=2 if desc in ('J','D') else 1
    for ins in m['instructions']:
        op=ins['op']
        if 21<=op<=25:stack.append({'self':True} if ins['var']==0 else {'argument':args[ins['var']]})
        elif op==1:stack.append({'constant':None})
        elif 2<=op<=8:stack.append({'constant':op-3})
        elif op in (9,10,11,12,13,14,15):stack.append({'constant':op-9 if op<11 else float(op-11 if op<14 else op-14)})
        elif op in (16,17,18):require(ins.get('constant_type')!='Type','Class literal constructor effect unsupported');stack.append({'constant':ins.get('operand',ins.get('constant'))})
        elif op==183 and ins['name']=='<init>':
            values=[stack.pop() for _ in descriptors(ins['desc'])][::-1];recv=stack.pop();require(recv=={'self':True},'Delegation receiver differs')
            call=callee(ins)
            if call=='java/lang/Object.<init>()V':continue
            require(ins['owner']==m['owner'] and call in model['methods'],'Only same-class constructor delegation shortcut')
            for name,value in assignment_effects(model,call,active).items():
                require(name not in fields,'Repeated delegated constructor field assignment');fields[name]=values[value['argument']] if 'argument' in value else value
        elif op==181:
            value,recv=stack.pop(),stack.pop();name=ins['owner']+'.'+ins['name'];require(recv=={'self':True} and name not in fields,'Constructor assignment target/version differs');fields[name]=value
        elif op==177:require(not stack,'Constructor shortcut stack differs')
        else:raise ValueError('Constructor needs execution Frame at '+key+'@'+str(ins['index']))
    return fields


def constructor_start(method):
    c=method['instructions']
    require(len(c)>=3 and c[0]['op']==25 and c[0].get('var')==0 and c[1]['op']==183 and callee(c[1])=='java/lang/Object.<init>()V','Constructor Frame currently requires direct empty Object initialization')
    return 2
