"""Binary-derived field-copy dependencies with selected branch observations."""
import copy
import ctypes as ct
import hashlib
import json
import re
from bounded_field_flow import analyze
from go_byte_adapter import assembly_rows
from go_string_adapter import file_offset,physical_probes
from hybrid_model import require
from string_capture import HEADER

FUNCTION='github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice.chooseUnits'
TYPE='github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.Money'


def plan_binary(binary,command,reader,out,function=FUNCTION):
    data=binary.read_bytes()
    asm=command(['tool','objdump','-s','^'+re.escape(function)+'$',str(binary)])
    (out/'function.asm').write_text(asm);rows=assembly_rows(asm)
    require(rows,'Missing optimized function; no fallback to source interpretation')
    for row in rows:
        offset=file_offset(data,row['address']);code=bytes.fromhex(row['code'])
        require(data[offset:offset+len(code)]==code,'ELF/disassembly mismatch')
    layout=json.loads(command(['run',str(reader),str(binary),TYPE]))[TYPE]
    fields=[f for f in layout['fields'] if f['name']=='Units' and f['size']==8]
    require(len(fields)==1,'Missing int64 Units layout')
    field_offset=fields[0]['offset'];flow=analyze(rows,field_offset,object_size=layout['size'])
    by_addr={r['address']:r for r in rows};sites=[]
    def add(address,kind,**kw):
        sites.append(dict(id=len(sites),address=address,file_offset=file_offset(data,address),
                          kind=kind,asm=by_addr[address]['asm'],**kw))
    add(flow['entry'],'entry')
    for branch in flow['branches']:
        add(branch['address'],'branch',op=branch['op'])
    for address in sorted({p['return_address'] for p in flow['paths']}):add(address,'exit')
    require(len({s['address'] for s in sites})==len(sites),'Overlapping observation sites')
    (out/'field-flow.json').write_text(json.dumps(flow,indent=2)+'\n')
    selected=[s for s in sites if s['kind']!='branch' or s['address'] in flow['selected_branches']]
    return dict(adapter='bounded-go-field-choice-v2',binary_sha256=hashlib.sha256(data).hexdigest(),
                function=function,go='go1.25.4',field='Units',field_offset=field_offset,layout=layout,
                flow=flow,all_sites=sites,sites=selected,event_order=[s['id'] for s in selected],strategy='selected',
                scope='Controlled variant; acyclic immutable int64 field copy to one fresh object; not original checkout logic',
                abi={'inputs':['AX','BX'],'result':'AX','goroutine':'R14','branch_flags':'x86 RFLAGS ZF'})


def strategy_plan(plan,strategy):
    require(strategy in ('selected','boundaries','all_branches'),'Unknown field-choice policy')
    result=copy.deepcopy(plan);result['strategy']=strategy
    if strategy=='boundaries':result['sites']=[s for s in result['sites'] if s['kind']!='branch']
    if strategy=='all_branches':result['sites']=copy.deepcopy(plan['all_sites'])
    result['event_order']=[s['id'] for s in result['sites']]
    return result


class Raw(ct.Structure):
    _fields_=[(k,ct.c_uint64) for k in ('timestamp','pid_tid','g')]+[
        ('site',ct.c_uint32),('error',ct.c_uint32)]+[(k,ct.c_uint64) for k in ('a','b','c','d')]


def source(plan,pid,namespace):
    header=re.sub(r'struct event_t \{.*?\};','struct event_t {u64 timestamp,pid_tid,g;u32 site,error;u64 a,b,c,d;};',HEADER,count=1,flags=re.S)
    start=header.index('static __always_inline void snapshot(')
    end=header.index('static __always_inline struct event_t *begin',start)
    header=header[:start]+header[end:]
    header=header.replace('NSDEV',str(namespace.st_dev)+'ULL').replace('NSINO',str(namespace.st_ino)+'ULL').replace('TARGET_PID',str(pid))
    header+='''
static __always_inline u64 word(struct event_t *e,u64 ptr) {
 u64 value=0;if(!ptr || bpf_probe_read_user(&value,8,(void *)ptr)<0)e->error=1;return value;
}
'''
    for s in plan['sites']:
        offset=plan['field_offset']
        if s['kind']=='entry':code=f'e->a=ctx->ax;e->b=ctx->bx;if(!e->a || !e->b)e->error=1;else {{e->c=word(e,e->a+{offset});e->d=word(e,e->b+{offset});}}'
        elif s['kind']=='branch':code='e->a=ctx->flags;'
        elif s['kind']=='exit':code=f'e->a=ctx->ax;if(!e->a)e->error=1;else e->b=word(e,e->a+{offset});'
        else:raise ValueError('Unknown probe kind')
        header+=f'\nint probe_{s["id"]}(struct pt_regs *ctx) {{struct event_t *e=begin(ctx,{s["id"]});if(!e)return 0;{code} submit(ctx,e);return 0;}}\n'
    return header


