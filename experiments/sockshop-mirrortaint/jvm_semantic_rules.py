"""One finite JVM rule defines transfer, static demands and runtime witnesses.

Contracts resolve heap/call effects separately. These primitives never infer a
source from equal values or grant ownership. No new event encoding is required.
"""
from dataclasses import dataclass, asdict
from execution_dependency_state import Value, combine
from query_observation_planner import require


@dataclass(frozen=True)
class Rule:
    name: str
    inputs: tuple
    outputs: int
    value_inputs: tuple
    identity_inputs: tuple
    evidence: tuple
    effects: tuple = ()
    bits: int = 0
    field_value_result: bool = False
    def demand(self, result=True, effect=True):
        return {'values':list(self.value_inputs) if result else [],
                'identities':list(self.identity_inputs) if result or effect else [],
                'evidence':list(self.evidence) if result or effect else [],
                'effects':list(self.effects) if effect else [],
                'field_value':self.field_value_result and result}


RULES={
    133:Rule('I2L',('int',),1,(0,),(),('execution-i2l input/result/method/pc',),bits=32),
    96:Rule('IADD',('int','int'),1,(0,1),(),('witnessed operands and executed JVM path','downstream value consistency'),bits=32),
    97:Rule('LADD',('long','long'),1,(0,1),(),('witnessed operands and executed JVM path','downstream value consistency'),bits=64),
    180:Rule('GETFIELD',('receiver',),1,(),(0,),('read owner/declared-field/site/version/value','original null exception'),('read/version/alias',),field_value_result=True),
    181:Rule('PUTFIELD',('receiver','value'),0,(1,),(0,),('successful write owner/declared-field/site/new-version','payload unless licensed','original null exception'),('write/version/alias/publication',)),
}


def specification():
    return {'version':1,'rules':{str(op):asdict(rule) for op,rule in RULES.items()}}


def validate_plan(plan):
    declared=plan.get('execution_kernel',{}).get('semantic_primitive_rules')
    if declared is not None:
        # JSON roundtrip normalizes tuples; never trust a plan-supplied transfer.
        import json
        require(declared==json.loads(json.dumps(specification())),'JVM primitive rule definition differs')


def compute(op,values,event=None,method=None):
    rule=RULES[op];require(op in (133,96,97) and len(values)==len(rule.inputs),'JVM value rule operands differ')
    numbers=[v.observed.get('value') for v in values]
    require(all(type(n)is int and -2**(rule.bits-1)<=n<2**(rule.bits-1) for n in numbers),'JVM exact signed operands absent/out of range')
    result=numbers[0] if op==133 else (sum(numbers)+2**(rule.bits-1))%2**rule.bits-2**(rule.bits-1)
    if op==133:
        require(event is not None and event['method']==method and event['input']==numbers[0] and event['result']==result,'I2L JVM value/widening differs')
    return combine({'value':result},values)


def field_event(op,receiver,ins,event,actual_identity=None):
    require(op in (180,181),'Not a field rule')
    owner=receiver.observed.get('object') if actual_identity is None else actual_identity
    require(owner==event['owner'] and event['field']==ins['owner']+'.'+ins['name'],'JVM field receiver/declaration differs')
    require(type(event['version'])is int and event['version']>=int(op==181),'JVM field version invalid')
    require(event['kind'] in (('read',) if op==180 else ('write','write-version')),'JVM field event kind differs')
    require(('observed'in event)==(event['kind']!='write-version'),'JVM field payload presence differs')


def field_transfer(op,value,observed,omitted=False):
    require(op in (180,181),'Not a field transfer')
    if omitted:
        require(op==181,'Read payload cannot use write omission')
        return Value(unknown=True)
    return value.project(observed)


def write_payload_eligible(field,required_values,descriptor):
    # PUTFIELD's receiver/effect evidence always survives. The caller supplies
    # the conservative whole-plan value demand, including choices/callbacks.
    return field not in required_values and descriptor in {'Z','B','C','S','I','J','F','D','Ljava/lang/String;'} and bool(RULES[181].demand(False,True)['effects'])
