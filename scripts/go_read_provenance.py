#!/usr/bin/env python3
"""Go read boundary: syscall registers/G identity and safe scope instruction probes."""
from functools import partial
import json
import re

import go_provenance as go
from go_interproc_provenance import decode_go
import read_provenance as shared
import read_boundaries as boundaries
from language_adapters import GO_CALLS, get_adapter, require


def scope_plan(assembly, symbols, config):
    name = config['read_boundary']['scope_function']
    require(re.fullmatch(GO_CALLS.function_pattern,name) and name in symbols and name not in config['functions'], 'Invalid Go workload scope')
    base,size = symbols[name]
    rows=[]
    for line in assembly.splitlines():
        m=re.match(r'^\s*([0-9a-f]+):\s+(.+?)\s*$',line)
        if m and base <= int(m[1],16) < base+size:
            rows.append((int(m[1],16)-base,' '.join(m[2].split()).split(' #')[0]))
    require(rows and rows[0][0]==0,'Missing Go workload entry')
    guard=1 if re.fullmatch(r'lea r12,\[rsp-0x[0-9a-f]+\]',rows[0][1]) else 0
    require(len(rows)>guard+2 and rows[guard][1]==('cmp r12,QWORD PTR [r14+0x10]' if guard else 'cmp rsp,QWORD PTR [r14+0x10]'), 'Unsupported Go workload stack-check prologue')
    branch=re.fullmatch(r'jbe ([0-9a-f]+)(?: <[^>]+>)?',rows[guard+1][1])
    require(branch is not None,'Unsupported workload guard branch')
    slow=int(branch[1],16)-base
    require(rows[guard+2][0]<slow<size and slow in {off for off,_ in rows},'Invalid workload guard target')
    targets={addr for symbol,(addr,_) in symbols.items() if symbol=='runtime.morestack_noctxt.abi0'}
    slow_calls=[re.fullmatch(r'call ([0-9a-f]+)(?: <[^>]+>)?',asm) for off,asm in rows if off>=slow]
    require(any(m and int(m[1],16) in targets for m in slow_calls),'Unrecognized workload runtime slow path')
    # Scope begins on the guard's fast fallthrough, not on a possible morestack
    # retry. RET instruction probes never patch a Go return address.
    exits=[off for off,asm in rows if asm=='ret' and off<slow]
    require(exits,'No ordinary Go workload return')
    return dict(function=name,entry_offset=rows[guard+2][0],return_offsets=exits,
                policy='fast-path entry and RET instruction uprobes; no uretprobe; workload internals not instruction-replayed')


def plan_program(assembly,symbols,config):
    require(get_adapter(config)==GO_CALLS,'Go read boundary requires the calls adapter')
    scope_plan(assembly,symbols,config)
    return shared.core.plan_program(assembly,symbols,config,decoder=decode_go)


