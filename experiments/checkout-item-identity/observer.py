"""Bounded reference identity observation, not heap write-history reconstruction."""
import ctypes as ct
import hashlib
import json
import re
from go_byte_adapter import assembly_rows, GO_REGS, PT_REGS
from go_object_graph import analyze
from go_string_adapter import file_offset, physical_probes
from hybrid_model import require
from string_capture import HEADER

LIMIT = 32
FUNCTION = 'github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice.(*checkoutService).prepOrderItems'
TYPE = 'github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.OrderItem'
CONVERT = FUNCTION.rsplit('.',1)[0]+'.convertCurrency'


def plan_binary(binary, command, layout_reader, out):
    data = binary.read_bytes()
    asm = command(['tool', 'objdump', '-s', '^'+re.escape(FUNCTION)+'$', str(binary)])
    (out/'function.asm').write_text(asm)
    rows = assembly_rows(asm)
    require(rows, 'Missing function')
    for row in rows:
        offset = file_offset(data, row['address'])
        code = bytes.fromhex(row['code'])
        require(data[offset:offset+len(code)] == code, 'Instruction bytes differ')
    layout = json.loads(command(['run', str(layout_reader), str(binary), TYPE]))[TYPE]
    offsets = {}
    for name in ('Item','Cost'):
        fields = [f for f in layout['fields'] if f['name'] == name and f['size'] == 8]
        require(len(fields) == 1, 'Missing pointer-sized '+name+' field')
        offsets[name] = fields[0]['offset']
    graph = analyze(rows, FUNCTION, allow_indirect_calls=True)
    by_addr = {r['address']: r for r in rows}
    sites = []
    def add(address, kind, **kw):
        r = by_addr[address]
        sites.append(dict(id=len(sites), address=address, file_offset=file_offset(data,address),
                          kind=kind, asm=r['asm'], **kw))
    add(graph['frame_entry'], 'entry')
    stores = graph['stores']
    for field,offset in offsets.items():
        candidates = [s for s in stores if s['asm'].startswith('MOVQ ') and
                      s['memory']['offset'] == offset and not s['memory']['index'] and
                      s['value_operand'] in GO_REGS and s['memory']['base'] not in ('SP','BP')]
        require(candidates, 'No candidate '+field+'-offset stores')
        for s in candidates:
            add(s['address'], 'field_operand', field=field, base=s['memory']['base'], value=s['value_operand'])
    calls = [r for r in rows if r['asm']=='CALL '+CONVERT+'(SB)']
    require(len(calls)==1,'Requires one direct convertCurrency call site')
    call=calls[0]
    require(bytes.fromhex(call['code'])[0]==0xe8,'Expected direct CALL encoding')
    continuation=call['address']+len(bytes.fromhex(call['code']))
    incoming=[int(a) for a,targets in graph['cfg'].items() if continuation in targets]
    require(incoming==[call['address']],'Conversion continuation has another predecessor')
    add(call['address'],'conversion_enter')
    add(continuation,'conversion_return',call_address=call['address'])
    publications = [s for s in stores if s['asm'].startswith('MOVQ ') and
                    s['memory']['index'] and s['memory']['scale'] == 8 and
                    s['value_operand'] in GO_REGS and s['memory']['offset'] == 0]
    require(len(publications) == 1, 'Expected one supported indexed publication instruction')
    s = publications[0]
    continuation = s['address'] + len(bytes.fromhex(by_addr[s['address']]['code']))
    incoming = [int(a) for a, targets in graph['cfg'].items() if continuation in targets]
    require(incoming == [s['address']], 'Publication continuation has another predecessor')
    add(continuation, 'publication', base=s['memory']['base'], index=s['memory']['index'],
        store_address=s['address'])
    for r in graph['returns']:
        add(r['address'], 'exit')
    require(len({s['address'] for s in sites}) == len(sites), 'Overlapping probes')
    return dict(schema_version=2,binary_sha256=hashlib.sha256(data).hexdigest(), function=FUNCTION,
                go='go1.25.4', item_offset=offsets['Item'], cost_offset=offsets['Cost'], layout=layout, max_items=LIMIT,
                sites=sites, event_order=[s['id'] for s in sites],
                scope='One call/process; live object reference identity only; not field contents or write history',
                abi={'input_slice':'DI/SI', 'output_slice':'AX/BX', 'error':'DI/SI', 'goroutine':'R14',
                     'conversion_input':'DI', 'conversion_result':'AX', 'conversion_error':'BX/CX'})


class Raw(ct.Structure):
    _fields_ = [(k,ct.c_uint64) for k in ('timestamp','pid_tid','g','a','b','c','d','n')] + [
        ('site',ct.c_uint32), ('error',ct.c_uint32),
        ('values',ct.c_uint64*LIMIT), ('items',ct.c_uint64*LIMIT), ('costs',ct.c_uint64*LIMIT)]


