"""Shared snapshot transport/ELF binding for four honestly named method controls.

Production selected/all retain their inference. Independent methods receive only
verified instruction rows, frame/field ABI, event site definitions and events:
never production paths, selected branch lists, fixture cases or oracle answers.
"""
import copy
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[1]/'scripts')]
import payment_adapter as production
from go_byte_adapter import assembly_rows
from go_string_adapter import file_offset
from independent_machine import check
from independent_replay import PLACE,MULT,SUM,VALID,infer as independent_infer,validate_capture

Raw=production.Raw
decode_record=production.decode_record
physical_probes=production.physical_probes
STRATEGIES=('all_branches','selected','path_sensitive_slice','boundary_replay')

def bind_independent(binary,command,reader,out,common):
    data=binary.read_bytes(); functions={}
    for name in (PLACE,MULT,SUM,VALID):
        # Read raw disassembly, not the production numeric path/selection model.
        asm=command(['tool','objdump','-s','^'+re.escape(name)+'$',str(binary)])
        rows=assembly_rows(asm); check(rows,'Missing '+name)
        (out/(name.rsplit('.',1)[-1]+'.independent.asm')).write_text(asm)
        for r in rows:
            off=file_offset(data,r['address']); code=bytes.fromhex(r['code'])
            check(data[off:off+len(code)]==code,'Independent ELF byte mismatch')
        frames=[i for i,r in enumerate(rows) if re.fullmatch(r'SUBQ \$0x[0-9a-f]+, SP',r['asm'])]
        check(len(frames)==1,'Independent frame differs'); fi=frames[0]
        frame=int(rows[fi]['asm'].split('$')[1].split(',')[0],16)
        if name in (PLACE,MULT):
            entry=common['functions'][name]['entry']; exit=common['functions'][name]['exit']
            start=next(i for i,r in enumerate(rows) if r['address']==entry)
            end=next(i for i,r in enumerate(rows) if r['address']==exit)
        elif name==SUM:
            start=fi+1
            # Keep all three numeric/error returns; exclude morestack ABI path.
            end=max(i for i,r in enumerate(rows) if r['asm']=='RET')
        else:
            start=fi+1; end=next(i for i,r in enumerate(rows) if r['asm']=='RET')
        region=copy.deepcopy(rows[start:end+1])
        for i,r in enumerate(region): r['next']=region[i+1]['address'] if i+1<len(region) else None
        functions[name]=dict(frame=frame,entry=region[0]['address'],exit=region[-1]['address'],rows=region)
    request=production.BASE+'/genproto.PlaceOrderRequest'; money=production.BASE+'/genproto.Money'
    layout=json.loads(command(['run',str(reader),str(binary),request,money]))
    fields={f['name']:(f['offset'],f['size']) for f in layout[request]['fields']}
    check(fields.get('UserCurrency')==(56,16) and layout[request]['size']==104,'Request layout differs')
    fields={f['name']:(f['offset'],f['size']) for f in layout[money]['fields']}
    check(fields.get('CurrencyCode')==(40,16) and layout[money]['size']==72,'Money currency layout differs')
    # The original request register DI is spilled before the preparation call.
    place=assembly_rows(command(['tool','objdump','-s','^'+re.escape(PLACE)+'$',str(binary)]))
    spill=f'MOVQ DI, {hex(functions[PLACE]["frame"]+40)}(SP)'
    check(any(r['asm']==spill and r['address']<functions[PLACE]['entry'] for r in place),'Request spill ABI differs')
    return dict(version='bounded-amd64-ssa-v1',functions=functions,request_size=104,request_currency=56,
                source_items_limit=32,quantity_limit=32,currency_byte_limit=8,
                contracts=['Typed immutable source graph and direct numeric data dependency query',
                    'Unobserved protobuf bookkeeping is non-source metadata; unknown operands remain unknown',
                    'Fresh zeroed 72-byte Money allocation; Go runtime WB summaries preserve application payload',
                    'Boundary replay verifies both WB alternatives at each join using live registers and complete application storage',
                    'Pinned Go amd64 aggregate/stack ABI, initialized nonnil error globals, <=200000 instructions',
                    'No asynchronous mutation or unsupported calls/memory; these cause unknown'])

