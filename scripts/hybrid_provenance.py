#!/usr/bin/env python3
"""Static CFG/def-use planning + selected uprobes for a bounded native subset.

build: inspect plans without root; run: actual BCC/eBPF capture on the host.
"""
import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import struct
import subprocess
import sys
import time
import zipfile

from hybrid_model import REGS, decode_function, infer, require, static_plan, validate_config

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def build(scenario, out, planner=None, source_generator=None, extra_flags=()):
    config = json.loads((scenario / 'config.json').read_text())
    validate_config(config)
    copied = out / 'sources'
    copied.mkdir()
    for name in ('config.json', 'main.c', 'operations.c', 'model.h'):
        shutil.copyfile(scenario / name, copied / name)
    assertions = ['#include <stddef.h>', '#include "model.h"']
    for region in ('input', 'output'):
        fields = config[region + '_fields']
        assertions.append('_Static_assert(sizeof(struct %s) == %d, "schema size mismatch");' % (region, len(fields) * 4))
        for index, field in enumerate(fields):
            assertions.append('_Static_assert(offsetof(struct %s, %s) == %d && sizeof(((struct %s *)0)->%s) == 4, "schema field mismatch");' % (region, field, index * 4, region, field))
    (copied / 'layout_check.c').write_text('\n'.join(assertions) + '\n')
    binary = out / 'hybrid-demo'
    command = ['gcc', '-O1', '-g', '-fPIE', '-pie', '-fno-if-conversion', '-fno-if-conversion2',
               '-fno-inline', '-fno-lto', '-fno-ipa-icf', '-fno-stack-protector',
               *extra_flags, '-o', str(binary), str(copied / 'main.c'), str(copied / 'operations.c'), str(copied / 'layout_check.c')]
    result = subprocess.run(command, capture_output=True, text=True)
    save(out / 'build.json', dict(command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
    result.check_returncode()
    asm = subprocess.check_output(['objdump', '-d', '-M', 'intel', '--no-show-raw-insn', str(binary)], text=True)
    (out / 'disassembly.txt').write_text(asm)
    symbols = {}
    nm = subprocess.check_output(['nm', '-S', '--defined-only', str(binary)], text=True)
    for line in nm.splitlines():
        words = line.split()
        if len(words) == 4 and words[2] in ('t', 'T'):
            symbols[words[3]] = int(words[0], 16), int(words[1], 16)
    plans = planner(asm, symbols, config) if planner else [static_plan(decode_function(f, asm, symbols), config) for f in config['functions']]
    save(out / 'probe-plan.json', plans)
    save(out / 'config.json', config)
    save(out / 'build-identity.json', {'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'gcc': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
        'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in copied.iterdir()}})
    (out / 'collector.bpf.c').write_text((source_generator or bpf_source)(plans, config))
    return binary, plans, config


def bpf_source(plans, config):
    source = r'''
#include <uapi/linux/ptrace.h>
struct state_t { u64 call, step, src, dst; u32 active, fid; };
struct event_t {
    u64 timestamp, pid_tid, call_id, sequence, src_addr, dst_addr, ip, flags;
    u64 regs[16];
    u32 function, offset, inputs[8], outputs[8];
    s32 source_error, destination_error;
};
BPF_HASH(states, u64, struct state_t, 64);
BPF_ARRAY(metrics, u64, 4);
BPF_PERF_OUTPUT(events);
static __always_inline void count(u32 k) {
    u64 *v = metrics.lookup(&k);
    if (v) __sync_fetch_and_add(v, 1);
}
static __always_inline int record(struct pt_regs *ctx, u32 fid, u32 offset, u32 is_ret) {
    count(3);
    u64 tid = bpf_get_current_pid_tgid();
    struct state_t zero = {}, *s = states.lookup_or_try_init(&tid, &zero);
    if (!s) { count(2); return 0; }
    if (offset == 0) {
        if (s->active) count(2);
        s->call += 1; s->step = 0; s->active = 1; s->fid = fid;
        s->src = PT_REGS_PARM2(ctx); s->dst = PT_REGS_PARM1(ctx);
    }
    if (!s->active || s->fid != fid) { count(2); return 0; }
    struct event_t e = {};
    e.timestamp = bpf_ktime_get_ns(); e.pid_tid = tid;
    e.call_id = s->call; e.sequence = s->step++;
    e.src_addr = s->src; e.dst_addr = s->dst;
    e.ip = PT_REGS_IP(ctx); e.flags = ctx->flags;
    e.function = fid; e.offset = offset;
    e.regs[0] = ctx->ax; e.regs[1] = ctx->bx; e.regs[2] = ctx->cx; e.regs[3] = ctx->dx;
    e.regs[4] = ctx->si; e.regs[5] = ctx->di; e.regs[6] = ctx->bp; e.regs[7] = ctx->sp;
    e.regs[8] = ctx->r8; e.regs[9] = ctx->r9; e.regs[10] = ctx->r10; e.regs[11] = ctx->r11;
    e.regs[12] = ctx->r12; e.regs[13] = ctx->r13; e.regs[14] = ctx->r14; e.regs[15] = ctx->r15;
    e.source_error = bpf_probe_read_user(e.inputs, INPUT_BYTES, (void *)e.src_addr);
    e.destination_error = bpf_probe_read_user(e.outputs, OUTPUT_BYTES, (void *)e.dst_addr);
    count(0);
    if (events.perf_submit(ctx, &e, sizeof(e)) < 0) count(1);
    if (is_ret) s->active = 0;
    return 0;
}
'''.replace('INPUT_BYTES', str(4 * len(config['input_fields']))).replace('OUTPUT_BYTES', str(4 * len(config['output_fields'])))
    for fid, plan in enumerate(plans):
        ins = {n['offset']: n for n in plan['instructions']}
        for off in plan['probe_offsets']:
            source += '\nint probe_%d_%d(struct pt_regs *ctx) { return record(ctx, %d, %d, %d); }\n' % (
                fid, off, fid, off, ins[off]['op'] == 'ret')
    return source


def wait_stopped(process, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
        if pid:
            if os.WIFSTOPPED(status):
                return os.WSTOPSIG(status)
            process.returncode = os.waitstatus_to_exitcode(status)
            raise RuntimeError('Target exited before attachment')
        time.sleep(0.01)
    raise RuntimeError('Target did not stop for attachment')


def runtime_metadata(process, binary, plans, out):
    proc = Path('/proc') / str(process.pid)
    maps = (proc / 'maps').read_text()
    (out / 'target-maps.txt').write_text(maps)
    save(out / 'target-process.json', {'subprocess_pid': process.pid,
        'target_status': [l for l in (proc / 'status').read_text().splitlines() if l.split(':')[0] in ('Name', 'Pid', 'Tgid', 'NSpid', 'NStgid')],
        'target_pid_namespace': os.readlink(proc / 'ns/pid'), 'executable': os.readlink(proc / 'exe')})
    # This runner explicitly builds PIE with the first PT_LOAD at vaddr/offset 0.
    # Refuse other layouts rather than guessing a relocation base.
    elf = binary.read_bytes()
    require(elf[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', elf, 16)[0] == 3, 'Expected little-endian ELF64 PIE')
    phoff = struct.unpack_from('<Q', elf, 32)[0]
    entsize, number = struct.unpack_from('<HH', elf, 54)
    segments = [struct.unpack_from('<IIQQQQQQ', elf, phoff + i * entsize) for i in range(number)]
    require(any(s[0] == 1 and s[2] == 0 and s[3] == 0 for s in segments), 'Unsupported PIE segment layout')
    starts = []
    for line in maps.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and parts[5] == str(binary) and int(parts[2], 16) == 0:
            starts.append(int(parts[0].split('-')[0], 16))
    require(len(starts) == 1, 'Cannot uniquely resolve executable mapping')
    bases = {p['function']: starts[0] + p['symbol_address'] for p in plans}
    save(out / 'runtime-bases.json', bases)
    return bases


def attach_probes(bpf, binary, plans, pid):
    require(pid > 0, 'Global probe attachment is forbidden')
    attached = []
    for fid, p in enumerate(plans):
        for off in p['probe_offsets']:
            handler = 'probe_%d_%d' % (fid, off)
            bpf.attach_uprobe(name=str(binary), sym=p['function'], sym_off=off, fn_name=handler, pid=pid)
            attached.append(dict(function=p['function'], offset=off, pid=pid, handler=handler))
    return attached


def record_bpf(binary, plans, config, out, source_generator=None):
    import bcc
    process = bpf = None
    events, bases = [], {}
    stats = {'backend': 'ebpf', 'lost_events': 0, 'submit_errors': None, 'state_errors': None,
             'attempted_events': None, 'raw_probe_hits': None, 'process_returncode': None,
             'bcc_version': getattr(bcc, '__version__', 'unknown')}
    try:
        with (out / 'program.stdout.jsonl').open('w') as stdout, (out / 'program.stderr.log').open('w') as stderr:
            process = subprocess.Popen([str(binary), '--wait'], stdout=stdout, stderr=stderr)
            wait_stopped(process)
            bases = runtime_metadata(process, binary, plans, out)
            bpf = bcc.BPF(text=(source_generator or bpf_source)(plans, config))
            attached = attach_probes(bpf, binary, plans, process.pid)
            save(out / 'attached-probes.json', attached)
            with (out / 'events.jsonl').open('w') as stream:
                def receive(cpu, data, size):
                    obj = bpf['events'].event(data)
                    event = {name: int(getattr(obj, name)) for name, _ in obj._fields_ if name not in ('regs', 'inputs', 'outputs', 'stack')}
                    event.update(regs=list(obj.regs), inputs=list(obj.inputs)[:len(config['input_fields'])],
                                 outputs=list(obj.outputs)[:len(config['output_fields'])])
                    if hasattr(obj, 'stack'):
                        event['stack'] = list(obj.stack)
                    events.append(event)
                    stream.write(json.dumps(event) + '\n'); stream.flush()
                def lost(cpu, n):
                    stats['lost_events'] += n
                bpf['events'].open_perf_buffer(receive, lost_cb=lost, page_cnt=64)
                process.send_signal(signal.SIGCONT)
                deadline = time.monotonic() + 20
                while process.poll() is None:
                    bpf.perf_buffer_poll(timeout=100)
                    if time.monotonic() > deadline:
                        raise RuntimeError('Target timed out')
                for _ in range(3):
                    bpf.perf_buffer_poll(timeout=100)
                os.fsync(stream.fileno())
            stats['process_returncode'] = process.returncode
    finally:
        if process is not None and process.poll() is None:
            process.kill(); process.wait()
        stats['received_events'] = len(events)
        stats['observed_kernel_tgids'] = sorted({e['pid_tid'] >> 32 for e in events})
        if bpf is not None:
            try:
                for i, key in enumerate(('attempted_events', 'submit_errors', 'state_errors', 'raw_probe_hits')):
                    stats[key] = int(bpf['metrics'][ctypes.c_int(i)].value)
            except Exception as exc:
                stats['statistics_error'] = str(exc)
            try:
                bpf.cleanup()
            except Exception as exc:
                stats['cleanup_error'] = str(exc)
        save(out / 'capture.json', stats)
    return events, stats, bases


def evaluate(inferred, oracle, stats, plans):
    rows = inferred['results']
    checks, stp, sfp, sfn, dtp, dfp, dfn = [], 0, 0, 0, 0, 0, 0
    by_call = {r['call_id']: r for r in rows}
    static_by_function = {p['function']: set(p['static_sources']) for p in plans}
    for truth in oracle:
        row = by_call.get(truth['sequence'], {})
        aligned = row.get('function') == truth['function']
        expected = set(truth['expected_sources'])
        dynamic = set(row.get('sources', [])) if aligned else set()
        static = static_by_function.get(truth['function'], set())
        stp += len(static & expected); sfp += len(static - expected); sfn += len(expected - static)
        dtp += len(dynamic & expected); dfp += len(dynamic - expected); dfn += len(expected - dynamic)
        passed = aligned and row.get('status') == 'resolved' and dynamic == expected and row.get('value') == truth['output'] == truth['expected_value']
        checks.append({'sequence': truth['sequence'], 'function': truth['function'], 'passed': passed,
                       'expected_sources': sorted(expected), 'observed_sources': sorted(dynamic)})
    expected_ids = {t['sequence'] for t in oracle}
    unexpected = [r for r in rows if r['call_id'] not in expected_ids]
    dfp += sum(len(r['sources']) for r in unexpected)
    clean = bool(stats.get('received_events')) and all(stats.get(k) == 0 for k in ('lost_events', 'submit_errors', 'state_errors', 'process_returncode'))
    clean = clean and stats.get('attempted_events') == stats.get('received_events')
    passed = bool(oracle) and len(rows) == len(oracle) and len(by_call) == len(rows) and len(expected_ids) == len(oracle) and not unexpected and not inferred['issues'] and clean and all(c['passed'] for c in checks)
    def metrics(tp, fp, fn):
        return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': tp / (tp + fp) if tp + fp else None,
                'recall': tp / (tp + fn) if tp + fn else None}
    return {'passed': passed, 'capture_clean': clean, 'checks': checks,
            'static_source_relations': metrics(stp, sfp, sfn), 'dynamic_source_relations': metrics(dtp, dfp, dfn),
            'resolved_calls': sum(r.get('status') == 'resolved' for r in rows),
            'expected_calls': len(oracle), 'inference_issues': len(inferred['issues']), 'unexpected_calls': len(unexpected),
            'scope': 'fixture-specific source relation accuracy; not statement-edge recall or microservice accuracy'}


def main(default_scenario=None, prefix='hybrid-provenance', build_fn=build, record_fn=record_bpf, infer_fn=infer):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'run'])
    parser.add_argument('--scenario', type=Path, default=default_scenario or ROOT / 'scenarios/hybrid-provenance')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    out = (args.out or ROOT / 'artifacts' / (prefix + '-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(2))).resolve()
    out.mkdir(parents=True, exist_ok=False); os.chmod(out, 0o700)
    report = {'status': 'failed', 'action': args.action, 'stage': 'build', 'kernel_ebpf_tested': False,
              'platform': platform.platform()}
    try:
        require(sys.platform == 'linux' and platform.machine() == 'x86_64', 'Linux x86-64 only')
        require(all(shutil.which(t) for t in ('gcc', 'objdump', 'nm')), 'Install gcc and binutils')
        binary, plans, config = build_fn(args.scenario.resolve(), out)
        if args.action == 'build':
            report.update(status='build_verified', stage='complete')
        else:
            report['stage'] = 'capture'
            require(os.geteuid() == 0, 'Run with sudo /usr/bin/python3; BCC must be installed')
            with (out / 'collector.log').open('w') as log:
                fd = os.dup(2)
                try:
                    sys.stderr.flush(); os.dup2(log.fileno(), 2)
                    events, stats, bases = record_fn(binary, plans, config, out)
                finally:
                    sys.stderr.flush(); os.dup2(fd, 2); os.close(fd)
            report['kernel_ebpf_tested'] = bool(stats.get('raw_probe_hits'))
            report['stage'] = 'inference'
            inferred = infer_fn(events, plans, config, bases)
            save(out / 'inferred.json', inferred)
            # Evaluation alone opens the independent harness oracle.
            oracle = [json.loads(l) for l in (out / 'program.stdout.jsonl').read_text().splitlines()]
            evaluation = evaluate(inferred, oracle, stats, plans)
            save(out / 'evaluation.json', evaluation)
            report.update(stage='complete', events=len(events), results=len(inferred['results']),
                          status='ebpf_checks_passed' if evaluation['passed'] else 'incomplete')
    except Exception as exc:
        report['error'] = '%s: %s' % (type(exc).__name__, exc)
        print(report['error'], file=sys.stderr)
    finally:
        save(out / 'result.json', report)
        bundle = out.with_suffix('.zip')
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(out.rglob('*')):
                if p.is_file():
                    archive.write(p, str(p.relative_to(out)))
        os.chmod(bundle, 0o600)
        if os.environ.get('SUDO_UID') and os.environ.get('SUDO_GID'):
            for p in [out, *out.rglob('*'), bundle]:
                os.chown(p, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
        print('RESULT BUNDLE: ' + str(bundle))
    return 0 if report['status'] in ('build_verified', 'ebpf_checks_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
