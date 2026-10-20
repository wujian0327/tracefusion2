"""Concrete offline replay over one shared field/container/call dependency state.

v1 deliberately expands evidence. Only the documented original-bytecode and
pinned library contracts produce known values. No application or query names.
"""
from collections import defaultdict
from analysis_status import AnalysisLimit
from execution_dependency_state import Value, Frame, State, Container, Call, combine
from plan_service_observations import callee
from query_observation_planner import descriptors, require


def coordinate(f):return (f['owner'],f['field'],f['version'])


def same_value(expected,actual):
    if 'date_epoch_ms' in expected:
        require(all(expected.get(k)==actual.get(k) for k in ('object','date_epoch_ms','date_type')),'Date identity/instant differs');return
    if 'value' in expected:require(expected['value']==actual.get('value'),'Execution scalar value differs')
    elif expected.get('object') is not None:require(expected['object']==actual.get('object'),'Execution object identity differs')


def infer_execution(plan,rows):
    if plan['execution_kernel']['version']>=2:
        from infer_application_execution import infer_application
        return infer_application(plan,rows)
    cfg=plan['execution_kernel'];method=plan['collection_method'];code=method['instructions'];entry=plan['entry']
    runtime=[r for r in rows if r['kind']=='execution-runtime']
    require(len(runtime)==1,'Execution runtime proof absent/duplicated')
    require(any(all(runtime[0][k]==p[k] for k in ('java_runtime_version','class_sha256')) for p in cfg['runtime_profiles']),'Execution runtime pin differs')
    # Completed roots must contain a closed call stream, including exceptional
    # exits before entering a method body. Never skip an incomplete invocation.
    pending=defaultdict(list)
    for row in rows:
        kind=row['kind'];frame=row.get('frame')
        if kind=='collection-call-enter':pending[frame].append(row['pc'])
        elif kind in ('collection-call-exit','collection-call-throw'):
            require(pending[frame] and pending[frame].pop()==row['pc'],'Execution call completion missing/mispaired')
        elif kind in ('exit','abort') and frame is not None:require(not pending[frame],'Execution root has unfinished calls')
    require(not any(pending.values()),'Execution capture has unfinished calls')
    results=[];audits=[]
    for root in [r for r in rows if r['kind']=='enter' and r['method']==entry]:
        ends=[r for r in rows if r['kind'] in ('exit','abort') and r.get('frame')==root['frame']]
        require(len(ends)==1,'Execution root completion absent/duplicated')
        if ends[0]['kind']=='abort':
            audits.append({'frame':root['frame'],'completion':'aborted','answers':0});continue
        end=ends[0];fr=Frame(root['frame']);state=State(fr);slots=0
        if not method['access']&8:fr.locals[0]=Value({'object':root['receiver']});slots=1
        for index,desc in enumerate(descriptors(method['desc'])):
            fr.locals[slots]=Value(root['args'][index],unknown=True);slots+=2 if desc in ('J','D') else 1
        relevant=[r for r in rows if r.get('frame')==root['frame'] and root['seq']<r['seq']<end['seq']]
        events=[r for r in relevant if r['kind'] in ('collection-call-enter','collection-call-exit','execution-constructed','read','write','branch')
                and (r['kind'] not in ('read','write','branch') or r['site'].startswith(entry+'@'))]
        # Constructor field writes execute in the root frame but have constructor
        # sites. They are consumed by exact constructor assignment semantics.
        writes=[r for r in relevant if r['kind']=='write']
        returns=[r for r in relevant if r['kind']=='binding-return'];require(len(returns)==1,'Execution return binding absent')
        providers=defaultdict(list)
        for row in relevant:
            if row['kind'] in ('binding-source','binding-input'):
                for i,f in enumerate(row['fields']):providers[coordinate(f)].append((row,i,f))
        pos=0; allocation_count=0;opaque_barrier=False;branch_count=0

        def take(kind):
            nonlocal pos
            require(pos<len(events) and events[pos]['kind']==kind,'Execution expected '+kind+' at pc '+str(fr.pc))
            event=events[pos];pos+=1
            if 'pc' in event:require(event['pc']==fr.pc,'Execution call pc differs')
            elif 'site' in event:require(event['site']==entry+'@'+str(fr.pc),'Execution field/branch site differs')
            return event

        def identity(value):return state.allocations.get(value.allocation) if value.allocation is not None else value.observed.get('object')
        def actual(value):
            return {'object':identity(value)} if value.allocation is not None else value.observed
        def bind(value,observed):
            if value.allocation is not None:
                require(observed.get('object') is not None,'Execution allocation lost identity')
                old=state.allocations.setdefault(value.allocation,observed['object']);require(old==observed['object'],'Execution allocation rebound')
            else:same_value(value.observed,observed)
        def origin(f,before):
            candidates=[v for v in providers.get(coordinate(f),[]) if v[0]['seq']<before]
            if len(candidates)!=1:return Value(f['observed'],unknown=True)
            row,index,source=candidates[0];same_value(source['observed'],f['observed'])
            return Value(f['observed'],frozenset({(row['seq'],index)}))
        def container(call):
            owner=call['receiver']['object'];items=call.get('collection');require(items is not None,'Execution collection content absent')
            require(call.get('receiver_type') in ('java.util.ArrayList','java.util.Arrays$ArrayList'),'Execution list implementation unsupported')
            if owner not in state.containers:
                epoch=call['collection_epoch'];values=[]
                for i,item in enumerate(items):
                    f={'owner':owner,'field':'@list:'+str(i),'version':epoch,'observed':item}
                    # Reference identity is usable without assigning the element
                    # itself a scalar origin. Subsequent field reads carry origins.
                    values.append(origin(f,call['seq']) if 'value' in item else Value(item))
                state.containers[owner]=Container(owner,values,epoch,False)
            c=state.containers[owner]
            require(c.epoch==call['collection_epoch'] and len(c.elements)==len(items),'Execution list version/length changed')
            for v,item in zip(c.elements,items):same_value(actual(v),item)
            return c
        def complete(call,ret):
            require(ret['seq']>call['seq'],'Execution completion order differs')
            return ret['result']
        while True:
            fr.steps+=1
            if fr.steps>cfg['step_limit']:raise AnalysisLimit('offline-execution','Execution iteration budget exceeded on complete capture')
            ins=code[fr.pc];op=ins['op'];pop=fr.pop
            if 21<=op<=25:
                require(ins['var'] in fr.locals,'Execution uninitialized local');fr.stack.append(fr.locals[ins['var']])
            elif 54<=op<=58:fr.locals[ins['var']]=pop()
            elif op==0:pass
            elif op==1:fr.stack.append(Value({'value':None,'object':None}))
            elif 2<=op<=8:fr.stack.append(Value({'value':op-3}))
            elif op in (16,17,18):fr.stack.append(Value({'value':ins.get('operand',ins.get('constant'))}))
            elif op==89:require(fr.stack,'Execution empty DUP');fr.stack.append(fr.stack[-1])
            elif op==87:pop()
            elif op==132:
                previous=fr.locals[ins['var']];require('value' in previous.observed,'Execution IINC lacks value')
                n=(int(previous.observed['value'])+ins['increment']+2**31)%2**32-2**31
                fr.locals[ins['var']]=previous.project({'value':n})
            elif op==187:
                allocation_count+=1;fr.stack.append(Value(allocation=allocation_count))
            elif op==178:fr.stack.append(Value(unknown=True))
            elif op==180:
                receiver=pop();read=take('read');require(identity(receiver)==read['owner'] and read['field']==ins['owner']+'.'+ins['name'],'Execution field receiver differs')
                v=state.fields.get(coordinate(read),origin(read,read['seq']))
                fr.stack.append(v)
            elif op==181:
                value,receiver=pop(),pop();write=take('write');require(identity(receiver)==write['owner'] and write['field']==ins['owner']+'.'+ins['name'],'Execution field write differs')
                bind(value,write['observed']);state.field_write(coordinate(write),value.project(write['observed']))
            elif op==192:pass  # Exact runtime invocation/schema checks retain the object identity.
            elif op in (96,100,104):
                b,a=pop(),pop();require('value' in a.observed and 'value' in b.observed,'Execution integer operands absent')
                x,y=a.observed['value'],b.observed['value'];n=x+y if op==96 else x-y if op==100 else x*y
                fr.stack.append(combine({'value':(n+2**31)%2**32-2**31},[a,b]))
            elif op in (182,183,184,185):
                args=[pop() for _ in descriptors(ins['desc'])][::-1];recv=None if op==184 else pop();key=callee(ins)
                if ins['name']=='<init>':
                    event=take('execution-constructed');bind(recv,event['receiver'])
                    require(event['receiver_type']==ins['owner'].replace('/','.'),'Execution constructor type differs')
                    require(len(args)==len(event['args']),'Execution constructor arity differs')
                    for a,b in zip(args,event['args']):bind(a,b)
                    owner=identity(recv)
                    if key=='java/util/ArrayList.<init>()V':state.containers[owner]=Container(owner,[],0,True)
                    else:
                        require(key in cfg['constructors'],'Execution constructor effects absent')
                        for name,index in cfg['constructors'][key].items():
                            matching=[w for w in writes if w['owner']==owner and w['field']==name and w['seq']<event['seq']]
                            require(len(matching)==1,'Execution constructor write missing/ambiguous');w=matching[0];bind(args[index],w['observed']);state.field_write(coordinate(w),args[index].project(w['observed']))
                else:
                    call=take('collection-call-enter');require(call['callee']==key,'Execution invoked method differs')
                    if recv is not None:bind(recv,call['receiver'])
                    require(len(args)==len(call['args']),'Execution call arity differs')
                    for a,b in zip(args,call['args']):bind(a,b)
                    ret=take('collection-call-exit');observed=complete(call,ret);v=Value(observed,unknown=True)
                    invocation=Call(str(call['seq']),fr.pc,recv,args,'normal')
                    if key in plan['response_binding']['source_calls']:
                        v=Value(observed)  # Source leaves must still match concrete boundary fields later.
                    elif key in plan['collection_getters']:
                        f=call.get('getter');require(f and f['field']==plan['collection_getters'][key]['field'],'Execution getter evidence absent')
                        same_value(f['observed'],observed)
                        v=state.fields.get(coordinate(f),origin(f,call['seq'])) if 'value' in observed else Value(observed)
                    elif key in plan['collection_setters']:
                        name=plan['collection_setters'][key]['field'];matching=[w for w in writes if w['owner']==identity(recv) and w['field']==name and call['seq']<w['seq']<ret['seq']]
                        require(len(matching)==1,'Execution setter version missing');w=matching[0];bind(args[0],w['observed']);state.field_write(coordinate(w),args[0].project(w['observed']));v=Value(observed)
                    elif ins['owner'] in ('java/util/List','java/util/ArrayList'):
                        c=container(call);name=ins['name']
                        if name in ('size','isEmpty'):
                            expected=len(c.elements) if name=='size' else not c.elements;require(observed.get('value')==expected,'Execution list size differs');v=Value(observed)
                        elif name=='get':
                            i=args[0].observed.get('value');require(isinstance(i,int) and 0<=i<len(c.elements),'Execution get index differs');v=c.elements[i].project(observed);bind(c.elements[i],observed)
                        elif name in ('contains','indexOf'):
                            needle=args[0].observed.get('value');require('value' in args[0].observed and all('value' in x.observed for x in c.elements),'Execution equality contract requires scalar elements')
                            index=next((i for i,x in enumerate(c.elements) if x.observed['value']==needle),-1);require(observed.get('value')==(index>=0 if name=='contains' else index),'Execution equality result differs');v=combine(observed,c.elements+args)
                        elif name=='iterator':
                            require(ret.get('result_type')=='java.util.ArrayList$Itr','Execution iterator implementation unsupported');state.iterators[observed['object']]=[c.owner,0,c.epoch];v=Value(observed)
                        elif name=='add':
                            require(c.local and not c.escaped and not args[0].allocation==recv.allocation,'Execution append to nonlocal/escaped/self list');require(observed.get('value') is True,'Execution append failed');c.elements.append(args[0]);c.epoch=ret['collection_epoch'];v=Value(observed)
                        else:raise ValueError('Execution list method unsupported: '+key)
                        after=ret.get('collection_after');require(after is not None and len(after)==len(c.elements),'Execution list post-state absent/differs')
                        for value,item in zip(c.elements,after):same_value(actual(value),item)
                        require(ret['collection_epoch']==c.epoch,'Execution list post-version differs')
                    elif ins['owner']=='java/util/Iterator':
                        require(call.get('receiver_type')=='java.util.ArrayList$Itr','Execution iterator type differs');require(identity(recv) in state.iterators,'Execution iterator source absent')
                        owner,index,epoch=state.iterators[identity(recv)];c=state.containers[owner];require(epoch==c.epoch,'Execution iterator concurrent modification')
                        if ins['name']=='hasNext':require(observed.get('value')==(index<len(c.elements)),'Execution hasNext differs');v=Value(observed)
                        elif ins['name']=='next':
                            require(index<len(c.elements),'Execution iterator outside contents');v=c.elements[index].project(observed);bind(c.elements[index],observed);state.iterators[identity(recv)][1]+=1
                        else:raise ValueError('Execution iterator method unsupported')
                    elif key=='java/lang/Integer.valueOf(I)Ljava/lang/Integer;':v=args[0].project(observed);same_value(args[0].observed,observed)
                    elif ins['owner']=='org/slf4j/Logger' and ins['name'] in ('info','warn','error','debug') and all('value' in a.observed for a in args):v=Value(observed)
                    else:
                        state.opaque_effect(([recv] if recv else [])+args);opaque_barrier=True
                    invocation.result=v;state.calls.append(invocation)
                    if ins['desc'].split(')')[1]!='V':fr.stack.append(v)
            elif 153<=op<=166 or op in (198,199):
                b=pop();a=pop() if 159<=op<=166 else None;event=take('branch');branch_count+=1;choice=None
                if 153<=op<=158 and 'value' in b.observed:
                    x=b.observed['value'];choice=[x==0,x!=0,x<0,x>=0,x>0,x<=0][op-153]
                elif 159<=op<=164 and 'value' in a.observed and 'value' in b.observed:
                    x,y=a.observed['value'],b.observed['value'];choice=[x==y,x!=y,x<y,x>=y,x>y,x<=y][op-159]
                elif op in (198,199):choice=(identity(b) is None and b.observed.get('value','non-null') is None);choice=choice if op==198 else not choice
                elif op in (165,166):choice=(identity(a)==identity(b));choice=choice if op==165 else not choice
                if choice is not None:require(choice==event['taken'],'Execution branch contradicts operands')
                fr.pc=ins['target'] if event['taken'] else fr.pc+1;continue
            elif op==167:fr.pc=ins['target'];continue
            elif op==176:
                returned=pop();bind(returned,end['result']);require(not fr.stack,'Execution root return stack differs');require(pos==len(events),'Execution unconsumed necessary evidence');break
            else:raise ValueError('Execution opcode not modeled: '+str(op))
            fr.pc+=1
        ret=returns[0];require(ret['result']==end['result'],'Execution return witness differs')
        for f in ret['fields']:
            owner,name,version=coordinate(f)
            if name.startswith('@list:') and owner in state.containers and state.containers[owner].local:
                c=state.containers[owner];index=int(name.split(':')[1]);require(version==c.epoch and 0<=index<len(c.elements),'Execution returned list version differs');value=c.elements[index]
            else:value=state.fields.get(coordinate(f),origin(f,ret['seq']))
            bind(value,f['observed'])
            known=not(value.unknown or opaque_barrier or owner in state.poisoned)
            results.append({'root_frame':root['frame'],'seq':ret['seq'],'path':f['path'],**f,'known':known,'origins':[list(x) for x in sorted(value.origins)],'selectors':[list(x) for x in sorted(value.selectors)]})
        audits.append({'frame':root['frame'],'completion':'normal','steps':fr.steps,'calls':len(state.calls),'branches':branch_count,'allocations':allocation_count,'opaque_barrier':opaque_barrier,'answers':len(ret['fields'])})
    return {'answers':results,'roots':audits,'evidence_policy':cfg['evidence_policy']}
