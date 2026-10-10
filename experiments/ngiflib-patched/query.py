"""Configured GetGifWord boundary replay. Does not import GIF reference truth."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from c_bit_machine import Machine, Value, value, EMPTY, UNKNOWN, REGS, decode, check
from elftools.elf.elffile import ELFFile

CALLEE_SAVED = ['rbx','rbp','r12','r13','r14','r15','rsp']


def plan(binary, source, out):
    data = binary.read_bytes()
    elf = ELFFile(io.BytesIO(data))
    check(elf.elfclass == 64 and elf.little_endian and elf['e_machine'] == 'EM_X86_64', 'Unsupported ELF ABI')
    names = ['GetGifWord','GetByte','GetByteStr','DecodeGifImg']
    syms = {s.name: dict(address=s['st_value'], size=s['st_size'])
            for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name in names}
    check(set(syms) == set(names) and all(s['size'] for s in syms.values()), 'Missing configured function')
    start, size = syms['GetGifWord'].values()
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and
                s['p_vaddr'] <= start and start+size <= s['p_vaddr']+s['p_filesz']]
    check(len(segments) == 1, 'Invalid function segment')
    offset = segments[0]['p_offset']+start-segments[0]['p_vaddr']
    rows = decode(data[offset:offset+size],start)
    helpers = {syms[n]['address']: n for n in ('GetByte','GetByteStr')}
    check(all(r['args'][0]['value'] in helpers for r in rows.values() if r['op'] == 'call'), 'Unconfigured call')
    # Compile a layout probe against the unmodified upstream header. This is
    # explicitly configured C type information, not automatic type recovery.
    fields = {'ngiflib_decode_context':['srcbyte','lbyte','max','restbyte','nbbit','restbits','byte_buffer'],
              'ngiflib_img':['parent','palette','width','height'],
              'ngiflib_gif':['input','palette','frbuff','log','width','height','imgbits','mode']}
    lines = ['#include <stdio.h>','#include <stddef.h>','#include "ngiflib.h"','int main(void) {']
    for typ, members in fields.items():
        lines.append(f'printf("{typ} size %zu\\n", sizeof(struct {typ}));')
        for member in members:
            lines.append(f'printf("{typ} {member} %zu\\n", offsetof(struct {typ}, {member}));')
    lines.append('return 0; }')
    probe = out/'layout.c'; probe.write_text('\n'.join(lines)+'\n')
    subprocess.run(['gcc','-I',str(source),str(probe),'-o',str(out/'layout')],check=True,capture_output=True)
    text = subprocess.check_output([str(out/'layout')],text=True)
    layout = {}
    for line in text.splitlines():
        typ, member, off = line.split()
        layout.setdefault(typ,{})[member] = int(off)
    check(layout['ngiflib_decode_context']['byte_buffer']+256 <= layout['ngiflib_decode_context']['size'], 'Buffer layout')
    check(elf.has_dwarf_info(), 'ELF debug types required for configured ABI verification')
    verified = set()
    for cu in elf.get_dwarf_info().iter_CUs():
        for die in cu.iter_DIEs():
            attr = die.attributes.get('DW_AT_name')
            if die.tag != 'DW_TAG_structure_type' or attr is None:
                continue
            name = attr.value.decode()
            if name not in fields or 'DW_AT_byte_size' not in die.attributes:
                continue
            actual = {'size':die.attributes['DW_AT_byte_size'].value}
            for child in die.iter_children():
                member = child.attributes.get('DW_AT_name')
                off = child.attributes.get('DW_AT_data_member_location')
                if member is not None and off is not None and member.value.decode() in fields[name]:
                    check(type(off.value) is int, 'Nonconstant DWARF member offset')
                    actual[member.value.decode()] = off.value
            check(actual == layout[name], 'Header layout differs from target ELF DWARF: '+name)
            verified.add(name)
    check(verified == set(fields), 'Missing required ELF type layouts')
    result = dict(binary_sha256=hashlib.sha256(data).hexdigest(), symbols=syms, instructions=list(rows.values()),
                  layout=layout, layout_verified_against_elf_dwarf=True, max_steps_per_query=1024, abi='SysV AMD64',
                  source='successful GetByteStr buffer fills within GetGifWord, identified by input offset and write version',
                  target='GetGifWord return AX, each invocation',
                  semantics='explicit bit routing, projected to input byte identity; metadata fixed; arithmetic conservative',
                  strategy='boundary_replay', manual_runtime_contract=True)
    return result


def infer(plan, trace, file_bytes):
    check(trace['binary_sha256'] == plan['binary_sha256'], 'ELF identity mismatch')
    check(trace['complete'] and not trace.get('errors'), 'Incomplete/error capture')
    check(trace['input_sha256'] == hashlib.sha256(file_bytes).hexdigest(), 'Input identity mismatch')
    # This implementation currently consumes only an explicitly synthetic,
    # checked trace schema. A native collector must qualify its own transport.
    check(trace['backend'] == 'unicorn-original-decoder-v1', 'Unqualified capture backend')
    check(trace['decoder_return'] == 0 and trace['records'], 'Decoder did not complete')
    check(len(trace['records']) <= 131072, 'Query budget exceeded')
    rows = {r['address']:r for r in plan['instructions']}
    syms, layout = plan['symbols'], plan['layout']
    ctx_layout = layout['ngiflib_decode_context']
    helpers = {syms[n]['address']: n for n in ('GetByte','GetByteStr')}
    prior = None
    saved = {}
    results = []
    writes = []
    refill = 0
    file_cursor = None
    identity = None
    for sequence, record in enumerate(trace['records'],1):
        check(record['sequence'] == sequence, 'Missing/reordered invocation')
        registers = record['entry']['registers']
        ctx = registers['rsi']; img = registers['rdi']; sp = registers['rsp']
        check(record['context_pointer'] == ctx and record['image_pointer'] == img, 'Object binding mismatch')
        observed = bytes.fromhex(record['entry']['context'])
        check(len(observed) == ctx_layout['size'], 'Short context snapshot')
        parent = record['parent_pointer']
        if identity is None:
            identity = ctx,img,parent,sp
        check(identity == (ctx,img,parent,sp), 'Context/image/frame identity changed')
        m = Machine(registers)
        m.region(ctx,len(observed)); m.seed(ctx,observed,unknown=True)
        m.region(img,layout['ngiflib_img']['size'])
        m.store(img+layout['ngiflib_img']['parent'],value(parent,64))
        m.region(sp-4096,4096+8)
        m.store(sp,value(record['return_pc'],64))
        for r in ('rdi','rsi','rsp'):
            m.reg[r] = value(registers[r],64)
        # Pixel output state is outside this query. Caller-supplied code width
        # and mask are declared metadata, not inferred taint-free data.
        nb = observed[ctx_layout['nbbit']]
        mask = int.from_bytes(observed[ctx_layout['max']:ctx_layout['max']+2],'little')
        check(3 <= nb <= 12 and mask == (1 << nb)-1, 'Invalid width/mask contract')
        for field,size in [('nbbit',1),('max',2)]:
            off = ctx_layout[field]
            m.seed(ctx+off,observed[off:off+size])
        state_fields = [('srcbyte',8),('lbyte',2),('restbyte',1),('restbits',1),('byte_buffer',256)]
        if prior is None:
            for field,size in [('lbyte',2),('restbyte',1),('restbits',1)]:
                off = ctx_layout[field]
                check(observed[off:off+size] == bytes(size), 'Nonzero initial residual state')
                m.seed(ctx+off,bytes(size))
            # srcbyte and byte_buffer are intentionally unknown until a fill.
        else:
            for field,size in state_fields:
                off = ctx_layout[field]
                check(observed[off:off+size] == prior[off:off+size], 'Cross-call state changed outside query')
                for i in range(size):
                    m.mem[ctx+off+i] = saved[off+i]
        calls = iter(record['calls'])
        pc = syms['GetGifWord']['address']
        call_count = 0
        for _ in range(plan['max_steps_per_query']):
            check(pc in rows, 'Execution leaves configured function')
            row = rows[pc]
            if row['op'] == 'call':
                call = next(calls,None)
                check(call is not None and call['pc'] == pc and call['name'] == helpers[row['args'][0]['value']], 'Missing/wrong helper boundary')
                for r in REGS:
                    check(m.reg[r].number == call['before'][r], 'Pre-call register mismatch '+r)
                before = call['before']; after = call['after']
                check(before['rdi'] == parent, 'Wrong reader parent')
                check(all(after[r] == before[r] for r in CALLEE_SAVED), 'Callee ABI changed')
                offset = call['input_offset']; data = bytes.fromhex(call['data'])
                check(type(offset) is int and offset >= 0 and offset+len(data) <= len(file_bytes) and
                      data == file_bytes[offset:offset+len(data)], 'Read identity/content mismatch')
                check(file_cursor is None or offset == file_cursor, 'Nonsequential/incomplete input reads')
                file_cursor = offset+len(data)
                if call['name'] == 'GetByte':
                    check(len(data) == 1 and after['rax'] & 255 == data[0], 'Length read mismatch')
                else:
                    destination, count = before['rsi'], before['rdx'] & 0xffffffff
                    check(destination == ctx+ctx_layout['byte_buffer'] and 0 < count <= 255 and
                          count == len(data) and after['rax'] & 0xffffffff == 0, 'Invalid refill summary')
                    refill += 1
                    for i,b in enumerate(data):
                        # Label includes write identity even when an address or
                        # byte value is reused. Output projects it to file offset.
                        label = frozenset({f'input:{offset+i}:write:{refill}'})
                        m.store(destination+i,value(b,8,label))
                    writes.append(dict(version=refill,input_offset=offset,length=count,sequence=sequence))
                for r in REGS:
                    if r not in CALLEE_SAVED:
                        m.reg[r] = value(after[r],64,UNKNOWN)
                m.reg['rax'] = value(after['rax'],64)
                m.flags = None
                m.steps.append(pc); pc = row['next']; call_count += 1
            else:
                pc = m.step(row)
                if pc is None:
                    break
        else:
            raise ValueError('Instruction budget exceeded')
        check(next(calls,None) is None, 'Unused/duplicate helper boundary')
        check(m.reg['rsp'].number == sp and m.load(sp,64).number == record['return_pc'], 'Return frame mismatch')
        for r in REGS:
            check(m.reg[r].number == record['exit']['registers'][r], 'Return register mismatch '+r)
        end = bytes.fromhex(record['exit']['context'])
        check(len(end) == len(observed), 'Short exit context')
        for field,size in state_fields:
            off = ctx_layout[field]
            for i in range(size):
                b = m.mem[ctx+off+i]
                check(b.number == end[off+i], 'Context replay mismatch')
                saved[off+i] = b
        result = m.regread('ax')
        check('<unknown>' not in result.origins, 'Unknown reached queried return')
        labels = sorted(result.origins)
        origins = sorted({int(x.split(':')[1]) for x in labels})
        results.append(dict(sequence=sequence,value=result.number,source_file_offsets=origins,
                            source_versions=labels,instruction_steps=len(m.steps),helper_calls=call_count,
                            instruction_path_sha256=hashlib.sha256(json.dumps(m.steps).encode()).hexdigest(),
                            address_source_labels=sorted(m.address_origins),control_source_labels=sorted(m.control_origins)))
        prior = end
    return dict(status='inferred',strategy='boundary_replay',queries=results,source_writes=writes,
                semantics=plan['semantics'],oracle_used_for_inference=False,native_capture=False,
                libdft_compared=False,performance_eligible=False)
