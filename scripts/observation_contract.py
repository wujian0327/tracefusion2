"""Conservative sufficient conditions for reusing one runtime-input snapshot.

IR checks prove no modeled leaf write can change the input, conditional on
runtime non-alias checks and the declared absence of external writers. They
do not discover ownership, prove a global minimum, or cover arbitrary code.
"""
from hybrid_model import BRANCHES,require
from copy import deepcopy


def deterministic_runtime_input(plan):
    """Certify supported load/XOR-immediate/store updates, not immutability.

    Remove only separately checked update blocks when applying the existing
    output/alias/ownership rules. No branch may enter halfway into a block.
    Concrete replay must still validate every register and memory operation.
    """
    require(plan.get('runtime_state_model')=='xor-control-byte-v1','Missing deterministic control-state contract')
    ir=plan['instructions'];blocks=[];removed=set()
    def control(arg):
        return arg.get('kind')=='mem' and arg.get('base')=='rdi' and not arg.get('index') and arg.get('offset')==0 and arg.get('width')==8
    targets={n['target'] for n in ir if 'target' in n}|{plan['entry']}
    for i,n in enumerate(ir):
        if n['op']!='mov' or not control(n['args'][-1]):continue
        require(i>=2,'Incomplete control update block')
        load,xor=ir[i-2:i];src=n['args'][0]
        require(src['kind']=='reg' and src['width']==8 and load['op']=='movzx' and control(load['args'][0]) and
                load['args'][1]==dict(kind='reg',reg=src['reg'],width=32),'Unsupported control update load/store')
        require(xor['op']=='xor' and xor['width']==32 and xor['args'][1]==load['args'][1] and
                xor['args'][0]['kind']=='imm' and 0<=xor['args'][0]['value']<=255,'Control update must be a byte XOR constant')
        require(load['next']==xor['address'] and xor['next']==n['address'] and
                xor['address'] not in targets and n['address'] not in targets,'Branch enters inside control update')
        blocks.append(dict(load=load['address'],xor=xor['address'],store=n['address'],constant=xor['args'][0]['value']))
        removed.update((load['address'],xor['address'],n['address']))
    require(blocks,'No supported control updates found')
    shadow=deepcopy(plan)
    for n in shadow['instructions']:
        if n['address'] in removed:n.update(op='nop',args=[])
    stable=stable_runtime_input(shadow)
    return dict(version='replay-control-byte-v1',entry=plan['entry'],update_blocks=blocks,
        remaining_leaf_checks=stable,
        static_fact='Control writes are complete load/XOR-constant/store blocks; other writes satisfy destination rules',
        runtime_requirements=['initial control observation','complete modeled execution','disjoint data/control regions','final control snapshot matches replay'],
        assumed_environment='request-private input, no external writer during leaf execution')


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
