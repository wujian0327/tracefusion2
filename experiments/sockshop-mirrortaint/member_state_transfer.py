"""Shared member state only. Frameworks must validate their own operation facts."""
from execution_dependency_state import Value,Container

def member_coordinate(owner,index,epoch,observed):
    return {'owner':owner,'field':'@list:'+str(index),'version':epoch,'observed':observed}

def read_members(owner,epoch,observed,before,origin,reference_selectors=frozenset(),reference_unknown=False):
    values=[]
    for index,item in enumerate(observed):
        if 'value'in item or 'date_epoch_ms'in item:
            value=origin(member_coordinate(owner,index,epoch,item),before)if origin else Value(item,unknown=True)
        else:value=Value(item,selectors=reference_selectors,unknown=reference_unknown)
        values.append(value)
    return values

def copy_member(member,observed=None,selectors=frozenset(),uncertain=False):
    return Value(member.observed if observed is None else observed,member.origins,
                 member.selectors|selectors,member.unknown or uncertain,member.allocation)

def install_members(state,owner,values,epoch,local=False):
    # Copying is not an ownership certificate. Existing callers explicitly
    # supply local=True only when their separate allocation proof permits it.
    result=Container(owner,values,epoch,local);state.containers[owner]=result
    return result

def register_references(heap_refs,owner,members,actual):
    heap_refs[owner].update(actual(v)['object']for v in members if actual(v).get('object'))
