#!/usr/bin/env python3
"""Conservative def-use slice for bounded acyclic collection computations.

Join reaching instruction definitions, rather than enumerate complete paths.
Handlers are explicit CFG edges. Mutable local Map/StringBuilder allocations
include every possibly aliasing operation; no field or application names occur
in the rules. This plan is a separate opt-in profile, not a silent fallback.
"""
from collections import deque
from plan_service_observations import callee, field
from plan_distributed_fields import any_target, json_schema
from query_observation_planner import descriptors, digest, require


def direct_accessors(model):
    getters = {}; setters = {}
    for key, m in model['methods'].items():
        if m['access']&8:continue
        c = m['instructions']
        if not descriptors(m['desc']) and len(c) == 3 and c[0].get('var') == 0 and c[0]['op'] == 25 and c[1]['op'] == 180 and 172 <= c[2]['op'] <= 176:
            getters[key] = {'field': field(c[1]), 'descriptor': c[1]['desc']}
        if len(descriptors(m['desc']))==1 and len(c) == 4 and c[0] == {'index': 0, 'op': 25, 'var': 0} and c[1].get('var') == 1 and c[2]['op'] == 181 and c[3]['op'] == 177:
            setters[key] = {'field': field(c[2]), 'descriptor': c[2]['desc']}
    return getters, setters


def analyze(method):
    code = method['instructions']; handlers = method.get('exception_handlers', [])
    require(len(handlers) == method['try_catches'], 'Explicit exception table required; rebuild the bytecode model')
    n = len(code); require(0 < n < 5000, 'Method size bound')
    args = {}; slot = 0 if method['access'] & 8 else 1
    if slot: args[0] = frozenset({-1})
    for i, d in enumerate(descriptors(method['desc'])):
        args[slot] = frozenset({-i-2}); slot += 2 if d in ('J', 'D') else 1
    states = {0: ([], args)}; queue = deque([0]); dependencies = {i: set() for i in range(n)}
    operands = {}; steps = 0

    def enqueue(pc, stack, locals_):
        require(0 <= pc < n, 'CFG target outside method')
        if pc not in states:
            states[pc] = (list(stack), dict(locals_)); queue.append(pc); return
        old_stack, old_locals = states[pc]
        require(len(stack) == len(old_stack), 'Stack height differs at CFG join')
        merged_stack = [a | b for a, b in zip(stack, old_stack)]
        # A local is usable only when initialized on every incoming path.
        merged_locals = {k: v | old_locals[k] for k, v in locals_.items() if k in old_locals}
        if (merged_stack, merged_locals) != states[pc]:
            states[pc] = (merged_stack, merged_locals); queue.append(pc)

    while queue:
        pc = queue.popleft(); steps += 1
        require(steps <= n * n, 'Def-use convergence bound')
        stack, locals_ = states[pc]; stack = list(stack); locals_ = dict(locals_)
        before = dict(locals_); ins = code[pc]; op = ins['op']; used = []
        def pop():
            require(stack, 'Static stack underflow at ' + str(pc)); v = stack.pop(); used.append(v); return v
        def push(): stack.append(frozenset({pc}))
        if 21 <= op <= 25:
            require(ins['var'] in locals_, 'Uninitialized local at ' + str(pc)); used.append(locals_[ins['var']]); push()
        elif 54 <= op <= 58: locals_[ins['var']] = pop()
        elif op in (0,): pass
        elif op in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 178, 187): push()
        elif op == 89: require(stack, 'Empty DUP'); stack.append(stack[-1])
        elif op == 87: pop()
        elif op == 180: pop(); push()
        elif op == 181: pop(); pop()
        elif op == 192: v = pop(); stack.append(v)
        elif op in (96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111): pop(); pop(); push()
        elif 133 <= op <= 147: pop(); push()
        elif op in (182, 183, 184, 185):
            for _ in descriptors(ins['desc']): pop()
            if op != 184: pop()
            if ins['desc'].split(')')[1] != 'V': push()
        elif 153 <= op <= 166 or op in (198, 199):
            pop()
            if 159 <= op <= 166: pop()
        elif op == 167: pass
        elif 172 <= op <= 177:
            if op != 177: pop()
        elif op == 191: pop()
        else: raise ValueError('Unsupported instruction in collection profile: ' + str(op))
        dependencies[pc].update(x for v in used for x in v)
        previous = operands.get(pc)
        operands[pc] = used if previous is None else [a | b for a, b in zip(previous, used)]
        if op == 167 or 153 <= op <= 166 or op in (198, 199):
            require(ins['target'] > pc, 'Loops/back edges are not admitted')
            enqueue(ins['target'], stack, locals_)
        if op != 167 and not 172 <= op <= 177 and op != 191:
            enqueue(pc + 1, stack, locals_)
        # Model actual possible throwing instructions, not branches/constants.
        if op in (180, 181, 178, 187, 192, 182, 183, 184, 185, 108, 109, 112, 113, 191):
            for h in handlers:
                if h['start'] <= pc < h['end']:
                    require(h['handler'] > pc, 'Backward exception handler unsupported')
                    enqueue(h['handler'], [frozenset({pc})], before)
    return dependencies, operands, states, steps


