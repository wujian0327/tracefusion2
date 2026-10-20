"""Shared offline dependency state. Runtime values validate identities, never origins."""
from dataclasses import dataclass, field
from query_observation_planner import require


@dataclass(frozen=True)
class Value:
    observed: dict = field(default_factory=dict)
    origins: frozenset = frozenset()
    selectors: frozenset = frozenset()
    unknown: bool = False
    allocation: int | None = None

    def project(self, observed):
        return Value(observed, self.origins, self.selectors, self.unknown, self.allocation)


@dataclass
class Frame:
    invocation: str
    locals: dict = field(default_factory=dict)
    stack: list = field(default_factory=list)
    pc: int = 0
    steps: int = 0

    def pop(self):
        require(self.stack, 'Execution operand stack underflow')
        return self.stack.pop()


@dataclass
class Container:
    owner: str
    elements: list = field(default_factory=list)
    epoch: int = 0
    local: bool = False
    escaped: bool = False


@dataclass
class Call:
    invocation: str
    pc: int
    receiver: Value | None
    arguments: list
    completion: str = 'pending'
    result: Value | None = None


@dataclass
class State:
    frame: Frame
    fields: dict = field(default_factory=dict)  # (owner, field, actual version) -> Value
    containers: dict = field(default_factory=dict)
    iterators: dict = field(default_factory=dict)
    allocations: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)
    poisoned: set = field(default_factory=set)

    def field_write(self, coordinate, value):
        require(coordinate not in self.fields, 'Duplicate actual field version')
        self.fields[coordinate] = value

    def opaque_effect(self, values):
        # Scalar values cannot be mutated; all reachable modeled heap state of
        # reference arguments is conservatively poisoned. Unknown global effects
        # also require a caller-level barrier in the replay engine.
        for value in values:
            if value and value.observed.get('object') and 'value' not in value.observed:
                self.poisoned.add(value.observed['object'])


def combine(observed, values):
    return Value(observed, frozenset(x for v in values for x in v.origins),
                 frozenset(x for v in values for x in v.selectors), any(v.unknown for v in values))