def source(plan, pid, namespace):
    # Reuse namespace filtering, counters, zeroing and perf submission unchanged.
    header = re.sub(r'struct event_t \{.*?\};',
        'struct event_t { u64 timestamp,pid_tid,g,a,b,c,d,n; u32 site,error; u64 values[32],items[32],costs[32]; };',
        HEADER, count=1, flags=re.S)
    start = header.index('static __always_inline void snapshot(')
    end = header.index('static __always_inline struct event_t *begin',start)
    header = header[:start] + header[end:]
    header = header.replace('NSDEV',str(namespace.st_dev)+'ULL').replace('NSINO',str(namespace.st_ino)+'ULL').replace('TARGET_PID',str(pid))
    header += '''
static __always_inline u64 readptr(struct event_t *e,u64 address) {
 u64 v=0; if(!address || bpf_probe_read_user(&v,8,(void *)address)<0)e->error=1; return v;
}
'''
    def reg(name): return 'ctx->'+PT_REGS[GO_REGS[name]]
    for s in plan['sites']:
        kind = s['kind']
        if kind in ('entry','exit'):
            code = 'e->a=ctx->di;e->n=ctx->si;' if kind=='entry' else 'e->a=ctx->ax;e->n=ctx->bx;e->b=ctx->di;e->c=ctx->si;'
            code += '''if(e->n>32)e->error=1;
 #pragma unroll
 for(int i=0;i<32;i++) { if(i<e->n) {
 e->values[i]=readptr(e,e->a+8*i);
'''
            if kind=='exit':
                code+=f'e->items[i]=e->values[i]?readptr(e,e->values[i]+{plan["item_offset"]}):0;'
                code+=f'e->costs[i]=e->values[i]?readptr(e,e->values[i]+{plan["cost_offset"]}):0;'
            code += '} }'
        elif kind=='field_operand':
            code = f'e->a={reg(s["base"])};e->b={reg(s["value"])};'
        elif kind=='conversion_enter':code='e->a=ctx->di;'
        elif kind=='conversion_return':code='e->a=ctx->ax;e->b=ctx->bx;e->c=ctx->cx;'
        elif kind=='publication':
            code = f'e->a={reg(s["base"])};e->n={reg(s["index"])};if(e->n>=32)e->error=1;else {{e->b=readptr(e,e->a+8*e->n);e->c=e->b?readptr(e,e->b+{plan["item_offset"]}):0;e->d=e->b?readptr(e,e->b+{plan["cost_offset"]}):0;}}'
        else:raise ValueError('Unknown probe kind')
        header += f'\nint probe_{s["id"]}(struct pt_regs *ctx) {{ struct event_t *e=begin(ctx,{s["id"]});if(!e)return 0;{code}\nsubmit(ctx,e);return 0;}}\n'
    return header


