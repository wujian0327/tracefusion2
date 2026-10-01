#!/usr/bin/env python3
"""Cross-function native provenance pilot: build or run with system Python BCC."""
from functools import partial

import hybrid_provenance as common
from interproc_model import MAX_DEPTH, REGS, STACK_BYTES, STACK_WORDS, infer, plan_program


def bpf_source(plans, config):
    source = r'''
#include <uapi/linux/ptrace.h>
struct state_t {
    u64 call, step, src, dst, root_sp;
    u32 depth, root, frames[MAX_DEPTH];
};
struct event_t {
    u64 timestamp, pid_tid, call_id, sequence, src_addr, dst_addr, ip, flags, root_sp;
    u64 regs[16], stack[STACK_WORDS];
    u32 function, offset, root, depth, inputs[8], outputs[8];
    s32 source_error, destination_error, stack_error;
};
BPF_HASH(states, u64, struct state_t, 64);
BPF_ARRAY(metrics, u64, 4);
/* The event is larger than 512 bytes: do not allocate it on the BPF stack. */
BPF_PERCPU_ARRAY(scratch, struct event_t, 1);
BPF_PERF_OUTPUT(events);
static __always_inline void count(u32 k) {
    u64 *v = metrics.lookup(&k);
    if (v) __sync_fetch_and_add(v, 1);
}
static __always_inline int record(struct pt_regs *ctx, u32 fid, u32 offset, u32 is_ret, u32 is_root) {
    count(3);
    u64 tid = bpf_get_current_pid_tgid();
    struct state_t zero = {}, *s = states.lookup_or_try_init(&tid, &zero);
    if (!s) { count(2); return 0; }
    u32 d = s->depth;
    if (offset == 0) {
        if (is_root) {
            if (d != 0) { count(2); return 0; }
            s->call += 1; s->step = 0; s->root = fid;
            s->src = PT_REGS_PARM2(ctx); s->dst = PT_REGS_PARM1(ctx);
            s->root_sp = ctx->sp;
        } else if (d == 0) { count(2); return 0; }
        if (d >= MAX_DEPTH) { count(2); return 0; }
        s->frames[d] = fid; d += 1; s->depth = d;
    }
    if (d == 0 || d > MAX_DEPTH) { count(2); return 0; }
    if (s->frames[d-1] != fid) { count(2); return 0; }
    u32 key = 0;
    struct event_t *e = scratch.lookup(&key);
    if (!e) { count(2); return 0; }
    __builtin_memset(e, 0, sizeof(*e));
    e->timestamp = bpf_ktime_get_ns(); e->pid_tid = tid;
    e->call_id = s->call; e->sequence = s->step++;
    e->src_addr = s->src; e->dst_addr = s->dst; e->root_sp = s->root_sp;
    e->ip = PT_REGS_IP(ctx); e->flags = ctx->flags;
    e->function = fid; e->offset = offset; e->root = s->root; e->depth = d;
REGISTER_ASSIGNMENTS
    e->source_error = bpf_probe_read_user(e->inputs, INPUT_BYTES, (void *)s->src);
    e->destination_error = bpf_probe_read_user(e->outputs, OUTPUT_BYTES, (void *)s->dst);
    e->stack_error = bpf_probe_read_user(e->stack, sizeof(e->stack), (void *)(s->root_sp-STACK_BYTES));
    count(0);
    if (events.perf_submit(ctx, e, sizeof(*e)) < 0) count(1);
    if (is_ret) s->depth = d-1;
    return 0;
}
'''
    fields = ['ax','bx','cx','dx','si','di','bp','sp'] + ['r%d'%i for i in range(8,16)]
    substitutions = dict(MAX_DEPTH=str(MAX_DEPTH),STACK_WORDS=str(STACK_WORDS),STACK_BYTES=str(STACK_BYTES),
                         INPUT_BYTES=str(4*len(config['input_fields'])),OUTPUT_BYTES=str(4*len(config['output_fields'])),
                         REGISTER_ASSIGNMENTS='\n'.join('    e->regs[%d] = ctx->%s;'%(i,f) for i,f in enumerate(fields)))
    for name,value in substitutions.items(): source=source.replace(name,value)
    for fid,p in enumerate(plans):
        instructions={n['offset']:n for n in p['instructions']}
        for off in p['probe_offsets']:
            source+='\nint probe_%d_%d(struct pt_regs *ctx) { return record(ctx, %d, %d, %d, %d); }\n'%(fid,off,fid,off,instructions[off]['op']=='ret',p['is_root'])
    return source


build=partial(common.build,planner=plan_program,source_generator=bpf_source,
              extra_flags=('-fno-optimize-sibling-calls','-fno-ipa-ra'))
record=partial(common.record_bpf,source_generator=bpf_source)

if __name__=='__main__':
    raise SystemExit(common.main(default_scenario=common.ROOT/'scenarios/interproc-provenance',
        prefix='interproc-provenance',build_fn=build,record_fn=record,infer_fn=infer))
