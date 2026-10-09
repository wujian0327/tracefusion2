"""Go Money value ABI and BPF transport, separate from integer provenance core."""
import copy
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'experiments/checkout-field-choice')]
from bounded_numeric_flow import analyze, branch_taken
from go_byte_adapter import assembly_rows
from go_string_adapter import file_offset, physical_probes
from hybrid_model import require
from string_capture import HEADER
from field_choice import Raw, decode_record

BASE='github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice'
FUNCTION=BASE+'/money.Sum'
TYPE=BASE+'/genproto.Money'


def plan_binary(binary,command,reader,out):
    data=binary.read_bytes()
    asm=command(['tool','objdump','-s','^'+re.escape(FUNCTION)+'$',str(binary)])
    rows=assembly_rows(asm);require(rows,'Missing original Sum symbol')
    for row in rows:
        offset=file_offset(data,row['address']);code=bytes.fromhex(row['code'])
        require(data[offset:offset+len(code)]==code,'ELF bytes differ')
    (out/'function.asm').write_text(asm)
    layout=json.loads(command(['run',str(reader),str(binary),TYPE]))[TYPE]
    fields={f['name']:f for f in layout['fields']}
    require(layout['size']==72 and (fields['Units']['offset'],fields['Units']['size'])==(56,8) and
            (fields['Nanos']['offset'],fields['Nanos']['size'])==(64,4),'Unsupported Money ABI layout')
    frames=[i for i,r in enumerate(rows) if re.fullmatch(r'SUBQ \$0x[0-9a-f]+, SP',r['asm'])]
    require(len(frames)==1,'Expected one fixed stack frame')
    idx=frames[0];frame=int(rows[idx]['asm'].split('$')[1].split(',')[0],0)
    require([r['asm'].split(' ')[0] for r in rows[:idx+1]]==['LEAQ','CMPQ','JBE','PUSHQ','MOVQ','SUBQ'], 'Unmodeled Go prologue')
    require(rows[0]['asm'].endswith('(SP), R12') and rows[1]['asm']=='CMPQ R12, 0x10(R14)' and
            rows[3]['asm']=='PUSHQ BP' and rows[4]['asm']=='MOVQ SP, BP','Prologue ABI differs')
    # Pinned Go aggregate ABI: first Money uses nine registers, second is a
    # 72-byte stack value; error result occupies 16 bytes before spill area.
    right_base=frame+16;left_spill=right_base+72+16
    regs=['AX','BX','CX','DI','SI','R8','R9','R10','R11']
    for i,reg in enumerate(regs):
        expected=f'MOV{"L" if i in (1,8) else "Q"} {reg}, {hex(left_spill+i*8)}(SP)'
        require(rows[idx+1+i]['asm']==expected,'Aggregate register spill ABI differs: '+expected)
    calls=[BASE+'/money.IsValid(SB)','runtime.memequal(SB)']
    globals_read=[BASE+'/money.'+name+offset+'(SB)' for name in ('ErrInvalidValue','ErrMismatchingCurrency') for offset in ('','+8')]
    seeds=[(right_base+56,8,'r.Units'),(right_base+64,4,'r.Nanos')]
    flow=analyze(rows[idx+1:],frame,[('R10',8,'l.Units'),('R11',4,'l.Nanos')],seeds,
                 {'Units':('R10',8),'Nanos':('R11',4)},calls,globals_read)
    by={r['address']:r for r in rows};sites=[]
    def add(address,kind,**kw):
        sites.append(dict(id=len(sites),address=address,file_offset=file_offset(data,address),kind=kind,asm=by[address]['asm'],**kw))
    add(flow['entry'],'entry')
    for b in flow['branches']:add(b['address'],'branch',op=b['op'])
    for address in sorted({p['return_address'] for p in flow['paths']}):add(address,'exit')
    selected=[s for s in sites if s['kind']!='branch' or s['address'] in flow['selected_branches']]
    (out/'numeric-flow.json').write_text(json.dumps(flow,indent=2)+'\n')
    return dict(adapter='original-go-money-sum-v1',binary_sha256=hashlib.sha256(data).hexdigest(),
                function=FUNCTION,layout=layout,frame=frame,right_units=right_base+56,right_nanos=right_base+64,
                error_return_sp_offset=80,flow=flow,all_sites=sites,sites=selected,
                event_order=[s['id'] for s in selected],strategy='selected',
                assumptions=['Go 1.25.4 amd64 aggregate ABI verified against register spills and DWARF',
                    'X15 is the Go ABI permanent-zero SIMD register',
                    'Pinned money.IsValid and runtime.memequal do not mutate caller argument/frame storage; caller registers clobbered',
                    'One Sum invocation, no unsafe/concurrent mutation; acyclic path model; data dependencies exclude implicit control taint'],
                scope='Unmodified original money.Sum in test executable; not full checkout or cross-service lineage')


def strategy_plan(plan,strategy):
    require(strategy in ('selected','all_branches','boundaries'),'Unknown strategy')
    p=copy.deepcopy(plan);p['strategy']=strategy
    if strategy=='all_branches':p['sites']=copy.deepcopy(p['all_sites'])
    elif strategy=='boundaries':p['sites']=[s for s in p['sites'] if s['kind']!='branch']
    p['event_order']=[s['id'] for s in p['sites']];return p


