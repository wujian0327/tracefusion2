#!/usr/bin/env python3
"""Replay frozen root bytecode with concrete call/branch evidence and heap slots.

Instruction def-use establishes all propagation. Recorded values validate that
replay, and never select a candidate origin. Library effects are generic; input
field/collection coordinates are exported into the shared distributed graph.
"""
from dataclasses import dataclass, field
import math
from query_observation_planner import descriptors, require
from plan_service_observations import callee


@dataclass
class Value:
    observed: dict = field(default_factory=dict)
    sources: frozenset = frozenset()
    selectors: frozenset = frozenset()
    allocation: int | None = None
    unknown: bool = False


def constant(v): return Value({'value': v})
def union(vs, attr='sources'): return frozenset(x for v in vs for x in getattr(v, attr))
def source_key(f): return (f['owner'], f['field'], f['version'])
def source_value(f, fields):
    k = source_key(f); fields[k] = f
    return Value(f['observed'], frozenset({k}))


def int32(v): return (int(v) + 2**31) % 2**32 - 2**31


def infer_collection(plan, rows):
    method = plan['collection_method']; code = method['instructions']; entry = plan['entry']
    starts = [r for r in rows if r['kind'] == 'enter' and r['method'] == entry]
    answers = []; fields = {}; roots = []
    for root in starts:
        exits = [r for r in rows if r['kind'] == 'exit' and r['frame'] == root['frame']]
        if not exits: continue  # Aborted calls remain without completed targets.
        require(len(exits) == 1, 'Root exits duplicated'); end = exits[0]
        events = [r for r in rows if r.get('frame') == root['frame'] and r['kind'] in ('collection-call-enter', 'collection-call-exit', 'branch', 'collection-catch')
                  and (r['kind']!='branch' or r['site'].startswith(entry+'@'))]
        # Keep full mode's extra field/branch observations outside this stream.
        pos = 0; pc = 0; stack = []; locals_ = {}; bindings = {}; maps = {}; builders = {}; steps = 0
        if not method['access'] & 8: locals_[0] = Value({'object': root['receiver']}); slot = 1
        else: slot = 0
        for i, d in enumerate(descriptors(method['desc'])):
            locals_[slot] = Value(root['args'][i]); slot += 2 if d in ('J', 'D') else 1

        def pop(): require(stack, 'Replay stack underflow'); return stack.pop()
        def bind(v, actual):
            if v.unknown and not v.observed: return
            if v.allocation is not None:
                require(actual.get('object') is not None, 'Allocation lost identity')
                old = bindings.setdefault(v.allocation, actual['object']); require(old == actual['object'], 'Allocation identity changed')
            elif 'object' in v.observed and v.observed['object'] is not None:
                require(v.observed['object'] == actual.get('object'), 'Def-use object identity mismatch at pc '+str(pc)+': '+str(v.observed)+' vs '+str(actual))
            if 'value' in v.observed:
                require(v.observed['value'] == actual.get('value') or isinstance(v.observed['value'], float) and math.isnan(v.observed['value']) and math.isnan(actual.get('value', 0)), 'Replay value differs')
        def actual_id(v): return bindings.get(v.allocation) if v.allocation is not None else v.observed.get('object')
        def take(kind):
            nonlocal pos
            require(pos < len(events) and events[pos]['kind'] == kind, 'Missing/out-of-order ' + kind + ' at pc ' + str(pc))
            e = events[pos]; pos += 1; return e
        def arithmetic(op, args):
            if any(v.unknown or 'value' not in v.observed for v in args): return Value(unknown=True)
            a, b = [v.observed['value'] for v in args]
            group = (op - 96) // 4
            require(group in (0, 1, 2), 'Unsupported arithmetic operation')
            value = a + b if group == 0 else a - b if group == 1 else a * b
            if op % 4 == 0: value = int32(value)
            return Value({'value': value}, union(args), union(args, 'selectors'))

        while True:
            steps += 1; require(steps < 10000, 'Replay bound'); ins = code[pc]; op = ins['op']
            if 21 <= op <= 25: require(ins['var'] in locals_, 'Replay uninitialized local'); stack.append(locals_[ins['var']])
            elif 54 <= op <= 58: locals_[ins['var']] = pop()
            elif op == 0: pass
            elif op == 1: stack.append(constant(None))
            elif 2 <= op <= 8: stack.append(constant(op - 3))
            elif 9 <= op <= 15: stack.append(constant(op - (9 if op <= 10 else 11 if op <= 13 else 14)))
            elif op in (16,17): stack.append(constant(ins['operand']))
            elif op == 18: stack.append(constant(ins['constant']))
            elif op == 89: stack.append(stack[-1])
            elif op == 87: pop()
            elif op == 187: stack.append(Value(allocation=pc))
            elif op == 178: stack.append(Value(unknown=True))
            elif op == 192: pass
            elif op in (96,97,98,99,100,101,102,103,104,105,106,107):
                b, a = pop(), pop(); stack.append(arithmetic(op, [a,b]))
            elif op in (133,135,138,141):
                a = pop(); stack.append(Value({'value': float(a.observed['value'])}, a.sources, a.selectors) if not a.unknown else a)
            elif op in (182,183,184,185):
                args = [pop() for _ in descriptors(ins['desc'])][::-1]; recv = None if op == 184 else pop(); key = callee(ins)
                if ins['name'] == '<init>':
                    if ins['owner'] == 'java/util/HashMap': maps.setdefault(recv.allocation, {'entries':{},'epoch':0})
                    if ins['owner'] == 'java/lang/StringBuilder': builders[recv.allocation] = constant('')
                elif pc not in plan['collection_selected_calls'] and rows[0]['mode'] != 'full':
                    if ins['desc'].split(')')[1] != 'V': stack.append(Value(unknown=True))
                else:
                    call = take('collection-call-enter'); require(call['pc'] == pc and call['callee'] == key, 'Call site differs')
                    if recv is not None: bind(recv, call['receiver'])
                    for a, v in zip(args, call['args']): bind(a, v)
                    # A throwing call has no exit; only an actually entered
                    # original handler may resume this root.
                    if pos < len(events) and events[pos]['kind'] == 'collection-catch':
                        caught = take('collection-catch'); require(caught.get('failed_call_pc') == pc, 'Failed call differs')
                        require(any(h['start'] <= pc < h['end'] and h['handler'] == caught['pc'] for h in method['exception_handlers']), 'Handler outside original exception table')
                        pc = caught['pc']; stack = [Value(caught['observed'])]; continue
                    ret = take('collection-call-exit'); require(ret['pc'] == pc, 'Call exit differs')
                    actual = ret['result']; value = Value(actual, unknown=True)
                    if key in plan['collection_getters']:
                        f = call.get('getter'); require(f and f['field'] == plan['collection_getters'][key]['field'], 'Getter evidence absent')
                        # Container/DTO getter supplies an identity, not a scalar
                        # origin; subsequent field/element reads supply leaves.
                        observed = dict(f['observed'])
                        if f['descriptor'] in ('Z','B','C','S','I','J','F','D'): observed.pop('object',None)
                        bind(Value(observed), actual)
                        value = source_value(f, fields) if 'value' in actual else Value(actual)
                        value.observed = dict(actual)
                        if f['descriptor'] in ('Z','B','C','S','I','J','F','D'):value.observed.pop('object',None)
                    elif ins['owner'] == 'java/util/List' and ins['name'] == 'get':
                        index = int(args[0].observed['value']); items = call['collection']; require(0 <= index < len(items), 'Successful List.get outside bounds')
                        f = {'owner':call['receiver']['object'],'field':'@list:'+str(index),'version':call['collection_epoch'],'observed':items[index]}
                        value = source_value(f, fields); value.selectors = args[0].sources | args[0].selectors
                        bind(Value(items[index]), actual)
                    elif ins['owner'] == 'java/util/List' and ins['name'] in ('indexOf', 'size'):
                        items = call['collection']; expected = len(items) if ins['name'] == 'size' else next((i for i,x in enumerate(items) if x.get('value') == args[0].observed.get('value')), -1)
                        require(actual['value'] == expected, 'List lookup contract differs')
                        selectors = set(union(args) | union(args,'selectors'))
                        for i,x in enumerate(items):
                            f={'owner':call['receiver']['object'],'field':'@list:'+str(i),'version':call['collection_epoch'],'observed':x}; fields[source_key(f)]=f; selectors.add(source_key(f))
                        value = Value(actual, frozenset(selectors))
                    elif key in ('java/lang/Integer.intValue()I','java/lang/Integer.valueOf(I)Ljava/lang/Integer;'):
                        source = recv if recv is not None else args[0]
                        value = Value(dict(actual),source.sources,source.selectors,unknown=source.unknown)
                        if ins['name']=='intValue':value.observed.pop('object',None)
                        require(source.observed.get('value') == actual.get('value'), 'Boxing/unboxing differs')
                    elif ins['owner'] == 'java/lang/StringBuilder':
                        require(recv.allocation in builders, 'Escaped/unmodeled StringBuilder'); content = builders[recv.allocation]
                        if ins['name'] == 'append':
                            arg=args[0]; value=Value(actual, allocation=recv.allocation)
                            # JVM conversion result is observed at toString;
                            # origin union is independent of decimal formatting.
                            builders[recv.allocation]=Value(sources=content.sources|arg.sources, selectors=content.selectors|arg.selectors,unknown=content.unknown or arg.unknown)
                        elif ins['name'] == 'toString': value=Value(actual,content.sources,content.selectors,unknown=content.unknown)
                        else: raise ValueError('Unsupported StringBuilder operation')
                    elif ins['owner'] in ('java/util/Map','java/util/HashMap') and ins['name'] == 'put':
                        require(recv.allocation in maps and isinstance(args[0].observed.get('value'),str), 'Map must be local with a known string key')
                        state=maps[recv.allocation]; state['owner']=call['receiver']['object']; state['epoch']=ret['collection_epoch']; state['entries'][args[0].observed['value']]=args[1]
                        value=Value(actual)
                    elif key in plan['collection_setters']:
                        require(len(args)==1,'Setter arity'); value=Value(actual)
                    elif ins['owner'].startswith('org/slf4j/'):
                        value=Value(actual)
                    # Opaque calls supply only a concrete runtime boundary
                    # value. A later verified getter may resolve a field; an
                    # opaque scalar directly reaching the target stays unknown.
                    return_type=ins['desc'].split(')')[1]
                    if return_type in ('Z','B','C','S','I','J','F','D'):value.observed.pop('object',None)
                    if return_type != 'V': stack.append(value)
            elif 153 <= op <= 166 or op in (198,199):
                right=pop();left=pop() if 159 <= op <= 166 else None
                branch=take('branch'); require(branch['site']==entry+'@'+str(pc),'Branch site differs')
                # Validate the recorded choice whenever replay has the actual
                # operands. Missing scalar evidence remains explicitly opaque.
                choice=None
                if 153<=op<=158 and 'value' in right.observed:
                    x=right.observed['value'];choice=[x==0,x!=0,x<0,x>=0,x>0,x<=0][op-153]
                elif 159<=op<=164 and 'value' in left.observed and 'value' in right.observed:
                    x,y=left.observed['value'],right.observed['value'];choice=[x==y,x!=y,x<y,x>=y,x>y,x<=y][op-159]
                elif op in (198,199) and right.observed:
                    null=right.observed.get('value','non-null') is None and right.observed.get('object') is None
                    choice=null if op==198 else not null
                if choice is not None:require(choice==branch['taken'],'Recorded branch contradicts operands')
                pc=ins['target'] if branch['taken'] else pc+1; continue
            elif op == 167: pc=ins['target']; continue
            elif 172 <= op <= 177:
                result=None if op==177 else pop()
                if result is not None:bind(result,end['result'])
                require(pos==len(events),'Unconsumed replay observations'); break
            else: raise ValueError('Unsupported replay opcode '+str(op))
            pc+=1
        # Only the Map passed at an actual target setter is an answer. Other
        # local maps must not accidentally supply a query provider.
        selected_maps=set()
        for e in events:
            if e['kind']=='collection-call-enter' and e['pc'] in plan['collection_writer_sites']:
                selected_maps.add(e['args'][0]['object'])
        for state in maps.values():
            if state.get('owner') not in selected_maps:continue
            for key,v in state['entries'].items():
                answers.append({'root_frame':root['frame'],'owner':state['owner'],'field':'@map:'+key,'version':state['epoch'],
                    'observed':v.observed,'known':not v.unknown,'sources':[list(k) for k in sorted(v.sources)],
                    'selectors':[list(k) for k in sorted(v.selectors)],'target_field':plan['target'],'seq':end['seq']})
        roots.append(root['frame'])
    return {'answers':answers,'fields':list(fields.values()),'completed_roots':roots,'origin_matching_uses_values':False}
