"""Actual root-return/serialization binding; output snapshots never create sources."""
from query_observation_planner import require


def matches(pattern,path):
    a=pattern.split('/');b=path.split('/')
    return len(a)==len(b) and all(x==y or x=='*' and y.isdecimal() for x,y in zip(a,b))


def sources(graph,role):
    plan=graph.plans[role]; config=plan.get('response_binding')
    if not config:return
    if plan.get('read_forward_contracts'):audit_read_effects(graph.rows[role],plan)
    graph.binding_blocked=getattr(graph,'binding_blocked',{})
    for row in graph.rows[role]:
        kind=row['kind']
        if kind=='binding-call-summary' and not row['root_effects_verified']:
            for f in row['fields']:
                scope=(role,row['frame'],(f['owner'],f['field'],f['version']))
                graph.binding_blocked.setdefault(scope,[]).append(row['seq'])
            continue
        if kind in ('binding-call-exit','binding-call-throw') and not row['valid']:
            for f in row['detail']['effect_fields']:
                scope=(role,row['frame'],(f['owner'],f['field'],f['version']))
                graph.binding_blocked.setdefault(scope,[]).append(row['seq'])
            continue
        if kind not in ('binding-source','binding-input','binding-opaque-touch','binding-opaque-result'):continue
        if kind=='binding-source':require(row['callee'] in config['source_calls'],'Undeclared source call')
        for index,f in enumerate(row['fields']):
            coord=(f['owner'],f['field'],f['version']);scope=(role,row['frame'],coord)
            if kind.startswith('binding-opaque'):
                graph.binding_blocked.setdefault(scope,[]).append(row['seq']);continue
            key=(role,'binding-source',row['seq'],index)
            node=dict(f,service=role,seq=row['seq'],kind='binding-source',root_frame=row['frame'],
                      source_kind=kind,message=row.get('message'),callee=row.get('callee'),argument=row.get('argument'))
            graph.add(key,node);graph.providers[(role,coord)].append(key)


def audit_read_effects(rows,plan):
    """A missing/mispaired contract witness can never silently certify a call."""
    stacks={};counts={};streams={};optional={};runtime=[];summaries={};call_ids=set();roots={};ends={};returned=set();failed_roots=set()
    lifecycle=plan['read_forward_contracts'].get('version',1)>=2
    classes={r['class'] for r in rows if r['kind']=='class'}
    for r in rows:
        k=r['kind'];thread=r['thread'];stack=stacks.setdefault(thread,[])
        coord=(thread,r.get('frame'))
        if k=='enter' and r['method']==plan['entry']:
            require(coord not in roots,'Duplicate read-effect root identity');roots[coord]=r
        if k in ('exit','abort'):ends.setdefault(coord,[]).append(r)
        if k=='binding-return':returned.add(coord)
        if k=='binding-call-runtime':
            require(any(r['java_runtime_version']==p['java_runtime_version'] and r['class_sha256']==p['class_sha256'] for p in plan['read_forward_contracts']['runtime_profiles']),'Read-effect runtime pin differs')
            runtime.append(r)
        elif k=='binding-call-enter':
            require(r.get('call_id') and r.get('mode') in {'existing','composed','opaque','list-stream','stream-first','optional-present'},'Invalid read-effect call declaration')
            require(r['call_id'] not in call_ids,'Repeated read-effect call identity');call_ids.add(r['call_id'])
            stack.append(r);counts[(thread,r['frame'])]=counts.get((thread,r['frame']),0)+1
        elif k in ('binding-call-exit','binding-call-throw'):
            if not r['valid']:failed_roots.add((thread,r['frame']))
            require(bool(stack),'Read-effect exit without entry');start=stack.pop()
            require(all(r.get(k)==start.get(k) for k in ('call_id','callee','receiver','receiver_type','mode','implementation','frame')),'Read-effect call pairing differs')
            if lifecycle:
                expected='exceptional' if k=='binding-call-throw' else 'normal'
                require(r['detail'].get('completion')==expected,'Read-effect completion kind differs')
            if k=='binding-call-throw':
                require(lifecycle and not r['valid'] and r['detail'].get('exception_object') and r['detail'].get('exception_type'),'Invalid exceptional invocation witness')
                continue
            if not r['valid']:continue
            mode=r['mode'];d=r['detail']
            if mode=='composed':
                require(r['implementation'] in plan['read_forward_contracts']['composed_methods'],'Undeclared composed implementation')
                require(r['implementation'].split('.')[0] in classes,'Composed implementation lacks checked class')
            elif mode=='list-stream':
                require(r['callee'] in ('java/util/Collection.stream()Ljava/util/stream/Stream;','java/util/List.stream()Ljava/util/stream/Stream;'),'Wrong list stream contract')
                require(start['detail']['element_ids']==d['element_ids'],'List changed during stream creation')
                streams[d['result_object']]=d['element_ids']
            elif mode=='stream-first':
                require(r['callee']=='java/util/stream/Stream.findFirst()Ljava/util/Optional;' and r['receiver'] in streams,'Stream first lacks actual list creation')
                ids=streams.pop(r['receiver']);require(ids==d['element_ids'],'Stream membership differs')
                require(d['present']==bool(ids) and d['selected_object']==(ids[0] if ids else None),'Stream did not select actual first object')
                optional[d['result_object']]=d['selected_object']
            elif mode=='optional-present':
                # Present Optional never executes its Supplier. Result identity
                # must be the contained value, not a same-valued replacement.
                require(r['callee']=='java/util/Optional.orElseGet(Ljava/util/function/Supplier;)Ljava/lang/Object;' and r['receiver_type']=='java.util.Optional','Wrong Optional contract')
                require(d['selected_object'] is not None and d['selected_object']==d['result_object']==start['detail']['selected_object'],'Optional selected identity differs')
                require(optional.get(r['receiver'])==d['selected_object'],'Optional result lacks checked findFirst witness')
        elif k=='binding-call-summary':
            coord=(thread,r['frame']);require(coord not in summaries,'Duplicate read-effect root summary');summaries[coord]=r
            verified=plan['entry'] in plan['read_forward_contracts']['composed_methods'] and not (plan.get('date_projection') and coord in failed_roots)
            require(r['root_effects_verified']==verified,'Root effect proof differs from frozen analysis')
            require(r['calls']==counts.pop(coord,0),'Executed call witness count differs')
            require(r['unpaired']==0 and not stack,'Read-effect call evidence incomplete (including exceptional calls)')
    require(not any(stacks.values()) and not counts,'Missing read-effect completion/summary')
    if lifecycle:
        require(summaries.keys()==roots.keys(),'Missing/extra read-effect root lifecycle')
        for coord,summary in summaries.items():
            completed=ends.get(coord,[])
            require(len(completed)==1 and roots[coord]['seq']<summary['seq']<completed[0]['seq'],'Missing/ambiguous read-effect root completion')
            require(summary.get('completion')==('normal' if completed[0]['kind']=='exit' else 'exceptional'),'Root completion kind differs')
            require(coord not in returned or completed[0]['kind']=='exit','Aborted root supplied a return witness')
    if any(r['kind']=='binding-return' for r in rows):require(len(runtime)==1,'Missing/ambiguous read-effect runtime witness')