def decode_record(data,size,sites):
    n=ct.sizeof(Raw); padded=((n+4+7)//8)*8-4
    require(size in (n,padded), f'Event layout mismatch: {size}, expected {n}/{padded}')
    raw=Raw.from_buffer_copy(ct.string_at(data,n))
    require(raw.site in sites and not raw.error, 'Unknown site or failed memory read')
    doc={k:int(getattr(raw,k)) for k in ('timestamp','pid_tid','g','a','b','c','d','n','site')}
    doc['kind']=sites[raw.site]['kind']
    require(raw.n<=LIMIT,'Snapshot exceeds item limit')
    doc['values']=list(raw.values)[:raw.n] if doc['kind'] in ('entry','exit') else []
    doc['items']=list(raw.items)[:raw.n] if doc['kind']=='exit' else []
    doc['costs']=list(raw.costs)[:raw.n] if doc['kind']=='exit' else []
    return doc


def infer(plan,doc):
    with_cost=plan.get('schema_version',1)==2
    require(plan.get('schema_version',1) in (1,2),'Unsupported plan schema')
    require(doc['binary_sha256']==plan['binary_sha256'],'Wrong binary')
    require(not doc['capture_errors'] and doc['returncode']==0,'Capture/target failed')
    events=sorted(doc['events'],key=lambda e:e['timestamp'])
    stats=doc['stats']
    require(stats['submitted']==len(events) and not any(stats[k] for k in ('lost','read_errors','submit_errors')), 'Incomplete capture')
    require(stats['namespace_errors']==0 and stats['probe_hits']-stats['pid_rejections']==stats['submitted'], 'Unaccounted probe hits')
    require(len(events)>=2 and events[0]['kind']=='entry' and events[-1]['kind']=='exit','Missing boundaries')
    require(all(a['timestamp']<b['timestamp'] for a,b in zip(events,events[1:])), 'Ambiguous event order')
    sites={s['id']:s for s in plan['sites']}
    require(all(e['site'] in sites and e['kind']==sites[e['site']]['kind'] for e in events),'Unknown event site')
    require(sum(e['kind']=='entry' for e in events)==1 and sum(e['kind']=='exit' for e in events)==1,'Requires one invocation')
    require(len({(e['pid_tid']>>32,e['g']) for e in events})==1 and events[0]['g']!=0,'Invocation identity mismatch')
    entry,exit=events[0],events[-1]
    inputs=entry['values']
    require(entry['n']==len(inputs)<=LIMIT and all(inputs),'Invalid input snapshot')
    require(exit['n']==len(exit['values'])==len(exit['items']) and exit['n']<=LIMIT,'Invalid output snapshot')
    if with_cost:require(len(exit['costs'])==exit['n'],'Invalid Cost snapshot')
    latest={};publications={};publication_count=0
    conversions=[];pending=None
    for e in events[1:-1]:
        if e['kind']=='field_operand':latest[e['a'],sites[e['site']].get('field','Item')]=e
        elif with_cost and e['kind']=='conversion_enter':
            require(pending is None and e['a'] and len(conversions)<LIMIT,'Invalid/nested conversion entry')
            pending=e
        elif with_cost and e['kind']=='conversion_return':
            require(pending is not None,'Conversion return without entry')
            failed=bool(e['b'])
            require((failed and e['a']==0) or (not failed and e['a']!=0),'Unsupported conversion return')
            conversions.append(dict(input=pending['a'],result=e['a'],error=failed))
            pending=None
        elif e['kind']=='publication':
            require(e['n']<LIMIT and e['a'] and e['b'] and e['c'],'Invalid publication')
            witness=latest.get((e['b'],'Item'))
            require(witness is not None and witness['b']==e['c'],'Missing/mismatching latest observed field operand')
            publication=dict(e)
            if with_cost:
                require(pending is None and e['d'],'Publication during conversion or nil Cost')
                witness=latest.get((e['b'],'Cost'))
                require(witness is not None and witness['b']==e['d'],'Missing/mismatching Cost operand')
                publication['cost_candidates']=[i for i,c in enumerate(conversions) if not c['error'] and c['result']==e['d']]
            publications[e['a'],e['n']]=publication
            publication_count+=1
        else:raise ValueError('Unexpected intermediate boundary')
    require(pending is None,'Unfinished conversion call')
    failed=bool(exit['b'])
    require(not failed or exit['n']==0,'Partial output on error')
    outputs=[]
    for i,(obj,item) in enumerate(zip(exit['values'],exit['items'])):
        p=publications.get((exit['a'],i))
        require(p is not None and p['b']==obj and p['c']==item,'Final object lacks matching publication evidence')
        candidates=[j for j,v in enumerate(inputs) if v==item]
        outputs.append(dict(object=obj,item=item,source_candidates=candidates,
            status='exact_reference' if len(candidates)==1 else 'ambiguous_input_position' if candidates else 'unknown'))
        if with_cost:
            require(p['d']==exit['costs'][i],'Final Cost differs from publication')
            candidates=p['cost_candidates']
            outputs[-1].update(cost=exit['costs'][i],cost_source_candidates=candidates,
                cost_status='exact_reference' if len(candidates)==1 else 'ambiguous_conversion_instance' if candidates else 'unknown')
    result=dict(inputs=inputs,error=failed,outputs=outputs,publications=publication_count,
                observed_threads=len({e['pid_tid'] for e in events}),
                claim='Final Item reference identity; no attribution of contents, input slot reads, or complete write history')
    if with_cost:
        result.update(conversions=conversions,claim='Final Item and Cost reference identity; Cost candidates are prior successful conversion returns; no numeric computation or complete write history')
    return result


def evaluate(inference, truth):
    require(inference['inputs']==truth['inputs'] and inference['error']==truth['error'],'Boundary truth differs')
    keys=('object','item','source_candidates')
    if 'conversions' in inference:
        require(inference['conversions']==truth['conversions'],'Conversion boundary truth differs')
        keys+=('cost','cost_source_candidates')
    actual=[{k:o[k] for k in keys} for o in inference['outputs']]
    require(actual==truth['outputs'],'Reference attribution differs from independent truth')
    result=dict(case=truth['case'],passed=True,outputs=len(actual),
                ambiguous=sum(o['status']=='ambiguous_input_position' for o in inference['outputs']))
    if 'conversions' in inference:
        result.update(conversions=len(inference['conversions']),cost_outputs=len(actual),
                      cost_ambiguous=sum(o['cost_status']=='ambiguous_conversion_instance' for o in inference['outputs']))
    return result
