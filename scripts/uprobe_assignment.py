#!/usr/bin/env python3
"""Instruction-level eBPF assignment experiment: Linux x86-64, GCC, BCC.

This recognizes a deliberately small, verified native instruction subset.
It is not a general source-language tracer or a full dynamic taint engine.
"""
import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ('copy_secret', 'copy_public', 'transform_secret')
FIELDS = {0: 'secret', 4: 'public_value'}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def plan_function(name, disassembly):
    """Accept ONLY a complete load/[xor]/store/ret function, no hidden calls.

    The symbol chooses the region, not the source field. The source offset and
    transform are decoded from actual machine instructions at this build.
    """
    match = re.search(r'^([0-9a-f]+) <' + re.escape(name) + r'>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)',
                      disassembly, re.M | re.S)
    if not match:
        raise ValueError('Missing function symbol: ' + name)
    base, body = int(match[1], 16), match[2]
    instructions = []
    for line in body.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+(.+?)\s*$', line)
        if m:
            asm = ' '.join(m[2].split())
            instructions.append({'offset': int(m[1], 16) - base, 'asm': asm})
            if asm == 'ret':
                break
    # CET landing pads are not part of the data operation.
    if instructions and instructions[0]['asm'] == 'endbr64':
        instructions = instructions[1:]
    if len(instructions) not in (3, 4):
        raise ValueError('Unsupported instruction sequence in ' + name)
    load = re.fullmatch(r'mov eax,DWORD PTR \[rsi(?:\+(0x[0-9a-f]+))?\]', instructions[0]['asm'])
    if not load or instructions[-2]['asm'] != 'mov DWORD PTR [rdi],eax' or instructions[-1]['asm'] != 'ret':
        raise ValueError('Unsupported load/store ABI in ' + name)
    source_offset = int(load[1], 16) if load[1] else 0
    if source_offset not in FIELDS:
        raise ValueError('Source offset outside explicit input schema')
    mask = None
    if len(instructions) == 4:
        transform = re.fullmatch(r'xor eax,(0x[0-9a-f]+)', instructions[1]['asm'])
        if not transform:
            raise ValueError('Unsupported transform in ' + name)
        mask = int(transform[1], 16)
    return {'function': name, 'symbol_address': base, 'instructions': instructions,
            'source_offset': source_offset, 'source_field': FIELDS[source_offset],
            'destination_field': 'value', 'xor_mask': mask,
            'store_stage': len(instructions) - 2, 'post_store_stage': len(instructions) - 1}