def bind_outputs(graph,role):
    config=graph.plans[role].get('response_binding')
    if not config:return
    rows=graph.rows[role];enters={r['frame']:r for r in rows if r['kind']=='enter' and r['method']==graph.plans[role]['entry']}
    returns=[r for r in rows if r['kind']=='binding-return']
    for ret in returns:
        require(ret['frame'] in enters,'Return witness does not belong to configured entry')
        ends=[r for r in rows if r['kind']=='exit' and r['frame']==ret['frame']]
        require(len(ends)==1 and ends[0]['result']==ret['result'],'Root return witness/result disagree')
    for key,event in graph.json:
        if key[0]!=role or event['direction']!='response' or event['phase']!='write':continue
        node=graph.nodes[key]
        if not matches(config['path'],node['path']):continue
        candidates=[]
        for ret in returns:
            if ret.get('message')!=event['message'] or ret['seq']>=event['seq']:continue
            for f in ret['fields']:
                if config['root_prefix']+f['path']==node['path'] and (f['owner'],f['field'],f['version'])==(node['owner'],node['field'],node['version']):
                    if 'date_epoch_ms' in f['observed']:
                        from infer_execution_kernel import same_value
                        same_value(f['observed'],node['observed'])
                    require(f['observed'].get('value')==node['observed'].get('value'),'Bound response value changed')
                    candidates.append((ret,f))
        if len(candidates)!=1:
            node['unknown']='Root-to-serialized target witness missing or ambiguous';continue
        ret,f=candidates[0];local=(role,'bound-return',ret['seq'],node['path'])
        if graph.plans[role]['profile']=='execution-dependency':
            provider=getattr(graph,'execution_outputs',{}).get((role,ret['seq'],f['path']))
            require(provider is not None,'Execution target proof absent')
            require((graph.nodes[provider]['owner'],graph.nodes[provider]['field'],graph.nodes[provider]['version'])==(f['owner'],f['field'],f['version']),'Execution target coordinate differs')
            graph.edges[key]=[provider]
            continue
        graph.add(local,dict(f,service=role,seq=ret['seq'],kind='input-snapshot',root_frame=ret['frame'],message=ret.get('message')))
        graph.alias(local)
        if local not in graph.edges:graph.nodes[local]['unknown']='No source or computed provider for actual returned field'
        scope=(role,ret['frame'],(f['owner'],f['field'],f['version']))
        if any(enters[ret['frame']]['seq']<s<ret['seq'] for s in graph.binding_blocked.get(scope,[])):
            graph.nodes[local]['unknown']='Unmodeled necessary call result/effect touches returned field'
        graph.edges[key]=[local]
