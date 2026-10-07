"""Bounded CFG input analysis and conservative observation policy selection.

Abstract pointer regions locate missing control reads; concrete replay still
checks bounds and identities. This is neither a general pointer analysis nor
a minimum-cost probe placement algorithm.
"""
import argparse
from collections import deque
import json
from pathlib import Path

from hybrid_model import BRANCHES,require
from observation_contract import stable_runtime_input

UNKNOWN=frozenset({'unknown'})
SCALAR=frozenset({'scalar'})
POINTERS={'src','dst','aux','control'}


def analyze_inputs(plan):
    ir=plan['instructions'];instructions={n['address']:n for n in ir}
    require(ir and len(instructions)==len(ir) and len(ir)<=64,'Invalid bounded instruction graph')
    require(plan['entry'] in instructions,'Missing entry')
    abi=plan['abi'];initial={abi['src_register']:frozenset({'src'}),abi['dst_register']:frozenset({'dst'})}
    if 'aux_register' in abi:initial[abi['aux_register']]=frozenset({'aux'})
    if plan.get('runtime_inputs'):
        require(plan['runtime_inputs']==[dict(register='rdi',length=1)],'Unsupported runtime input contract')
        initial['rdi']=frozenset({'control'})
    initial['flags']=UNKNOWN
    states={plan['entry']:initial};queue=deque([plan['entry']]);queued={plan['entry']}
    supported={'mov','movzx','lea','xor','add','sub','inc','cmp','test','nop','ret','jmp'}|BRANCHES
    # Finite sets of region tags are joined at CFG merges. Unknown is retained;
    # a definition present on just one incoming path is not considered known.
    def transfer(n,state,validate=False,reads=None,stores=None):
        op=n['op'];args=n['args'];out=dict(state)
        require(op in supported,'Unmodeled effect: '+op)
        def reg(name):return state.get(name,UNKNOWN)
        def address(arg):
            base=reg(arg['base']);index=reg(arg['index']) if arg.get('index') else SCALAR
            return base if base<=POINTERS and index==SCALAR else UNKNOWN
        def read(arg):
            if arg['kind']=='imm':return SCALAR
            if arg['kind']=='reg':
                value=reg(arg['reg'])
                if validate:require('unknown' not in value,'Read of unmodeled initial register: '+arg['reg'])
                return SCALAR if arg['width']<64 and 'unknown' not in value else value
            region=address(arg)
            if validate:
                require(arg['width']==8 and region<=POINTERS,'Unmodeled memory input at '+hex(n['address']))
                if 'control' in region:
                    require(region==frozenset({'control'}) and op=='cmp' and arg==args[0] and
                            arg['base']=='rdi' and not arg.get('index') and arg['offset']==0,
                            'Control read requires an unsupported alias or operation')
                    reads.add(n['address'])
            return SCALAR
        if op in ('mov','movzx'):
            value=read(args[0]);target=args[1]
            if target['kind']=='reg':out[target['reg']]=value if target['width']==64 else SCALAR
            elif validate:
                require(op=='mov' and target['width']==8 and address(target)==frozenset({'dst'}),
                        'Store target is not proven to be in the destination region')
                stores.add(n['address'])
        elif op=='lea':
            value=address(args[0])
            if validate:require(value!=UNKNOWN,'Unmodeled address calculation')
            out[args[1]['reg']]=value
        elif op in ('xor','add','sub'):
            if op=='xor' and args[0]==args[1]:value=SCALAR
            else:
                right=read(args[0]);left=read(args[1])
                value=left if op in ('add','sub') and left<=POINTERS and right==SCALAR else SCALAR if left==right==SCALAR else UNKNOWN
            out[args[1]['reg']]=value;out['flags']=frozenset({'defined'})
        elif op=='inc':
            value=read(args[0]);out[args[0]['reg']]=value if value==SCALAR else UNKNOWN
            # INC preserves CF; do not manufacture fully known flags if the
            # incoming flags were unavailable.
            out['flags']=state.get('flags',UNKNOWN)
        elif op in ('cmp','test'):
            read(args[0]);read(args[1]);out['flags']=frozenset({'defined'})
        elif op in BRANCHES and validate:require(state.get('flags')==frozenset({'defined'}),'Unmodeled branch flags')
        return out
    def successors(n):
        if n['op']=='ret':return []
        if n['op']=='jmp':return [n['target']]
        return [n['next'],n['target']] if n['op'] in BRANCHES else [n['next']]
    for n in ir:
        require(n['op'] in supported,'Unmodeled effect: '+n['op'])
        require(all(a in instructions for a in successors(n)),'Control flow leaves decoded leaf')
    while queue:
        pc=queue.popleft();queued.remove(pc);out=transfer(instructions[pc],states[pc])
        for target in successors(instructions[pc]):
            old=states.get(target)
            joined=out if old is None else {r:old.get(r,UNKNOWN)|out.get(r,UNKNOWN) for r in set(old)|set(out)}
            if old!=joined:
                states[target]=dict(joined)
                if target not in queued:queue.append(target);queued.add(target)
    reads=set();stores=set()
    for pc,state in states.items():transfer(instructions[pc],state,True,reads,stores)
    require(any(instructions[a]['op']=='ret' for a in states),'No reachable return')
    return dict(reachable_instructions=len(states),runtime_read_addresses=sorted(reads),destination_store_addresses=sorted(stores),
        runtime_guards=['actual memory addresses inside modeled regions','disjoint source/destination/control objects','complete supported bounded execution'])


