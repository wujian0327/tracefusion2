"""Discover bytecode methods and conservative effects; never per-business summaries."""
from plan_service_observations import callee
from plan_collection_service import analyze
from query_observation_planner import require
from analysis_status import AnalysisLimit
from plan_constructor_effects import assignment_effects,constructor_start
from pathlib import Path
import json,re


def augment_calls(plan,model,sources):
    from plan_execution_kernel import constructor_writes
    methods={};targets={};opaque={};visiting=set();lambdas={};constructor_starts={};constructors=dict(plan['execution_kernel']['constructors'])
    supported={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,87,89,96,100,104,132,167,178,180,181,182,183,184,185,187,191,192,198,199,186,189,190,50,83}|set(range(21,26))|set(range(54,59))|set(range(153,167))|set(range(172,178))
    supported|={107,135}  # Finite double multiply and exact JVM int-to-double.
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
        require(not re.search(r'\[[ZBCSIJFD]|\[\[',m['desc']),'Primitive/multidimensional array parameters unsupported')
        for ins in m['instructions']:
            require(not re.search(r'\[[ZBCSIJFD]|\[\[',ins.get('desc','')) and not (ins['op'] in (189,192) and ins.get('type','').startswith('[') and (ins['type'].startswith('[[') or not ins['type'].startswith('[L'))),'Primitive/multidimensional array effects unsupported')
            require(ins['op'] in supported,'Application opcode unsupported: '+str(ins['op']))
            if ins['op']==18 and ins.get('constant_type')=='Type':
                require(ins['constant'].startswith('L') and ins['constant'].endswith(';') and ins['constant'][1:-1] in model['classes'],'Class literal requires frozen concrete class')
            if ins['op']==189:require(not ins.get('type','').startswith('['),'Multidimensional array allocation unsupported')
            if ins['op']==186:
                bs=ins.get('bootstrap_args',[]);require(ins.get('bootstrap')=='java/lang/invoke/LambdaMetafactory.metafactory' and len(bs)==3 and isinstance(bs[1],dict) and bs[1].get('tag') in (5,6,7),'Lambda bootstrap/handle unsupported')
                sam={'get':('Ljava/util/function/Supplier;','()Ljava/lang/Object;'),
                     'test':('Ljava/util/function/Predicate;','(Ljava/lang/Object;)Z'),
                     'run':('Ljava/lang/Runnable;','()V')}
                require(ins['name'] in sam and (ins['desc'].split(')')[1],bs[0])==sam[ins['name']],'Lambda SAM unsupported')
            if ins['op']==183 and ins['name']=='<init>':
                call=callee(ins)
                if key in constructor_starts and ins['index']==constructor_starts[key]-1:continue
                if call=='java/util/ArrayList.<init>()V':constructors[call]={}
                elif call=='java/lang/StringBuilder.<init>()V':constructors[call]={'kind':'string-builder'}
                elif call in ('java/util/Date.<init>()V','java/util/Date.<init>(J)V'):constructors[call]={'kind':'date-constructor'}
                elif call=='org/springframework/http/HttpEntity.<init>(Ljava/lang/Object;Lorg/springframework/util/MultiValueMap;)V':
                    constructors[call]={'kind':'http-entity-null-headers'}
                else:
                    try:
                        require(call in model['methods'],'Application constructor bytecode absent: '+call)
                        initializer=model['methods'].get(ins['owner']+'.<clinit>()V')
                        require(initializer is None or all(x['op'] in (0,177) for x in initializer['instructions']),'Application allocation initializer unsupported')
                        try:
                            fields=assignment_effects(model,call)
                            constructors[call]={'kind':'assignments','fields':fields}
                            if any('field' in value for value in fields.values()):constructors[call]['input_projections']=True
                        except ValueError as assignment_error:
                            try:constructor_starts[call]=constructor_start(model['methods'][call])
                            except ValueError as frame_error:raise ValueError(str(assignment_error)+'; '+str(frame_error)) from frame_error
                            constructors[call]={'kind':'frame','start_pc':constructor_starts[call]}
                    except ValueError as error:
                        constructors[call]={'kind':'opaque','reason':str(error)};opaque[call]=str(error)
        analyze(m,allow_loops=True)
    def visit(key):
        if key in methods:return
        validate(key);visiting.add(key);m=model['methods'][key];methods[key]=m
        for ins in m['instructions']:
            if ins['op']==186:
                site=key+'@'+str(ins['index']);lambdas[site]=ins;implementation=ins['bootstrap_args'][1]['handle']
                if implementation in model['methods']:
                    try:validate(implementation)
                    except AnalysisLimit:raise
                    except ValueError as e:opaque[implementation]=str(e)
                    else:
                        checkpoint=(set(methods),set(targets),set(lambdas))
                        try:visit(implementation)
                        except AnalysisLimit:raise
                        except ValueError as e:
                            for table,keys in zip((methods,targets,lambdas),checkpoint):
                                for added in set(table)-keys:table.pop(added)
                            visiting.intersection_update(methods);opaque[implementation]=str(e)
                else:opaque.setdefault(implementation,'Lambda implementation bytecode missing')
                continue
            if ins['op']==183 and ins['name']=='<init>':
                call=callee(ins)
                if constructors.get(call,{}).get('kind')=='frame':visit(call)
                continue
            if ins['op'] not in (182,183,184,185):continue
            call=callee(ins)
            if call in ('java/lang/StringBuilder.append(Ljava/lang/Object;)Ljava/lang/StringBuilder;','org/springframework/hateoas/Resource.toString()Ljava/lang/String;','org/springframework/http/RequestEntity.toString()Ljava/lang/String;'):
                synthetic={'op':182,'owner':'java/lang/Object','name':'toString','desc':'()Ljava/lang/String;'}
                for candidate in candidates(synthetic):
                    try:validate(candidate)
                    except AnalysisLimit:raise
                    except ValueError as error:opaque[candidate]=str(error);continue
                    targets.setdefault(key+'@'+str(ins['index'])+':render',[]).append(candidate);visit(candidate)
            if call in sources or call in plan['collection_getters'] or call in plan['collection_setters']:continue
            options=candidates(ins)
            for candidate in options:
                try:validate(candidate)
                except AnalysisLimit:raise
                except ValueError as e:opaque[candidate]=str(e);continue
                targets.setdefault(key+'@'+str(ins['index']),[]).append(candidate);visit(candidate)
        visiting.remove(key)
    visit(plan['entry'])
    # A direct, empty Object initialization precedes any opportunity for this
    # reference to escape. Observe this point even for framework-created DTOs.
    births={}
    for key,m in methods.items():
        c=m['instructions']
        if m['name']=='<init>' and len(c)>1 and c[0]['op']==25 and c[0].get('var')==0 and c[1]['op']==183 and callee(c[1])=='java/lang/Object.<init>()V':
            births[key]={'pc':1,'class_sha256':model['classes'][m['owner']]['sha256']}
    decoder_births={}
    for owner in plan.get('json_schema',{}):
        key=owner+'.<init>()V';m=model['methods'].get(key);c=m['instructions'] if m else []
        if len(c)>1 and c[0]['op']==25 and c[0].get('var')==0 and c[1]['op']==183 and callee(c[1])=='java/lang/Object.<init>()V' and all(i['op'] in {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,25,89,181,183,187,177} and (i['op']!=25 or i['var']==0) and (i['op']!=181 or i['owner']==owner) and (i['op']!=183 or callee(i) in ('java/lang/Object.<init>()V','java/util/ArrayList.<init>()V')) and (i['op']!=187 or i['type']=='java/util/ArrayList') for i in c) and owner+'.<clinit>()V' not in model['methods']:
            decoder_births[key]={'pc':1,'class_sha256':model['classes'][owner]['sha256'],'written_fields':sorted({i['owner']+'.'+i['name'] for i in c if i['op']==181}),'field_write_counts':{f:sum(i['op']==181 and i['owner']+'.'+i['name']==f for i in c) for f in sorted({i['owner']+'.'+i['name'] for i in c if i['op']==181})}}
    plan['execution_kernel']['decoder_birth_sites']=decoder_births
    framework=any(v.get('kind')=='http-entity-null-headers' for v in constructors.values())
    if framework:
        plan['execution_kernel']['framework_contracts']=json.loads((Path(__file__).parent/'framework-wrapper-contracts-20261020.json').read_text())
        plan['response_binding']['runtime_container_path']=True
    effects={key:{'field_reads':sorted({i['owner']+'.'+i['name'] for i in m['instructions'] if i['op']==180}),
                  'field_writes':sorted({i['owner']+'.'+i['name'] for i in m['instructions'] if i['op']==181}),
                  'call_sites':[key+'@'+str(i['index']) for i in m['instructions'] if i['op'] in (182,183,184,185)],
                  'exceptions':m['exception_handlers'],'meaning':'Candidate effects only; actual object/alias/write versions are interpreted, never assumed pure.'} for key,m in methods.items()}
    plan['algorithm']='execution-dependency-v7-conservative-constructor-effects'
    plan['frame_methods']=sorted(methods);plan['binding_callsites']=sorted(key+'@'+str(i['index']) for key,m in methods.items() for i in m['instructions'] if i['op'] in (182,183,184,185) and (i['name']!='<init>' or constructors.get(callee(i),{}).get('kind')=='frame'))
    plan['selected_read_sites']=[key+'@'+str(i['index']) for key,m in methods.items() for i in m['instructions'] if i['op']==180]
    plan['execution_kernel'].update(callback_lifecycle_version=2,constructor_lifecycle=True,scalar_builders=True,static_field_evidence=True,call_depth_limit=64,object_birth_sites=births,version=7,library_contracts=json.loads((Path(__file__).parent/'constructor-library-contracts-20261020.json').read_text()),constructor_starts=constructor_starts,methods=methods,public_contracts=True,lambda_sites=lambdas,
        class_literals={i['constant']:model['classes'][i['constant'][1:-1]]['sha256'] for m in methods.values() for i in m['instructions'] if i['op']==18 and i.get('constant_type')=='Type'},
        runtime_profiles=json.loads((Path(__file__).parent/'kernel-contract-runtimes-20261020.json').read_text())['profiles'],call_targets=targets,opaque_methods=opaque,constructors=constructors,effects=effects,
        class_parents={o:{'super':c.get('super'),'interfaces':c.get('interfaces',[])} for o,c in model['classes'].items()},
        evidence_policy='All planned application frames/calls, necessary field writes/reads and actual branch/handler sequence in both modes; no cost claim.')
    plan['contracts']=[c for c in plan['contracts'] if not c.startswith('v1 has')]
    plan['contracts']+=['Finite application call graph including cycles; actual distinct invocation frames are depth/step bounded, with analysis_limited on exhaustion.',
        'Static read/write sets are candidates, not purity claims; opaque calls poison possibly reachable nonlocal/escaped state.',
        'Offline/static budget exhaustion is analysis_limited, never business N/A or automatically evidence_invalid.']
    return plan
