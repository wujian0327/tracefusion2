"""Bounded formal access paths, never a cross product of arguments and fields.

Summaries describe addresses, not purity or ownership. Their reference edges
must be resolved in the caller's already verified state before certification.
"""
from dataclasses import dataclass
from analysis_status import AnalysisLimit
from query_observation_planner import descriptors
from plan_collection_service import analyze
from plan_service_observations import callee


def unclosed(message):
    raise AnalysisLimit('control-write-address', message)


@dataclass(frozen=True)
class Path:
    root: int  # -1 = this, 0.. = descriptor argument ordinal
    fields: tuple = ()  # (JVM declaring field, descriptor)


def bindings(ins, operands):
    args = descriptors(ins['desc'])
    if len(operands) != len(args) + (ins['op'] != 184):
        unclosed('Call write footprint lacks complete static operands')
    result = {i: operands[len(args)-1-i] for i in range(len(args))}
    if ins['op'] != 184: result[-1] = operands[-1]
    return result


class WriteEffects:
    def __init__(self, methods, targets, opaque):
        self.methods, self.targets, self.opaque = methods, targets, opaque
        self.cache = {}

    def candidates(self, method, pc):
        ins = method['instructions'][pc]
        targets = tuple(self.targets(method, pc))
        # Abstract declarations need not have code. Every supplied concrete
        # candidate is retained; a missing one must not disappear silently.
        named = callee(ins)
        for target in targets:
            if target not in self.methods and target not in self.opaque:
                unclosed('Planned conditional call candidate has no write/effect definition')
        concrete = named in self.methods and bool(self.methods[named].get('instructions'))
        return tuple(dict.fromkeys(((named,) if concrete or not targets else ()) + targets))

    def summary(self, key, trail=()):
        if key in self.cache: return self.cache[key]
        if key in self.opaque:
            return frozenset(), frozenset({key})
        if key not in self.methods:
            # Not a new purity certificate. Calls outside the application
            # interpreter remain owned by their existing library contracts;
            # the planner separately marks unsupported ones opaque.
            return frozenset(), frozenset()
        # A write-free recursive scalar computation needs no address proof.
        # Inspect the whole finite planned call graph, retaining opaque effects.
        todo,seen,has_writes,uncertain=[key],set(),False,set()
        while todo:
            target=todo.pop()
            if target in seen:continue
            seen.add(target)
            if target in self.opaque:uncertain.add(target);continue
            if target not in self.methods:continue
            m=self.methods[target]
            for pc,ins in enumerate(m['instructions']):
                if ins['op']==181:has_writes=True
                elif ins['op']in(179,79,80,81,82,83,84,85,86):uncertain.add(target+'@'+str(pc))
                elif ins['op']in(182,183,184,185):todo.extend(self.candidates(m,pc))
        if not has_writes:
            result=frozenset(),frozenset(uncertain)
            self.cache[key]=result
            return result
        if key in trail: unclosed('Recursive conditional call write footprint is not closed')
        original = self.methods[key]
        method = dict(original)
        # Legacy isolated models may omit the redundant key metadata.
        method.setdefault('owner', key.split('.',1)[0])
        method.setdefault('name', key.split('.',1)[1].split('(',1)[0])
        method.setdefault('desc', key[key.index('('):])
        method.setdefault('access', 0)
        operands = analyze(method, allow_loops=True)[1]
        writes, opaque = set(), set()

        def paths(definitions, seen=()):
            result = set()
            for definition in definitions:
                if definition in seen: unclosed('Cyclic reference definition in call write address')
                if definition < 0:
                    result.add(Path(-1 if definition == -1 else -definition-2)); continue
                op = method['instructions'][definition]
                inputs = operands.get(definition, ())
                if op['op'] in (25,192):
                    result.update(paths(inputs[0], seen+(definition,)))
                elif op['op'] == 180 and op['desc'].startswith(('L','[')):
                    result.update(Path(p.root,p.fields+((op['owner']+'.'+op['name'],op['desc']),))
                                  for p in paths(inputs[0],seen+(definition,)))
                else:
                    # Includes newly allocated wrappers, returned aliases,
                    # globals and array members: none implies private state.
                    unclosed('Conditional callee reference address needs an unsupported alias proof')
            if not result: unclosed('Conditional callee reference address is empty')
            return result

        for pc, ins in enumerate(method['instructions']):
            if ins['op'] == 181:
                writes.update(Path(p.root,p.fields+((ins['owner']+'.'+ins['name'],ins['desc']),))
                              for p in paths(operands[pc][1]))
            elif ins['op'] in (182,183,184,185):
                actual = bindings(ins,operands[pc])
                for target in self.candidates(method,pc):
                    child, unknown = self.summary(target,trail+(key,))
                    opaque.update(unknown)
                    for p in child:
                        if p.root not in actual: unclosed('Callee formal has no actual argument')
                        writes.update(Path(q.root,q.fields+p.fields) for q in paths(actual[p.root]))
            elif ins['op'] in (179,79,80,81,82,83,84,85,86):
                opaque.add(key+'@'+str(pc))  # global/array effect not a closed field footprint
        result = frozenset(writes), frozenset(opaque)
        self.cache[key] = result
        return result
