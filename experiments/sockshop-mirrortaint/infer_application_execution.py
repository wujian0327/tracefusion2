"""v2 nonrecursive bytecode calls over shared heap/container state and actual frames."""
from collections import defaultdict
from execution_dependency_state import Value, Frame, State, Container, Call, combine
from query_observation_planner import require, descriptors
from plan_service_observations import callee
from analysis_status import AnalysisLimit
from infer_execution_kernel import coordinate, same_value


def infer_application(plan,rows):
    cfg=plan['execution_kernel'];runtime=[r for r in rows if r['kind']=='execution-runtime']
    require(len(runtime)==1 and any(all(runtime[0][k]==p[k] for k in ('java_runtime_version','class_sha256')) for p in cfg['runtime_profiles']),'Application runtime pin differs')
    pending=defaultdict(list);seen=set()
    for row in rows:
        kind=row['kind'];frame=row.get('frame')
        if kind=='collection-call-enter':
            cid=row.get('call_id');require(isinstance(cid,int) and cid not in seen,'Application call ID absent/repeated');seen.add(cid);pending[frame].append(cid)
        elif kind in ('collection-call-exit','collection-call-throw'):require(pending[frame] and pending[frame].pop()==row.get('call_id'),'Application call-ID completion differs')
        elif kind in ('exit','abort'):require(not pending[frame],'Application frame has unfinished calls')
    require(not any(pending.values()),'Application capture incomplete calls')
    results=[];audits=[]
    all_enters={r['frame']:r for r in rows if r['kind']=='enter'}
    require(len(all_enters)==sum(r['kind']=='enter' for r in rows),'Application invocation frame ID reused')
    for root in [r for r in rows if r['kind']=='enter' and r['method']==plan['entry']]:
        ends=[r for r in rows if r['kind'] in ('exit','abort') and r.get('frame')==root['frame']];require(len(ends)==1,'Application root completion differs');end=ends[0]
        family={root['frame']}
        changed=True
        while changed:
            before=len(family);family.update(k for k,r in all_enters.items() if r.get('parent') in family);changed=len(family)!=before
        relevant=[r for r in rows if r.get('frame') in family and root['seq']<=r['seq']<=end['seq']]
        methods=cfg['methods'];events=[r for r in relevant if r['kind'] in ('enter','exit','abort','collection-call-enter','collection-call-exit','collection-call-throw','execution-constructed','collection-catch','branch','read','write') and (r['kind'] not in ('read','write','branch') or r['site'].rsplit('@',1)[0] in methods)]
        writes=[r for r in relevant if r['kind']=='write'];providers=defaultdict(list)
        for row in relevant:
            if row['kind'] in ('binding-source','binding-input'):
                for index,f in enumerate(row['fields']):providers[coordinate(f)].append((row,index,f))
        state=State(Frame(root['frame']));pos=1;allocation_count=0;total_steps=0;branch_count=0
        fr=None;method=None;code=None;entry=None;field_seq={};poisoned_at={};frame_audits=[]
        nonlocal_owners={f['owner'] for rows_ in providers.values() for _,_,f in rows_}
        nonlocal_owners.update(v.get('object') for v in root['args'] if 'value' not in v and v.get('object'))
        if root.get('receiver'):nonlocal_owners.add(root['receiver'])
        heap_refs=defaultdict(set)
        def identity(v):return state.allocations.get(v.allocation) if v.allocation is not None else v.observed.get('object')
        def actual(v):return {'object':identity(v)} if v.allocation is not None else v.observed
        def bind(v,observed):
            if v.allocation is not None:
                require(observed.get('object') is not None,'Application allocation identity absent');old=state.allocations.setdefault(v.allocation,observed['object']);require(old==observed['object'],'Application allocation rebound')
            else:
                same_value(v.observed,observed)
                if v.observed.get('object') is not None and observed.get('object') is not None:require(v.observed['object']==observed['object'],'Application reference argument/return identity differs')
        def origin(f,before):
            candidates=[v for v in providers.get(coordinate(f),[]) if v[0]['seq']<before]
            if len(candidates)!=1 or f['owner'] in poisoned_at:return Value(f['observed'],unknown=True)
            row,index,source=candidates[0];same_value(source['observed'],f['observed']);return Value(f['observed'],frozenset({('field',row['seq'],index)}))
        def lookup(f,before):
            key=coordinate(f)
            if key in state.fields and field_seq[key]>poisoned_at.get(f['owner'],-1):return state.fields[key]
            return origin(f,before)
        def write_field(w,v):
            bind(v,w['observed']);state.field_write(coordinate(w),v.project(w['observed']));field_seq[coordinate(w)]=w['seq']
        def poison(values,seq):
            affected=set()
            todo=list(nonlocal_owners|state.poisoned)+[identity(v) for v in values if v is not None and 'value' not in v.observed]
            while todo:
                owner=todo.pop()
                if owner is None or owner in affected:continue
                affected.add(owner)
                todo.extend(heap_refs.get(owner,()))
                for (o,_,_),v in state.fields.items():
                    if o==owner and identity(v) is not None and 'value' not in v.observed:todo.append(identity(v))
                if owner in state.containers:
                    state.containers[owner].escaped=True
                    todo.extend(identity(v) for v in state.containers[owner].elements if 'value' not in v.observed)
            for owner in affected:poisoned_at[owner]=seq
            state.poisoned.update(affected)
        def take(kind,check_frame=True,check_pc=True):
            nonlocal pos
            require(pos<len(events) and events[pos]['kind']==kind,'Application expected '+kind+' at '+str(entry)+'@'+str(fr.pc))
            event=events[pos];pos+=1
            if check_frame:require(event.get('frame')==fr.invocation,'Application invocation frame differs')
            if check_pc:
                if 'pc' in event:require(event['pc']==fr.pc,'Application call pc differs')
                elif 'site' in event:require(event['site']==entry+'@'+str(fr.pc),'Application instruction site differs')
            return event
        def handle(error,typename):
            hierarchy={'java.lang.NullPointerException':{'java/lang/NullPointerException','java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'},'java.lang.IllegalArgumentException':{'java/lang/IllegalArgumentException','java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'}}
            protected=[h for h in method['exception_handlers'] if h['start']<=fr.pc<h['end']]
            if protected and typename not in hierarchy and all(h['type'] is not None for h in protected):raise AnalysisLimit('exception-dispatch','Exception hierarchy unsupported: '+str(typename))
            eligible=[h for h in protected if h['type'] is None or h['type'] in hierarchy.get(typename,set())]
            if not eligible:return False
            caught=take('collection-catch',check_pc=False);require(caught['pc']==eligible[0]['handler'] and caught['exception']==typename,'Application original handler differs');same_value(error,caught['observed'])
            fr.stack=[Value(caught['observed'],unknown=True)];fr.pc=caught['pc'];return True
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
            if owner in poisoned_at:c.elements=[Value(v.observed,unknown=True,allocation=v.allocation) for v in c.elements]
            return c
        def complete(call,ret):
            require(ret['seq']>call['seq'],'Execution completion order differs')
            return ret['result']
        def execute(begin,args,receiver):
            nonlocal fr,method,code,entry,allocation_count,total_steps,branch_count
            saved=(fr,method,code,entry)
            entry=begin['method'];method=methods[entry];code=method['instructions'];fr=Frame(begin['frame']);slot=0
            if not method['access']&8:fr.locals[0]=receiver;slot=1
            require(len(args)==len(begin['args']),'Application argument count differs')
            for index,desc in enumerate(descriptors(method['desc'])):
                bind(args[index],begin['args'][index]);fr.locals[slot]=args[index];slot+=2 if desc in ('J','D') else 1
            try:
                while True:
                    fr.steps+=1; total_steps+=1
                    if total_steps>cfg['step_limit']:raise AnalysisLimit('offline-execution','Application execution budget exceeded on complete evidence')
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
                        receiver=pop()
                        if identity(receiver) is None and receiver.observed.get('value') is None:
                            error=events[pos].get('observed',{'object':None})
                            if handle(error,'java.lang.NullPointerException'):continue
                            take('abort');return None,error
                        read=take('read');require(identity(receiver)==read['owner'] and read['field']==ins['owner']+'.'+ins['name'],'Execution field receiver differs')
                        if ins['desc'].startswith(('L','[')) and 'value' not in read['observed'] and read['observed'].get('object'):heap_refs[read['owner']].add(read['observed']['object'])
                        v=lookup(read,read['seq'])
                        if ins['desc'] in ('Z','B','C','S','I','J','F','D'):v=v.project({k:x for k,x in v.observed.items() if k!='object'})
                        fr.stack.append(v)
                    elif op==181:
                        value,receiver=pop(),pop();write=take('write');require(identity(receiver)==write['owner'] and write['field']==ins['owner']+'.'+ins['name'],'Execution field write differs')
                        bind(value,write['observed']);write_field(write,value)
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
                                    require(len(matching)==1,'Execution constructor write missing/ambiguous');w=matching[0];bind(args[index],w['observed']);write_field(w,args[index])
                        else:
                            call=take('collection-call-enter');require(call['callee']==key,'Execution invoked method differs')
                            if recv is not None:bind(recv,call['receiver'])
                            require(len(args)==len(call['args']),'Execution call arity differs')
                            for a,b in zip(args,call['args']):bind(a,b)
                            child_value=None;child_error=None
                            permitted=cfg['call_targets'].get(entry+'@'+str(fr.pc),[])
                            expected_impl=None
                            if ins['op'] in (183,184):expected_impl=key if key in permitted else None
                            else:
                                actual_owner=call['receiver_type'].replace('.','/') if call['receiver_type'] else None;suffix='.'+ins['name']+ins['desc']
                                while actual_owner:
                                    candidate=actual_owner+suffix
                                    if candidate in permitted:expected_impl=candidate;break
                                    actual_owner=cfg['class_parents'].get(actual_owner,{}).get('super')
                            if pos<len(events) and events[pos]['kind']=='enter':
                                begin=take('enter',check_frame=False)
                                require(begin['parent']==fr.invocation and begin.get('callsite')==entry+'@'+str(fr.pc),'Application parent/callsite differs')
                                require(begin['method'] in permitted and begin['method']==expected_impl,'Unplanned actual application implementation')
                                if ins['op'] in (183,184):require(begin['method']==key,'Static/special application implementation differs')
                                else:
                                    actual_owner=call['receiver_type'].replace('.','/');suffix='.'+ins['name']+ins['desc'];resolved=None
                                    while actual_owner:
                                        candidate=actual_owner+suffix
                                        if candidate in methods:resolved=candidate;break
                                        actual_owner=cfg['class_parents'].get(actual_owner,{}).get('super')
                                    require(resolved==begin['method'],'Actual virtual dispatch differs from frozen hierarchy')
                                if recv is not None:require(begin['receiver']==identity(recv),'Application receiver binding differs')
                                child_value,child_error=execute(begin,args,recv)
                            elif expected_impl and not (recv is not None and identity(recv) is None and recv.observed.get('value') is None):
                                raise ValueError('Planned application frame evidence absent')
                            exceptional=pos<len(events) and events[pos]['kind']=='collection-call-throw'
                            if exceptional:
                                failure=take('collection-call-throw');require(failure['call_id']==call['call_id'],'Application throw instance differs')
                                if child_error and child_error.get('object') is not None:require(child_error['object']==failure['exception']['object'],'Application rethrown object differs')
                                if child_error is None and not (recv is not None and identity(recv) is None and recv.observed.get('value') is None):poison(([recv] if recv else [])+args,failure['seq'])
                                if handle(failure['exception'],failure['exception_type']):continue
                                take('abort');return None,failure['exception']
                            require(child_error is None,'Exceptional child has normal caller completion')
                            ret=take('collection-call-exit');require(ret['call_id']==call['call_id'],'Application completion instance differs');observed=complete(call,ret);v=Value(observed,unknown=True)
                            invocation=Call(str(call['seq']),fr.pc,recv,args,'normal')
                            if child_value is not None:
                                bind(child_value,observed);v=child_value.project(observed)
                            elif key in plan['response_binding']['source_calls']:
                                v=Value(observed)  # Source leaves must still match concrete boundary fields later.
                            elif key in plan['collection_getters']:
                                f=call.get('getter');require(f and f['field']==plan['collection_getters'][key]['field'],'Execution getter evidence absent')
                                same_value(f['observed'],observed)
                                v=lookup(f,call['seq']) if 'value' in observed else Value(observed)
                            elif key in plan['collection_setters']:
                                name=plan['collection_setters'][key]['field'];matching=[w for w in writes if w['owner']==identity(recv) and w['field']==name and call['seq']<w['seq']<ret['seq']]
                                require(len(matching)==1,'Execution setter version missing');w=matching[0];bind(args[0],w['observed']);write_field(w,args[0]);v=Value(observed)
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
                                poison(([recv] if recv else [])+args,ret['seq'])
                            invocation.result=v;state.calls.append(invocation)
                            result_desc=ins['desc'].split(')')[1]
                            if result_desc in ('Z','B','C','S','I','J','F','D'):v=v.project({k:x for k,x in v.observed.items() if k!='object'})
                            if result_desc!='V':fr.stack.append(v)
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
                    elif 172<=op<=177:
                        returned=Value({'value':None,'object':None}) if op==177 else pop();completion=take('exit');bind(returned,completion['result']);require(not fr.stack,'Application return stack differs');return returned,None
                    elif op==191:
                        error=pop();typename=events[pos].get('exception') if pos<len(events) else None
                        if handle(actual(error),typename):continue
                        take('abort');return None,actual(error)
                    else:raise ValueError('Execution opcode not modeled: '+str(op))
                    fr.pc+=1
            finally:
                frame_audits.append({'frame':fr.invocation,'method':entry,'steps':fr.steps})
                fr,method,code,entry=saved
        root_args=[]
        for index,arg in enumerate(root['args']):
            desc=descriptors(plan['collection_method']['desc'])[index]
            if desc in ('Z','B','C','S','I','J','F','D'):arg={k:v for k,v in arg.items() if k!='object'}
            value=Value(arg)
            if 'value' in arg:value=Value(arg,frozenset({('argument',root['frame'],index)}))
            root_args.append(value)
        _,error=execute(root,root_args,Value({'object':root['receiver']}) if root.get('receiver') else None)
        require(pos==len(events),'Application unconsumed necessary evidence')
        if end['kind']=='abort':
            require(error is not None,'Application root abort disagrees with replay');audits.append({'frame':root['frame'],'completion':'aborted','steps':total_steps,'frames':frame_audits,'answers':0});continue
        require(error is None,'Application normal root has unhandled exception')
        returns=[r for r in relevant if r['kind']=='binding-return' and r['frame']==root['frame']];require(len(returns)==1,'Application return binding absent');ret=returns[0]
        for f in ret['fields']:
            owner,name,version=coordinate(f)
            if name.startswith('@list:') and owner in state.containers and state.containers[owner].local:
                c=state.containers[owner];index=int(name.split(':')[1]);require(version==c.epoch and 0<=index<len(c.elements),'Application returned container version differs');value=c.elements[index]
                if c.escaped:value=Value(f['observed'],unknown=True)
            else:value=lookup(f,ret['seq'])
            bind(value,f['observed'])
            results.append({'root_frame':root['frame'],'seq':ret['seq'],'path':f['path'],**f,'known':not value.unknown,'origins':[list(x) for x in sorted(value.origins,key=str)],'selectors':[list(x) for x in sorted(value.selectors,key=str)]})
        audits.append({'frame':root['frame'],'completion':'normal','steps':total_steps,'frames':frame_audits,'answers':len(ret['fields']),'poisoned_objects':len(poisoned_at)})
    return {'answers':results,'roots':audits,'evidence_policy':cfg['evidence_policy']}
