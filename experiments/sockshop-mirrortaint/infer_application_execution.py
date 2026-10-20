"""v2 nonrecursive bytecode calls over shared heap/container state and actual frames."""
from collections import defaultdict
from execution_dependency_state import Value, Frame, State, Container, Call, combine
from query_observation_planner import require, descriptors
from plan_service_observations import callee
from analysis_status import AnalysisLimit
from infer_execution_kernel import coordinate, same_value


def infer_application(plan,rows):
    from infer_date_projection import validate_date_runtime
    validate_date_runtime(plan,rows)
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
        methods=cfg['methods'];events=[r for r in relevant if r['kind'] in ('enter','exit','abort','collection-call-enter','collection-call-exit','collection-call-throw','execution-constructed','execution-constructor-throw','execution-lambda','execution-class-literal','execution-array','execution-array-throw','collection-catch','branch','read','write') and (r['kind'] not in ('read','write','branch') or r['site'].rsplit('@',1)[0] in methods)]
        writes=[r for r in relevant if r['kind']=='write'];providers=defaultdict(list)
        for row in relevant:
            if row['kind'] in ('binding-source','binding-input'):
                for index,f in enumerate(row['fields']):providers[coordinate(f)].append((row,index,f))
        state=State(Frame(root['frame']));pos=1;allocation_count=0;total_steps=0;branch_count=0
        http_entities={};response_entities={};class_literals={};date_values={};calendars={};environment_facts=[]
        fr=None;method=None;code=None;entry=None;field_seq={};poisoned_at={};frame_audits=[]
        nonlocal_owners={f['owner'] for rows_ in providers.values() for _,_,f in rows_}
        nonlocal_owners.update(v.get('object') for v in root['args'] if 'value' not in v and v.get('object'))
        if root.get('receiver'):nonlocal_owners.add(root['receiver'])
        heap_refs=defaultdict(set);opaque_frames=[]
        def identity(v):return state.allocations.get(v.allocation) if v.allocation is not None else v.observed.get('object')
        def actual(v):return {'object':identity(v)} if v.allocation is not None else v.observed
        def bind(v,observed):
            if v.allocation is not None:
                require(observed.get('object') is not None,'Application allocation identity absent');old=state.allocations.setdefault(v.allocation,observed['object']);require(old==observed['object'],'Application allocation rebound')
            else:
                if 'date_epoch_ms' in v.observed and v.observed.get('object') in poisoned_at:
                    require(v.observed.get('object')==observed.get('object'),'Opaque Date reference identity differs');return
                same_value(v.observed,observed)
                if v.observed.get('object') is not None and observed.get('object') is not None:require(v.observed['object']==observed['object'],'Application reference argument/return identity differs')
        def origin(f,before):
            candidates=[v for v in providers.get(coordinate(f),[]) if v[0]['seq']<before]
            if len(candidates)!=1:return Value(f['observed'],unknown=True)
            if f['owner'] in poisoned_at and not (candidates[0][0]['kind']=='http-json' and candidates[0][0]['seq']>poisoned_at[f['owner']]):return Value(f['observed'],unknown=True)
            row,index,source=candidates[0];same_value(source['observed'],f['observed']);return Value(f['observed'],frozenset({('http',row['seq'],source['path']) if row['kind']=='http-json' else ('field',row['seq'],index)}))
        def lookup(f,before):
            key=coordinate(f)
            if 'date_epoch_ms' in f['observed']:
                obj=f['observed'].get('object')
                if obj in poisoned_at:return Value(f['observed'],unknown=True)
                if obj in date_values:return date_values[obj].project(f['observed'])
            if key in state.fields and field_seq[key]>poisoned_at.get(f['owner'],-1):return state.fields[key]
            return origin(f,before)
        def write_field(w,v):
            if 'date_epoch_ms' in w['observed'] and w['observed']['object'] in date_values:v=date_values[w['observed']['object']]
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
                if owner in state.streams:
                    todo.append(state.streams[owner][0])
                    if len(state.streams[owner])==3:todo.append(identity(state.streams[owner][2]))
                if owner in state.optionals and state.optionals[owner] is not None:todo.append(identity(state.optionals[owner]))
                if owner in state.lambdas:todo.extend(identity(v) for v in state.lambdas[owner][1] if 'value' not in v.observed)
                if owner in state.arrays:
                    todo.extend(identity(v) for v in state.arrays[owner]['elements'] if 'value' not in v.observed)
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
            for exception in ('ArrayIndexOutOfBoundsException','ArrayStoreException','NegativeArraySizeException'):
                hierarchy['java.lang.'+exception]={'java/lang/'+exception,'java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'}
            hierarchy['java.lang.ArrayIndexOutOfBoundsException'].add('java/lang/IndexOutOfBoundsException')
            if protected and typename not in hierarchy and all(h['type'] is not None for h in protected):raise AnalysisLimit('exception-dispatch','Exception hierarchy unsupported: '+str(typename))
            eligible=[h for h in protected if h['type'] is None or h['type'] in hierarchy.get(typename,set())]
            if not eligible:return False
            caught=take('collection-catch',check_pc=False);require(caught['pc']==eligible[0]['handler'] and caught['exception']==typename,'Application original handler differs');same_value(error,caught['observed'])
            fr.stack=[Value(caught['observed'],unknown=True)];fr.pc=caught['pc'];return True
        def container(call):
            owner=call['receiver']['object'];items=call.get('collection');require(items is not None,'Execution collection content absent')
            require(call.get('receiver_type') in ('java.util.ArrayList','java.util.Arrays$ArrayList','java.util.Collections$SingletonList','java.util.Collections$EmptyList'),'Execution list implementation unsupported')
            if owner not in state.containers:
                epoch=call['collection_epoch'];values=[]
                for i,item in enumerate(items):
                    f={'owner':owner,'field':'@list:'+str(i),'version':epoch,'observed':item}
                    # Reference identity is usable without assigning the element
                    # itself a scalar origin. Subsequent field reads carry origins.
                    values.append(origin(f,call['seq']) if 'value' in item or 'date_epoch_ms' in item else Value(item))
                state.containers[owner]=Container(owner,values,epoch,False)
            c=state.containers[owner]
            require(c.epoch==call['collection_epoch'] and len(c.elements)==len(items),'Execution list version/length changed')
            for v,item in zip(c.elements,items):same_value(actual(v),item)
            if owner in poisoned_at:c.elements=[Value(v.observed,unknown=True,allocation=v.allocation) for v in c.elements]
            return c
        def complete(call,ret):
            require(ret['seq']>call['seq'],'Execution completion order differs')
            return ret['result']
        def framework_fact(event,kind):
            fact=event.get('framework_contract')
            require(fact and fact['kind']==kind and fact['class_sha256']==cfg['framework_contracts']['class_sha256'],'Framework witness kind/library differs')
            return fact
        def execute(begin,args,receiver):
            nonlocal fr,method,code,entry,allocation_count,total_steps,branch_count,pos
            saved=(fr,method,code,entry)
            entry=begin['method'];method=methods[entry];code=method['instructions'];fr=Frame(begin['frame']);fr.pc=cfg.get('constructor_starts',{}).get(entry,0);slot=0
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
                    elif op==18 and ins.get('constant_type')=='Type':
                        event=take('execution-class-literal');require(event['descriptor']==ins['constant'] and event['class_sha256']==cfg['class_literals'][ins['constant']],'Class literal descriptor/hash differs')
                        require(event['observed'].get('object') is not None,'Class literal identity missing');class_literals[event['observed']['object']]=ins['constant'];fr.stack.append(Value(event['observed']))
                    elif op in (16,17,18):fr.stack.append(Value({'value':ins.get('operand',ins.get('constant'))}))
                    elif op==89:require(fr.stack,'Execution empty DUP');fr.stack.append(fr.stack[-1])
                    elif op==87:pop()
                    elif op==132:
                        previous=fr.locals[ins['var']];require('value' in previous.observed,'Execution IINC lacks value')
                        n=(int(previous.observed['value'])+ins['increment']+2**31)%2**32-2**31
                        fr.locals[ins['var']]=previous.project({'value':n})
                    elif op==186:
                        captured=[pop() for _ in descriptors(ins['desc'])][::-1];event=take('execution-lambda');require(event['instruction']==ins and event['site']==entry+'@'+str(fr.pc),'Lambda bootstrap/implementation evidence differs')
                        require(len(captured)==len(event['captures']),'Lambda capture arity differs')
                        for value,observed in zip(captured,event['captures']):bind(value,observed)
                        observed=event['lambda'];owner=observed.get('object');require(owner is not None and '$$Lambda$' in event['lambda_type'],'Lambda actual instance absent')
                        fact=(ins,captured)
                        if owner in state.lambdas:require(state.lambdas[owner]==fact,'Lambda instance rebound to different captures')
                        state.lambdas[owner]=fact;fr.stack.append(Value(observed))
                    elif op in (189,190,50,83):
                        if op==189:count=pop();array=None;index=count.observed.get('value');value=None
                        elif op==190:array=pop();index=-1;value=None
                        elif op==50:index_value=pop();index=index_value.observed.get('value');array=pop();value=None
                        else:value=pop();index=pop().observed.get('value');array=pop()
                        require(isinstance(index,int),'Array index/length absent')
                        failed=pos<len(events) and events[pos]['kind']=='execution-array-throw';event=take('execution-array-throw' if failed else 'execution-array')
                        require(event['operation']=={189:'new',190:'length',50:'load',83:'store'}[op] and event['index']==index,'Array operation/index differs')
                        if array is not None:bind(array,event['array'])
                        owner=event['array'].get('object');a=state.arrays.get(owner)
                        if op!=189 and owner is not None:
                            if a is None:
                                a={'elements':[Value(v,unknown=True) for v in event['elements']],'version':event['version'],'versions':event['element_versions']};state.arrays[owner]=a
                            require(a['version']==event['version'] and a['versions']==event['element_versions'] and len(a['elements'])==len(event['elements']),'Array version/size differs')
                            for v,o in zip(a['elements'],event['elements']):bind(v,o)
                        if failed:
                            typename=event['exception_type'];expected=('java.lang.NegativeArraySizeException' if op==189 and index<0 else 'java.lang.NullPointerException' if owner is None else 'java.lang.ArrayIndexOutOfBoundsException' if op in (50,83) and not 0<=index<len(a['elements']) else 'java.lang.ArrayStoreException' if op==83 and event.get('store_compatible') is False else None)
                            require(typename==expected,'Array exceptional semantics differ')
                            if handle(event['exception'],typename):continue
                            take('abort');return None,event['exception']
                        if op==189:
                            require(index>=0 and owner is not None and owner not in state.arrays and len(event['elements'])==index and event['version']==0 and event['element_versions']==[0]*index,'Array allocation evidence differs')
                            expected_component=ins['type'].replace('/','.');require(event['component']==expected_component,'Array runtime component differs')
                            require(all(v.get('value','not-null') is None for v in event['elements']),'Array default elements not null')
                            state.arrays[owner]={'elements':[Value(v) for v in event['elements']],'version':0,'versions':[0]*index};fr.stack.append(Value(event['array']))
                        elif op==190:require(event['result']==len(a['elements']),'Array length differs');fr.stack.append(Value({'value':event['result']}))
                        elif op==50:
                            require(0<=index<len(a['elements']),'Array index outside contents');v=a['elements'][index];bind(v,event['result']);fr.stack.append(Value(event['result'],v.origins,v.selectors|index_value.origins|index_value.selectors,v.unknown or owner in poisoned_at,v.allocation))
                        else:
                            require(0<=index<len(a['elements']) and event.get('store_compatible') is True and event['after_version']==a['version']+1,'Array write type/version differs');bind(value,event['value']);a['elements'][index]=value;a['versions'][index]+=1;a['version']=event['after_version'];require(a['versions']==event['after_element_versions'],'Array element write version differs')
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
                            effect=cfg['constructors'].get(key);require(effect is not None,'Execution constructor effects absent')
                            child_error=None
                            if effect.get('kind')=='frame':
                                begin=take('enter',check_frame=False);require(begin['method']==key and begin['parent']==fr.invocation and begin['callsite']==entry+'@'+str(fr.pc),'Constructor Frame binding differs')
                                bind(recv,{'object':begin['receiver']});_,child_error=execute(begin,args,recv)
                            if pos<len(events) and events[pos]['kind']=='execution-constructor-throw':
                                failure=take('execution-constructor-throw')
                                if child_error:require(child_error.get('object')==failure['exception']['object'],'Constructor exception identity differs')
                                else:raise ValueError('Shortcut constructor unexpectedly threw; required effects not explained')
                                if handle(failure['exception'],failure['exception_type']):continue
                                take('abort');return None,failure['exception']
                            require(child_error is None,'Aborted constructor has successful completion');event=take('execution-constructed');bind(recv,event['receiver'])
                            require(event['receiver_type']==ins['owner'].replace('/','.'),'Execution constructor type differs')
                            require(len(args)==len(event['args']),'Execution constructor arity differs')
                            for a,b in zip(args,event['args']):bind(a,b)
                            owner=identity(recv)
                            if key=='java/util/ArrayList.<init>()V':state.containers[owner]=Container(owner,[],0,True)
                            elif effect.get('kind')=='date-constructor':
                                fact=event.get('date_contract');require(fact and fact['kind']=='date-constructor' and fact['arity']==len(args) and fact['epoch_ms']==event['receiver']['date_epoch_ms'],'Date constructor evidence absent/differs')
                                if args:
                                    require(args[0].observed.get('value')==fact['epoch_ms'],'Date constructor millis differs');date_values[owner]=args[0].project(event['receiver'])
                                else:
                                    date_values[owner]=Value(event['receiver']);environment_facts.append({'kind':'clock','seq':event['seq'],'object':owner,'epoch_ms':fact['epoch_ms']})
                            elif effect.get('kind')=='http-entity-null-headers':
                                fact=framework_fact(event,'http-entity-null-headers');bind(args[0],fact['body'])
                                if fact['valid'] and args[1].observed.get('value','non-null') is None:http_entities[owner]=args[0]
                                else:poison([recv]+args,event['seq'])
                            elif effect.get('kind')!='frame':
                                fields=effect['fields'] if effect.get('kind')=='assignments' else {name:{'argument':index} for name,index in effect.items()}
                                for name,expression in fields.items():
                                    value=args[expression['argument']] if 'argument' in expression else Value({'value':expression['constant']})
                                    matching=[w for w in writes if w['owner']==owner and w['field']==name and w['seq']<event['seq']]
                                    require(len(matching)==1,'Execution constructor write missing/ambiguous');w=matching[0];bind(value,w['observed']);write_field(w,value)
                        else:
                            call=take('collection-call-enter');require(call['callee']==key,'Execution invoked method differs')
                            if recv is not None:bind(recv,call['receiver'])
                            require(len(args)==len(call['args']),'Execution call arity differs')
                            for a,b in zip(args,call['args']):bind(a,b)
                            child_value=None;child_error=None;filter_selection=None;filter_executed=False;filter_selectors=frozenset()
                            stream=state.streams.get(identity(recv)) if recv is not None else None
                            if key=='java/util/stream/Stream.findFirst()Ljava/util/Optional;' and stream and len(stream)==3:
                                owner,epoch,predicate=stream;c=state.containers[owner];require(c.epoch==epoch,'Filter source container changed')
                                declaration,captured=state.lambdas.get(identity(predicate),(None,None));implementation=declaration['bootstrap_args'][1] if declaration else None
                                if implementation and implementation['handle'] in methods:
                                    filter_executed=True;accepted=False
                                    for index,member in enumerate(c.elements):
                                        begin=take('enter',check_frame=False);require(begin['method']==implementation['handle'] and begin['parent']==fr.invocation and begin.get('callback_call_id')==call['call_id'] and begin['callsite']==entry+'@'+str(fr.pc),'Filter callback implementation/instance differs')
                                        bound=list(captured)+[member];child_recv=None if implementation['tag']==6 else bound.pop(0)
                                        if child_recv is not None:require(begin['receiver']==identity(child_recv),'Filter captured receiver differs')
                                        predicate_value,child_error=execute(begin,bound,child_recv)
                                        if child_error is not None:break
                                        require(isinstance(predicate_value.observed.get('value'),(int,bool)) and predicate_value.observed['value'] in (0,1),'Filter predicate result not boolean')
                                        filter_selectors|=predicate_value.origins|predicate_value.selectors
                                        if predicate_value.unknown:poison([predicate,Value({'object':owner})],events[pos-1]['seq'])
                                        if predicate_value.observed['value']:
                                            filter_selection=Value(member.observed,member.origins,member.selectors|filter_selectors,member.unknown,member.allocation);accepted=True;break
                                    if not accepted and child_error is None:require(not (pos<len(events) and events[pos]['kind']=='enter'),'Filter callback count exceeds source membership')
                            permitted=cfg['call_targets'].get(entry+'@'+str(fr.pc),[])
                            expected_impl=None
                            if ins['op'] in (183,184):expected_impl=key if key in permitted else None
                            else:
                                actual_owner=call['receiver_type'].replace('.','/') if call['receiver_type'] else None;suffix='.'+ins['name']+ins['desc']
                                while actual_owner:
                                    candidate=actual_owner+suffix
                                    if candidate in permitted:expected_impl=candidate;break
                                    actual_owner=cfg['class_parents'].get(actual_owner,{}).get('super')
                            callback=None
                            if key=='java/util/function/Supplier.get()Ljava/lang/Object;' and identity(recv) in state.lambdas:callback=state.lambdas[identity(recv)]
                            elif key in ('java/util/Optional.orElseGet(Ljava/util/function/Supplier;)Ljava/lang/Object;','java/util/Optional.orElseThrow(Ljava/util/function/Supplier;)Ljava/lang/Object;') and identity(recv) in state.optionals and state.optionals[identity(recv)] is None:
                                callback=state.lambdas.get(identity(args[0]))
                            child_args=args;child_recv=recv
                            if callback:
                                declaration,captured=callback;handle_spec=declaration['bootstrap_args'][1];implementation=handle_spec['handle']
                                if implementation in methods:
                                    expected_impl=implementation;permitted=[implementation]
                                    bound=list(captured)+(args if key.startswith('java/util/function/Supplier.') else [])
                                    child_recv=None if handle_spec['tag']==6 else bound.pop(0);child_args=bound
                            if filter_executed:require(not (pos<len(events) and events[pos]['kind']=='enter'),'Filter has unexpected additional callback')
                            if pos<len(events) and events[pos]['kind']=='enter' and expected_impl is None:
                                # An opaque callback may itself enter instrumented bodies.
                                # Validate their closed extent, then conservatively poison
                                # all reachable/nonlocal state; never infer from that subtree.
                                finish=next((j for j in range(pos,len(events)) if events[j]['kind'] in ('collection-call-exit','collection-call-throw') and events[j].get('frame')==fr.invocation and events[j].get('call_id')==call['call_id']),None)
                                require(finish is not None,'Opaque invocation completion absent');subtree=events[pos:finish];children={r['frame']:r for r in subtree if r['kind']=='enter'}
                                require(all(r.get('parent')==fr.invocation or r.get('parent') in children for r in children.values()),'Opaque callback parent extent differs')
                                require(all(sum(r['kind'] in ('exit','abort') and r.get('frame')==f for r in subtree)==1 for f in children),'Opaque callback not closed')
                                require(all(r.get('frame') in children for r in subtree),'Opaque callback contains unrelated parent evidence')
                                completion={f:next(r for r in subtree if r['kind'] in ('exit','abort') and r.get('frame')==f) for f in children}
                                require(all(r['seq']<completion[f]['seq'] and (r.get('parent')==fr.invocation or children[r['parent']]['seq']<r['seq']<completion[f]['seq']<completion[r['parent']]['seq']) for f,r in children.items()),'Opaque callback nested lifetime differs')
                                opaque_frames.extend({'frame':f,'method':r['method'],'parent_call_id':call['call_id']} for f,r in children.items());pos=finish
                            if pos<len(events) and events[pos]['kind']=='enter':
                                begin=take('enter',check_frame=False)
                                require(begin['parent']==fr.invocation and begin.get('callsite')==entry+'@'+str(fr.pc),'Application parent/callsite differs')
                                require(begin['method'] in permitted and begin['method']==expected_impl,'Unplanned actual application implementation')
                                if callback:require(begin['method']==expected_impl,'Lambda actual implementation differs')
                                elif ins['op'] in (183,184):require(begin['method']==key,'Static/special application implementation differs')
                                else:
                                    actual_owner=call['receiver_type'].replace('.','/');suffix='.'+ins['name']+ins['desc'];resolved=None
                                    while actual_owner:
                                        candidate=actual_owner+suffix
                                        if candidate in methods:resolved=candidate;break
                                        actual_owner=cfg['class_parents'].get(actual_owner,{}).get('super')
                                    require(resolved==begin['method'],'Actual virtual dispatch differs from frozen hierarchy')
                                if child_recv is not None:require(begin['receiver']==identity(child_recv),'Application receiver binding differs')
                                child_value,child_error=execute(begin,child_args,child_recv)
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
                            elif key=='java/util/Calendar.getInstance()Ljava/util/Calendar;' and plan.get('date_projection'):
                                fact=ret.get('date_contract');require(fact and fact['kind']=='calendar-environment','Calendar creation evidence absent')
                                if fact['valid']:
                                    require(fact['provider_type']=='sun.util.locale.provider.CalendarProviderImpl','Calendar provider differs');calendars[observed['object']]=ret['seq'];v=Value(observed)
                            elif key=='java/util/Calendar.getTime()Ljava/util/Date;' and plan.get('date_projection'):
                                fact=ret.get('date_contract');require(fact and fact['kind']=='calendar-date','Calendar Date evidence absent')
                                if fact['valid'] and identity(recv) in calendars and identity(recv) not in poisoned_at:
                                    same_value(fact['date'],observed);v=Value(observed);date_values[observed['object']]=v;environment_facts.append({'kind':'calendar-clock','seq':ret['seq'],'calendar':identity(recv),'object':observed['object'],'epoch_ms':observed['date_epoch_ms']})
                            elif key=='java/util/Date.getTime()J' and plan.get('date_projection'):
                                fact=ret.get('date_contract');require(fact and fact['kind']=='date-get-time','Date getTime evidence absent');source=date_values.get(identity(recv),recv)
                                if 'date_epoch_ms' in source.observed and identity(recv) not in poisoned_at:same_value(source.observed,fact['date'])
                                else:require(identity(recv)==fact['date']['object'],'Date getTime object differs')
                                require(fact['epoch_ms']==observed.get('value')==fact['date']['date_epoch_ms'],'Date getTime millis differs')
                                v=Value(observed,source.origins,source.selectors,source.unknown or identity(recv) in poisoned_at)
                            elif key=='org/springframework/web/client/RestTemplate.exchange(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;' and cfg.get('framework_contracts'):
                                fact=framework_fact(ret,'rest-exchange');poison(([recv] if recv else [])+args,call['seq'])
                                # This models transport return identity, not a purity
                                # summary. Only fresh, actual decoder facts can recover.
                                valid=fact['valid'] and identity(args[2]) in http_entities and identity(args[3]) in class_literals
                                if valid:
                                    bind(http_entities[identity(args[2])],fact['request_body']);require(fact['url']==args[0].observed.get('value'),'RPC URL differs')
                                    require(class_literals[identity(args[3])]=='L'+fact['response_class'].replace('.','/')+';','RPC response Class differs')
                                    reads=[r for r in relevant if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and call['seq']<r['seq']<ret['seq']]
                                    require(len(reads)==1,'RPC decoded response absent/ambiguous');read=reads[0]
                                    same_value(fact['body'],read['decoded_body']);require(fact['body_type']==read['decoded_type'] and fact['fields']==read['fields'],'RPC decoded body changed after read')
                                    starts=[r for r in relevant if r['kind']=='http-rpc-enter' and r.get('message')==read['message'] and call['seq']<r['seq']<read['seq']]
                                    ends=[r for r in relevant if r['kind']=='http-rpc-exit' and r.get('message')==read['message'] and read['seq']<r['seq']<ret['seq']]
                                    require(len(starts)==len(ends)==1 and starts[0]['uri']==fact['url'] and starts[0]['method']==fact['method'] and read.get('parent_message') in {r.get('message') for r in relevant if r['kind'] in ('binding-input','binding-return') and r.get('frame')==root['frame'] and r.get('message') is not None},'RPC call/message binding differs')
                                    require(fact['body'].get('object') not in nonlocal_owners,'RPC body aliases input/global boundary')
                                    for index,f in enumerate(read['fields']):
                                        providers[coordinate(f)].append((read,index,f));nonlocal_owners.add(f['owner'])
                                    nonlocal_owners.add(fact['body'].get('object'));heap_refs[observed['object']].add(fact['body'].get('object'))
                                    response_entities[observed['object']]=Value(fact['body']);v=Value(observed)
                            elif key in ('org/springframework/http/ResponseEntity.getBody()Ljava/lang/Object;','org/springframework/http/HttpEntity.getBody()Ljava/lang/Object;') and cfg.get('framework_contracts'):
                                fact=framework_fact(ret,'http-entity-body');same_value(fact['body'],observed);body=response_entities.get(identity(recv),http_entities.get(identity(recv)))
                                if fact['valid'] and body is not None:bind(body,observed);v=body.project(observed)
                                else:poison([recv,Value(observed)],ret['seq'])
                            elif key in plan['response_binding']['source_calls']:
                                v=Value(observed)  # Source leaves must still match concrete boundary fields later.
                            elif key in plan['collection_getters']:
                                f=call.get('getter');require(f and f['field']==plan['collection_getters'][key]['field'],'Execution getter evidence absent')
                                same_value(f['observed'],observed)
                                v=lookup(f,call['seq']) if 'value' in observed or 'date_epoch_ms' in observed else Value(observed)
                                if 'date_epoch_ms' in observed:heap_refs[f['owner']].add(observed['object'])
                            elif key in plan['collection_setters']:
                                name=plan['collection_setters'][key]['field'];matching=[w for w in writes if w['owner']==identity(recv) and w['field']==name and call['seq']<w['seq']<ret['seq']]
                                require(len(matching)==1,'Execution setter version missing');w=matching[0];bind(args[0],w['observed']);write_field(w,args[0]);v=Value(observed)
                            elif key in ('java/util/Collection.stream()Ljava/util/stream/Stream;','java/util/List.stream()Ljava/util/stream/Stream;'):
                                fact=ret.get('contract');require(fact and fact['kind']=='list-stream' and fact['valid'] and ret['result_type']=='java.util.stream.ReferencePipeline$Head','Sequential stream contract absent/invalid');c=container(call)
                                require(fact['source']==c.owner and fact['epoch']==c.epoch and fact['elements']==call['collection'],'Stream source identity/stage differs')
                                require(observed['object'] not in state.streams,'Stream instance reused');state.streams[observed['object']]=(c.owner,c.epoch);v=Value(observed)
                            elif key=='java/util/stream/Stream.filter(Ljava/util/function/Predicate;)Ljava/util/stream/Stream;' and identity(recv) in state.streams:
                                fact=ret.get('contract');require(fact and fact['kind']=='stream-filter' and fact['valid'],'Filter contract missing/invalid')
                                owner,epoch=state.streams.pop(identity(recv));require(fact['source']==owner and fact['epoch']==epoch and fact['predicate']==identity(args[0]),'Filter source/predicate instance differs')
                                require(any(p['java_runtime_version']==runtime[0]['java_runtime_version'] and p['class_sha256']['java/util/stream/ReferencePipeline$2']==fact['filter_class_sha256'] for p in cfg['library_contracts']['filter_profiles']),'Unmodeled filter runtime')
                                state.streams[observed['object']]=(owner,epoch,args[0]);v=Value(observed)
                            elif key=='java/util/stream/Stream.findFirst()Ljava/util/Optional;' and identity(recv) in state.streams and (len(state.streams[identity(recv)])==2 or filter_executed):
                                fact=ret.get('contract');require(fact and fact['kind']==('filter-first' if filter_executed else 'stream-first') and fact['valid'] and ret['result_type']=='java.util.Optional','findFirst contract absent/invalid');stream=state.streams.pop(identity(recv));owner,epoch=stream[:2];c=state.containers[owner]
                                require(owner==fact['source'] and epoch==fact['epoch']==c.epoch and fact['present']==(filter_selection is not None if filter_executed else bool(c.elements)),'findFirst source stage differs')
                                if filter_executed:require(fact['predicate']==identity(stream[2]),'Filter terminal predicate differs')
                                selected=filter_selection if filter_executed else c.elements[0] if c.elements else None
                                if selected is not None and (owner in poisoned_at or c.escaped):selected=Value(selected.observed,selected.origins,selected.selectors,True,selected.allocation)
                                if selected:bind(selected,fact['selected'])
                                else:require(fact['selected'].get('value','not-null') is None,'Empty Optional selected object differs')
                                state.optionals[observed['object']]=selected;v=Value(observed)
                            elif key in ('java/util/Optional.orElseGet(Ljava/util/function/Supplier;)Ljava/lang/Object;','java/util/Optional.orElseThrow(Ljava/util/function/Supplier;)Ljava/lang/Object;') and identity(recv) in state.optionals:
                                fact=ret.get('contract');require(fact and fact['valid'] and fact['kind']=='optional-result' and call['receiver_type']=='java.util.Optional','Optional contract absent/invalid');selected=state.optionals[identity(recv)]
                                require(fact['present']==(selected is not None),'Optional presence differs')
                                if selected is not None:bind(selected,observed);bind(selected,fact['selected']);v=selected.project(observed)
                                else:poison(([recv] if recv else [])+args,ret['seq'])
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
                            elif key=='org/slf4j/LoggerFactory.getLogger(Ljava/lang/Class;)Lorg/slf4j/Logger;':
                                fact=ret.get('contract');require(fact and fact['kind']=='logger-factory','Logging factory witness absent')
                                if fact.get('valid'):
                                    require(any(p['class_sha256']==fact['class_sha256'] for p in cfg['library_contracts']['logger_factory_profiles']),'Unmodeled logging factory/binder version');v=Value(observed)
                                else:poison(args,ret['seq'])
                            elif key=='java/lang/String.equals(Ljava/lang/Object;)Z' and isinstance(recv.observed.get('value'),str) and 'value' in args[0].observed:
                                fact=ret.get('contract');require(fact and fact['kind']=='string-equality' and fact['valid'],'String equality witness absent')
                                require(any(p['java_runtime_version']==runtime[0]['java_runtime_version'] and p['class_sha256']['java/lang/String']==fact['class_sha256'] for p in cfg['library_contracts']['filter_profiles']),'Unmodeled String runtime')
                                require(observed.get('value')==(recv.observed['value']==args[0].observed['value']),'String equality contradicts operands');v=combine(observed,[recv,args[0]])
                            elif key=='java/lang/Object.getClass()Ljava/lang/Class;':
                                fact=ret.get('contract');require(fact and fact['kind']=='object-class' and fact['valid'] and fact['receiver_type']==call['receiver_type'] and ret['result_type']=='java.lang.Class','Object.getClass runtime identity differs');v=Value(observed)
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
            if 'value' in arg or 'date_epoch_ms' in arg:value=Value(arg,frozenset({('argument',root['frame'],index)}))
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
            if 'date_epoch_ms' in f['observed'] and f['observed']['object'] in poisoned_at:value=Value(f['observed'],unknown=True)
            bind(value,f['observed'])
            results.append({'root_frame':root['frame'],'seq':ret['seq'],'path':f['path'],**f,'known':not value.unknown,'origins':[list(x) for x in sorted(value.origins,key=str)],'selectors':[list(x) for x in sorted(value.selectors,key=str)]})
        audits.append({'frame':root['frame'],'completion':'normal','steps':total_steps,'frames':frame_audits,'answers':len(ret['fields']),'poisoned_objects':len(poisoned_at),'opaque_frames':opaque_frames,'environment_facts':environment_facts})
    return {'answers':results,'roots':audits,'evidence_policy':cfg['evidence_policy']}
