#!/usr/bin/env python3
"""Run the original decoder ELF in Unicorn, then score isolated inference.

Native conversion was checked separately by validate_normal.py. These records
are synthetic. Standard-library file/heap/copy behavior is explicitly modeled;
this is neither BPF evidence nor a libdft64 result nor a performance benchmark.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

from PIL import Image
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, __version__ as unicorn_version
from unicorn import x86_const as x86
import query
from validate_normal import REVISION
from gif_reference import parse, decode as reference_decode

REG = {r:getattr(x86,'UC_X86_REG_'+r.upper()) for r in query.REGS}


def save(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n')


def emulate(binary, plan, data, image, indexed):
    cpu = Uc(UC_ARCH_X86,UC_MODE_64)
    mapped = set()
    def write(address, block):
        for page in range(address & ~4095,(address+len(block)+4095) & ~4095,4096):
            if page not in mapped:
                cpu.mem_map(page,4096); mapped.add(page)
        cpu.mem_write(address,block)
    def put(address, n, size=8):
        write(address,int(n).to_bytes(size,'little'))
    def get(address, size=8):
        return int.from_bytes(cpu.mem_read(address,size),'little')
    def regs():
        return {r:cpu.reg_read(n) for r,n in REG.items()}
    elf = ELFFile(io.BytesIO(binary.read_bytes()))
    for seg in elf.iter_segments():
        if seg['p_type'] == 'PT_LOAD':
            write(seg['p_vaddr'],seg.data()+bytes(seg['p_memsz']-seg['p_filesz']))
    # Local symbolic/heap identities are synthetic, not native process pointers.
    stack, gif, img, palette, pixels, tcb, finish = 0x20010000,0x30000000,0x30001000,0x30002000,0x31000000,0x40000000,0x50000000
    write(stack-65536,bytes(131072)); write(gif,bytes(16384)); write(pixels,bytes(image.width*image.height*4))
    write(tcb,bytes(4096)); put(tcb+40,0x123456789abc0000); write(finish,b'\x90')
    cpu.reg_write(x86.UC_X86_REG_FS_BASE,tcb)
    put(stack,finish)
    cpu.reg_write(REG['rsp'],stack); cpu.reg_write(REG['rdi'],img)
    gl = plan['layout']['ngiflib_gif']; il = plan['layout']['ngiflib_img']; cl = plan['layout']['ngiflib_decode_context']
    put(img+il['parent'],gif); put(gif+gl['input'],0x60000000)
    put(gif+gl['palette'],palette); write(palette,image.palette)
    put(gif+gl['frbuff'],pixels)
    put(gif+gl['width'],image.width,2); put(gif+gl['height'],image.height,2)
    put(gif+gl['imgbits'],(len(image.palette)//3).bit_length()-1,1)
    put(gif+gl['mode'],int(indexed),1)
    cursor = image.descriptor+1
    malloc_next = 0x32000000
    asm = subprocess.check_output(['objdump','-d',str(binary)],text=True)
    plt = {int(a,16):n for a,n in re.findall(r'^([0-9a-f]+) <([^>]+)@plt>:',asm,re.M)}
    symbols = plan['symbols']; rows = {r['address']:r for r in plan['instructions']}
    entry = symbols['GetGifWord']['address']
    records = []; active = None; pending = None; instructions = 0; read_events = []
    allowed_ranges = []
    for sym in elf.get_section_by_name('.symtab').iter_symbols():
        if sym.name in ('DecodeGifImg','GetGifWord','GetByte','GetByteStr','GetWord','WritePixels','GifIndexToTrueColor'):
            allowed_ranges.append((sym['st_value'],sym['st_value']+sym['st_size']))
    def hook(uc, pc, size, _):
        nonlocal cursor,malloc_next,active,pending,instructions
        instructions += 1
        query.check(instructions <= 1000000,'Decoder instruction budget')
        if pc == finish:
            uc.emu_stop(); return
        if pc in plt:
            name = plt[pc]; r = regs(); result = None
            if name == 'getc':
                query.check(r['rdi'] == 0x60000000 and cursor < len(data),'Invalid modeled getc')
                result = data[cursor]; read_events.append(dict(offset=cursor,hex=data[cursor:cursor+1].hex()))
                cursor += 1
            elif name == 'fread':
                n = r['rsi']*r['rdx']
                query.check(r['rcx'] == 0x60000000 and r['rsi'] == 1 and 0 < n <= 255 and cursor+n <= len(data),'Invalid modeled fread')
                write(r['rdi'],data[cursor:cursor+n]); result = r['rdx']
                read_events.append(dict(offset=cursor,hex=data[cursor:cursor+n].hex())); cursor += n
            elif name == 'memcpy':
                query.check(r['rdx'] <= 65536,'Copy budget')
                write(r['rdi'],bytes(cpu.mem_read(r['rsi'],r['rdx']))); result = r['rdi']
            elif name == 'malloc':
                query.check(0 < r['rdi'] <= 65536,'Allocation budget')
                result = malloc_next; malloc_next += (r['rdi']+4095) & ~4095
                write(result,bytes(r['rdi']))
            else:
                raise ValueError('Unmodeled external call '+name)
            # SysV caller-save state is deterministically destroyed. Retaining
            # labels across an external call by accident must not make a pass.
            for name in query.REGS:
                if name not in query.CALLEE_SAVED:
                    uc.reg_write(REG[name],0)
            uc.reg_write(REG['rax'],result)
            sp = uc.reg_read(REG['rsp']); resume = get(sp)
            uc.reg_write(REG['rsp'],sp+8); uc.reg_write(x86.UC_X86_REG_RIP,resume)
            return
        query.check(any(a <= pc < b for a,b in allowed_ranges),'Execution outside original decoder functions')
        if active is not None and pc == active['return_pc']:
            query.check('exit' in active and regs()['rsp'] == active['entry']['registers']['rsp']+8, 'Missing return/frame')
            records.append(active); active = None
        if pending is not None and pc == pending['resume']:
            query.check(len(read_events) == pending.pop('read_index')+1,'Helper must perform exactly one modeled read')
            event = read_events[-1]
            pending.update(after=regs(),input_offset=event['offset'],data=event['hex'])
            active['calls'].append(pending); pending = None
        if pc == entry:
            query.check(active is None,'Nested GetGifWord')
            r = regs(); ctx = r['rsi']
            active = dict(sequence=len(records)+1,context_pointer=ctx,image_pointer=r['rdi'],parent_pointer=get(r['rdi']+il['parent']),
                          return_pc=get(r['rsp']),entry=dict(registers=r,context=bytes(cpu.mem_read(ctx,cl['size'])).hex()),calls=[],instruction_pcs=[])
        if active is not None and pc in rows:
            active['instruction_pcs'].append(pc)
            row = rows[pc]
            if row['op'] == 'ret':
                active['exit'] = dict(registers=regs(),context=bytes(cpu.mem_read(active['context_pointer'],cl['size'])).hex())
            if row['op'] == 'call':
                name = next(n for n in ('GetByte','GetByteStr') if symbols[n]['address'] == row['args'][0]['value'])
                query.check(pending is None,'Nested observed helper')
                pending = dict(name=name,pc=pc,resume=row['next'],before=regs(),read_index=len(read_events))
    cpu.hook_add(UC_HOOK_CODE,hook)
    cpu.emu_start(symbols['DecodeGifImg']['address'],finish+1,count=1000001)
    query.check(cpu.reg_read(x86.UC_X86_REG_RIP) == finish and active is None and pending is None,'Incomplete decoder execution')
    result = cpu.reg_read(REG['rax']) & 0xffffffff
    query.check(result == 0,'Decoder rejected normal input')
    frame = bytes(cpu.mem_read(pixels,image.width*image.height*(1 if indexed else 4)))
    if indexed:
        rgb = b''.join(image.palette[b*3:b*3+3] for b in frame)
    else:
        rgb = b''.join(frame[i:i+3][::-1] for i in range(0,len(frame),4))
    return dict(backend='unicorn-original-decoder-v1',synthetic=True,complete=True,errors=[],
                binary_sha256=plan['binary_sha256'],input_sha256=hashlib.sha256(data).hexdigest(),
                decoder_return=result,records=records,total_decoder_instructions=instructions,
                modeled_library_calls=['getc','fread','memcpy','malloc'],pixels_rgb_hex=rgb.hex())


def faults(plan, trace, data):
    checks = []
    def reject(name, edit):
        changed = copy.deepcopy(trace); edit(changed)
        try:
            query.infer(plan,changed,data)
        except ValueError as exc:
            checks.append(dict(name=name,rejected=True,reason=str(exc)))
        else:
            raise AssertionError('Fault accepted: '+name)
    reject('wrong_elf',lambda t:t.update(binary_sha256='0'*64))
    reject('incomplete_capture',lambda t:t.update(complete=False))
    reject('wrong_input_identity',lambda t:t.update(input_sha256='0'*64))
    reject('unqualified_native_backend',lambda t:t.update(backend='native-unverified'))
    reject('missing_first_invocation',lambda t:t['records'].pop(0))
    reject('duplicate_sequence',lambda t:t['records'][1].update(sequence=1))
    reject('missing_refill',lambda t:t['records'][0]['calls'].pop())
    reject('wrong_read_offset',lambda t:t['records'][0]['calls'][1].update(input_offset=0))
    reject('wrong_abi_parent',lambda t:t['records'][0].update(parent_pointer=1))
    reject('wrong_return',lambda t:t['records'][0]['exit']['registers'].update(rax=12345))
    reject('source_write_corruption',lambda t:t['records'][0]['calls'][1].update(data='00'))
    def mutate_residual(t):
        block = bytearray.fromhex(t['records'][1]['entry']['context'])
        block[plan['layout']['ngiflib_decode_context']['lbyte']] ^= 1
        t['records'][1]['entry']['context'] = block.hex()
    reject('wrong_context_version',mutate_residual)
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--validation',type=Path,required=True,help='Existing validate_normal.py output (not rerun)')
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args(); v = args.validation.resolve(); out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    previous = json.loads((v/'summary.json').read_text())
    query.check(previous['revision'] == REVISION and previous['native_runs_passed'] == 8, 'Requires validated pinned revision')
    for name, digest in previous['source_sha256'].items():
        query.check(hashlib.sha256((v/'source'/name).read_bytes()).hexdigest() == digest, 'Changed upstream source')
    binary = v/'gif2tga-native'
    query.check(hashlib.sha256(binary.read_bytes()).hexdigest() == previous['binary_sha256']['native'],'Changed native binary')
    plan = query.plan(binary,v/'source',out); save(out/'plan.json',plan)
    summary = dict(stage='local-original-decoder-query',native_capture=False,bpf_executed=False,libdft_executed=False,
                   performance_eligible=False,synthetic=True,unicorn_version=unicorn_version,
                   binary_sha256=plan['binary_sha256'],cases=[])
    for name in ('single_pixel','stripes','checker','blocks'):
        path = v/name/'normal.gif'; data = path.read_bytes(); metadata = parse(data)
        for indexed in (False,True):
            folder = out/(name+('-indexed' if indexed else '-truecolor')); folder.mkdir()
            trace = emulate(binary,plan,data,metadata,indexed)
            # Remove instruction diagnostics from the input passed to inference.
            # This replay strategy has no access to observed instruction paths.
            transport = copy.deepcopy(trace)
            for record in transport['records']:
                del record['instruction_pcs']
            result = query.infer(plan,transport,data)
            for actual, captured in zip(result['queries'], trace['records']):
                query.check(actual['instruction_path_sha256'] == hashlib.sha256(json.dumps(captured['instruction_pcs']).encode()).hexdigest(), 'Replayed control path differs from Unicorn')
            save(folder/'trace.json',trace); save(folder/'inference.json',result)
            # Only now construct/open the independent code and source oracle.
            expected, pixels = reference_decode(metadata)
            with Image.open(path) as im:
                query.check(im.mode == 'P' and im.tobytes() == pixels,'Independent LZW pixels differ from Pillow')
                query.check(im.convert('RGB').tobytes().hex() == trace['pixels_rgb_hex'],'Original decoder emulation pixel mismatch')
            query.check(len(expected) == len(result['queries']),'Code invocation count differs')
            rows = []
            for actual, gold in zip(result['queries'],expected):
                a,b = set(actual['source_file_offsets']),set(gold['source_file_offsets'])
                rows.append(dict(sequence=gold['sequence'],value_match=actual['value']==gold['value'],
                                 sources_match=a==b,tp=len(a&b),fp=len(a-b),fn=len(b-a)))
            save(folder/'reference.json',dict(codes=expected,pixels_sha256=hashlib.sha256(pixels).hexdigest()))
            save(folder/'evaluation.json',rows)
            summary['cases'].append(dict(input=name,indexed=indexed,queries=len(rows),
                value_matches=sum(r['value_match'] for r in rows),exact_sources=sum(r['sources_match'] for r in rows),
                tp=sum(r['tp'] for r in rows),fp=sum(r['fp'] for r in rows),fn=sum(r['fn'] for r in rows),
                refills=len(result['source_writes']),code_widths=sorted({r['width'] for r in expected}),
                instruction_steps=sum(r['instruction_steps'] for r in result['queries']),pixels_match=True))
            save(out/'summary.json',summary)
            if name == 'stripes' and not indexed:
                summary['rejection_checks'] = faults(plan,transport,data)
    summary['all_passed'] = all(c['queries'] == c['value_matches'] == c['exact_sources'] for c in summary['cases'])
    summary['total_queries'] = sum(c['queries'] for c in summary['cases'])
    summary['distinct_input_code_positions'] = sum(c['queries'] for c in summary['cases'] if not c['indexed'])
    summary['source_sha256'] = previous['source_sha256']
    summary['revision'] = REVISION
    summary['semantics'] = plan['semantics']
    summary['strategy'] = plan['strategy']
    summary['layout_verified_against_elf_dwarf'] = plan['layout_verified_against_elf_dwarf']
    summary['scope'] = 'one image per file; normal global-palette noninterlaced inputs; widths 9 and 10 observed; GetByteStr source boundary; code metadata fixed'
    summary['unvalidated'] = ['native collection','libdft comparison','BPF','performance','arbitrary C/C++','minimal bit dependence for general arithmetic']
    save(out/'summary.json',summary)
    print(json.dumps(summary,indent=2))
    if not summary['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
