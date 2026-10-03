#!/usr/bin/env python3
"""Go request state follows observed G; raw TIDs remain evidence, never keys."""
from functools import partial
import json
from pathlib import Path
import sys

import gin_api_provenance as serial
import gin_concurrent_provenance as concurrent
import gin_migration_boundaries as boundary
from hybrid_model import require

common = serial.common
SCENARIO = common.ROOT / 'scenarios/gin-migration-provenance'
client = concurrent.client
oracle = concurrent.oracle


def bpf_source(plans, config):
    require(config['gin_api'].get('pinned_request_thread') is False and
            config['gin_api'].get('execution_identity') == 'process-g-request-v1',
            'Migration requires the explicit observed-G request contract')
    source = concurrent.bpf_source(plans, config)
    replace = concurrent._replace
    def section(start, end, replacement):
        nonlocal source
        require(source.count(start) == source.count(end) == 1, 'Shared collector section changed')
        a, b = source.index(start), source.index(end)
        source = source[:a] + replacement + source[b:]
    section('/* Keyed by kernel pid_tid', 'static __always_inline u64 next_observation', r'''
/* One target process per collector. Seed its host TGID at the PID-scoped
 * uprobe, not from a potentially namespace-local userspace PID. */
BPF_ARRAY(target_tgid, u64, 1);
struct request_context_t {
    u64 request_id, g, step, read_tid;
    struct read_state_t reads;
};
BPF_HASH(requests, u64, struct request_context_t, 64);
static __always_inline int in_target(void) {
    u32 key=0; u64 *tgid=target_tgid.lookup(&key);
    return tgid && *tgid && *tgid==(bpf_get_current_pid_tgid()>>32);
}
static __always_inline struct request_context_t *current_request(u64 g) {
    if (!g || !in_target()) return 0;
    return requests.lookup(&g);
}
static __always_inline struct read_state_t *current_reads(u64 g) {
    struct request_context_t *s=current_request(g); return s ? &s->reads : 0;
}
''')
    source = replace(source, '''    u32 scope_key = 0; u64 *scope_tid = current_tid_ptr();
    if (!scope_tid || *scope_tid != tid) { count(2); return 0; }
    struct state_t zero = {}, *s = states.lookup_or_try_init(&tid, &zero);''', '''    struct request_context_t *active=current_request(ctx->r14);
    if (!active) { count(2); return 0; }
    u64 execution=active->request_id;
    struct state_t zero = {}, *s = states.lookup_or_try_init(&execution, &zero);''')
    # Both emit paths already have an explicitly resolved active request.
    payload = '''    u64 *request = current_request_id();
    if (!request || !*request) { count(2); return 0; }
    e->request_id = *request;
    struct request_context_t *active=current_request();
    if (!active) { count(2); return 0; }
    e->request_sequence=active->step++;'''
    source = replace(source, payload, '''    e->request_id=active->request_id;
    e->request_sequence=active->step++;''', count=2)
    section('static __always_inline int in_read_scope', 'static __always_inline int emit_boundary', r'''
static __always_inline struct event_t *boundary_event(u32 kind, u64 g) {
    struct request_context_t *active=current_request(g);
    if (!active) { count(2); return 0; }
    u32 key=0; struct event_t *e=scratch.lookup(&key);
    if (!e) { count(2); return 0; }
    __builtin_memset(e,0,sizeof(*e));
    e->regs[14]=g;
    e->kind=kind; e->timestamp=bpf_ktime_get_ns();
    e->pid_tid=bpf_get_current_pid_tgid();
    e->observation_sequence=next_observation();
    e->request_id=active->request_id; e->request_sequence=active->step++;
    return e;
}
''')
    for name in ('enter', 'exit'):
        source = replace(source, 'traced_pread_%s(void *ctx, struct read_%s_args *args)' % (name, name),
                         'traced_pread_%s(void *ctx, struct read_%s_args *args, u64 g)' % (name, name))
    section('/* Linux amd64 syscall ABI:', '/* Go ABIInternal,', r'''
/* Never consult a stale TID->G cache. Read actual saved R14 at every syscall.
 * An individual kernel syscall must return on its entering TID. Migration
 * may occur after that return, when the Go runtime schedules the goroutine. */
static __always_inline int read_user_regs(struct bpf_raw_tracepoint_args *ctx, struct pt_regs *regs) {
    if (bpf_probe_read_kernel(regs,sizeof(*regs),(void *)ctx->args[0])<0) { count(2); return -1; }
    return 0;
}
RAW_TRACEPOINT_PROBE(sys_enter) {
    u64 nr=ctx->args[1];
    if (!in_target() || (nr!=__NR_pread64 && nr!=__NR_close && nr!=__NR_dup2 && nr!=__NR_dup3)) return 0;
    struct pt_regs regs={}; if (read_user_regs(ctx,&regs)<0) return 0;
    struct request_context_t *active=current_request(regs.r14);
    if (!active) return 0; /* Other runtime/HTTP goroutines are outside scope. */
    if (nr!=__NR_pread64) return reject_lifecycle(ctx,regs.r14);
    if (active->reads.pending) { count(2); return 0; }
    active->read_tid=bpf_get_current_pid_tgid();
    struct read_enter_args decoded={};
    decoded.fd=regs.di; decoded.buf=regs.si; decoded.count=regs.dx; decoded.pos=regs.r10;
    return traced_pread_enter(ctx,&decoded,regs.r14);
}
RAW_TRACEPOINT_PROBE(sys_exit) {
    if (!in_target()) return 0;
    struct pt_regs regs={}; if (read_user_regs(ctx,&regs)<0) return 0;
    if (regs.orig_ax!=__NR_pread64) return 0;
    struct request_context_t *active=current_request(regs.r14);
    if (!active) return 0;
    if (!active->reads.pending || active->read_tid!=bpf_get_current_pid_tgid()) { count(2); return 0; }
    struct read_exit_args decoded={}; decoded.ret=(s64)ctx->args[1];
    return traced_pread_exit(ctx,&decoded,regs.r14);
}

''')
    section('static __always_inline struct event_t *gin_event', 'static __always_inline void copy_json', r'''
static __always_inline struct event_t *gin_event(struct pt_regs *ctx, u32 kind) {
    if (!current_request(ctx->r14)) return 0;
    count(3); return boundary_event(kind,ctx->r14);
}
''')
    source = replace(source, 'reject_lifecycle(void *ctx)', 'reject_lifecycle(void *ctx, u64 g)')
    source = replace(source, 'if (!in_read_scope()) return 0;', 'if (!current_request(g)) return 0;', count=3)
    source = replace(source, 'current_reads()', 'current_reads(g)', count=2)
    for kind in (1, 2, 5):
        source = replace(source, 'boundary_event(%d)' % kind, 'boundary_event(%d,g)' % kind)
    source = source[:source.index('int read_scope_enter(')] + r'''
int read_scope_enter(struct pt_regs *ctx) {
    count(3); u32 key=0; u64 tgid=bpf_get_current_pid_tgid()>>32, g=ctx->r14;
    u64 *target=target_tgid.lookup(&key);
    if (!target || !tgid || !g) { count(2); return 0; }
    if ((*target && *target!=tgid) || requests.lookup(&g)) { count(2); return 0; }
    *target=tgid; /* All PID-scoped entry probes seed the same process. */
    u64 *clock=request_clock.lookup(&key);
    if (!clock) { count(2); return 0; }
    struct request_context_t fresh={};
    fresh.request_id=__sync_fetch_and_add(clock,1)+1; fresh.g=g;
    if (requests.update(&g,&fresh)<0) { count(2); return 0; }
    struct event_t *e=boundary_event(3,g);
    return e ? emit_boundary(ctx,e) : 0;
}
int read_scope_exit(struct pt_regs *ctx) {
    count(3); u64 g=ctx->r14;
    struct request_context_t *active=current_request(g);
    if (!active) { count(2); return 0; }
    u64 execution=active->request_id;
    struct state_t *state=states.lookup(&execution);
    if (active->reads.pending || (state && state->depth)) count(2);
    struct event_t *e=boundary_event(4,g);
    if (e) emit_boundary(ctx,e);
    states.delete(&execution); requests.delete(&g);
    return 0;
}
'''
    require('current_tid_ptr' not in source and 'in_read_scope' not in source and
            'states.lookup(&tid)' not in source, 'Thread-keyed state survived migration adaptation')
    return source


def build(scenario, out):
    result=serial.build(scenario,out,source_generator=bpf_source)
    metadata=json.loads((out/'adapter.json').read_text())
    metadata.update(context_policy=boundary.POLICY.name,
                    execution_identity='host TGID filter + actual R14 + request generation',
                    observed_thread_identity='raw pid_tid retained; never rewritten',
                    scheduling_fixture='GOMAXPROCS=1; auxiliary goroutines park previous threads')
    common.save(out/'adapter.json',metadata)
    return result

record = partial(serial.record, source_generator=bpf_source, client_script=__file__)

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'client':
        client(Path(sys.argv[2]))
    else:
        raise SystemExit(common.main(default_scenario=SCENARIO, prefix='gin-migration-provenance',
            build_fn=build, record_fn=record, infer_fn=boundary.bind,
            evaluate_fn=boundary.evaluate, oracle_loader=oracle, required_tools=('go','objdump')))
