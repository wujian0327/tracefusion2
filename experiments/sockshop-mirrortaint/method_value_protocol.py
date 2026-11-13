"""Method-value v1: declaration-directed values; no runtime Number inference."""
from query_observation_planner import require
from field_value_protocol import primitive,PRIMITIVES


def parse_descriptor(desc):
    require(isinstance(desc,str) and desc.startswith('('),'Method descriptor absent/invalid')
    def typ(i,void=False):
        require(i<len(desc),'Truncated method descriptor');start=i;c=desc[i]
        if c in PRIMITIVES or c=='V'and void:return c,i+1
        if c=='L':
            end=desc.find(';',i);name=desc[i+1:end]
            require(end>i+1 and not any(x in name for x in '.;[()') and all(name.split('/')),'Invalid reference descriptor');return desc[i:end+1],end+1
        if c=='[':
            while i<len(desc)and desc[i]=='[':i+=1
            require(i-start<=255,'Array descriptor dimension bound');_,end=typ(i);return desc[start:end],end
        require(False,'Invalid descriptor type')
    args=[];i=1
    while i<len(desc)and desc[i]!=')':
        t,i=typ(i);args.append(t)
    require(i<len(desc)and desc[i]==')','Method return descriptor absent');returned,end=typ(i+1,True)
    require(end==len(desc) and sum(2 if a in ('J','D')else 1 for a in args)<=255,'Invalid method descriptor/slots')
    return args,returned


def value(observed,desc):
    require(isinstance(observed,dict),'Method value absent')
    if desc in PRIMITIVES:primitive(observed,desc)
    elif desc=='V':require(observed=={'object':None,'value':None,'void':True},'Void result encoding differs')
    else:
        require('primitive'not in observed and 'void'not in observed and 'object'in observed,'Reference encoded as primitive/void or lacks identity')
        if observed['object']is None:require(observed=={'object':None,'value':None},'Null reference differs')
        else:require(isinstance(observed['object'],str),'Reference identity invalid')


def validate(plan,rows):
    headers=[r for r in rows if r.get('kind')=='start'];version=headers[0].get('method_value_version',0)if len(headers)==1 else 0
    require(type(version)is int and version in (0,1),'Unsupported method value protocol')
    if not version:
        require(not any('method_descriptor'in r for r in rows),'Method descriptor without versioned header');return 0
    cfg=plan.get('execution_kernel',{});methods=cfg.get('methods',{});frames={};calls={};pending={};sources={}
    def desc(key):
        require(isinstance(key,str)and '('in key,'Original method signature absent');d=key[key.index('('):];parse_descriptor(d);return d
    def declared(row,expected,args_key=None,result=False):
        require(row.get('method_descriptor')==expected,'Method descriptor differs/absent');args,returned=parse_descriptor(expected)
        if args_key:
            values=row.get(args_key);require(isinstance(values,list)and len(values)==len(args),'Method argument count differs')
            for d,v in zip(args,values):value(v,d)
        if result:value(row.get('result'),returned)
    def instruction(row,caller=None):
        key=caller or row.get('method',plan.get('entry'));m=methods.get(key)
        if m is None and plan.get('collection_method')and key==plan.get('entry'):m=plan['collection_method']
        require(m is not None and type(row.get('pc'))is int and 0<=row['pc']<len(m['instructions']),'Original method/call PC absent');return m['instructions'][row['pc']]
    for row in rows:
        k=row['kind'];frame=row.get('frame');thread=row.get('thread',0)
        if k=='enter':
            key=row.get('method');require(key in plan.get('frame_methods',[]) or key in methods,'Unplanned method value Frame')
            require(frame not in frames,'Duplicate method value Frame');frames[frame]=key;declared(row,desc(key),'args')
        elif k in ('exit','abort'):
            require(frame in frames,'Method completion without Frame');declared(row,desc(frames[frame]),result=k=='exit')
        elif k=='collection-call-enter':
            ins=instruction(row);require(ins['op']in (182,183,184,185)and row.get('callee')==ins['owner']+'.'+ins['name']+ins['desc'],'Method value original call differs');declared(row,ins['desc'],'args')
            calls[(frame,row.get('call_id',row['pc']))]=ins['desc'];pending.setdefault((thread,frame),[]).append(ins['desc'])
        elif k in ('collection-call-exit','collection-call-throw'):
            stack=pending.get((thread,frame),[]);require(stack,'Method call completion without entry');expected=stack.pop();declared(row,expected,result=k=='collection-call-exit')
        elif k in ('execution-constructor-enter','execution-constructed','execution-constructor-throw'):
            ins=instruction(row,frames.get(frame));require(ins['op']==183 and ins['name']=='<init>','Original constructor call absent');declared(row,ins['desc'],'args'if k!='execution-constructor-throw'else None)
            if k=='execution-constructed':value(row.get('receiver'),'Ljava/lang/Object;');require(row['receiver']['object']is not None,'Constructed receiver absent')
        elif k=='execution-lambda':
            ins=instruction(row);require(ins['op']==186 and ins==row.get('instruction'),'Original lambda capture descriptor differs');declared(row,ins['desc'],'captures')
        elif k=='execution-direct-dispatch':
            expected=calls.get((frame,row.get('call_id')));require(expected is not None and desc(row.get('callee'))==expected,'Method dispatch call absent/different');declared(row,expected,'args')
        elif k=='async-submit-begin'and row.get('supported'):
            key=row.get('method');require(key in methods,'Async Method bytecode absent');declared(row,desc(key),'args')
        elif k=='source-call-enter':
            proof=plan.get('source_observation',{}).get('sites',{}).get(row.get('site'));require(proof and proof['callee']==row.get('callee'),'Observation-only original call absent');declared(row,desc(row['callee']),'args');sources[row['source_call_id']]=row['callee']
        elif k in ('source-call-exit','source-call-throw'):
            key=sources.get(row.get('source_call_id'));require(key==row.get('callee'),'Observation-only completion without call');declared(row,desc(key),result=k=='source-call-exit')
        elif k=='date-call':declared(row,desc(row.get('callee')),result=True)
        elif k=='binding-return':
            if plan.get('session_history'):
                key=frames.get(frame);require(key in plan['session_history']['roots'],'Session return has no declared actual root')
                declared(row,desc(key),result=True)
            else:declared(row,desc(plan.get('entry')),result=True)
        if row.get('async_future'):
            fact=row['async_future'];expected=row.get('method_descriptor');declared(fact,expected,result=fact.get('completion')=='normal')
        if row.get('remove_if'):
            fact=row['remove_if'];declared(fact,row.get('method_descriptor'),result='result'in fact)
    return 1
