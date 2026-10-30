"""Resolve JVM field references to declaring classes, including hidden fields."""
import copy

def canonical_model(model):
    if '_field_declarations'in model:return model
    mappings={}
    def declaration(owner,name,desc,seen=None):
        seen=set() if seen is None else seen
        if owner not in model['classes'] or owner in seen:return None
        seen=seen|{owner};c=model['classes'][owner]
        if any(f['name']==name and f['desc']==desc for f in c['fields']):return owner
        # JVM field resolution searches direct superinterfaces before the
        # superclass. Do not resolve a hidden interface field to a base field.
        for interface in c.get('interfaces',[]):
            found=declaration(interface,name,desc,seen)
            if found:return found
        return declaration(c.get('super'),name,desc,seen)
    for m in model['methods'].values():
        for ins in m['instructions']:
            if ins['op']not in (178,179,180,181):continue
            owner=declaration(ins['owner'],ins['name'],ins['desc'])
            if owner and owner!=ins['owner']:mappings[ins['owner']+'.'+ins['name']+':'+ins['desc']]=owner+'.'+ins['name']
    result=copy.deepcopy(model);result['_field_declarations']=mappings
    for m in result['methods'].values():
        for ins in m['instructions']:
            if ins['op']in (178,179,180,181):
                canonical=mappings.get(ins['owner']+'.'+ins['name']+':'+ins['desc'])
                if canonical:ins['owner']=canonical.rsplit('.',1)[0]
    return result
