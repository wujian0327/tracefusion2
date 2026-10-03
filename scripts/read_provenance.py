#!/usr/bin/env python3
"""C real-file-read boundary pilot, reusing the loop/call dependency engine."""
from functools import partial
import os
from pathlib import Path
import re
import stat

import hybrid_provenance as common
import interproc_provenance as collector
import loop_calls_provenance as core
import read_boundaries as boundaries
from hybrid_model import require


def bpf_source(plans, config):
    boundary = config['read_boundary']
    require(boundary['api'] == 'pread64' and boundary['maximum_bytes'] == 32, 'Unsupported read contract')
    source = collector.bpf_source(plans,config)
    source = source.replace('struct event_t {', '''struct event_t {
    u64 observation_sequence, io_id, buffer_addr, requested;
    s64 file_offset, returned;
    u32 kind; s32 fd, read_error;
    u8 read_data[32];''')
    source = source.replace('BPF_PERF_OUTPUT(events);', '''BPF_PERF_OUTPUT(events);
struct read_state_t { u64 io_id, buffer, count; s64 offset; s32 fd; u32 pending; };
BPF_ARRAY(read_state, struct read_state_t, 1);
/* Seed the host-kernel TID with a PID-scoped application uprobe. The runner
 * PID may be in a nested namespace and must not filter kernel tracepoints. */
BPF_ARRAY(read_context, u64, 1);
BPF_ARRAY(observation_clock, u64, 1);
static __always_inline u64 next_observation(void) {
    u32 key = 0; u64 *seq = observation_clock.lookup(&key);
    if (!seq) return 0;
    /* Only the seeded thread can emit within this scope. */
    u64 previous = *seq; *seq = previous + 1; return previous;
}''')
    source = source.replace('    u64 tid = bpf_get_current_pid_tgid();', '''    u64 tid = bpf_get_current_pid_tgid();
    u32 scope_key = 0; u64 *scope_tid = read_context.lookup(&scope_key);
    if (!scope_tid || *scope_tid != tid) { count(2); return 0; }''')
    source = source.replace('    count(0);', '    e->observation_sequence = next_observation();\n    count(0);')
    source += r'''
static __always_inline int in_read_scope(void) {
    u32 key = 0; u64 *tid = read_context.lookup(&key);
    return tid && *tid == bpf_get_current_pid_tgid();
}
static __always_inline struct event_t *boundary_event(u32 kind) {
    u32 key = 0; struct event_t *e = scratch.lookup(&key);
    if (!e) { count(2); return 0; }
    __builtin_memset(e, 0, sizeof(*e));
    e->kind = kind; e->timestamp = bpf_ktime_get_ns();
    e->pid_tid = bpf_get_current_pid_tgid();
    e->observation_sequence = next_observation();
    return e;
}
static __always_inline int emit_boundary(void *ctx, struct event_t *e) {
    count(0);
    int submitted = events.perf_submit(ctx, e, sizeof(*e));
    if (submitted < 0) {
        count(1); s32 error = -submitted; u64 zero_errors = 0;
        u64 *errors = submit_errnos.lookup_or_try_init(&error, &zero_errors);
        if (errors) __sync_fetch_and_add(errors, 1);
    }
    return 0;
}
int read_scope_enter(struct pt_regs *ctx) {
    count(3); u32 key = 0; u64 *tid = read_context.lookup(&key);
    if (!tid || *tid) { count(2); return 0; }
    *tid = bpf_get_current_pid_tgid();
    struct event_t *e = boundary_event(3);
    return e ? emit_boundary(ctx,e) : 0;
}
int read_scope_exit(struct pt_regs *ctx) {
    count(3); u32 key = 0; u64 *tid = read_context.lookup(&key);
    if (!tid || *tid != bpf_get_current_pid_tgid()) { count(2); return 0; }
    struct event_t *e = boundary_event(4);
    if (e) emit_boundary(ctx,e);
    *tid = 0;
    return 0;
}
TRACEPOINT_PROBE(syscalls, sys_enter_pread64) {
    if (!in_read_scope()) return 0;
    count(3); u32 key = 0; struct read_state_t *s = read_state.lookup(&key);
    if (!s || s->pending) { count(2); return 0; }
    s->io_id++; s->pending = 1; s->fd = args->fd;
    s->buffer = (u64)args->buf; s->count = args->count; s->offset = args->pos;
    struct event_t *e = boundary_event(1);
    if (!e) return 0;
    e->io_id = s->io_id; e->fd = s->fd; e->buffer_addr = s->buffer;
    e->requested = s->count; e->file_offset = s->offset;
    return emit_boundary(args,e);
}
TRACEPOINT_PROBE(syscalls, sys_exit_pread64) {
    if (!in_read_scope()) return 0;
    count(3); u32 key = 0; struct read_state_t *s = read_state.lookup(&key);
    if (!s || !s->pending) { count(2); return 0; }
    s->pending = 0;
    struct event_t *e = boundary_event(2);
    if (!e) return 0;
    e->io_id = s->io_id; e->fd = s->fd; e->buffer_addr = s->buffer;
    e->requested = s->count; e->file_offset = s->offset; e->returned = args->ret;
    if (args->ret > 0 && args->ret <= 32) {
        u32 size = args->ret;
        e->read_error = bpf_probe_read_user(e->read_data, size, (void *)s->buffer);
    } else if (args->ret > 32) e->read_error = -1;
    return emit_boundary(args,e);
}
/* Snapshot identities are invalid once a descriptor can close or be replaced.
 * Reject even failed attempts, rather than guessing descriptor generations. */
static __always_inline int reject_lifecycle(void *ctx) {
    if (!in_read_scope()) return 0;
    count(3); struct event_t *e = boundary_event(5);
    return e ? emit_boundary(ctx,e) : 0;
}
TRACEPOINT_PROBE(syscalls, sys_enter_close) { return reject_lifecycle(args); }
TRACEPOINT_PROBE(syscalls, sys_enter_dup2) { return reject_lifecycle(args); }
TRACEPOINT_PROBE(syscalls, sys_enter_dup3) { return reject_lifecycle(args); }
'''
    return source


