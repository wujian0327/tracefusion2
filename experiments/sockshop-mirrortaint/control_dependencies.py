"""Bounded, invocation-local control selection over verified original bytecode.

No source is invented for an unexecuted read. Conditions select definitions,
not data origins. Field merge effects require concrete receiver footprints.
"""
from dataclasses import dataclass
from execution_dependency_state import Value
from query_observation_planner import require, descriptors
from analysis_status import AnalysisLimit


def selection(values, declared_only=False):
    deps = frozenset(x for v in values for x in v.origins | v.selectors
                     if not (declared_only and x[0] == 'argument'))
    return Value(selectors=deps, unknown=any(v.unknown for v in values))


def selected(value, condition):
    return Value(value.observed, value.origins, value.selectors | condition.selectors,
                 value.unknown or condition.unknown, value.allocation)


def branch_taken(op, operands, identity):
    b = operands[-1]
    a = operands[0] if len(operands) == 2 else None
    if 153 <= op <= 158 and 'value' in b.observed:
        x = b.observed['value']
        return (x == 0, x != 0, x < 0, x >= 0, x > 0, x <= 0)[op - 153]
    if 159 <= op <= 164 and 'value' in a.observed and 'value' in b.observed:
        x, y = a.observed['value'], b.observed['value']
        return (x == y, x != y, x < y, x >= y, x > y, x <= y)[op - 159]
    if op in (198, 199):
        null = identity(b) is None and b.observed.get('value', 'not-null') is None
        return null if op == 198 else not null
    if op in (165, 166):
        equal = identity(a) == identity(b)
        return equal if op == 165 else not equal
    return None


class ControlFlow:
    def __init__(self, method):
        self.method = method
        self.code = method['instructions']
        self.exit = len(self.code)
        require(self.exit > 0, 'Control CFG has no bytecode')
        handlers = method.get('exception_handlers', [])
        require(len(handlers) == method.get('try_catches', len(handlers)), 'Control exception table missing')
        for h in handlers:
            require(0 <= h['start'] < h['end'] <= self.exit and 0 <= h['handler'] < self.exit, 'Control exception range invalid')
        self.edges = {self.exit: set()}
        for pc, ins in enumerate(self.code):
            require(ins.get('index', pc) == pc, 'Control CFG instruction coordinate differs')
            op = ins['op']
            if op in (170, 171, 168, 169, 201):
                raise AnalysisLimit('control-shape', 'Switch/jsr/ret control not supported')
            if op == 191:
                # Explicit throwing control follows the original protected
                # handler graph. Actual type/order/identity is checked by handle;
                # an unhandled actual exception aborts and produces no answer.
                edges = {h['handler'] for h in handlers if h['start'] <= pc < h['end']} or {self.exit}
            elif 172 <= op <= 177: edges = {self.exit}
            elif op == 167: edges = {ins['target']}
            elif 153 <= op <= 166 or op in (198, 199): edges = {pc + 1, ins['target']}
            else: edges = {pc + 1}
            require(all(0 <= x <= self.exit for x in edges), 'Control CFG target outside method')
            self.edges[pc] = edges
        reachable = {self.exit}
        while True:
            added = {p for p, xs in self.edges.items() if xs & reachable} - reachable
            if not added: break
            reachable |= added
        self.pdom = {p: ({p} if p == self.exit else set(reachable)) for p in reachable}
        changed = True
        while changed:
            changed = False
            for p in sorted(reachable - {self.exit}, reverse=True):
                if not self.edges[p] <= reachable:
                    raise AnalysisLimit('control-nontermination', 'CFG has an exitless alternative')
                new = {p} | set.intersection(*(self.pdom[s] for s in self.edges[p]))
                if new != self.pdom[p]: self.pdom[p] = new; changed = True
        self.joins = {}
        self.regions = {}
        self.definitions = None
        for pc, ins in enumerate(self.code):
            if not (153 <= ins['op'] <= 166 or ins['op'] in (198, 199)): continue
            if pc not in reachable: continue
            strict = self.pdom[pc] - {pc}
            closest = [x for x in strict if strict - {x} <= self.pdom[x]]
            require(len(closest) == 1, 'Control postdominator absent/ambiguous')
            join = closest[0]; self.joins[pc] = join
            todo = list(self.edges[pc]); region = set()
            while todo:
                x = todo.pop()
                if x == join or x in region: continue
                require(x != self.exit, 'Control region escapes its verified join')
                region.add(x); todo.extend(self.edges[x])
            self.regions[pc] = region

    def operands(self):
        if self.definitions is None:
            from plan_collection_service import analyze
            self.definitions = analyze(self.method, allow_loops=True)[1]
        return self.definitions


@dataclass
class Region:
    pc: int
    join: int
    condition: Value
    locals: set
    stack_base: int