def build(out):
    source = ROOT / 'scenarios/uprobe-assignment'
    binary = out / 'assignment-demo'
    command = ['gcc', '-O2', '-g', '-fno-lto', '-o', str(binary),
               str(source / 'main.c'), str(source / 'operations.c')]
    result = subprocess.run(command, capture_output=True, text=True)
    save(out / 'build.json', {'command': command, 'returncode': result.returncode,
                            'stdout': result.stdout, 'stderr': result.stderr})
    result.check_returncode()
    assembly = subprocess.check_output(['objdump', '-d', '-M', 'intel', '--no-show-raw-insn', str(binary)], text=True)
    (out / 'disassembly.txt').write_text(assembly)
    plans = [plan_function(name, assembly) for name in FUNCTIONS]
    save(out / 'probe-plan.json', plans)
    save(out / 'build-identity.json', {
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'gcc': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
        'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}})
    return binary, plans


def bpf_source(pid, plans):
    source = r'''
#include <uapi/linux/ptrace.h>
struct input_data { u32 secret; u32 public_value; };
struct event_t {
    u64 timestamp, pid_tid, call_id, src_addr, dst_addr, ip;
    u32 function, stage, secret, public_value, output, eax;
    s32 source_error, destination_error;
};
BPF_HASH(sequence, u64, u64, 16);
BPF_ARRAY(metrics, u64, 3);
BPF_PERF_OUTPUT(events);
static __always_inline void count(u32 index) {
    u64 *value = metrics.lookup(&index);
    if (value) __sync_fetch_and_add(value, 1);
}
static __always_inline int record(struct pt_regs *ctx, u32 function, u32 stage) {
    u64 tid = bpf_get_current_pid_tgid();
    if ((tid >> 32) != TARGET_PID) return 0;
    u64 zero = 0, *seq = sequence.lookup_or_try_init(&tid, &zero);
    if (!seq) { count(2); return 0; }
    if (stage == 0) *seq += 1;
    struct event_t e = {};
    struct input_data data = {};
    e.timestamp = bpf_ktime_get_ns(); e.pid_tid = tid; e.call_id = *seq;
    e.function = function; e.stage = stage;
    e.src_addr = PT_REGS_PARM2(ctx); e.dst_addr = PT_REGS_PARM1(ctx);
    e.ip = PT_REGS_IP(ctx); e.eax = (u32)PT_REGS_RC(ctx);
    e.source_error = bpf_probe_read_user(&data, sizeof(data), (void *)e.src_addr);
    e.secret = data.secret; e.public_value = data.public_value;
    e.destination_error = bpf_probe_read_user(&e.output, sizeof(e.output), (void *)e.dst_addr);
    count(0);
    if (events.perf_submit(ctx, &e, sizeof(e)) < 0) count(1);
    return 0;
}
'''.replace('TARGET_PID', str(pid))
    for fid, plan in enumerate(plans):
        for stage in range(len(plan['instructions'])):
            source += '\nint probe_%d_%d(struct pt_regs *ctx) { return record(ctx, %d, %d); }\n' % (fid, stage, fid, stage)
    return source


def infer(events, plans):
    """Use only probe observations + verified instruction/schema metadata.

    Program stdout/oracle is deliberately absent from this interface.
    """
    groups = {}
    for e in events:
        groups.setdefault((e['pid_tid'], e['call_id']), []).append(e)
    results, issues = [], []
    for (tid, call), rows in sorted(groups.items()):
        rows.sort(key=lambda e: e['timestamp'])
        try:
            fid = rows[0]['function']
            if fid not in range(len(plans)):
                raise ValueError('Unknown function')
            p = plans[fid]
            if [e['stage'] for e in rows] != list(range(len(p['instructions']))):
                raise ValueError('Missing, duplicate or out-of-order instruction events')
            if any(e['function'] != fid or e['source_error'] or e['destination_error'] for e in rows):
                raise ValueError('Mixed function or failed memory read')
            if len({(e['src_addr'], e['dst_addr']) for e in rows}) != 1:
                raise ValueError('Pointers changed across the verified instruction region')
            first, loaded, before, after = rows[0], rows[1], rows[p['store_stage']], rows[-1]
            field = p['source_field']
            source = first[field]
            expected = source if p['xor_mask'] is None else source ^ p['xor_mask']
            if loaded['eax'] != source or before['eax'] != expected or after['output'] != before['eax']:
                raise ValueError('Observed registers/memory contradict instruction semantics')
            if any(e['output'] != first['output'] for e in rows[:-1]):
                raise ValueError('Destination changed before selected store')
            results.append({'pid_tid': tid, 'call_id': call, 'function': p['function'],
                'source_field': field, 'source_address': first['src_addr'] + p['source_offset'],
                'destination_field': 'value', 'destination_address': first['dst_addr'],
                'source_value': source, 'old_value': before['output'], 'new_value': after['output'],
                'transform': 'identity' if p['xor_mask'] is None else 'xor 0x%x' % p['xor_mask'],
                'dependency': ['input.' + field, 'eax', 'output.value'],
                'evidence_stages': [e['stage'] for e in rows],
                'basis': 'observed instruction execution plus verified load/store semantics'})
        except (KeyError, ValueError) as exc:
            issues.append({'pid_tid': tid, 'call_id': call, 'error': str(exc)})
    return {'assignments': results, 'issues': issues,
            'scope': 'one thread; selected straight-line 32-bit load/[xor]/store; explicit struct schema',
            'general_taint_tracking': False, 'oracle_used_for_inference': False}


def evaluate(inferred, oracle, stats):
    rows = inferred['assignments']
    checks = []
    for i, expected in enumerate(oracle):
        observed = rows[i] if i < len(rows) else {}
        checks.append({'sequence': expected['sequence'], 'function': expected['function'],
            'passed': observed.get('function') == expected['function']
                      and observed.get('source_field') == expected['expected_field']
                      and observed.get('new_value') == expected['output']})
    clean = (stats.get('lost_events') == 0 and stats.get('submit_errors') == 0
             and stats.get('state_errors') == 0 and stats.get('attempted_events') == stats.get('received_events')
             and stats.get('process_returncode') == 0)
    passed = bool(checks) and len(rows) == len(oracle) and all(c['passed'] for c in checks) and clean and not inferred['issues']
    return {'status': 'selected_assignment_checks_passed' if passed else 'incomplete',
            'checks': checks, 'capture_clean': clean,
            'meaning': 'correctness on six controlled assignments only; not microservice lineage accuracy'}


def record(binary, plans, out):
    from bcc import BPF
    process = bpf = None
    events = []
    stats = {'lost_events': 0, 'received_events': 0, 'attempted_events': None,
             'submit_errors': None, 'state_errors': None, 'process_returncode': None}
    try:
        with (out / 'program.stdout.jsonl').open('w') as stdout, (out / 'program.stderr.log').open('w') as stderr:
            process = subprocess.Popen([str(binary), '--wait'], stdout=stdout, stderr=stderr)
            deadline = time.monotonic() + 10
            while True:
                found, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
                if found:
                    if not os.WIFSTOPPED(status):
                        process.returncode = os.waitstatus_to_exitcode(status)
                        raise RuntimeError('Demo exited before probe attachment')
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('Demo did not stop for attachment')
                time.sleep(0.02)
            source = bpf_source(process.pid, plans)
            (out / 'collector.bpf.c').write_text(source)
            bpf = BPF(text=source)
            for fid, plan in enumerate(plans):
                for stage, instruction in enumerate(plan['instructions']):
                    bpf.attach_uprobe(name=str(binary), sym=plan['function'],
                        sym_off=instruction['offset'], fn_name='probe_%d_%d' % (fid, stage), pid=process.pid)
            with (out / 'events.jsonl').open('w') as stream:
                def receive(cpu, data, size):
                    obj = bpf['events'].event(data)
                    event = {name: int(getattr(obj, name)) for name, _ in obj._fields_}
                    events.append(event)
                    stream.write(json.dumps(event) + '\n'); stream.flush()
                def lost(cpu, count):
                    stats['lost_events'] += count
                bpf['events'].open_perf_buffer(receive, page_cnt=64, lost_cb=lost)
                process.send_signal(signal.SIGCONT)
                deadline = time.monotonic() + 15
                while process.poll() is None:
                    bpf.perf_buffer_poll(timeout=100)
                    if time.monotonic() > deadline:
                        raise RuntimeError('Demo execution timed out')
                for _ in range(3):
                    bpf.perf_buffer_poll(timeout=100)
                os.fsync(stream.fileno())
                stats['process_returncode'] = process.returncode
    finally:
        if process is not None and process.poll() is None:
            process.kill(); process.wait()
        stats['received_events'] = len(events)
        if bpf is not None:
            try:
                for index, name in enumerate(('attempted_events', 'submit_errors', 'state_errors')):
                    stats[name] = int(bpf['metrics'][ctypes.c_int(index)].value)
            except Exception as exc:
                stats['statistics_error'] = str(exc)
            try:
                bpf.cleanup()
            except Exception as exc:
                stats['cleanup_error'] = str(exc)
        save(out / 'capture.json', stats)
    return events, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'run'])
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    out = (args.out or ROOT / 'artifacts' / ('uprobe-assignment-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S')
           + '-' + secrets.token_hex(2))).resolve()
    out.mkdir(parents=True, exist_ok=False); os.chmod(out, 0o700)
    report = {'status': 'failed', 'stage': 'build', 'action': args.action,
              'platform': platform.platform(), 'scope': 'native x86-64 controlled assignment experiment'}
    try:
        if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'amd64'):
            raise RuntimeError('This instruction decoder supports Linux x86-64 only')
        if not all(shutil.which(tool) for tool in ('gcc', 'objdump')):
            raise RuntimeError('Install gcc and binutils')
        binary, plans = build(out)
        if args.action == 'build':
            report.update(status='build_verified', stage='complete', kernel_probes_tested=False)
        else:
            if os.geteuid() != 0:
                raise RuntimeError('Run with sudo /usr/bin/python3; BCC must be installed')
            report['stage'] = 'uprobe-capture'
            # BCC's compiler also writes to C stderr; redirect its descriptor.
            with (out / 'collector.log').open('w') as log:
                stderr_fd = os.dup(2)
                try:
                    sys.stderr.flush(); os.dup2(log.fileno(), 2)
                    events, stats = record(binary, plans, out)
                finally:
                    sys.stderr.flush(); os.dup2(stderr_fd, 2); os.close(stderr_fd)
            report['stage'] = 'inference'
            inferred = infer(events, plans)
            save(out / 'assignments.json', inferred)
            # Only the evaluator reads fixture stdout, after inference is complete.
            oracle = [json.loads(line) for line in (out / 'program.stdout.jsonl').read_text().splitlines()]
            evaluation = evaluate(inferred, oracle, stats)
            save(out / 'evaluation.json', evaluation)
            report.update(status=evaluation['status'], stage='complete', events=len(events),
                          assignments=len(inferred['assignments']), kernel_probes_tested=True)
    except Exception as exc:
        report['error'] = '%s: %s' % (type(exc).__name__, exc)
        print(report['error'], file=sys.stderr)
    finally:
        save(out / 'result.json', report)
        bundle = out.with_suffix('.zip')
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(out.rglob('*')):
                if path.is_file():
                    archive.write(path, str(path.relative_to(out)))
        os.chmod(bundle, 0o600)
        if os.environ.get('SUDO_UID') and os.environ.get('SUDO_GID'):
            for path in [out, *out.rglob('*'), bundle]:
                os.chown(path, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
        print('RESULT BUNDLE: ' + str(bundle), flush=True)
    return 0 if report['status'] in ('build_verified', 'selected_assignment_checks_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
