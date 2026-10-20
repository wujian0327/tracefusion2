"""Discover bytecode methods and conservative effects; never per-business summaries."""
from plan_service_observations import callee
from plan_collection_service import analyze
from query_observation_planner import require
from analysis_status import AnalysisLimit


def augment_calls(plan,model,sources):
    from plan_execution_kernel import constructor_writes
    methods={};targets={};opaque={};visiting=set();constructors=dict(plan['execution_kernel']['constructors'])
    supported={0,1,2,3,4,5,6,7,8,16,17,18,87,89,96,100,104,132,167,178,180,181,182,183,184,185,187,191,192,198,199}|set(range(21,26))|set(range(54,59))|set(range(153,167))|set(range(172,178))
    def subtype(child,parent,seen=None):
        if child==parent:return True
        seen=set() if seen is None else seen
        if child in seen or child not in model['classes']:return False
        seen.add(child);c=model['classes'][child]
        return any(subtype(x,parent,seen) for x in [c.get('super'),*c.get('interfaces',[])] if x)
    def candidates(ins):
        key=callee(ins)
        if ins['op'] in (183,184):return [key] if key in model['methods'] else []
        return [k for k,m in model['methods'].items() if m['name']==ins['name'] and m['desc']==ins['desc'] and m['instructions'] and subtype(m['owner'],ins['owner'])]
    def validate(key):
        m=model['methods'][key];require(m['instructions'] and not m['access']&(256|1024),'No concrete application bytecode')
        require(not model['classes'][m['owner']]['access']&512,'Interface default method dispatch unsupported')
        initializer=model['methods'].get(m['owner']+'.<clinit>()V')
        if m['access']&8 and m['owner']!=model['methods'][plan['entry']]['owner']:
            require(initializer is None or all(x['op'] in (0,177) for x in initializer['instructions']),'Foreign application static initialization unsupported')
        require(not m['access']&32,'Synchronized application methods unsupported')
        for ins in m['instructions']:
            require(ins['op'] in supported,'Application opcode unsupported: '+str(ins['op']))
            if ins['op']==18:require(ins.get('constant_type')!='Type','Class literal projection unsupported')
            if ins['op']==183 and ins['name']=='<init>':
                call=callee(ins)
                if call=='java/util/ArrayList.<init>()V':constructors[call]={}
                else:
                    require(call in model['methods'],'Application constructor bytecode absent: '+call)
                    initializer=model['methods'].get(ins['owner']+'.<clinit>()V')
                    require(initializer is None or all(x['op'] in (0,177) for x in initializer['instructions']),'Application allocation initializer unsupported')
                    constructors[call]=constructor_writes(model['methods'][call])
        analyze(m,allow_loops=True)
    def visit(key):
        require(key not in visiting,'Recursive application call unsupported: '+key)
        if key in methods:return
        validate(key);visiting.add(key);m=model['methods'][key];methods[key]=m
        for ins in m['instructions']:
            if ins['op'] not in (182,183,184,185) or ins['name']=='<init>':continue
            call=callee(ins)
            if call in sources or call in plan['collection_getters'] or call in plan['collection_setters']:continue
            options=candidates(ins)
            for candidate in options:
                require(candidate not in visiting,'Recursive application call unsupported: '+candidate)
                try:validate(candidate)
                except AnalysisLimit:raise
                except ValueError as e:opaque[candidate]=str(e);continue
                targets.setdefault(key+'@'+str(ins['index']),[]).append(candidate);visit(candidate)
        visiting.remove(key)
    visit(plan['entry'])
    effects={key:{'field_reads':sorted({i['owner']+'.'+i['name'] for i in m['instructions'] if i['op']==180}),
                  'field_writes':sorted({i['owner']+'.'+i['name'] for i in m['instructions'] if i['op']==181}),
                  'call_sites':[key+'@'+str(i['index']) for i in m['instructions'] if i['op'] in (182,183,184,185)],
                  'exceptions':m['exception_handlers'],'meaning':'Candidate effects only; actual object/alias/write versions are interpreted, never assumed pure.'} for key,m in methods.items()}
    plan['algorithm']='execution-dependency-v2-application-calls'
    plan['frame_methods']=sorted(methods);plan['binding_callsites']=sorted(targets)
    plan['selected_read_sites']=[key+'@'+str(i['index']) for key,m in methods.items() for i in m['instructions'] if i['op']==180]
    plan['execution_kernel'].update(version=2,methods=methods,call_targets=targets,opaque_methods=opaque,constructors=constructors,effects=effects,
        class_parents={o:{'super':c.get('super'),'interfaces':c.get('interfaces',[])} for o,c in model['classes'].items()},
        evidence_policy='All planned application frames/calls, necessary field writes/reads and actual branch/handler sequence in both modes; no cost claim.')
    plan['contracts']=[c for c in plan['contracts'] if not c.startswith('v1 has')]
    plan['contracts']+=['Nonrecursive application bodies are interpreted with shared heap/container state and distinct invocation frames.',
        'Static read/write sets are candidates, not purity claims; opaque calls poison possibly reachable nonlocal/escaped state.',
        'Offline/static budget exhaustion is analysis_limited, never business N/A or automatically evidence_invalid.']
    return plan
