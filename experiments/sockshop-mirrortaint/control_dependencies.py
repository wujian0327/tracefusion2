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
        require(type(x)in(int,bool)and -2**31<=x<2**31,'Branch operand is not a signed JVM int')
        return (x == 0, x != 0, x < 0, x >= 0, x > 0, x <= 0)[op - 153]
    if 159 <= op <= 164 and 'value' in a.observed and 'value' in b.observed:
        x, y = a.observed['value'], b.observed['value']
        require(all(type(x)in(int,bool)and -2**31<=x<2**31 for x in(x,y)),'Branch operands are not signed JVM ints')
        return (x == y, x != y, x < y, x >= y, x > y, x <= y)[op - 159]
    def reference(v):
        object_=identity(v)
        if object_ is not None:return ('object',object_)
        if 'value'in v.observed and v.observed['value']is None:return ('null',None)
        if isinstance(v.observed.get('value'),str):return ('nonnull-literal',None)
        if v.unknown:raise AnalysisLimit('control-reference','Reference operation lacks concrete identity evidence')
        require(False,'Branch reference identity/null witness absent')
    if op in (198, 199):
        null = reference(b)[0]=='null'
        return null if op == 198 else not null
    if op in (165, 166):
        left,right=reference(a),reference(b)
        if left[0]=='null'or right[0]=='null':equal=left[0]==right[0]
        else:
            if left[0]!='object'or right[0]!='object':raise AnalysisLimit('control-reference','Literal identity comparison needs an existing identity contract')
            equal=left[1]==right[1]
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
    def __init__(self, graph, frame, state, identity, methods=None, inherited=None, declared_only=False, opaque_methods=(),call_targets=None, reference_lookup=None):
        self.graph, self.frame, self.state, self.identity = graph, frame, state, identity
        self.methods = methods or {}
        self.inherited = inherited or Value()
        self.declared_only = declared_only
        self.opaque_methods = set(opaque_methods)
        self.call_targets = call_targets or {}
        self.reference_lookup = reference_lookup
        self.entry_locals = None
        from call_write_effects import WriteEffects
        self.write_effects = WriteEffects(self.methods, self.targets_for, self.opaque_methods)
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
        if self.entry_locals is None: self.entry_locals = dict(self.frame.locals)
        ended = [r for r in self.regions if r.join == pc]
        self.regions = [r for r in self.regions if r.join != pc]
        for r in ended:
            for slot in r.locals & self.frame.locals.keys():
                self.frame.locals[slot] = selected(self.frame.locals[slot], r.condition)
            for i in range(r.stack_base, len(self.frame.stack)):
                self.frame.stack[i] = selected(self.frame.stack[i], r.condition)
        self.consumed = []

    def _reference(self, receiver, field, descriptor, seq):
        from call_write_effects import unclosed
        owner = self.identity(receiver)
        if owner is None or receiver.unknown:
            unclosed('Conditional write path lacks a known physical receiver')
        if self.reference_lookup is not None:
            value = self.reference_lookup(owner, field, descriptor, seq)
        else:
            # State.fields contains only already executed, verified writes.
            # A later source/input snapshot is deliberately not searched here.
            matches = [(k,v) for k,v in self.state.fields.items() if k[:2] == (owner,field)]
            matches.extend((k,v) for k,v,at in self.state.reference_reads if k[:2] == (owner,field) and at < seq)
            if owner in self.state.poisoned or self.state.control_barriers or not matches:
                unclosed('Conditional write path lacks prior verified reference state')
            version = max(k[2] for k,v in matches)
            values = [v for k,v in matches if k[2] == version]
            if any(v != values[0] for v in values[1:]): unclosed('Conditional write path reference is ambiguous')
            value = field_selection(self.state,(owner,field,version),values[0])
        if value.unknown or self.identity(value) is None:
            unclosed('Conditional write path reference is unknown/null')
        if value.selectors - self.current().selectors:
            unclosed('Conditional write path crosses an unclosed selected alias')
        return value

    def _receivers(self, definitions, region, seq, edges, trail=()):
        from call_write_effects import unclosed
        values = []
        if self.entry_locals is None: self.entry_locals = dict(self.frame.locals)
        for pc in definitions:
            if pc in trail: unclosed('Cyclic caller reference definition')
            if pc < 0:
                slot = 0
                mapping = {-1: 0} if not self.graph.method['access'] & 8 else {}
                if mapping: slot = 1
                for i,d in enumerate(descriptors(self.graph.method['desc'])):
                    mapping[-i-2] = slot; slot += 2 if d in ('J','D') else 1
                if pc not in mapping or mapping[pc] not in self.entry_locals:
                    unclosed('Conditional write actual argument is unavailable')
                values.append(self.entry_locals[mapping[pc]]); continue
            ins = self.graph.code[pc]
            inputs = self.graph.operands().get(pc, [])
            if ins['op'] == 25:
                modified = any(self.graph.code[x]['op'] in range(54,59) and self.graph.code[x].get('var') == ins['var'] for x in region)
                # A reference loaded before the branch is not the slot's new
                # value if that slot was subsequently overwritten.
                modified |= any(self.graph.code[x]['op'] in range(54,59) and self.graph.code[x].get('var') == ins['var']
                                for x in range(pc+1,self.frame.pc))
                if not modified and ins['var'] in self.frame.locals:
                    values.append(self.frame.locals[ins['var']]); continue
                values.extend(self._receivers(inputs[0],region,seq,edges,trail+(pc,)))
            elif ins['op'] == 180 and ins['desc'].startswith(('L','[')):
                for receiver in self._receivers(inputs[0],region,seq,edges,trail+(pc,)):
                    edge = (self.identity(receiver),ins['owner']+'.'+ins['name'])
                    edges.add(edge)
                    values.append(self._reference(receiver,edge[1],ins['desc'],seq))
            elif ins['op'] == 192:
                values.extend(self._receivers(inputs[0],region,seq,edges,trail+(pc,)))
            else:
                unclosed('Conditional caller reference address needs an unsupported alias proof')
        if not values: unclosed('Conditional write actual reference set is empty')
        return values

    def _field_effects(self, region, condition, seq):
        from call_write_effects import bindings,unclosed
        if not condition.selectors and not condition.unknown: return
        pending, edges, barriers = {}, set(), set()
        for pc in sorted(region):
            ins = self.graph.code[pc]
            if ins['op'] == 181:
                specs = [(self.graph.operands()[pc][1], ((ins['owner']+'.'+ins['name'],ins['desc']),))]
            elif ins['op'] in (182,183,184,185):
                actual = bindings(ins,self.graph.operands()[pc])
                specs = []
                for target in self.write_effects.candidates(self.graph.method,pc):
                    writes,opaque = self.write_effects.summary(target)
                    barriers.update(opaque)
                    for path in writes:
                        if path.root not in actual: unclosed('Call formal/actual write mapping is incomplete')
                        specs.append((actual[path.root],path.fields))
            else: continue
            for definitions,path in specs:
                # Only the fresh object's own slot cannot name preexisting
                # state. A path through that slot may still reach an old child.
                if len(path)==1 and definitions and all(p in region and self.graph.code[p]['op']==187 for p in definitions):continue
                receivers = self._receivers(definitions,region,seq,edges)
                for receiver in receivers:
                    for field,descriptor in path[:-1]:
                        edges.add((self.identity(receiver),field))
                        receiver = self._reference(receiver,field,descriptor,seq)
                    owner = self.identity(receiver)
                    if owner is None or receiver.unknown:
                        unclosed('Conditional write has no closed actual object')
                    if receiver.selectors-self.current().selectors:
                        unclosed('Conditional write has an unresolved alternative alias')
                    key = (owner,path[-1][0])
                    pending[key] = selection([pending.get(key,Value()),condition,selection([receiver])])
        # Even distinct formals can alias physically. Resolve all alternatives
        # before publishing anything, and reject a possibly rewritten path edge.
        if edges & pending.keys():
            unclosed('Conditional call may rewrite a reference edge used by its write footprint')
        if barriers and edges:
            unclosed('Opaque conditional effects prevent closing nested write addresses')
        for key,value in pending.items():
            self.state.control_fields[key] = selection([self.state.control_fields.get(key,Value()),value])
        if barriers:
            self.state.control_barriers.append((seq,Value(selectors=condition.selectors,unknown=True),tuple(sorted(barriers))))

    def branch(self, ins, operands, event):
        require(type(event.get('taken')) is bool, 'Branch result is not a JVM boolean')
        expected = branch_taken(ins['op'], operands, self.identity)
        if expected is None and any(v.unknown for v in operands):raise AnalysisLimit('control-operand','Concrete branch operand absent in the supported value model')
        require(expected is not None,'Concrete branch operand evidence absent')
        require(expected == event['taken'], 'Execution branch contradicts operands')
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