def plan_binary(binary,command,reader,out):
    common=production.plan_binary(binary,command,reader,out)
    common['snapshot_version']=2
    common['independent_model']=bind_independent(binary,command,reader,out,common)
    return strategy_plan(common,'selected')

def strategy_plan(common,strategy):
    check(strategy in STRATEGIES,'Unknown method')
    p=copy.deepcopy(common); p['strategy']=strategy
    if strategy in ('selected','all_branches'):
        p=production.strategy_plan(p,strategy)
    else:
        p['sites']=[s for s in p['all_sites'] if (s['kind'] in ('source','sink','end') if strategy=='boundary_replay'
                    else s['kind']!='sum_branch')]
        p['event_order']=[s['id'] for s in p['sites']]
    p['snapshot_version']=2
    return p

def source(plan,pid,namespace):
    check(plan['snapshot_version']==2,'Expected snapshot-v2')
    text=production.source(plan,pid,namespace)
    helper='''
static __always_inline void currency(struct event_t *e,u64 p,u32 offset) {
 e->registers[0]=word64(e,p+offset);e->registers[1]=word64(e,p+offset+8);
 u64 v=0;u32 n=e->registers[1];
 if(!e->registers[0]||!e->registers[1]||e->registers[1]>8)e->error=1;
 else if(bpf_probe_read_user(&v,n,(void *)e->registers[0])<0)e->error=1;
 e->registers[2]=v;
}
'''
    pos=text.index('\nint probe_'); text=text[:pos]+helper+text[pos:]
    old='e->tag=1;e->a=ctx->r9;'
    check(text.count(old)==1,'Shipping transport template differs')
    text=text.replace(old,old+'currency(e,e->a,40);',1)
    old='if(!item||!cart||!e->a)e->error=1;submit(ctx,e);}'
    check(text.count(old)==1,'Item transport template differs')
    source_site=next(s['id'] for s in plan['sites'] if s['kind']=='source')
    frame=plan['independent_model']['functions'][PLACE]['frame']
    more=f'''if(!item||!cart||!e->a)e->error=1;
 e->registers[3]=item;e->registers[4]=cart;currency(e,e->a,40);submit(ctx,e);}}
 e=begin(ctx,{source_site});if(!e)return 0;e->tag=ctx->bx+2;
 e->a=word64(e,ctx->sp+{frame+40});currency(e,e->a,56);submit(ctx,e);
'''
    return text.replace(old,more,1)

def infer(plan,doc):
    if plan['strategy'] in ('path_sensitive_slice','boundary_replay'): return independent_infer(plan,doc)
    try:
        events=validate_capture(plan,doc)
        # V2 has one extra metadata packet; production numeric inference consumes
        # a documented view. Raw stats/bytes/events are validated and reported
        # before projection, and remain identical in the four-method metric.
        view=copy.deepcopy(doc)
        if not events[0]['b']:
            n=events[0]['a']; packet=events[n+2]
            check(packet['kind']=='source' and packet['tag']==n+2,'Missing snapshot-v2 request packet')
            events=events[:n+2]+events[n+3:]
        view['events']=events; view['stats']['submitted']=len(events)
        return production.infer(plan,view)
    except (ValueError,KeyError,IndexError) as exc:
        return dict(status='unknown',reason=str(exc),origins={},output=[])

def evaluate(plan,result,truth):
    # Every method is judged against exactly the same oracle and denominator.
    # Unlike the legacy boundaries smoke test, unknown is never a success for
    # a sink-present query. Preserve native status/error fields in the report.
    return production.evaluate(plan,result,truth)
