#!/usr/bin/env python3
"""C JSON stdout pilot: explicit u32 serialization summary + observed write result."""
from functools import partial
import json
import os
from pathlib import Path
import stat

import read_provenance as read
import json_output_boundaries as boundary
from hybrid_model import require


def bpf_source(plans,config):
    spec=config['json_output']
    require(config.get('adapter','c-sysv-u32')=='c-sysv-u32','C JSON collector only')
    require(spec==dict(serializer='format_json',model='json-u32-value-v1',capacity=32,fd=1),'Unsupported JSON contract')
    source=read.bpf_source(plans,config)
    source+=r'''
/* A bounded serializer SUMMARY, not an instruction trace of snprintf. */
struct format_state_t { u64 id, input, buffer; u32 value, pending; s32 error; };
struct write_state_t { u64 id, buffer, count; s32 fd; u32 pending; };
BPF_ARRAY(format_state, struct format_state_t, 1);
BPF_ARRAY(write_state, struct write_state_t, 1);
int json_format_enter(struct pt_regs *ctx) {
    if (!in_read_scope()) return 0;
    count(3); u32 key=0; struct format_state_t *s=format_state.lookup(&key);
    if (!s || s->pending) { count(2); return 0; }
    s->id++; s->pending=1; s->buffer=ctx->di; s->input=ctx->si;
    s->error=bpf_probe_read_user(&s->value,sizeof(s->value),(void *)s->input);
    struct event_t *e=boundary_event(6); if (!e) return 0;
    e->io_id=s->id; e->src_addr=s->input; e->buffer_addr=s->buffer;
    e->outputs[0]=s->value; e->source_error=s->error; e->requested=32;
    return emit_boundary(ctx,e);
}
int json_format_exit(struct pt_regs *ctx) {
    if (!in_read_scope()) return 0;
    count(3); u32 key=0; struct format_state_t *s=format_state.lookup(&key);
    if (!s || !s->pending) { count(2); return 0; }
    s->pending=0;
    struct event_t *e=boundary_event(7); if (!e) return 0;
    e->io_id=s->id; e->src_addr=s->input; e->buffer_addr=s->buffer;
    e->outputs[0]=s->value; e->source_error=s->error; e->requested=32;
    e->returned=(s32)ctx->ax;
    if (e->returned>=0 && e->returned<32) {
        u32 size=e->returned+1;
        e->read_error=bpf_probe_read_user(e->read_data,size,(void *)s->buffer);
    } else e->read_error=-1;
    return emit_boundary(ctx,e);
}
TRACEPOINT_PROBE(syscalls, sys_enter_write) {
    if (!in_read_scope()) return 0;
    count(3); u32 key=0; struct write_state_t *s=write_state.lookup(&key);
    if (!s || s->pending) { count(2); return 0; }
    s->id++; s->pending=1; s->fd=args->fd; s->buffer=(u64)args->buf; s->count=args->count;
    struct event_t *e=boundary_event(8); if (!e) return 0;
    e->io_id=s->id; e->fd=s->fd; e->buffer_addr=s->buffer; e->requested=s->count;
    if (s->count>0 && s->count<=32) {
        u32 size=s->count;
        e->read_error=bpf_probe_read_user(e->read_data,size,(void *)s->buffer);
    } else e->read_error=-1;
    return emit_boundary(args,e);
}
TRACEPOINT_PROBE(syscalls, sys_exit_write) {
    if (!in_read_scope()) return 0;
    count(3); u32 key=0; struct write_state_t *s=write_state.lookup(&key);
    if (!s || !s->pending) { count(2); return 0; }
    s->pending=0;
    struct event_t *e=boundary_event(9); if (!e) return 0;
    e->io_id=s->id; e->fd=s->fd; e->buffer_addr=s->buffer; e->requested=s->count; e->returned=args->ret;
    return emit_boundary(args,e);
}
'''
    return source


def plan_program(assembly,symbols,config):
    require(config['json_output']['serializer'] in symbols,'Missing serializer boundary')
    require(config['json_output']['serializer'] not in config['functions'],'Serializer must use the explicit summary')
    return read.plan_program(assembly,symbols,config)


build=partial(read.common.build,planner=plan_program,source_generator=bpf_source,
              extra_flags=('-fno-optimize-sibling-calls','-fno-ipa-ra'))


def attach_scope(bpf,process,binary,plans,config,out):
    scope=config['read_boundary']['scope_function'];serializer=config['json_output']['serializer']
    attachments=[]
    for symbol,enter,exit in ((scope,'read_scope_enter','read_scope_exit'),(serializer,'json_format_enter','json_format_exit')):
        bpf.attach_uprobe(name=str(binary),sym=symbol,fn_name=enter,pid=process.pid)
        bpf.attach_uretprobe(name=str(binary),sym=symbol,fn_name=exit,pid=process.pid)
        attachments.append(dict(symbol=symbol,entry=enter,return_probe=exit,pid=process.pid))
    read.common.save(out/'json-boundary-attachments.json',dict(uprobes=attachments,
        tracepoints=['sys_enter_pread64','sys_exit_pread64','sys_enter_write','sys_exit_write','sys_enter_close','sys_enter_dup2','sys_enter_dup3']))
    fd=Path('/proc')/str(process.pid)/'fd'/'1';info=fd.stat()
    target=(out/'program.stdout.jsonl').stat()
    require(stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino)==(target.st_dev,target.st_ino),'stdout is not the capture artifact')
    read.common.save(out/'output-fd.json',dict(fd=1,path=os.readlink(fd),device=info.st_dev,inode=info.st_ino,
        meaning='Successful write acceptance by stdout redirected to this file; no network delivery claim'))


record=partial(read.record,source_generator=bpf_source,scope_attacher=attach_scope)


def load_oracle(out):
    # Only evaluation reads this; stdout is exclusively the business JSON.
    oracle=json.loads((out/'program.stderr.log').read_text())
    read.common.save(out/'oracle.json',oracle)
    return dict(**oracle,stdout_bytes=list((out/'program.stdout.jsonl').read_bytes()))


if __name__=='__main__':
    raise SystemExit(read.common.main(default_scenario=read.common.ROOT/'scenarios/json-output-provenance',
        prefix='json-output-provenance',build_fn=build,record_fn=record,infer_fn=boundary.bind,
        evaluate_fn=boundary.evaluate,oracle_loader=load_oracle))