def plan_program(assembly,symbols,config):
    require(config.get('adapter','c-sysv-u32') == 'c-sysv-u32', 'First read runner is C only')
    name = config['read_boundary']['scope_function']
    require(re.fullmatch(r'[A-Za-z_]\w*',name) and name in symbols and name not in config['functions'], 'Invalid workload scope symbol')
    return core.plan_program(assembly,symbols,config)


build = partial(common.build,planner=plan_program,source_generator=bpf_source,
                extra_flags=('-fno-optimize-sibling-calls','-fno-ipa-ra'))


def snapshot_files(pid, proc_root=Path('/proc')):
    files = {}
    for fd in (proc_root / str(pid) / 'fd').iterdir():
        if int(fd.name) < 3: continue
        info = fd.stat()
        if not stat.S_ISREG(info.st_mode): continue
        metadata = (fd.parent.parent/'fdinfo'/fd.name).read_text()
        flags = int(next(line.split()[1] for line in metadata.splitlines() if line.startswith('flags:')),8)
        files[fd.name] = dict(fd=int(fd.name),path=os.readlink(fd),device=info.st_dev,inode=info.st_ino,
                              size=info.st_size,regular=True,access_mode=flags & os.O_ACCMODE)
    return files


def record(binary,plans,config,out):
    manifest = {}
    def setup(bpf,process,binary,plans,config,out):
        manifest.update(snapshot_files(process.pid))
        require(manifest, 'No preopened regular file descriptors')
        common.save(out/'read-files.json',manifest)
        name = config['read_boundary']['scope_function']
        bpf.attach_uprobe(name=str(binary),sym=name,fn_name='read_scope_enter',pid=process.pid)
        bpf.attach_uretprobe(name=str(binary),sym=name,fn_name='read_scope_exit',pid=process.pid)
        common.save(out/'read-boundary-attachments.json',dict(scope_function=name,pid=process.pid,
            entry='read_scope_enter',return_probe='read_scope_exit',
            tracepoints=['sys_enter_pread64','sys_exit_pread64','sys_enter_close','sys_enter_dup2','sys_enter_dup3'],
            filter='kernel pid_tid learned at PID-scoped workload entry; single-thread scope'))
    events,stats,bases = common.record_bpf(binary,plans,config,out,source_generator=bpf_source,setup_fn=setup)
    runtime = dict(functions=bases,read_files=manifest)
    common.save(out/'runtime-bases.json',runtime)
    return events,stats,runtime


if __name__ == '__main__':
    raise SystemExit(common.main(default_scenario=common.ROOT/'scenarios/read-provenance',prefix='read-provenance',
        build_fn=build,record_fn=record,infer_fn=boundaries.bind,evaluate_fn=boundaries.evaluate))
