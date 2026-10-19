"""Actual root-return/serialization binding; output snapshots never create sources."""
from query_observation_planner import require


def matches(pattern,path):
    a=pattern.split('/');b=path.split('/')
    return len(a)==len(b) and all(x==y or x=='*' and y.isdecimal() for x,y in zip(a,b))


def sources(graph,role):
    plan=graph.plans[role]; config=plan.get('response_binding')
    if not config:return
    graph.binding_blocked=getattr(graph,'binding_blocked',{})
    for row in graph.rows[role]:
        kind=row['kind']
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
                    require(f['observed'].get('value')==node['observed'].get('value'),'Bound response value changed')
                    candidates.append((ret,f))
        if len(candidates)!=1:
            node['unknown']='Root-to-serialized target witness missing or ambiguous';continue
        ret,f=candidates[0];local=(role,'bound-return',ret['seq'],node['path'])
        graph.add(local,dict(f,service=role,seq=ret['seq'],kind='input-snapshot',root_frame=ret['frame'],message=ret.get('message')))
        graph.alias(local)
        if local not in graph.edges:graph.nodes[local]['unknown']='No source or computed provider for actual returned field'
        scope=(role,ret['frame'],(f['owner'],f['field'],f['version']))
        if any(enters[ret['frame']]['seq']<s<ret['seq'] for s in graph.binding_blocked.get(scope,[])):
            graph.nodes[local]['unknown']='Unmodeled necessary call result/effect touches returned field'
        graph.edges[key]=[local]