def source(plan,pid,namespace):
    h=re.sub(r'struct event_t \{.*?\};','struct event_t {u64 timestamp,pid_tid,g;u32 site,error;u64 a,b,c,d;};',HEADER,count=1,flags=re.S)
    start=h.index('static __always_inline void snapshot(');end=h.index('static __always_inline struct event_t *begin',start)
    h=h[:start]+h[end:]
    h=h.replace('NSDEV',str(namespace.st_dev)+'ULL').replace('NSINO',str(namespace.st_ino)+'ULL').replace('TARGET_PID',str(pid))
    h+='''
static __always_inline u64 word64(struct event_t *e,u64 ptr) {
 u64 v=0;if(bpf_probe_read_user(&v,8,(void *)ptr)<0)e->error=1;return v;
}
static __always_inline u64 word32(struct event_t *e,u64 ptr) {
 u32 v=0;if(bpf_probe_read_user(&v,4,(void *)ptr)<0)e->error=1;return v;
}
'''
    for s in plan['sites']:
        if s['kind']=='entry':code=f'e->a=ctx->r10;e->b=(u32)ctx->r11;e->c=word64(e,ctx->sp+{plan["right_units"]});e->d=word32(e,ctx->sp+{plan["right_nanos"]});'
        elif s['kind']=='branch':code='e->a=ctx->flags;'
        elif s['kind']=='exit':code=f'e->a=ctx->r10;e->b=(u32)ctx->r11;e->c=word64(e,ctx->sp+{plan["error_return_sp_offset"]});'
        else:raise ValueError('Unknown site')
        h+=f'\nint probe_{s["id"]}(struct pt_regs *ctx) {{struct event_t *e=begin(ctx,{s["id"]});if(!e)return 0;{code}submit(ctx,e);return 0;}}\n'
    return h


def signed(v,width):
    v&=(1<<width)-1
    return v-(1<<width) if v&(1<<(width-1)) else v


def infer(plan,doc):
    require(doc['binary_sha256']==plan['binary_sha256'] and not doc['capture_errors'] and doc['returncode']==0,'Capture failed/wrong binary')
    events=sorted(doc['events'],key=lambda e:e['timestamp']);stats=doc['stats'];sites={s['id']:s for s in plan['sites']}
    require(stats['submitted']==len(events) and stats['probe_hits']-stats['pid_rejections']==len(events) and
            not any(stats[k] for k in ('lost','read_errors','submit_errors','namespace_errors')),'Incomplete capture')
    require(len(events)>=2 and events[0]['kind']=='entry' and events[-1]['kind']=='exit','Missing boundaries')
    require(sum(e['kind']=='entry' for e in events)==sum(e['kind']=='exit' for e in events)==1,'Requires one invocation')
    require(len({(e['pid_tid']>>32,e['g']) for e in events})==1 and events[0]['g'],'Invocation mismatch')
    require(all(a['timestamp']<b['timestamp'] for a,b in zip(events,events[1:])),'Ambiguous event order')
    require(all(e['site'] in sites and e['kind']==sites[e['site']]['kind'] for e in events),'Unknown observation')
    observed=[]
    for e in events[1:-1]:
        require(e['kind']=='branch','Unexpected event')
        s=sites[e['site']];observed.append((s['address'],branch_taken(s['op'],e['a'])))
    controls={s['address'] for s in plan['sites'] if s['kind']=='branch'}
    exit=events[-1];entry=events[0]
    paths=[p for p in plan['flow']['paths'] if p['return_address']==sites[exit['site']]['address'] and
           [(b['address'],b['taken']) for b in p['branches'] if b['address'] in controls]==observed]
    candidates=[]
    for p in paths:
        if p['origins'] not in candidates:candidates.append(p['origins'])
    error=bool(exit['c'])
    status='unknown' if not candidates else 'rejected_input' if error else 'exact_data_origins' if len(candidates)==1 else 'ambiguous'
    # Nonzero error must agree with the modeled constant-zero numeric return;
    # never claim success on an error-only return or invent input origins.
    if candidates and (error != all(not any(c.values()) for c in candidates)):status='unknown'
    return dict(status=status,inputs=[signed(entry[k],w) for k,w in zip('abcd',(64,32,64,32))],
                output=[signed(exit['a'],64),signed(exit['b'],32)],error=error,
                candidates=candidates,matched_paths=[p['id'] for p in paths],
                observed_threads=len({e['pid_tid'] for e in events}),
                semantics=plan['flow']['semantics'])


def evaluate(plan,result,truth):
    for key in ('inputs','output','error'):require(result[key]==truth[key],'Truth differs: '+key)
    if truth['error']:require(result['status']=='rejected_input','Error was attributed as successful output')
    elif plan['strategy']=='boundaries':
        require(result['status']=='ambiguous' and truth['origins'] in result['candidates'],'Missing conservative candidate')
    else:require(result['status']=='exact_data_origins' and result['candidates']==[truth['origins']],'Data origins differ from independent truth')
    return dict(case=truth['case'],strategy=plan['strategy'],passed=True,status=result['status'],candidates=result['candidates'])