def choose_observation(plan):
    result=dict(version='bounded-observation-policy-v1',status='unsupported',mode=None,candidates=[],
        assumptions=['complete configured data regions and instruction model',
                     'no external writes to data buffers during leaf replay',
                     'declared private runtime input when present'],
        objective='Prefer boundary, then certified entry reuse, then observed reads; not a global minimum')
    try:
        require(plan.get('observation_mode','full')=='full','Select from a full plan')
        analysis=analyze_inputs(plan);result['analysis']=analysis
        reads=analysis['runtime_read_addresses']
        if plan.get('runtime_inputs'):
            require(plan.get('runtime_input_ownership')=='request-private',
                    'Runtime input ownership is unproven; per-read uprobes do not establish atomicity against external writers')
        if not reads:
            result.update(status='selected',mode='boundary',reason='All reachable reads are covered by the declared data model',instruction_sites=[])
            result['candidates'].append(dict(mode='boundary',accepted=True))
            return result
        result['candidates'].append(dict(mode='boundary',accepted=False,reason='Runtime control input is absent from existing boundary snapshots'))
        nodes={n['address']:n for n in plan['instructions']};sites={s['id']:s for s in plan['sites']}
        selected=[]
        for address in reads:
            node=nodes[address];sid=node['site'];site=sites[sid]
            require(site['op']=='instruction' and site['address']==address and
                    site['snapshots'].get('load')==dict(address=node['args'][0],length=1),'Missing control-read capture contract')
            selected.append(sid)
        require(set(selected)==set(plan.get('runtime_input_sites',[])),'Declared runtime probe sites disagree with CFG analysis')
        try:
            certificate=stable_runtime_input(plan)
            entry=sites[plan['instructions'][0]['site']]
            require(entry['address']==plan['entry'] and entry['op']=='instruction' and len(entry['snapshots'])<2 and
                    'control' not in entry['snapshots'],'No entry snapshot transport slot')
        except ValueError as exc:
            result['candidates'].append(dict(mode='entry',accepted=False,reason=str(exc)))
            result['candidates'].append(dict(mode='selective',accepted=True))
            result.update(status='selected',mode='selective',instruction_sites=sorted(selected),
                reason='Entry reuse not certified; retain every supported runtime control read')
        else:
            result['candidates'].append(dict(mode='entry',accepted=True))
            result.update(status='selected',mode='entry',instruction_sites=[entry['id']],entry_stability=certificate,
                reason='Entry reuse has a sufficient certificate under declared private ownership')
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        result.update(status='unsupported',mode=None,reason=str(exc))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path)
    args=p.parse_args();result=choose_observation(json.loads(args.plan.read_text()));encoded=json.dumps(result,indent=2)+'\n'
    if args.output:args.output.write_text(encoded)
    else:print(encoded,end='')
    return 0 if result['status']=='selected' else 2

if __name__=='__main__':raise SystemExit(main())