def decode_record(data,size,sites):
    n=ct.sizeof(Raw);padded=((n+4+7)//8)*8-4
    require(size in (n,padded),f'Event layout mismatch: {size}, expected {n}/{padded}')
    raw=Raw.from_buffer_copy(ct.string_at(data,n))
    require(raw.site in sites and not raw.error,'Unknown site or memory read failure')
    result={k:int(getattr(raw,k)) for k in ('timestamp','pid_tid','g','site','a','b','c','d')}
    result['kind']=sites[raw.site]['kind'];return result


def signed(value):return value if value<1<<63 else value-(1<<64)


def infer(plan,doc):
    require(doc['binary_sha256']==plan['binary_sha256'],'Wrong binary')
    require(not doc['capture_errors'] and doc['returncode']==0,'Capture failed')
    events=sorted(doc['events'],key=lambda e:e['timestamp']);stats=doc['stats']
    require(stats['submitted']==len(events) and not any(stats[k] for k in ('lost','read_errors','submit_errors','namespace_errors')),'Incomplete capture')
    require(stats['probe_hits']-stats['pid_rejections']==len(events),'Unaccounted probe hits')
    require(len(events)>=2 and events[0]['kind']=='entry' and events[-1]['kind']=='exit','Missing boundaries')
    require(sum(e['kind']=='entry' for e in events)==sum(e['kind']=='exit' for e in events)==1,'Requires one invocation')
    require(all(a['timestamp']<b['timestamp'] for a,b in zip(events,events[1:])),'Ambiguous event order')
    require(len({(e['pid_tid']>>32,e['g']) for e in events})==1 and events[0]['g'],'Invocation identity differs')
    sites={s['id']:s for s in plan['sites']}
    require(all(e['site'] in sites and e['kind']==sites[e['site']]['kind'] for e in events),'Unknown observation')
    entry,exit=events[0],events[-1];inputs=[entry['a'],entry['b']];values=[signed(entry['c']),signed(entry['d'])]
    require(all(inputs) and inputs[0]!=inputs[1],'Requires two distinct live input objects')
    require(exit['a'] and exit['a'] not in inputs,'Output must be a fresh object')
    observed=[]
    for e in events[1:-1]:
        require(e['kind']=='branch','Unexpected intermediate observation')
        site=sites[e['site']];zf=bool(e['a']&0x40)
        require(site['op'] in ('JE','JNE'),'Unsupported branch predicate')
        observed.append((site['address'],zf if site['op']=='JE' else not zf))
    controls={s['address'] for s in plan['sites'] if s['kind']=='branch'}
    paths=[p for p in plan['flow']['paths'] if
           [(e['address'],e['taken']) for e in p['branches'] if e['address'] in controls]==observed and
           p['return_address']==sites[exit['site']]['address']]
    candidates=sorted({p['sink']['input_index'] for p in paths})
    value=signed(exit['b'])
    consistent=bool(candidates) and any(values[i]==value for i in candidates)
    status='exact_field_source' if len(candidates)==1 and consistent else 'ambiguous' if candidates and consistent else 'unknown'
    # Values only check consistency; NEVER eliminate a candidate using value equality.
    return dict(input_objects=inputs,input_values=values,output_object=exit['a'],output_value=value,
                source_candidates=candidates,status=status,matched_paths=[p['id'] for p in paths],
                source_field_addresses=[inputs[i]+plan['field_offset'] for i in candidates],
                fresh_output=True,observed_threads=len({e['pid_tid'] for e in events}),
                reason='binary field-copy paths resolved by retained branch outcomes' if status=='exact_field_source' else
                       'remaining modeled paths have multiple origins' if status=='ambiguous' else 'missing path evidence or value/model mismatch',
                claim='Units field source in the bounded immutable copy model, not numeric transforms or remote-service lineage')


def evaluate(plan,inferred,truth):
    for key in ('input_objects','input_values','output_object','output_value'):
        require(inferred[key]==truth[key],'Boundary truth differs: '+key)
    if plan['strategy'] in ('selected','all_branches'):
        require(inferred['status']=='exact_field_source' and inferred['source_candidates']==truth['source_candidates'],'Selected source differs from independent truth')
        require(inferred['source_field_addresses']==[truth['source_field_address']],'Field address differs')
    else:
        require(inferred['status']=='ambiguous' and set(truth['source_candidates'])<=set(inferred['source_candidates']),
                'Boundary-only policy must preserve ambiguity in this variant')
    return dict(case=truth['case'],strategy=plan['strategy'],passed=True,status=inferred['status'],
                source_candidates=inferred['source_candidates'],fresh_output=True)