class ControlledStack(list):
    def __init__(self, control, values=()):
        self.control = control
        super().__init__(values)

    def append(self, value): super().append(self.control.apply(value))
    def pop(self, index=-1):
        value = self.control.apply(super().pop(index))
        self.control.consumed.append(value)
        return value


class ControlledLocals(dict):
    def __init__(self, control): self.control = control
    def __setitem__(self, key, value): super().__setitem__(key, self.control.apply(value))


class Control:
    def __init__(self, graph, frame, state, identity, methods=None, inherited=None, declared_only=False, opaque_methods=(),call_targets=None):
        self.graph, self.frame, self.state, self.identity = graph, frame, state, identity
        self.methods = methods or {}
        self.inherited = inherited or Value()
        self.declared_only = declared_only
        self.opaque_methods = set(opaque_methods)
        self.call_targets = call_targets or {}
        self.regions = []
        self.consumed = []
        self.escape_guards = Value()
        self.sequence = 0
        frame.control = self
        frame.stack = ControlledStack(self)
        frame.locals = ControlledLocals(self)

    def current(self): return selection([self.inherited] + [r.condition for r in self.regions], self.declared_only)
    def apply(self, value): return selected(value, self.current())

    def targets_for(self,method,index):
        name=method.get('owner','')+'.'+method.get('name','')+method['desc']+'@'+str(index)
        return self.call_targets.get(name,())

    def write_value(self,value,receiver):
        # A materialized address choice needs a may-alias footprint for the
        # targets not written on this execution. This revision does not invent
        # that proof from the observed owner or equal values.
        if receiver.selectors-self.current().selectors:
            raise AnalysisLimit('control-write-address','Cross-join selected write address lacks a closed alias footprint')
        return selected(value,Value(selectors=receiver.selectors,unknown=receiver.unknown))

    def at(self, pc):
        ended = [r for r in self.regions if r.join == pc]
        self.regions = [r for r in self.regions if r.join != pc]
        for r in ended:
            for slot in r.locals & self.frame.locals.keys():
                self.frame.locals[slot] = selected(self.frame.locals[slot], r.condition)
            for i in range(r.stack_base, len(self.frame.stack)):
                self.frame.stack[i] = selected(self.frame.stack[i], r.condition)
        self.consumed = []

    def _receivers(self, definitions, region, trail=()):
        values = []
        for pc in definitions:
            if pc in trail: continue
            if pc < 0:
                slot = 0
                mapping = {-1: 0} if not self.graph.method['access'] & 8 else {}
                if mapping: slot = 1
                for i, d in enumerate(descriptors(self.graph.method['desc'])):
                    mapping[-i-2] = slot; slot += 2 if d in ('J', 'D') else 1
                if pc in mapping and mapping[pc] in self.frame.locals: values.append(self.frame.locals[mapping[pc]])
                continue
            ins = self.graph.code[pc]
            if ins['op'] == 25:
                modified = any(self.graph.code[x]['op'] in range(54, 59) and self.graph.code[x].get('var') == ins['var'] for x in region)
                if not modified and ins['var'] in self.frame.locals:
                    values.append(self.frame.locals[ins['var']]); continue
                defs = self.graph.operands().get(pc, [])
                values.extend(self._receivers(set().union(*defs), region, trail + (pc,)))
            elif ins['op'] in (187, 1): continue  # Fresh allocation or null cannot name preexisting state.
            elif pc not in region:
                raise AnalysisLimit('control-write-address', 'Potential field receiver is not an available local reference')
            else: raise AnalysisLimit('control-write-address', 'Unexecuted field receiver requires unsupported alias proof')
        return values

    def _field_effects(self, region, condition, seq):
        if not condition.selectors and not condition.unknown: return
        for pc in region:
            ins = self.graph.code[pc]
            fields = set()
            if ins['op'] == 181:
                fields.add(ins['owner'] + '.' + ins['name'])
                defs = self.graph.operands().get(pc, [])
                receivers = self._receivers(defs[1], region)
            elif ins['op'] in (182, 183, 184, 185):
                from plan_service_observations import callee
                key = callee(ins)
                todo = [key,*self.targets_for(self.graph.method,pc)]; seen = set()
                opaque = set()
                while todo:
                    key = todo.pop()
                    if key in self.opaque_methods: opaque.add(key)
                    if key in seen or key not in self.methods: continue
                    seen.add(key)
                    for index,op in enumerate(self.methods[key]['instructions']):
                        if op['op'] == 181: fields.add(op['owner'] + '.' + op['name'])
                        elif op['op'] in (182,183,184,185):todo.extend([callee(op),*self.targets_for(self.methods[key],index)])
                if opaque:
                    self.state.control_barriers.append((seq,Value(selectors=condition.selectors,unknown=True),tuple(sorted(opaque))))
                if not fields: continue
                definitions = self.graph.operands().get(pc, [])
                types = list(reversed(descriptors(ins['desc']))) + ([] if ins['op'] == 184 else ['Lreceiver;'])
                refs = [d for d,t in zip(definitions,types) if t.startswith(('L','['))]
                receivers = self._receivers(set().union(*refs), region) if refs else []
            else: continue
            for receiver in receivers:
                owner = self.identity(receiver)
                if owner is None: continue
                for field in fields:
                    key = (owner, field)
                    self.state.control_fields[key] = selection([self.state.control_fields.get(key, Value()), condition])

    def branch(self, ins, operands, event):
        require(type(event.get('taken')) is bool, 'Branch result is not a JVM boolean')
        expected = branch_taken(ins['op'], operands, self.identity)
        if expected is not None: require(expected == event['taken'], 'Execution branch contradicts operands')
        pc = self.frame.pc
        require(pc in self.graph.joins, 'Executed branch has no supported CFG join')
        condition = selection([self.current(), *operands], self.declared_only)
        nodes = self.graph.regions[pc]
        self._field_effects(nodes, condition,event.get('seq',0))
        slots = {self.graph.code[x]['var'] for x in nodes if 54 <= self.graph.code[x]['op'] <= 58 or self.graph.code[x]['op'] == 132}
        prior = next((r for r in self.regions if r.pc == pc), None)
        if prior:
            prior.condition = selection([prior.condition, condition]); prior.locals |= slots
        else: self.regions.append(Region(pc, self.graph.joins[pc], condition, slots, len(self.frame.stack)))
        return ins['target'] if event['taken'] else pc + 1

    def caught(self, handler):
        condition = selection([self.current(), self.state.exception_control, *self.consumed], self.declared_only)
        self.state.exception_control = Value()
        retained = [r for r in self.regions if r.pc >= 0 and handler in self.graph.regions.get(r.pc, set())]
        following = self.frame.pc + 1
        candidates = self.graph.pdom[handler] & self.graph.pdom.get(following, {self.graph.exit})
        join = max(candidates, key=lambda p: len(self.graph.pdom[p])) if candidates else self.graph.exit
        if join == handler: join = self.graph.exit
        if retained:
            join = max((r.join for r in retained), key=lambda p: len(self.graph.pdom[p]))
        self.regions = retained + [Region(-1, join, condition, set(), 0)]
        self.frame.stack = ControlledStack(self)

    def normal_completion(self):
        # Only an actually executed condition with an explicit throwing arm
        # exports a normal/exception outcome choice. A returned data value is
        # not automatically an exception condition.
        return selection([self.escape_guards]+[r.condition for r in self.regions if r.pc >= 0 and
                          any(self.graph.code[p]['op'] == 191 for p in self.graph.regions[r.pc])], self.declared_only)

    def normal_outcome(self, condition, seq=None):
        if not condition.selectors and not condition.unknown: return
        handlers = [h['handler'] for h in self.graph.method.get('exception_handlers', [])
                    if h['start'] <= self.frame.pc < h['end']]
        if not handlers:
            self.escape_guards=selection([self.escape_guards,condition],self.declared_only)
            return
        following = self.frame.pc + 1
        candidates = set.intersection(*(self.graph.pdom[p] for p in [following, *handlers]))
        join = max(candidates, key=lambda p: len(self.graph.pdom[p])) if candidates else self.graph.exit
        todo=[following,*handlers];nodes=set()
        while todo:
            p=todo.pop()
            if p==join or p==self.graph.exit or p in nodes:continue
            nodes.add(p);todo.extend(self.graph.edges[p])
        slots={self.graph.code[p]['var']for p in nodes if 54<=self.graph.code[p]['op']<=58 or self.graph.code[p]['op']==132}
        self._field_effects(nodes,condition,self.sequence if seq is None else seq)
        self.regions.append(Region(-2, join, condition, slots, len(self.frame.stack)))

    def normal_operation(self, ins):
        """Normal exceptional-edge choices, separate from ordinary data use.

        A null/bounds/divisor guard can choose a handler even without an IF
        instruction. Export it through normal returns until a verified handler
        join consumes it; never attach all historical reads to ordinary values.
        """
        op=ins['op'];values=self.consumed;guards=[]
        if op in (180,181) and values:guards=[values[-1]]
        elif op in (182,183,184,185):
            from plan_service_observations import callee
            if op!=184 and values:guards.append(values[-1])
            targets=self.targets_for(self.graph.method,self.frame.pc)
            closed=callee(ins)in self.methods or bool(targets)and all(k in self.methods for k in targets)
            if not closed:guards.extend(values[:-1]if op!=184 else values)
        elif op in (108,109,112,113)and values:guards=[values[0]]
        elif op in (189,190,50,83,192):guards=values
        if guards:self.normal_outcome(selection(guards,self.declared_only))


def field_selection(state, key, value, established_at=None):
    value=selected(value, state.control_fields.get(key[:2], Value()))
    if established_at is not None:
        for seq,condition,_ in state.control_barriers:
            if established_at<=seq:value=selected(value,condition)
    return value
