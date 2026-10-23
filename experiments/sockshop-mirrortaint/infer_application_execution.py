"""Bounded bytecode calls over shared heap/container state and concrete effects."""
from collections import defaultdict
from execution_dependency_state import Value, Frame, State, Container, Call, combine
from query_observation_planner import require, descriptors
from plan_service_observations import callee
from analysis_status import AnalysisLimit
from infer_execution_kernel import coordinate, same_value


def infer_application(plan,rows,worker_request=None):
    from infer_date_projection import validate_date_runtime
    validate_date_runtime(plan,rows)
    from infer_async_protocol import validate_async_protocol
    async_audit=validate_async_protocol(plan,rows)
    cfg=plan['execution_kernel']
    from infer_execution_closure import validate as validate_closure
    validate_closure(plan,rows)
    primitive_fields={i['owner']+'.'+i['name'] for m in cfg.get('methods',{}).values() for i in m['instructions'] if i['op'] in (180,181) and i['desc'] in ('Z','B','C','S','I','J','F','D')}
    primitive_fields.update(v['field']for v in plan.get('collection_getters',{}).values()if v['descriptor']in ('Z','B','C','S','I','J','F','D'))
    if cfg.get('request_entity_contracts') and cfg['request_entity_contracts'].get('version')!=2:raise AnalysisLimit('typed-decoder-version','Old candidate decoder evidence requires its frozen interpreter; source/default write roles are missing')
    runtime=[r for r in rows if r['kind']=='execution-runtime']
    require(len(runtime)==1 and any(all(runtime[0][k]==p[k] for k in ('java_runtime_version','class_sha256')) for p in cfg['runtime_profiles']),'Application runtime pin differs')
    def request_hashes(actual):
        contract=cfg['request_entity_contracts']
        return actual in [contract['class_sha256'], *contract.get('class_sha256_profiles',[])]
    if cfg.get('request_entity_contracts'):
        starts={r.get('call_id'):r for r in rows if r['kind']=='collection-call-enter'}
        for event in rows:
            if event['kind']!='collection-call-exit':continue
            call=starts.get(event.get('call_id'),{}).get('callee','')
            modeled=(call.startswith('org/springframework/http/RequestEntity$') and any('.'+n+'(' in call for n in ('accept','contentType','build','body'))) or call in (
                'org/springframework/http/RequestEntity.get(Ljava/net/URI;)Lorg/springframework/http/RequestEntity$HeadersBuilder;',
                'org/springframework/http/RequestEntity.post(Ljava/net/URI;)Lorg/springframework/http/RequestEntity$BodyBuilder;',
                'org/springframework/web/client/RestTemplate.exchange(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;',
                'org/springframework/http/ResponseEntity.getBody()Ljava/lang/Object;',
                'org/springframework/http/HttpEntity.getBody()Ljava/lang/Object;',
                'org/springframework/hateoas/Resource.getContent()Ljava/lang/Object;')
            if modeled:require('request_entity_contract' in event,'Required RequestEntity witness absent')
    pending=defaultdict(list);seen=set()
    for row in rows:
        kind=row['kind'];frame=row.get('frame')
        if kind=='collection-call-enter':
            cid=row.get('call_id');require(isinstance(cid,int) and cid not in seen,'Application call ID absent/repeated');seen.add(cid);pending[frame].append(cid)
        elif kind in ('collection-call-exit','collection-call-throw'):require(pending[frame] and pending[frame].pop()==row.get('call_id'),'Application call-ID completion differs')
        elif kind in ('exit','abort'):require(not pending[frame],'Application frame has unfinished calls')
    require(not any(pending.values()),'Application capture incomplete calls')
    constructor_pending=defaultdict(list);constructor_ids=set()
    if cfg.get('constructor_lifecycle'):
        for row in rows:
            if row['kind']=='execution-constructor-enter':
                cid=row['constructor_id'];require(cid not in constructor_ids,'Constructor ID repeated');constructor_ids.add(cid);constructor_pending[row['thread']].append(row)
            elif row['kind'] in ('execution-constructed','execution-constructor-throw'):
                stack=constructor_pending[row['thread']];require(stack,'Constructor completion without entry');start=stack.pop();require(all(start[k]==row[k] for k in ('constructor_id','frame','pc')),'Constructor completion identity/caller differs')
        require(not any(constructor_pending.values()),'Constructor lifecycle incomplete')
    results=[];audits=[]
    all_enters={r['frame']:r for r in rows if r['kind']=='enter'}
    require(len(all_enters)==sum(r['kind']=='enter' for r in rows),'Application invocation frame ID reused')
    roots=[r for r in rows if r['kind']=='enter' and (r['frame']==worker_request['frame'] if worker_request else r['method']==plan['entry'])]
    if worker_request:require(len(roots)==1,'Worker replay frame missing/ambiguous')
    for root in roots:
        ends=[r for r in rows if r['kind'] in ('exit','abort') and r.get('frame')==root['frame']];require(len(ends)==1,'Application root completion differs');end=ends[0]
        family={root['frame']}
        changed=True
        while changed:
            before=len(family);family.update(k for k,r in all_enters.items() if r.get('parent') in family);changed=len(family)!=before
        relevant=[r for r in rows if r.get('frame') in family and root['seq']<=r['seq']<=end['seq']]
        if any(r['kind']=='enter' and r['method']==plan['entry'] and r['frame']!=root['frame'] for r in relevant):
            raise AnalysisLimit('entry-reentry','Nested query-entry invocation is not a separately supported root boundary')
        births={}
        for row in relevant:
            if row['kind']!='execution-object-birth':continue
            site=cfg.get('object_birth_sites',{}).get(row['constructor'])
            require(site and site['class_sha256']==row['class_sha256'],'Object birth constructor/hash differs')
            invocation=all_enters.get(row.get('frame'))
            require(invocation and invocation['method']==row['constructor'] and invocation['receiver']==row['object'] and invocation['seq']<row['seq'],'Object birth constructor frame/receiver differs')
            require(row['object'] not in births,'Object birth identity repeated')
            births[row['object']]=row['seq']
        methods=cfg['methods'];events=[r for r in relevant if r['kind'] in ('enter','exit','abort','collection-call-enter','collection-call-exit','collection-call-throw','execution-constructor-enter','execution-constructed','execution-constructor-throw','execution-static-read','execution-lambda','execution-class-literal','execution-array','execution-array-throw','collection-catch','branch','read','write') and (r['kind'] not in ('read','write','branch') or r['site'].rsplit('@',1)[0] in methods)]
        writes=[r for r in relevant if r['kind']=='write'];providers=defaultdict(list)
        for row in relevant:
            if row['kind'] in ('binding-source','binding-input'):
                for index,f in enumerate(row['fields']):providers[coordinate(f)].append((row,index,f))
        state=State(Frame(root['frame']));preserved_fields={};pos=1;allocation_count=0;total_steps=0;branch_count=0
        request_builders={};request_entities={};resources={};decoded_types={};decoded_fields={};decoded_seq={};http_entities={};response_entities={};class_literals={};date_values={};calendars={};environment_facts=[];builders={};opaque_calls=[];async_results={};future_states={};async_transfers=[];maps={}
        fr=None;method=None;code=None;entry=None;field_seq={};poisoned_at={};frame_audits=[]
        execution_budget=worker_request['budget'] if worker_request else {'steps':0}
        nonlocal_owners={f['owner'] for rows_ in providers.values() for _,_,f in rows_}
        nonlocal_owners.update(v.get('object') for v in root['args'] if 'value' not in v and v.get('object'))
        if root.get('receiver'):nonlocal_owners.add(root['receiver'])
        heap_refs=defaultdict(set);opaque_frames=[];unproved_statics=[];depth=0;transport_effects=[]
        task_by_call={t['parent_call_id']:t for t in async_audit.get('tasks',[])} if plan.get('async_dependencies') else {}
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
        def bind_argument(v,observed,desc):
            if desc=='C' and isinstance(observed.get('value'),str) and len(observed['value'])==1 and isinstance(v.observed.get('value'),int):observed={**observed,'value':ord(observed['value'])}
            bind(v,observed)
        def origin(f,before):
            candidates=[v for v in providers.get(coordinate(f),[]) if v[0]['seq']<before]
            if len(candidates)!=1:return Value(f['observed'],unknown=True)
            if f['owner'] in poisoned_at and not (candidates[0][0]['kind']=='http-json' and candidates[0][0]['seq']>poisoned_at[f['owner']]):return Value(f['observed'],unknown=True)
            row,index,source=candidates[0];same_value(source['observed'],f['observed']);return Value(f['observed'],frozenset({('http',row['seq'],source['path']) if row['kind']=='http-json' else ('field',row['seq'],index)}))
        def lookup(f,before):
            key=coordinate(f)
            preserved=preserved_fields.get(key)
            if preserved and poisoned_at.get(f['owner'],-1)<=preserved[0]<before:
                bind(preserved[1],f['observed']);return preserved[1].project(f['observed'])
            if f['observed'].get('uuid_type') and f['observed'].get('object')in poisoned_at:return Value(f['observed'],unknown=True)
            if 'date_epoch_ms' in f['observed']:
                obj=f['observed'].get('object')
                if obj in poisoned_at:return Value(f['observed'],unknown=True)
                if obj in date_values:return date_values[obj].project(f['observed'])
            if key in state.fields and field_seq[key]>poisoned_at.get(f['owner'],-1):return state.fields[key]
            return origin(f,before)
        def write_field(w,v):
            if 'date_epoch_ms' in w['observed'] and w['observed']['object'] in date_values:v=date_values[w['observed']['object']]
            bind(v,w['observed'])
            # Reflection/Recorder boxes primitive fields independently at every
            # observation. Those wrapper identities are not JVM field identity.
            observed={k:x for k,x in w['observed'].items() if k!='object'} if w['field'] in primitive_fields else w['observed']
            state.field_write(coordinate(w),v.project(observed));field_seq[coordinate(w)]=w['seq']
            if w['owner'] in nonlocal_owners or w['owner'] in state.poisoned:escape(v)
        def escape(value):
            todo=[identity(value)] if 'value' not in value.observed else [];seen=set()
            while todo:
                owner=todo.pop()
                if owner is None or owner in seen:continue
                seen.add(owner);nonlocal_owners.add(owner);todo.extend(heap_refs.get(owner,()))
                for (o,_,_),v in state.fields.items():
                    if o==owner and 'value' not in v.observed:todo.append(identity(v))
                if owner in state.arrays:todo.extend(identity(v) for v in state.arrays[owner]['elements'] if 'value' not in v.observed)
                if owner in state.containers:todo.extend(identity(v) for v in state.containers[owner].elements if 'value' not in v.observed)
        def poison(values,seq):
            affected=set()
            todo=list(nonlocal_owners|state.poisoned)+[identity(v) for v in values if v is not None and 'value' not in v.observed]
            while todo:
                owner=todo.pop()
                if owner is None or owner in affected:continue
                # Metadata for future boundary fields is pre-indexed, but an
                # earlier effect cannot reach a reference not yet initialized.
                # Without this JVM allocation witness, retain the old barrier.
                if births.get(owner,-1)>seq:continue
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
            for name in ('ExecutionException','TimeoutException','CancellationException'):
                hierarchy['java.util.concurrent.'+name]={'java/util/concurrent/'+name,'java/lang/Exception','java/lang/Throwable'}
                if name=='CancellationException':hierarchy['java.util.concurrent.'+name].add('java/lang/RuntimeException')
            protected=[h for h in method['exception_handlers'] if h['start']<=fr.pc<h['end']]
            for exception in ('ArrayIndexOutOfBoundsException','ArrayStoreException','NegativeArraySizeException'):
                hierarchy['java.lang.'+exception]={'java/lang/'+exception,'java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'}
            hierarchy['java.lang.IndexOutOfBoundsException']={'java/lang/IndexOutOfBoundsException','java/lang/RuntimeException','java/lang/Exception','java/lang/Throwable'}
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
        def library_values(fact):
            require(fact and fact in cfg.get('library_values',{}).get('profiles',[]),'Library value runtime missing/different')
            require(fact['java_runtime_version']==runtime[0]['java_runtime_version'],'Library value runtime differs from root')
        def request_fact(event,kind):
            fact=event.get('request_entity_contract')
            require(fact and fact['kind']==kind and request_hashes(fact['class_sha256']),'RequestEntity witness kind/library differs')
            require(any(p['java_runtime_version']==runtime[0]['java_runtime_version'] and p['class_sha256']==fact['jdk_sha256'] for p in cfg['request_entity_contracts']['jdk_profiles']),'RequestEntity JDK profile differs')
            return fact
        def date_render(event,observed):
            fact=event.get('date_effect');require(fact and fact['kind']=='date-render','Date render evidence absent')
            require(fact['before']==observed and fact['before']==fact['after'],'Date render identity/semantic time changed')
            require(fact['render_runtime'] in plan['date_effects']['render_runtime_profiles'],'Date render runtime differs')
            if fact['valid']:require(fact['zone']=='sun.util.calendar.ZoneInfo','Unsupported render timezone claimed valid')
            return fact['valid']
        def opaque_extent(finish):
            nonlocal pos
            require(finish is not None,'Opaque invocation completion absent');subtree=events[pos:finish];children={r['frame']:r for r in subtree if r['kind']=='enter'}
            require(all(r.get('parent')==fr.invocation or r.get('parent') in children for r in children.values()),'Opaque callback parent extent differs')
            require(all(sum(r['kind'] in ('exit','abort') and r.get('frame')==f for r in subtree)==1 for f in children),'Opaque callback not closed')
            require(all(r.get('frame') in children for r in subtree),'Opaque callback contains unrelated parent evidence')
            completion={f:next(r for r in subtree if r['kind'] in ('exit','abort') and r.get('frame')==f) for f in children}
            require(all(r['seq']<completion[f]['seq'] and (r.get('parent')==fr.invocation or children[r['parent']]['seq']<r['seq']<completion[f]['seq']<completion[r['parent']]['seq']) for f,r in children.items()),'Opaque callback nested lifetime differs')
            opaque_frames.extend({'frame':f,'method':r['method']} for f,r in children.items());pos=finish
        def receive_future(record,observed,seq):
            task=record['task']
            if worker_request or task['status']!='worker_completed':
                return Value(observed,unknown=True)
            if 'export' not in record:
                record['export']=infer_application(plan,rows,{'frame':task['worker_frame'],'args':record['args'],'receiver':record['receiver'],'borrowed':record['borrowed'],'budget':execution_budget})['worker_export']
            export=record['export'];value=export['value']
            if not record.get('joined'):
                for key,item in export['fields'].items():
                    require(key not in state.fields,'Async imported field version already exists')
                    state.field_write(key,item);field_seq[key]=export['field_seq'][key]
                    # Proven private task allocations remain private after join.
                    # Passing/publishing them to an opaque effect still poisons
                    # their reachable graph through the normal barrier.
                for wrapper,content in export.get('resources',{}).items():
                    require(wrapper not in resources,'Async resource identity reused');resources[wrapper]=content;heap_refs[wrapper].add(identity(content))
                decoded_types.update(export.get('decoded_types',{}))
                record['joined']=seq
            bind(value,observed)
            if observed.get('object') in poisoned_at:value=Value(observed,unknown=True)
            async_transfers.append({'task_id':task['task_id'],'get_seq':seq,'worker_frame':task['worker_frame'],'worker_status':export['status'],'imported_fields':len(export['fields']),'known_return_value':not value.unknown})
            return value.project(observed)
        def execute(begin,args,receiver):
            nonlocal fr,method,code,entry,allocation_count,total_steps,branch_count,pos,depth
            if depth>=cfg.get('call_depth_limit',64):raise AnalysisLimit('call-depth','Application invocation depth budget exhausted')
            depth+=1
            saved=(fr,method,code,entry)
            entry=begin['method'];method=methods[entry];code=method['instructions'];fr=Frame(begin['frame']);fr.pc=cfg.get('constructor_starts',{}).get(entry,0);slot=0
            if not method['access']&8:fr.locals[0]=receiver;slot=1
            require(len(args)==len(begin['args']),'Application argument count differs')
            for index,desc in enumerate(descriptors(method['desc'])):
                bind_argument(args[index],begin['args'][index],desc);fr.locals[slot]=args[index];slot+=2 if desc in ('J','D') else 1
            try:
                while True:
                    fr.steps+=1; total_steps+=1;execution_budget['steps']+=1
                    if execution_budget['steps']>cfg['step_limit']:raise AnalysisLimit('offline-execution','Application execution budget exceeded on complete evidence')
                    ins=code[fr.pc];op=ins['op'];pop=fr.pop
                    if 21<=op<=25:
                        require(ins['var'] in fr.locals,'Execution uninitialized local');fr.stack.append(fr.locals[ins['var']])
                    elif 54<=op<=58:fr.locals[ins['var']]=pop()
                    elif op==0:pass
                    elif op==1:fr.stack.append(Value({'value':None,'object':None}))
                    elif 2<=op<=8:fr.stack.append(Value({'value':op-3}))
                    elif 9<=op<=15:fr.stack.append(Value({'value':op-9 if op<11 else float(op-11 if op<14 else op-14)}))
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
                            if owner in nonlocal_owners or owner in state.poisoned or not any(r['kind']=='execution-array' and r['operation']=='new' and r['array'].get('object')==owner for r in relevant):escape(value)
                    elif op==187:
                        allocation_count+=1;fr.stack.append(Value(allocation=allocation_count))
                    elif op==178:
                        if cfg.get('static_field_evidence'):
                            if pos<len(events) and events[pos]['kind']=='enter':
                                finish=next((j for j in range(pos,len(events)) if events[j]['kind']=='execution-static-read' and events[j].get('frame')==fr.invocation and events[j].get('pc')==fr.pc),None);opaque_extent(finish)
                            fact=take('execution-static-read');require(fact['field']==ins['owner']+'.'+ins['name'] and fact['descriptor']==ins['desc'],'Static field evidence differs')
                            if ins['owner']!=method['owner']:
                                contracts=cfg.get('request_entity_contracts',{});pinned=contracts.get('class_sha256',{}).get(ins['owner']) if ins['owner'] in ('org/springframework/hateoas/MediaTypes','org/springframework/http/MediaType','org/springframework/http/HttpMethod') else None
                                if ins['owner']=='java/util/concurrent/TimeUnit':pinned=next((p['class_sha256'][ins['owner']] for p in contracts.get('jdk_profiles',[]) if p['java_runtime_version']==runtime[0]['java_runtime_version']),None)
                                if pinned:require(fact.get('declaring_class_sha256')==pinned,'Static library owner differs')
                                else:poison([],fact['seq']);unproved_statics.append(fact['seq'])
                            if fact['observed'].get('object'):nonlocal_owners.add(fact['observed']['object'])
                            fr.stack.append(Value(fact['observed'],unknown=True))
                        else:fr.stack.append(Value(unknown=True))
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
                    elif op==135:
                        value=pop();n=value.observed.get('value')
                        require(type(n) is int and -2**31<=n<2**31,'I2D requires an actual JVM int')
                        fr.stack.append(value.project({'value':float(n)}))
                    elif op==107:
                        import math
                        b,a=pop(),pop();x,y=a.observed.get('value'),b.observed.get('value')
                        require(type(x) in (int,float) and type(y) in (int,float),'DMUL operands absent')
                        n=float(x)*float(y)
                        if not math.isfinite(n):raise AnalysisLimit('numeric-domain','Nonfinite double result unsupported')
                        fr.stack.append(combine({'value':n},[a,b]))
                    elif op in (182,183,184,185):
                        args=[pop() for _ in descriptors(ins['desc'])][::-1];recv=None if op==184 else pop();key=callee(ins)
                        if ins['name']=='<init>':
                            effect=cfg['constructors'].get(key);require(effect is not None,'Execution constructor effects absent')
                            ctor_start=None
                            if cfg.get('constructor_lifecycle'):
                                ctor_start=take('execution-constructor-enter');require(ctor_start['callee']==key and ctor_start['method']==entry and len(args)==len(ctor_start['args']),'Constructor begin callee/arity differs')
                                for desc,a,b in zip(descriptors(ins['desc']),args,ctor_start['args']):bind_argument(a,b,desc)
                            child_error=None
                            if effect.get('kind')=='frame':
                                begin=take('enter',check_frame=False);require(begin['method']==key and begin['parent']==fr.invocation and begin['callsite']==entry+'@'+str(fr.pc),'Constructor Frame binding differs')
                                bind(recv,{'object':begin['receiver']});_,child_error=execute(begin,args,recv)
                            elif effect.get('input_projections'):
                                # A pure accessor may also be instrumented as a
                                # lambda target elsewhere. Consume its real Frame
                                # rather than silently skipping nested evidence.
                                while pos<len(events) and events[pos]['kind']=='enter':
                                    begin=take('enter',check_frame=False,check_pc=False)
                                    getter=plan['collection_getters'].get(begin['method'])
                                    allowed=[e for e in effect['fields'].values() if 'field' in e and getter and e['field']==getter['field'] and identity(args[e['argument']])==begin['receiver']]
                                    require(allowed and begin['parent']==fr.invocation and not begin['args'],'Constructor projection accessor Frame differs')
                                    _,child_error=execute(begin,[],args[allowed[0]['argument']])
                                    if child_error is not None:break
                            elif effect.get('kind')=='opaque' and pos<len(events) and events[pos]['kind']=='enter':
                                finish=next((j for j in range(pos,len(events)) if events[j]['kind'] in ('execution-constructed','execution-constructor-throw') and events[j].get('constructor_id')==ctor_start['constructor_id']),None);opaque_extent(finish)
                            if pos<len(events) and events[pos]['kind']=='execution-constructor-throw':
                                failure=take('execution-constructor-throw')
                                if ctor_start:require(failure['constructor_id']==ctor_start['constructor_id'],'Constructor throw ID differs')
                                if child_error:require(child_error.get('object')==failure['exception']['object'],'Constructor exception identity differs')
                                elif effect.get('kind')=='opaque':poison(args,failure['seq']);opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':failure['seq'],'completion':'exceptional-constructor'})
                                else:raise ValueError('Shortcut constructor unexpectedly threw; required effects not explained')
                                if handle(failure['exception'],failure['exception_type']):continue
                                take('abort');return None,failure['exception']
                            require(child_error is None,'Aborted constructor has successful completion');event=take('execution-constructed');bind(recv,event['receiver'])
                            if ctor_start:require(event['constructor_id']==ctor_start['constructor_id'],'Constructor completion ID differs')
                            require(event['receiver_type']==ins['owner'].replace('/','.'),'Execution constructor type differs')
                            require(len(args)==len(event['args']),'Execution constructor arity differs')
                            # Mutable arguments may legitimately change inside an
                            # opaque constructor. Invalidate before checking its
                            # post-state; retain reference identity checks.
                            if effect.get('kind')=='opaque':poison([recv]+args,event['seq'])
                            for desc,a,b in zip(descriptors(ins['desc']),args,event['args']):bind_argument(a,b,desc)
                            owner=identity(recv)
                            if key=='java/util/ArrayList.<init>()V':state.containers[owner]=Container(owner,[],0,True)
                            elif effect.get('kind')=='string-builder':builders[owner]=('',Value({'value':''}))
                            elif effect.get('kind')=='opaque':
                                opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':event['seq'],'completion':'normal-constructor'})
                            elif effect.get('kind')=='async-result':
                                fact=event.get('async_result');require(fact and len(args)==1 and fact['class_sha256']==plan['async_protocol']['class_sha256']['org/springframework/scheduling/annotation/AsyncResult'] and fact['exception'].get('value','not-null') is None,'AsyncResult constructor witness missing/different')
                                bind(args[0],fact['payload']);async_results[owner]=args[0]
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
                            elif effect.get('kind')=='http-entity-headers-effects':
                                fact=framework_fact(event,'http-entity-headers-effects');poison(args,event['seq'])
                                if fact['valid'] and fact['body'].get('value','non-null') is None:http_entities[owner]=Value(fact['body'])
                            elif effect.get('kind')=='local-map':
                                library_values(event.get('library_values'));require(event.get('collection')==[],'New HashMap not empty');maps[owner]={'epoch':0,'values':{},'local':True}
                            elif effect.get('kind')!='frame':
                                fields=effect['fields'] if effect.get('kind')=='assignments' else {name:{'argument':index} for name,index in effect.items()}
                                for name,expression in fields.items():
                                    if 'field' in expression:
                                        proofs=ctor_start.get('input_projections',[]) if ctor_start else []
                                        matches=[p for p in proofs if p['argument']==expression['argument'] and p['field']==expression['field']]
                                        require(len(matches)==1,'Constructor input projection missing/ambiguous');proof=matches[0]
                                        require(proof['runtime_class']==expression['runtime_class'],'Constructor accessor dispatch differs')
                                        require(proof['class_sha256']==plan['class_sha256'][expression['runtime_class']],'Constructor input class hash differs')
                                        require(proof['owner']==identity(args[expression['argument']]),'Constructor projection input object differs')
                                        require(event.get('input_projections')==proofs,'Constructor input field version changed')
                                        value=lookup(proof,ctor_start['seq'])
                                    else:value=args[expression['argument']] if 'argument' in expression else Value({'value':expression['constant']})
                                    matching=[w for w in writes if w['owner']==owner and w['field']==name and w['seq']<event['seq']]
                                    require(len(matching)==1,'Execution constructor write missing/ambiguous');w=matching[0];bind(value,w['observed']);write_field(w,value)
                        else:
                            call=take('collection-call-enter');require(call['callee']==key,'Execution invoked method differs')
                            if recv is not None:bind(recv,call['receiver'])
                            require(len(args)==len(call['args']),'Execution call arity differs')
                            for desc,a,b in zip(descriptors(ins['desc']),args,call['args']):bind_argument(a,b,desc)
                            builder_initial=builders.get(identity(recv)) if recv is not None else None
                            builder_was_poisoned=identity(recv) in poisoned_at if recv is not None else False
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
                            async_submission=task_by_call.get(call['call_id'])
                            if async_submission:expected_impl=None
                            callback=None
                            if key in ('java/util/function/Supplier.get()Ljava/lang/Object;','java/lang/Runnable.run()V') and identity(recv) in state.lambdas:callback=state.lambdas[identity(recv)]
                            elif key in ('java/util/Optional.orElseGet(Ljava/util/function/Supplier;)Ljava/lang/Object;','java/util/Optional.orElseThrow(Ljava/util/function/Supplier;)Ljava/lang/Object;') and identity(recv) in state.optionals and state.optionals[identity(recv)] is None:
                                callback=state.lambdas.get(identity(args[0]))
                            child_args=args;child_recv=recv
                            render_callback=False
                            if key=='java/lang/StringBuilder.append(Ljava/lang/Object;)Ljava/lang/StringBuilder;' and cfg.get('scalar_builders') and args and 'value' not in args[0].observed:
                                permitted=cfg['call_targets'].get(entry+'@'+str(fr.pc)+':render',[]);actual_owner=call.get('argument_types',[None])[0];actual_owner=actual_owner.replace('.','/') if actual_owner else None
                                while actual_owner:
                                    candidate=actual_owner+'.toString()Ljava/lang/String;'
                                    if candidate in permitted:expected_impl=candidate;render_callback=True;child_args=[];child_recv=args[0];break
                                    actual_owner=cfg['class_parents'].get(actual_owner,{}).get('super')
                            list_render=False;render_finish=next((r for r in events[pos:] if r['kind']=='collection-call-exit' and r.get('call_id')==call['call_id']),None)
                            render_proof=render_finish.get('request_render',{}) if render_finish else {}
                            if key=='java/lang/StringBuilder.append(Ljava/lang/Object;)Ljava/lang/StringBuilder;' and render_proof.get('kind')=='list-render' and render_proof.get('valid'):
                                require(request_hashes(render_proof['class_sha256']) and any(p['java_runtime_version']==runtime[0]['java_runtime_version'] and p['class_sha256']==render_proof['jdk_sha256'] for p in cfg['request_entity_contracts']['jdk_profiles']),'List render framework/runtime differs')
                                bind(args[0],render_proof['object']);require(call.get('argument_types',[None])[0].replace('.','/')==render_proof['class'],'List render argument type differs');require(runtime[0]['class_sha256'].get(render_proof['class'])==render_proof['list_class_sha256'],'List render implementation differs')
                                permitted_render=cfg['call_targets'].get(entry+'@'+str(fr.pc)+':render',[])
                                choices=[(member,member['type'].replace('.','/')+'.toString()Ljava/lang/String;' if member['type'] else None) for member in render_proof['elements']]
                                if all('value' in member['observed'] or impl in permitted_render for member,impl in choices):
                                    list_render=True
                                    for member,impl in choices:
                                        if 'value' in member['observed']:continue
                                        begin=take('enter',check_frame=False);require(begin['method']==impl and begin['receiver']==member['observed']['object'] and begin['parent']==fr.invocation and begin['callsite']==entry+'@'+str(fr.pc),'List render callback object/order differs')
                                        if cfg.get('callback_lifecycle_version',0)>=2:require(begin.get('callback_call_id')==call['call_id'],'List render callback invocation differs')
                                        _,render_error=execute(begin,[],Value(member['observed']));require(render_error is None,'List render callback unexpectedly exceptional')
                                    require(not (pos<len(events) and events[pos]['kind']=='enter'),'List render extra callback')
                            resource_render=False
                            if key=='org/springframework/hateoas/Resource.toString()Ljava/lang/String;' and identity(recv) in resources:
                                content=resources[identity(recv)];implementation=decoded_types.get(identity(content),'')+'.toString()Ljava/lang/String;'
                                permitted=cfg['call_targets'].get(entry+'@'+str(fr.pc)+':render',[])
                                if implementation in permitted:expected_impl=implementation;resource_render=True;child_args=[];child_recv=content
                            if key=='org/springframework/http/RequestEntity.toString()Ljava/lang/String;' and identity(recv) in request_entities and render_proof.get('kind')=='request-render':
                                content=request_entities[identity(recv)]['body'];implementation=(render_proof.get('content_type') or '').replace('.','/')+'.toString()Ljava/lang/String;'
                                permitted=cfg['call_targets'].get(entry+'@'+str(fr.pc)+':render',[])
                                if implementation in permitted:expected_impl=implementation;resource_render=True;child_args=[];child_recv=content
                            if callback:
                                declaration,captured=callback;handle_spec=declaration['bootstrap_args'][1];implementation=handle_spec['handle']
                                require(declaration['name']==('run' if key=='java/lang/Runnable.run()V' else 'get'),'Lambda invocation SAM differs from declaration')
                                if implementation in methods:
                                    expected_impl=implementation;permitted=[implementation]
                                    bound=list(captured)+(args if key.startswith(('java/util/function/Supplier.','java/lang/Runnable.')) else [])
                                    child_recv=None if handle_spec['tag']==6 else bound.pop(0);child_args=bound
                            if filter_executed:require(not (pos<len(events) and events[pos]['kind']=='enter'),'Filter has unexpected additional callback')
                            if pos<len(events) and events[pos]['kind']=='enter' and expected_impl is None:
                                # An opaque callback may itself enter instrumented bodies.
                                # Validate their closed extent, then conservatively poison
                                # all reachable/nonlocal state; never infer from that subtree.
                                finish=next((j for j in range(pos,len(events)) if events[j]['kind'] in ('collection-call-exit','collection-call-throw') and events[j].get('frame')==fr.invocation and events[j].get('call_id')==call['call_id']),None)
                                opaque_extent(finish)
                            if pos<len(events) and events[pos]['kind']=='enter':
                                begin=take('enter',check_frame=False)
                                require(begin['parent']==fr.invocation and begin.get('callsite')==entry+'@'+str(fr.pc),'Application parent/callsite differs')
                                if cfg.get('callback_lifecycle_version',0)>=2:require(begin.get('callback_call_id')==call['call_id'],'Application callback invocation differs')
                                require(begin['method'] in permitted and begin['method']==expected_impl,'Unplanned actual application implementation')
                                if callback:require(begin['method']==expected_impl,'Lambda actual implementation differs')
                                elif render_callback or resource_render:require(begin['method']==expected_impl,'Rendering actual implementation differs')
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
                                read_only_bounds=False
                                if key in ('java/util/List.get(I)Ljava/lang/Object;','java/util/ArrayList.get(I)Ljava/lang/Object;') and recv is not None and call.get('receiver_type') in ('java.util.ArrayList','java.util.Arrays$ArrayList') and failure['exception_type'] in ('java.lang.IndexOutOfBoundsException','java.lang.ArrayIndexOutOfBoundsException'):
                                    c=container(call);index=args[0].observed.get('value')
                                    require(type(index) is int and not 0<=index<len(c.elements),'List bounds failure contradicts actual index/members')
                                    read_only_bounds=True  # Pinned get performs no writes or user callbacks.
                                if child_error is None and not read_only_bounds and not (recv is not None and identity(recv) is None and recv.observed.get('value') is None):poison(([recv] if recv else [])+args,failure['seq'])
                                if handle(failure['exception'],failure['exception_type']):continue
                                take('abort');return None,failure['exception']
                            require(child_error is None,'Exceptional child has normal caller completion')
                            ret=take('collection-call-exit');require(ret['call_id']==call['call_id'],'Application completion instance differs');observed=complete(call,ret);v=Value(observed,unknown=True)
                            invocation=Call(str(call['seq']),fr.pc,recv,args,'normal')
                            if async_submission:
                                captured=[];borrowed=[]
                                for index,arg in enumerate(args):
                                    kind=call.get('argument_types',[None]*len(args))[index]
                                    immutable=kind in ('java.lang.String','java.lang.Boolean','java.lang.Byte','java.lang.Short','java.lang.Character','java.lang.Integer','java.lang.Long','java.lang.Float','java.lang.Double') or arg.observed.get('value','not-null') is None
                                    borrowed.append(not immutable)
                                    captured.append(Value(actual(arg),arg.origins,arg.selectors,arg.unknown) if immutable else Value(actual(arg),unknown=True))
                                future_states[observed['object']]={'task':async_submission,'args':captured,'borrowed':borrowed,'receiver':Value({'object':all_enters[async_submission['worker_frame']]['receiver']},unknown=True) if async_submission.get('worker_frame') else None}
                                record=future_states[observed['object']]
                                if async_submission['status']=='worker_completed' and not worker_request:
                                    record['export']=infer_application(plan,rows,{'frame':async_submission['worker_frame'],'args':captured,'receiver':record['receiver'],'borrowed':borrowed,'budget':execution_budget})['worker_export']
                                if not (record.get('export',{}).get('status')=='verified-decoder-result' and record['export'].get('private_input_preserving')):poison(([recv] if recv else [])+args,call['seq'])
                                else:poison([recv] if recv else [],call['seq'])
                                v=Value(observed)
                            elif ret.get('async_future',{}).get('operation')=='get' and identity(recv) in future_states:
                                v=receive_future(future_states[identity(recv)],observed,ret['seq'])
                            elif cfg.get('scalar_builders') and ins['owner']=='java/lang/StringBuilder' and identity(recv) in builders and (key=='java/lang/StringBuilder.toString()Ljava/lang/String;' or ins['name']=='append' and ins['desc'] in tuple('('+d+')Ljava/lang/StringBuilder;' for d in ('Ljava/lang/String;','Ljava/lang/Object;','C','I','J','F','D','Z'))):
                                fact=ret.get('scalar_contract');require(fact and fact['kind']=='string-builder' and fact['receiver']==identity(recv) and call['receiver_type']=='java.lang.StringBuilder','StringBuilder witness absent/identity differs')
                                require(all(runtime[0]['class_sha256'].get(k)==v for k,v in fact['class_sha256'].items()) and set(fact['class_sha256'])=={'java/lang/StringBuilder','java/lang/AbstractStringBuilder'},'StringBuilder runtime hash differs')
                                if not builder_was_poisoned:require(builder_initial[0]==fact['before'],'StringBuilder prior contents differ')
                                text,content=builders[identity(recv)];tainted=identity(recv) in poisoned_at
                                if tainted:content=Value({'value':text},unknown=True)
                                if ins['name']=='toString':
                                    require(fact['after']==fact['before']==observed.get('value') and not fact['returns_receiver'],'StringBuilder string result differs')
                                    if not tainted:require(text==fact['after'],'StringBuilder modeled result differs')
                                    v=content.project(observed)
                                else:
                                    require(fact['returns_receiver'] and observed.get('object')==identity(recv),'StringBuilder append receiver differs')
                                    operand=args[0];desc=descriptors(ins['desc'])[0]
                                    if desc=='Ljava/lang/Object;' and render_callback:
                                        require(child_value is not None and isinstance(child_value.observed.get('value'),str),'Rendering did not return String');operand=child_value
                                        if not tainted:require(fact['after']==text+operand.observed['value'],'Rendering append result differs')
                                    elif desc=='Ljava/lang/Object;' and plan.get('date_effects') and call.get('argument_types',[None])[0]=='java.util.Date':
                                        if not date_render(ret,call['args'][0]):poison([recv]+args,ret['seq']);tainted=True
                                        operand=Value({'value':fact['after'][len(fact['before']):]},unknown=True)
                                    elif desc=='Ljava/lang/Object;' and list_render:
                                        operand=Value({'value':fact['after'][len(fact['before']):]},unknown=True)
                                    elif desc=='Ljava/lang/Object;' and ret.get('request_render',{}).get('kind')=='empty-list-render':
                                        render=ret['request_render'];bind(operand,render['object']);require(runtime[0]['class_sha256'].get(render['class'])==render['class_sha256'],'Empty list render runtime differs');require(fact['after']==fact['before']+'[]','Empty list render result differs');operand=Value({'value':'[]'})
                                    elif desc=='Ljava/lang/Object;' and not (operand.observed.get('value','non-null') is None or call.get('argument_types',[None])[0]=='java.lang.String'):
                                        poison([recv]+args,ret['seq']);operand=Value(operand.observed,unknown=True);tainted=True;opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':ret['seq'],'completion':'opaque-render'})
                                    if not tainted:require(fact['after'].startswith(text),'StringBuilder append changed prefix')
                                    content=combine({'value':fact['after']},[content,operand]);content=Value(content.observed,content.origins,content.selectors,content.unknown or tainted);builders[identity(recv)]=(fact['after'],content);v=Value(observed)
                            elif resource_render:
                                render=ret.get('request_render');require(render and request_hashes(render['class_sha256']) and render['valid'],'Resource render closure witness absent/differs');bind(child_recv,render['content']);require(child_value is not None,'Resource render missing content callback');v=Value(observed,unknown=True)
                            elif child_value is not None:

                                bind(child_value,observed);v=child_value.project(observed)
                            elif key in cfg.get('conversion_contracts',{}).get('methods',[]):
                                conversions=[r for r in relevant if r['kind']=='json-conversion' and r.get('conversion_contract',{}).get('call_id')==call['call_id'] and call['seq']<r['seq']<ret['seq']]
                                require(len(conversions)==1,'Conversion invocation evidence absent/ambiguous');conversion=conversions[0];proof=conversion['conversion_contract']
                                require(proof['method']==key and proof['summary_class_sha256']==cfg['conversion_contracts']['summary_class_sha256'] and request_hashes(proof['class_sha256']),'Conversion library/callee differs');library_values(proof.get('library_values'));bind(args[0],proof['source']);bind(Value(observed),proof['target'])
                                require(proof['target_class'].replace('.','/')==class_literals.get(identity(args[1]),'')[1:-1],'Conversion target Class differs')
                                if proof['valid']:
                                    require(proof['serialization_valid'] and proof['read_class_matches'] and proof['source_after']==conversion['input'],'Conversion readonly/input proof contradicts events')
                                    decoder=proof['decoder'];owner=observed.get('object');require(decoder['valid'] and decoder['wrapper_kind']=='plain-bean' and decoder['content']==proof['target'],'Conversion decoder target differs')
                                    sites=cfg['decoder_birth_sites'];site=sites.get(decoder['content_type'].replace('.','/')+'.<init>()V');require(site,'Conversion constructor unsupported')
                                    born=[r for r in relevant if r['kind']=='execution-decoder-birth' and r['object']==owner and call['seq']<r['seq']<conversion['seq']]
                                    require(len(born)==1 and born[0]['class_sha256']==site['class_sha256'],'Conversion allocation missing/ambiguous');births[owner]=born[0]['seq']
                                    require(owner!=identity(args[0]) and owner not in nonlocal_owners,'Conversion output aliases existing input/boundary')
                                    inputs={f['path']:f for f in conversion['input']};require(len(inputs)==len(conversion['input']),'Duplicate conversion input pointer')
                                    fields={coordinate(f):f for f in decoder['fields']};require(len(fields)==len(decoder['fields']),'Duplicate decoded field')
                                    for f in conversion['output']:
                                        require(coordinate(f) in fields and fields[coordinate(f)]==f,'Conversion field/decoder projection differs');name=f['path'][1:]
                                        base=site.get('field_write_counts',{}).get(f['field'],0)
                                        if name in decoder['source_properties']:
                                            require(f['owner']==owner and f['version']==base+1 and f['path'] in inputs,'Conversion assigned field evidence differs')
                                            source=inputs[f['path']];require(source['owner']==identity(args[0]),'Conversion input is not a flat root Map field');same_value(source['observed'],f['observed'])
                                            if source['owner'] in maps and source['owner'] not in poisoned_at:
                                                mapping=maps[source['owner']];require(source['version']==mapping['epoch'] and source['field'].startswith('@map:'),'Conversion Map stage/field differs');value=mapping['values'].get(source['field'][5:],Value(source['observed'],unknown=True));bind(value,source['observed'])
                                            else:value=lookup(source,call['seq'])
                                        elif name in decoder['default_properties'] and f['version']==0 and f['observed'].get('value','non-null') is None:value=Value(f['observed'])
                                        else:value=Value(f['observed'],unknown=True)
                                        state.field_write(coordinate(f),value.project(f['observed']));field_seq[coordinate(f)]=conversion['seq']
                                    v=Value(observed)
                                else:poison(args,ret['seq']);opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':ret['seq'],'completion':'unsupported-conversion-contract','reason':proof.get('reason')})
                            elif ret.get('request_entity_contract') and cfg.get('request_entity_contracts'):
                                fact=ret['request_entity_contract'];kind=fact['kind'];request_fact(ret,kind)
                                expected={
                                    'org/springframework/http/RequestEntity.get(Ljava/net/URI;)Lorg/springframework/http/RequestEntity$HeadersBuilder;':'request-builder',
                                    'org/springframework/http/RequestEntity.post(Ljava/net/URI;)Lorg/springframework/http/RequestEntity$BodyBuilder;':'request-builder',
                                    'org/springframework/web/client/RestTemplate.exchange(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;':'request-exchange',
                                    'org/springframework/http/ResponseEntity.getBody()Ljava/lang/Object;':'entity-body',
                                    'org/springframework/http/HttpEntity.getBody()Ljava/lang/Object;':'entity-body',
                                    'org/springframework/hateoas/Resource.getContent()Ljava/lang/Object;':'resource-content',
                                    'org/springframework/hateoas/Resource.getId()Lorg/springframework/hateoas/Link;':'resource-link',
                                    'org/springframework/hateoas/Link.getHref()Ljava/lang/String;':'link-href',
                                    'org/springframework/http/RequestEntity.toString()Ljava/lang/String;':'request-empty-render',
                                }.get(key)
                                if ins['owner'] in ('org/springframework/http/RequestEntity$HeadersBuilder','org/springframework/http/RequestEntity$BodyBuilder'):
                                    if ins['name']=='accept' and ins['desc'].startswith('([Lorg/springframework/http/MediaType;)'):expected='request-header'
                                    elif ins['name']=='contentType' and ins['desc'].startswith('(Lorg/springframework/http/MediaType;)'):expected='request-header'
                                    elif ins['name']=='build' and ins['desc']=='()Lorg/springframework/http/RequestEntity;':expected='request-built'
                                    elif ins['name']=='body' and ins['desc']=='(Ljava/lang/Object;)Lorg/springframework/http/RequestEntity;':expected='request-built'
                                require(expected==kind,'RequestEntity witness attached to a different operation')
                                if not fact['valid']:
                                    poison(([recv] if recv else [])+args,ret['seq']);opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':ret['seq'],'completion':'unsupported-request-contract'})
                                elif kind=='request-builder':
                                    require(observed.get('object') not in request_builders,'Request builder identity reused')
                                    request_builders[observed['object']]={'uri':fact['uri'],'method':fact['method'],'headers':0};v=Value(observed)
                                elif kind=='request-header':
                                    require(identity(recv) in request_builders and identity(recv)==observed.get('object'),'Request header builder differs')
                                    if ins['name']=='accept':
                                        array=state.arrays.get(identity(args[0]));require(array is not None and len(array['elements'])==len(fact['values']),'Request media array absent')
                                        for value,item in zip(array['elements'],fact['values']):bind(value,item)
                                    else:bind(args[0],fact['values'][0])
                                    request_builders[identity(recv)]['headers']+=1;v=recv.project(observed)
                                elif kind=='request-built':
                                    b=request_builders.get(identity(recv));require(b is not None and b['uri']==fact['uri'] and b['method']==fact['method'],'Request terminal builder method/URI differs')
                                    body=args[0] if args else Value({'value':None,'object':None});bind(body,fact['body'])
                                    request_entities[observed['object']]={**b,'body':body,'headers':fact['headers']};v=Value(observed)
                                elif kind=='request-empty-render':
                                    request=request_entities.get(identity(recv));require(request and request['uri']==fact['request']['uri'] and fact['request']['body'].get('value','not-null') is None,'Request render identity/body differs');v=Value(observed)
                                elif kind in ('resource-link','link-href'):
                                    bind(Value(observed),fact['link'] if kind=='resource-link' else fact['href']);v=Value(observed,unknown=True)
                                elif kind=='request-exchange':
                                    request=request_entities.get(identity(args[0]));require(request is not None and request['uri']==fact['uri'] and request['method']==fact['method'] and request['headers']==fact['headers'],'Exchange not bound to actual request')
                                    bind(request['body'],fact['body']);poison(([recv] if recv else [])+args,call['seq'])
                                    reads=[r for r in relevant if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and call['seq']<r['seq']<ret['seq']]
                                    require(len(reads)==1,'Request exchange decoder read missing/ambiguous');read=reads[0]
                                    same_value(fact['response_body'],read['decoded_body']);require(fact['response_type']==read['decoded_type'],'Exchange decoded response type differs')
                                    starts=[r for r in relevant if r['kind']=='http-rpc-enter' and r.get('message')==read['message'] and call['seq']<r['seq']<read['seq']]
                                    finishes=[r for r in relevant if r['kind']=='http-rpc-exit' and r.get('message')==read['message'] and read['seq']<r['seq']<ret['seq']]
                                    parent_frame=root['frame']
                                    if worker_request:
                                        task=next(t for t in async_audit['tasks'] if t.get('worker_frame')==root['frame']);parent_frame=task['caller_frame']
                                    messages={r.get('message') for r in rows if r['kind'] in ('binding-input','binding-return') and r.get('frame')==parent_frame and r.get('message')}
                                    require(len(starts)==len(finishes)==1 and starts[0]['uri']==fact['uri'] and starts[0]['method']==fact['method'] and read.get('parent_message') in messages,'Request exchange message/call context differs')
                                    decoder=read.get('resource_decoder')
                                    if fact['response_type']=='org.springframework.hateoas.Resource' or fact['response_type'].replace('.','/') in plan.get('json_schema',{}):require(decoder is not None,'Required typed decoder witness absent')
                                    if decoder:
                                        require(decoder['kind']=='resource-decoded' and request_hashes(decoder['class_sha256']),'Resource decoder library witness differs')
                                        bind(Value(fact['response_body']),decoder['wrapper'])
                                        if decoder['valid']:
                                            content=decoder['content'];owner=content.get('object')
                                            births_=[r for r in relevant if r['kind']=='execution-decoder-birth' and r['object']==owner and call['seq']<r['seq']<read['seq']]
                                            require(len(births_)==1,'Decoded content fresh allocation absent/ambiguous');birth=births_[0];site=cfg['decoder_birth_sites'].get(birth['constructor']);require(site and site['class_sha256']==birth['class_sha256'],'Decoded content constructor pin differs')
                                            require(owner not in nonlocal_owners and owner not in decoded_seq,'Decoded content aliases an existing boundary')

                                            if decoder['wrapper_kind']=='resource':resources[fact['response_body']['object']]=Value(content)
                                            decoded_types[owner]=decoder['content_type'].replace('.','/');decoded_seq[owner]=read['seq']
                                            roles={}
                                            for f in decoder['fields']:
                                                base=site['field_write_counts'].get(f['field'],0);name=f['path'][1:]
                                                if name in decoder['ignored']:require(f['version']==base,'Ignored property was written');roles[name]='default'
                                                elif name in decoder['properties']:
                                                    require(f['version'] in (base,base+1),'Duplicate/unmodeled decoder field writes');roles[name]='source' if f['version']==base+1 else 'default'
                                            require(set(decoder['source_properties'])=={n for n,r in roles.items() if r=='source'} and set(decoder['default_properties'])=={n for n,r in roles.items() if r=='default'},'Decoder source/default roles differ from actual writes')
                                            require(read['fields']==[f for f in decoder['fields'] if roles.get(f['path'][1:])=='source'],'Decoder projection not actual input writes')
                                            for index,f in enumerate(read['fields']):
                                                require(f['owner']==owner and f['path'][1:] in decoder['source_properties'],'Decoder property owner/name differs')
                                                providers[coordinate(f)].append((read,index,f));decoded_fields[coordinate(f)]=origin(f,ret['seq']);field_seq[coordinate(f)]=read['seq'];state.field_write(coordinate(f),decoded_fields[coordinate(f)])
                                            for f in decoder['fields']:
                                                if f['path'][1:] not in decoder['default_properties']:continue
                                                require(f['owner']==owner,'Ignored decoder field owner differs')
                                                if f['version']==0 and f['observed'].get('value','not-null') is None and f['field'] not in site.get('written_fields',[]):
                                                    decoded_fields[coordinate(f)]=Value(f['observed']);state.field_write(coordinate(f),decoded_fields[coordinate(f)]);field_seq[coordinate(f)]=read['seq']
                                            heap_refs[fact['response_body']['object']].add(owner)
                                    outgoing=[r for r in relevant if r['kind']=='http-json' and r.get('phase')=='write' and r.get('direction')=='request' and call['seq']<r['seq']<read['seq']]
                                    proof=not outgoing and request['body'].observed.get('value','not-null') is None
                                    if outgoing:
                                        proof=len(outgoing)==1 and outgoing[0].get('request_serialization',{}).get('valid',False)
                                        if proof:
                                            sf=outgoing[0]['request_serialization'];require(request_hashes(sf['class_sha256']),'Request serializer library differs')
                                    transport_effects.append(proof)
                                    response_entities[observed['object']]=Value(fact['response_body']);v=Value(observed)
                                elif kind=='entity-body':
                                    body=response_entities.get(identity(recv));bind(Value(observed),fact['body'])
                                    if body is not None:bind(body,observed);v=body.project(observed)
                                    else:poison([recv,Value(observed)],ret['seq'])
                                elif kind=='resource-content':
                                    content=resources.get(identity(recv));bind(Value(observed),fact['content'])
                                    if content is not None:bind(content,observed);v=content.project(observed)
                                    else:poison([recv],ret['seq'])
                                else:raise ValueError('Unsupported request witness kind: '+kind)
                            elif key=='java/util/Date.toString()Ljava/lang/String;' and plan.get('date_effects'):
                                if not date_render(ret,call['receiver']):poison([recv],ret['seq'])
                                v=Value(observed,unknown=True)
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
                            elif key.endswith('.save(Ljava/lang/Object;)Ljava/lang/Object;') and cfg.get('save_effect_contracts') and not cfg['save_effect_contracts'].get('observation_only',True):
                                proofs=[r for r in relevant if r['kind']=='mongo-save-effect' and r.get('call_id')==call['call_id'] and call['seq']<r['seq']<ret['seq']]
                                require(len(proofs)==1,'Save effect completion missing/ambiguous');proof=proofs[0]
                                require(proof['completion']=='normal' and proof['frame']==fr.invocation,'Save lifecycle differs');bind(args[0],proof['entity']);bind(Value(observed),proof['result'])
                                if proof['valid']:
                                    contract=cfg['save_effect_contracts'];matches=[p for p in [contract,*contract.get('additional_profiles',[])]if p['class_sha256']==proof['class_sha256']];require(len(matches)==1,'Save library profile absent/ambiguous');profile=matches[0]
                                    bind(args[0],proof['result']);bind(args[0],observed)
                                    if profile.get('provided_id_only'):require(proof.get('provided_id_only') and proof['id_before'].get('value')is not None and proof['id_before']==proof['id_after'] and not proof.get('id_write'),'Provided-ID save changed/generates ID')
                                    require(proof.get('preconditions') and proof.get('listeners_verified') and proof.get('callback_invocations')==0 and proof['events']>=3 and proof['registry']==proof['default_registry'] and proof['converters']==proof['default_converters'],'Save preservation conditions contradict runtime')
                                    before={coordinate(f):f for f in proof['before']};after={coordinate(f):f for f in proof['after']};identifier=proof.get('id_write')
                                    protected={}
                                    for k,f in before.items():
                                        if identifier and k[:2]==(identifier['owner'],identifier['field']):continue
                                        if 'value' not in f['observed']:continue  # Mutable references/Date need their own proofs.
                                        c=state.containers.get(k[0])
                                        if k[1].startswith('@list:')and c is not None and c.local and not c.escaped:
                                            index=int(k[1].split(':')[1]);require(k[2]==c.epoch and 0<=index<len(c.elements),'Save list member stage differs');value=c.elements[index];bind(value,f['observed']);protected[k]=value
                                        else:protected[k]=lookup(f,call['seq'])
                                    protected={k:v.project({a:b for a,b in v.observed.items()if a!='object'})if k[1]in primitive_fields else v for k,v in protected.items()}
                                    for k,f in before.items():
                                        if identifier and k[0]==identifier['owner'] and k[1]==identifier['field']:continue
                                        require(k in after and after[k]==f,'Unmodeled save field effect')
                                    if identifier:
                                        require(identifier['owner']==identity(args[0]) and identifier['field']==proof['id_field'] and coordinate(identifier) not in before,'Save ID write object/field/version differs')
                                        ws=[w for w in writes if w['seq']==identifier['seq']];require(len(ws)==1 and all(ws[0][k]==identifier[k] for k in ('owner','field','version','observed')),'Native save ID write evidence absent/differs');write_field(identifier,Value(identifier['observed'],unknown=True))
                                    # The finite contract confines domain DTOs, not all
                                    # database/global effects. Existing shared state and
                                    # mutable Date operands remain conservative.
                                    poison([recv] if recv else [],ret['seq'])
                                    # Retain only dependencies already established
                                    # before this verified effect. This cannot turn
                                    # an earlier unknown into a source or protect
                                    # unobserved fields/versions from later calls.
                                    for k,value in protected.items():preserved_fields[k]=(ret['seq'],value)
                                    dates_safe=False
                                    if plan.get('date_effects'):
                                        codecs=proof.get('date_codecs');require(isinstance(codecs,list) and len(codecs)==proof.get('date_codec_calls'),'Date codec observation count differs')
                                        dates_safe=bool(codecs) and all(c['valid'] for c in codecs)
                                        for c in codecs:
                                            require(c.get('class_sha256')==plan['date_effects']['codec_class_sha256'],'Date codec class hashes differ')
                                            if c['valid']:require(c['encoder']=='com.mongodb.DBObjectCodec' and c['date_codec']=='org.bson.codecs.DateCodec' and c['default_registry'] and not c['encoding_hooks'] and c['id_generator']=='org.bson.codecs.ObjectIdGenerator','Default Date encoder conditions contradict runtime')
                                    for f in proof['before']:
                                        if 'date_epoch_ms' in f['observed'] and not dates_safe:poison([Value(f['observed'])],ret['seq'])
                                    v=args[0].project(observed)
                                else:
                                    poison(([recv] if recv else [])+args,ret['seq']);opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':ret['seq'],'completion':'unsupported-save-effects','reason':proof.get('reason')})
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
                            elif key=='java/util/Optional.isPresent()Z' and cfg.get('library_values') and identity(recv) in state.optionals:
                                fact=ret.get('contract');require(fact and fact['valid'] and fact['kind']=='optional-presence' and call['receiver_type']=='java.util.Optional','Optional presence witness absent/invalid')
                                require(fact['present']==(state.optionals[identity(recv)] is not None) and observed.get('value')==fact['present'],'Optional presence contradicts actual member');v=Value(observed)
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
                                    require(observed.get('value') is True,'Execution append failed')
                                    require(ret.get('collection_after')==call.get('collection',[])+call['args'],'Execution append physical member delta differs')
                                    require(ret['collection_epoch']==call['collection_epoch']+1,'Execution append content version differs')
                                    if c.local and not c.escaped and not args[0].allocation==recv.allocation:
                                        c.elements.append(args[0]);v=Value(observed)
                                    else:
                                        # The application may mutate received state. An
                                        # unproved ownership effect is conservative unknown,
                                        # not a collector exception changing the business.
                                        after=ret.get('collection_after');require(after is not None,'Opaque list mutation post-state absent')
                                        poison([recv]+args,ret['seq']);c.elements=[Value(x,unknown=True) for x in after];c.escaped=True;v=Value(observed,unknown=True)
                                        opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':ret['seq'],'completion':'unproved-list-ownership'})
                                    c.epoch=ret['collection_epoch']
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
                            elif key=='org/springframework/hateoas/Resource.toString()Ljava/lang/String;' and cfg.get('request_entity_contracts') and ret.get('request_render',{}).get('plain_object'):
                                render=ret['request_render'];require(request_hashes(render['class_sha256']) and render['valid'],'Resource render contract differs');v=Value(observed,unknown=True)
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
                            elif key in ('java/lang/String.length()I','java/lang/String.split(Ljava/lang/String;)[Ljava/lang/String;','java/util/UUID.toString()Ljava/lang/String;','java/lang/Integer.parseInt(Ljava/lang/String;)I'):
                                from finite_string_values import utf16_length,literal_split,decimal_int
                                fact=ret.get('finite_value_contract');own=ins['owner'];require(fact and fact['callee']==key and fact['class']==own,'Immutable value call proof missing/different')
                                profiles=cfg['library_contracts']['filter_profiles']if own=='java/lang/String'else cfg['library_values']['profiles']
                                require(any(p['java_runtime_version']==runtime[0]['java_runtime_version']and p['class_sha256'].get(own)==fact['class_sha256']for p in profiles),'Immutable value runtime class differs')
                                if own=='java/lang/String':require(call['receiver_type']=='java.lang.String'and type(recv.observed.get('value'))is str,'String receiver differs')
                                if key=='java/lang/String.length()I':require(observed.get('value')==utf16_length(recv.observed['value']),'String length differs');v=combine(observed,[recv])
                                elif key=='java/util/UUID.toString()Ljava/lang/String;':
                                    require(call['receiver_type']=='java.util.UUID'and recv.observed.get('uuid_type')=='java.util.UUID'and observed.get('value')==recv.observed.get('value'),'UUID projection differs');v=combine(observed,[recv])
                                elif own=='java/lang/Integer':require(observed.get('value')==decimal_int(args[0].observed['value']),'Decimal parse differs');v=combine(observed,args)
                                else:
                                    expected=literal_split(recv.observed['value'],args[0].observed['value']);array=fact['array'];bind(Value(observed),array['array']);owner=observed.get('object')
                                    require(ret['result_type']=='[Ljava.lang.String;'and owner not in state.arrays and owner not in nonlocal_owners and array['version']==0 and array['element_versions']==[0]*len(expected)and array['component']=='java.lang.String'and [x.get('value')for x in array['elements']]==expected,'Split fresh array/contents differs')
                                    values=[Value(x,recv.origins,recv.selectors|args[0].origins|args[0].selectors,recv.unknown or args[0].unknown)for x in array['elements']]
                                    state.arrays[owner]={'elements':values,'version':0,'versions':[0]*len(values)};v=Value(observed)
                            elif key=='java/lang/Integer.intValue()I' and cfg.get('library_values'):
                                library_values(ret.get('library_values'));require(call['receiver_type']=='java.lang.Integer','Unboxing implementation differs');same_value(recv.observed,observed);v=recv.project(observed)
                            elif ins['owner'] in ('java/util/Map','java/util/HashMap') and ins['name'] in ('get','put') and cfg.get('library_values') and identity(recv) in maps and identity(recv) not in poisoned_at and identity(recv) not in nonlocal_owners:
                                library_values(ret.get('library_values'));require(call['receiver_type']=='java.util.HashMap' and type(args[0].observed.get('value'))is str,'Map contract requires exact HashMap/String key');owner=identity(recv);key_value=args[0].observed['value']
                                require(owner in maps and maps[owner]['local'] and owner not in poisoned_at,'Map ownership not proved');mapping=maps[owner];before=call.get('collection');require(before is not None and call['collection_epoch']==mapping['epoch'],'Map content stage differs')
                                require({x['key']:x['observed']for x in before}=={k:actual(x)for k,x in mapping['values'].items()},'Map pre-state differs')
                                previous=mapping['values'].get(key_value,Value({'object':None,'value':None}));bind(previous,observed)
                                if ins['name']=='put':
                                    mapping['values'][key_value]=args[1].project(call['args'][1])
                                    if 'value'not in args[1].observed and identity(args[1])is not None:heap_refs[owner].add(identity(args[1]))
                                require({x['key']:x['observed']for x in ret['collection_after']}=={k:actual(x)for k,x in mapping['values'].items()},'Map post-state differs');mapping['epoch']=ret['collection_epoch'];v=previous.project(observed)
                            elif key=='java/lang/Integer.valueOf(I)Ljava/lang/Integer;':v=args[0].project(observed);same_value(args[0].observed,observed)
                            elif ins['owner']=='org/slf4j/Logger' and ins['name'] in ('info','warn','error','debug') and all('value' in a.observed for a in args):v=Value(observed)
                            else:
                                poison(([recv] if recv else [])+args,ret['seq']);opaque_calls.append({'frame':fr.invocation,'callee':key,'seq':ret['seq'],'completion':'normal-call'})
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
                depth-=1
                fr,method,code,entry=saved
        root_args=[]
        for index,arg in enumerate(root['args']):
            if worker_request:
                inherited=worker_request['args'][index]
                if worker_request['borrowed'][index]:
                    require(inherited.observed.get('object')==arg.get('object'),'Borrowed worker argument identity differs')
                    inherited=Value(arg,unknown=True)
                    if arg.get('object'):
                        poisoned_at[arg['object']]=root['seq']-1;state.poisoned.add(arg['object'])
                root_args.append(inherited);continue
            desc=descriptors(plan['collection_method']['desc'])[index]
            if desc in ('Z','B','C','S','I','J','F','D'):arg={k:v for k,v in arg.items() if k!='object'}
            value=Value(arg)
            if 'value' in arg or 'date_epoch_ms' in arg:value=Value(arg,frozenset({('argument',root['frame'],index)}))
            root_args.append(value)
        returned,error=execute(root,root_args,worker_request['receiver'] if worker_request else Value({'object':root['receiver']}) if root.get('receiver') else None)
        require(pos==len(events),'Application unconsumed necessary evidence')
        if worker_request:
            def materialize(v):return Value(actual(v),v.origins,v.selectors,v.unknown)
            if error is not None:
                return {'worker_export':{'value':None,'error':error,'fields':{},'field_seq':{},'status':'exceptional'}}
            payload=async_results.get(identity(returned))
            if payload is None:
                unwrap=next(r for r in rows if r['kind']=='async-worker-unwrapped' and r.get('task_id')==root.get('async_task_id'))
                payload=Value(unwrap['result'],unknown=True)
            payload=materialize(payload);owner=payload.observed.get('object');local=set(state.allocations.values());exports={}
            local_arrays={r['array']['object'] for r in relevant if r['kind']=='execution-array' and r['operation']=='new'}
            outward=any(k[0] not in local for k in state.fields) or any(r['kind']=='execution-array' and r['operation']=='store' and r['array']['object'] not in local_arrays for r in relevant)
            private=owner in local and owner not in poisoned_at and not outward and not opaque_calls
            fields={k:materialize(v) for k,v in state.fields.items() if k[0]==owner}
            if private and fields and all('value' in v.observed and 'date_epoch_ms' not in v.observed for v in fields.values()):exports=fields
            elif 'value' not in payload.observed or 'date_epoch_ms' in payload.observed:payload=Value(payload.observed,unknown=True)
            if opaque_calls or outward:payload=Value(payload.observed,unknown=True);exports={}
            exported_resources={};external_writes=outward
            verified_decoder=False
            if owner in resources or owner in decoded_seq:
                content=resources.get(owner,Value(payload.observed));content_owner=identity(content);birth_seq=decoded_seq.get(content_owner)
                later_opaque=any(c['seq']>=birth_seq for c in opaque_calls) if birth_seq else True
                # A closed, freshly allocated decoder projection is a distinct
                # ownership path. Earlier opaque request setup cannot touch it.
                external_writes=any(k[0] not in local|set(decoded_seq) for k in state.fields) or any(r['kind']=='execution-array' and r['operation']=='store' and r['array']['object'] not in local_arrays for r in relevant)
                if birth_seq and content_owner not in poisoned_at and not later_opaque and not external_writes:
                    exports={k:materialize(v) for k,v in state.fields.items() if k[0]==content_owner and k in decoded_fields}
                    if owner in resources:exported_resources[owner]=materialize(content)
                    payload=Value(payload.observed);verified_decoder=True
            return {'worker_export':{'value':payload,'fields':exports,'field_seq':{k:field_seq[k] for k in exports},'resources':exported_resources,'decoded_types':{identity(v):decoded_types[identity(v)] for v in exported_resources.values()},'private_input_preserving':not opaque_calls and not unproved_statics and not external_writes and all(transport_effects),'status':'verified-decoder-result' if verified_decoder else 'private-result' if exports else 'scalar-result' if not payload.unknown else 'unsupported-or-opaque-result','frames':frame_audits,'opaque_calls':opaque_calls}}
        if end['kind']=='abort':
            require(error is not None,'Application root abort disagrees with replay');audits.append({'frame':root['frame'],'completion':'aborted','steps':total_steps,'frames':frame_audits,'answers':0});continue
        require(error is None,'Application normal root has unhandled exception')
        returns=[r for r in relevant if r['kind']=='binding-return' and r['frame']==root['frame']];require(len(returns)==1,'Application return binding absent');ret=returns[0]
        for f in ret['fields']:
            owner,name,version=coordinate(f)
            if name.startswith('@list:') and owner in state.containers and state.containers[owner].local:
                c=state.containers[owner];index=int(name.split(':')[1]);require(version==c.epoch and 0<=index<len(c.elements),'Application returned container version differs');value=c.elements[index]
                if c.escaped:
                    preservation=preserved_fields.get(coordinate(f))
                    value=lookup(f,ret['seq'])if preservation and poisoned_at.get(owner,-1)<=preservation[0]<ret['seq']else Value(f['observed'],unknown=True)
            else:value=lookup(f,ret['seq'])
            if 'date_epoch_ms' in f['observed'] and f['observed']['object'] in poisoned_at:value=Value(f['observed'],unknown=True)
            bind(value,f['observed'])
            results.append({'root_frame':root['frame'],'seq':ret['seq'],'path':f['path'],**f,'known':not value.unknown,'origins':[list(x) for x in sorted(value.origins,key=str)],'selectors':[list(x) for x in sorted(value.selectors,key=str)]})
        audits.append({'frame':root['frame'],'completion':'normal','steps':total_steps,'frames':frame_audits,'answers':len(ret['fields']),'poisoned_objects':len(poisoned_at),'opaque_frames':opaque_frames,'opaque_calls':opaque_calls,'environment_facts':environment_facts,'async_transfers':async_transfers,'steps_including_tasks':execution_budget['steps']})
    return {'answers':results,'roots':audits,'evidence_policy':cfg['evidence_policy'],'async_protocol':async_audit}
