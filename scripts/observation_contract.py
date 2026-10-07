"""Conservative sufficient conditions for reusing one runtime-input snapshot.

IR checks prove no modeled leaf write can change the input, conditional on
runtime non-alias checks and the declared absence of external writers. They
do not discover ownership, prove a global minimum, or cover arbitrary code.
"""
from hybrid_model import BRANCHES,require


def stable_runtime_input(plan):
    require(plan.get('runtime_inputs')==[dict(register='rdi',length=1)],'Entry reuse requires one declared control byte')
    require(plan.get('runtime_input_ownership')=='request-private','Entry reuse requires an explicit no-external-writer ownership contract')
    require(plan['abi']['dst_register']=='rax','Unsupported destination register')
    ir=plan['instructions'];require(ir and ir[0]['address']==plan['entry'],'Entry is not the first decoded instruction')
    protected={'rax','rdi'};reads=[];stores=[]
    supported={'mov','movzx','lea','xor','add','sub','inc','cmp','test','nop','ret','jmp'}|BRANCHES
    writes={'mov','movzx','lea','xor','add','sub','inc'}
    addresses={n['address'] for n in ir}
    for n in ir:
        op=n['op'];args=n['args']
        require(op in supported,'Entry reuse rejects unmodeled effects or calls')
        if 'target' in n:
            require(n['target'] in addresses and n['target']!=plan['entry'],'Entry reuse rejects external branches or repeated entry')
        if op in writes:
            target=args[-1]
            if target['kind']=='reg':require(target['reg'] not in protected,'Entry reuse rejects writes to region base registers')
            else:
                require(op=='mov' and target['kind']=='mem' and target['base']=='rax' and target['width']==8,
                        'Entry reuse rejects writes outside the declared destination')
                stores.append(n['address'])
        for i,arg in enumerate(args):
            if arg.get('kind')=='mem' and arg.get('base')=='rdi':
                require(op=='cmp' and i==0 and arg['width']==8 and not arg.get('index') and arg['offset']==0,
                        'Entry reuse requires direct byte comparisons of the control input')
                reads.append(n['address'])
    require(reads,'No control input comparisons found')
    return dict(version='stable-control-byte-v1',entry=plan['entry'],read_addresses=reads,store_addresses=stores,
        protected_registers=sorted(protected),
        static_fact='Only byte stores through unchanged destination base; unchanged control base; no calls; entry not revisited',
        runtime_requirements=['control and all data regions disjoint','all executed stores within destination'],
        assumed_environment='request-private input, no external writer during leaf execution')
