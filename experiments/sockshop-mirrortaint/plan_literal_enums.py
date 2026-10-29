"""Closed proof for private, literal-initialized enum state, independent of names.

No library/client/save effects are inferred here. Reflection/native mutation and
unmodeled class loading are outside the supported execution model.
"""
from query_observation_planner import require,descriptors


def prove(model,owner):
    c=model['classes'][owner]
    require(c['super']=='java/lang/Enum' and c['access']&16384,'Not a concrete enum')
    constants=[f['name']for f in c['fields']if f['access']&16384]
    data=[f for f in c['fields']if not f['access']&8]
    require(0<len(constants)<=128 and data,'Literal enum requires bounded constants and state')
    require(all(f['access']&2 and f['desc']in ('I','J','Ljava/lang/String;')for f in data),'Enum state must be private int/long/String fields')
    arrays=[f for f in c['fields']if f['access']&8 and not f['access']&16384]
    require(len(arrays)==1 and arrays[0]['desc']=='[L'+owner+';' and arrays[0]['access']&4096,'Additional enum statics unsupported')
    methods={k:v for k,v in model['methods'].items()if v['owner']==owner}
    ctors=[(k,v)for k,v in methods.items()if v['name']=='<init>']
    require(len(ctors)==1,'Multiple enum constructors unsupported')
    ctor_key,ctor=ctors[0];params=descriptors(ctor['desc'])
    require(ctor['access']&2 and not ctor['exception_handlers'] and params[:2]==['Ljava/lang/String;','I'],'Enum constructor preconditions differ')
    code=[{k:v for k,v in i.items()if k!='index'}for i in ctor['instructions']]
    prefix=[{'op':25,'var':0},{'op':25,'var':1},{'op':21,'var':2},{'op':183,'owner':'java/lang/Enum','name':'<init>','desc':'(Ljava/lang/String;I)V'}]
    require(code[:4]==prefix and code[-1]=={'op':177} and len(code)==5+3*len(data),'Enum constructor has extra effects')
    slots={};slot=1
    for i,d in enumerate(params):slots[slot]=(i,d);slot+=2 if d=='J'else 1
    fields={};definitions={f['name']:f for f in data}
    for i in range(4,len(code)-1,3):
        recv,load,write=code[i:i+3];name=write.get('name');arg,desc=slots.get(load.get('var'),(-1,None))
        require(recv=={'op':25,'var':0} and arg>=2 and load['op']==(22 if desc=='J'else 25 if desc=='Ljava/lang/String;'else 21),'Enum constructor assignment not a direct argument')
        require(name in definitions and name not in fields and write=={'op':181,'owner':owner,'name':name,'desc':desc}and definitions[name]['desc']==desc,'Enum field assignment differs')
        fields[name]={'field':owner+'.'+name,'descriptor':desc,'argument':arg}
    for key,m in model['methods'].items():
        for ins in m['instructions']:
            if ins['op']==181 and ins['owner']==owner:
                require(key==ctor_key,'Enum state has a write outside its closed constructor')
            if ins['op']==179 and ins['owner']==owner:
                require(key==owner+'.<clinit>()V','Enum statics modified outside initializer')
            if ins['op']==183 and ins.get('owner')==owner and ins.get('name')=='<init>':
                require(key==owner+'.<clinit>()V','Enum allocation outside initializer')
    initial=methods[owner+'.<clinit>()V'];require(not initial['exception_handlers'],'Enum initializer handlers unsupported')
    code=[{k:v for k,v in i.items()if k!='index'}for i in initial['instructions']];pc=0;values={}
    def take(expected):
        nonlocal pc
        require(pc<len(code)and code[pc]==expected,'Enum initializer has unproved effects at '+str(pc));pc+=1
    def literal(desc):
        nonlocal pc
        require(pc<len(code),'Missing enum literal');ins=code[pc];pc+=1;op=ins['op']
        if desc=='Ljava/lang/String;':require(op==18 and ins.get('constant_type')=='String','Nonliteral enum string');return ins['constant']
        if desc=='J':require(op in (9,10)or op==18 and ins.get('constant_type')=='Long','Nonliteral enum long');return op-9 if op!=18 else ins['constant']
        require(op in range(2,9)or op in (16,17)or op==18 and ins.get('constant_type')=='Integer','Nonliteral enum integral value')
        return op-3 if op in range(2,9)else ins.get('operand',ins.get('constant'))
    from plan_foundation_values import iconst
    for ordinal,name in enumerate(constants):
        take({'op':187,'type':owner});take({'op':89});take({'op':18,'constant':name,'constant_type':'String'});take(iconst(ordinal))
        args=[name,ordinal]+[literal(d)for d in params[2:]]
        take({'op':183,'owner':owner,'name':'<init>','desc':ctor['desc']});take({'op':179,'owner':owner,'name':name,'desc':'L'+owner+';'})
        values[name]=[{**f,'value':args[f['argument']]}for f in fields.values()]
    take(iconst(len(constants)));take({'op':189,'type':owner})
    for ordinal,name in enumerate(constants):
        for ins in ({'op':89},iconst(ordinal),{'op':178,'owner':owner,'name':name,'desc':'L'+owner+';'},{'op':83}):take(ins)
    take({'op':179,'owner':owner,'name':arrays[0]['name'],'desc':arrays[0]['desc']});take({'op':177});require(pc==len(code),'Trailing enum initializer effects')
    return {'class_sha256':c['sha256'],'constants':constants,'literal_fields':values,'constructor':ctor_key,'proof':'Private scalar fields, exact Enum initialization and argument assignments, literal-only constant/values initialization, no other application writes or constructor calls. Runtime identity, values and field versions still required.'}