def closure(graph, seeds):
    seen = set(); todo = list(seeds)
    while todo:
        x = todo.pop()
        if x in seen: continue
        seen.add(x); todo.extend(graph.get(x, ()))
    return seen


def plan_collection(model, entry, target, scalar_target=False):
    target = any_target(model, target); m = model['methods'][entry]; c = m['instructions']
    graph, operands, states, steps = analyze(m); getters, setters = direct_accessors(model)
    writers = [i for i, x in enumerate(c) if x['op'] in (182, 183, 185) and callee(x) in setters and setters[callee(x)]['field'] == target]
    require(writers, 'No direct target setter call')
    # Calls on a local mutable allocation depend on all its possible mutations.
    # Only these exact library contracts support this effect closure.
    def allocations(definitions,trail=()):
        result=set()
        for d in definitions:
            if d<0 or d in trail:continue
            x=c[d]
            if x['op']==187:result.add(d)
            elif x['op']==25:result.update(allocations(graph[d],trail+(d,)))
            elif x['op'] in (182,185) and x['owner']=='java/lang/StringBuilder' and x['name']=='append':
                result.update(allocations(operands[d][-1],trail+(d,)))
        return result
    effects = []
    for i, x in enumerate(c):
        if i not in states or x['op'] not in (182, 183, 184, 185): continue
        key = callee(x)
        recv = operands[i][-1] if x['op']!=184 else frozenset()
        local_allocations = {a for a in allocations(recv) if c[a]['type'] in ('java/util/HashMap', 'java/lang/StringBuilder')}
        for a in local_allocations:
            # An allocation escaping via an unsupported receiver call cannot be
            # inferred as a known Map/StringBuilder operation.
            require(x['owner'] in ('java/util/HashMap', 'java/util/Map', 'java/lang/StringBuilder'), 'Opaque mutable receiver effect')
            graph[a].add(i); effects.append([a, i])
        # Passing a mutable result to an opaque helper permits unobserved
        # mutation, even when it happens to preserve the serialized value.
        for value in operands[i][:-1] if x['op']!=184 else operands[i]:
            passed=allocations(value)
            require(not passed or key in setters, 'Local mutable allocation escapes to an opaque argument')
    selected = closure(graph, writers)
    calls = [i for i in sorted(selected) if i >= 0 and c[i]['op'] in (182, 183, 184, 185) and c[i]['name'] != '<init>']
    if not scalar_target:
        require(any(c[i]['owner'] in ('java/util/Map', 'java/util/HashMap') and c[i]['name'] == 'put' for i in calls), 'No collection result mutation')
    branches = [i for i, x in enumerate(c) if 153 <= x['op'] <= 166 or x['op'] in (198, 199)]
    schema, _ = json_schema(model)
    return {'algorithm': 'acyclic-collection-defuse-v1', 'profile': 'bounded-scalar' if scalar_target else 'collection-computation', 'entry': entry, 'target': target,
        'model_sha256': digest(model), 'class_sha256': {o: v['sha256'] for o, v in model['classes'].items()},
        'frame_methods': [entry], 'producer_method': None, 'writer_method': None, 'reduction': {},
        'snapshot_fields': [target], 'mapper_fields': [], 'full_snapshot_fields': [],
        'selected_read_sites': [], 'collection_method': m,
        'collection_getters': getters, 'collection_setters': setters,
        'collection_selected_calls': calls, 'collection_branches': branches,
        'collection_writer_sites': writers, 'collection_effect_edges': effects,
        'planning_stats': {'instructions': len(c), 'reachable_instructions': len(states), 'worklist_steps': steps,
                           'selected_calls': len(calls), 'all_nonconstructor_calls': sum(x['op'] in (182,183,184,185) and x['name'] != '<init>' for x in c)},
        'contracts': ['Acyclic original root bytecode, explicit exception-handler table and observed branch/handler path.',
                      'Direct getter/setter summaries verified from bytecode; external helper results are opaque object boundaries.',
                      'List element coordinates use container identity, index and observed collection epoch, not boxed value identity.',
                      'Map string keys and StringBuilder contents have explicit sequential library effects.',
                      'Data origins exclude branch/index selection origins, which are retained separately.',
                      'Reflection/native mutation and concurrent shared mutable collections are unsupported.']}