def bpf_source(plans,config):
    require(get_adapter(config)==GO_CALLS,'Go boundary requires G identity')
    source=shared.bpf_source(plans,config)
    source=source.replace('#include <uapi/linux/ptrace.h>','#include <uapi/linux/ptrace.h>\n#include <asm/unistd.h>')
    source=source.replace('BPF_ARRAY(read_context, u64, 1);','BPF_ARRAY(read_context, u64, 1);\nBPF_ARRAY(boundary_current_g, u64, 1);')
    source=source.replace('    e->kind = kind; e->timestamp', '''    u64 *observed_g = boundary_current_g.lookup(&key);
    if (!observed_g || !*observed_g) { count(2); return 0; }
    e->regs[14] = *observed_g;
    e->kind = kind; e->timestamp''')
    source=source.replace('    *tid = bpf_get_current_pid_tgid();', '''    u64 *observed_g = boundary_current_g.lookup(&key);
    if (!observed_g || !ctx->r14) { count(2); return 0; }
    *observed_g = ctx->r14;
    *tid = bpf_get_current_pid_tgid();''')
    source=source.replace('    struct event_t *e = boundary_event(4);', '''    u64 *observed_g = boundary_current_g.lookup(&key);
    if (!observed_g || !ctx->r14) { count(2); return 0; }
    *observed_g = ctx->r14;
    struct event_t *e = boundary_event(4);''')
    source=source.replace('TRACEPOINT_PROBE(syscalls, sys_enter_pread64)', '''struct read_enter_args { s32 fd; u64 buf, count; s64 pos; };
struct read_exit_args { s64 ret; };
static __always_inline int traced_pread_enter(struct read_enter_args *args)''')
    source=source.replace('TRACEPOINT_PROBE(syscalls, sys_exit_pread64)','static __always_inline int traced_pread_exit(struct read_exit_args *args)')
    # The perf helper needs the actual tracepoint context, not our decoded
    # argument struct. Keep it separate when adapting the shared payload logic.
    source=source.replace('traced_pread_enter(struct read_enter_args *args)','traced_pread_enter(void *ctx, struct read_enter_args *args)')
    source=source.replace('traced_pread_exit(struct read_exit_args *args)','traced_pread_exit(void *ctx, struct read_exit_args *args)')
    source=source.replace('return emit_boundary(args,e);','return emit_boundary(ctx,e);')
    for name in ('close','dup2','dup3'):
        source=source.replace('TRACEPOINT_PROBE(syscalls, sys_enter_%s) { return reject_lifecycle(args); }'%name,'')
    require('TRACEPOINT_PROBE(' not in source,'Unexpected syscall attachment remains')
    source += r'''
/* Linux amd64 syscall ABI: fd=DI, buffer=SI, count=DX, offset=R10.
 * Read G from the actual saved user registers on BOTH syscall boundaries;
 * copying the scope's initial G would conceal an intervening G switch. */
static __always_inline int read_user_regs(struct bpf_raw_tracepoint_args *ctx, struct pt_regs *regs) {
    if (bpf_probe_read_kernel(regs, sizeof(*regs), (void *)ctx->args[0]) < 0) { count(2); return -1; }
    u32 key=0; u64 *observed_g=boundary_current_g.lookup(&key);
    if (!observed_g || !regs->r14) { count(2); return -1; }
    *observed_g=regs->r14;
    return 0;
}
RAW_TRACEPOINT_PROBE(sys_enter) {
    if (!in_read_scope()) return 0;
    u64 nr=args->args[1];
    if (nr!=__NR_pread64 && nr!=__NR_close && nr!=__NR_dup2 && nr!=__NR_dup3) return 0;
    struct pt_regs regs={};
    if (read_user_regs(args,&regs)<0) return 0;
    if (nr!=__NR_pread64) return reject_lifecycle(args);
    struct read_enter_args decoded={};
    decoded.fd=regs.di; decoded.buf=regs.si; decoded.count=regs.dx; decoded.pos=regs.r10;
    return traced_pread_enter(args,&decoded);
}
RAW_TRACEPOINT_PROBE(sys_exit) {
    if (!in_read_scope()) return 0;
    /* Only a pending pread needs an exit. The shared pairing checks fail if
     * an unexpected return is substituted for it. */
    u32 key=0; struct read_state_t *s=read_state.lookup(&key);
    if (!s || !s->pending) return 0;
    struct pt_regs regs={};
    if (read_user_regs(args,&regs)<0) return 0;
    if (regs.orig_ax!=__NR_pread64) { count(2); return 0; }
    struct read_exit_args decoded={}; decoded.ret=(s64)args->args[1];
    return traced_pread_exit(args,&decoded);
}
'''
    return source


def build(scenario,out):
    binary,plans,config=go.build(scenario,out,planner=plan_program,source_generator=bpf_source)
    scope=scope_plan((out/'disassembly.txt').read_text(),go.parse_nm((out/'symbols.txt').read_text()),config)
    go.common.save(out/'read-scope-plan.json',scope)
    return binary,plans,config


def attach_scope(bpf,process,binary,plans,config,out):
    scope=json.loads((out/'read-scope-plan.json').read_text())
    bpf.attach_uprobe(name=str(binary),sym=scope['function'],sym_off=scope['entry_offset'],fn_name='read_scope_enter',pid=process.pid)
    for off in scope['return_offsets']:
        bpf.attach_uprobe(name=str(binary),sym=scope['function'],sym_off=off,fn_name='read_scope_exit',pid=process.pid)
    go.common.save(out/'read-boundary-attachments.json',dict(scope,pid=process.pid,
        raw_tracepoints=['sys_enter','sys_exit'],syscalls=['pread64','close','dup2','dup3'],
        identity='kernel pid_tid plus actual user R14 on scope, syscall and compute events',uretprobe=False))


record=partial(shared.record,source_generator=bpf_source,scope_attacher=attach_scope)

if __name__=='__main__':
    raise SystemExit(go.common.main(default_scenario=go.common.ROOT/'scenarios/go-read-provenance',prefix='go-read-provenance',
        build_fn=build,record_fn=record,infer_fn=boundaries.bind,evaluate_fn=boundaries.evaluate,required_tools=('go','objdump')))
