#!/usr/bin/env python3
"""Execute pinned original parse_string ELF in Unicorn; NOT native collection."""
import argparse
import collections
import copy
import json
from pathlib import Path
import struct
import sys

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
import unicorn.x86_const as ux
from preflight import prepare, command, FLAGS, save, sha, CASES, oracle, validate, HERE, ROOT
from parser_core import build, replay, require, REGS, decode

NAMES=('parse_string','parse_hex4','utf16_literal_to_utf8','tf_cjson_begin','tf_cjson_sink')
UREGS={r:getattr(ux,'UC_X86_REG_'+r.upper()) for r in REGS}


def fixture(source,out):
    files,manifest=prepare(source,out)
    binary=out/'cjson-workload'
    command(['gcc',*FLAGS,'-I',files,files/'driver.c',files/'cJSON.c','-lm','-o',binary],out)
    native=command([binary],out);(out/'native.jsonl').write_text(native)
    validate([json.loads(x) for x in native.splitlines()])
    # Private parser ABI is explicitly verified against this exact unmodified source.
    probe=out/'layout.c'
    probe.write_text('#include <stdio.h>\n#include <stddef.h>\n#include "cJSON.c"\n'
        'int main(void){printf("%zu %zu %zu %zu %zu %zu %zu %zu %zu %zu\\n",'
        'sizeof(cJSON),offsetof(cJSON,valuestring),sizeof(parse_buffer),'
        'offsetof(parse_buffer,content),offsetof(parse_buffer,length),offsetof(parse_buffer,offset),'
        'offsetof(parse_buffer,depth),offsetof(parse_buffer,hooks),'
        'offsetof(internal_hooks,allocate),sizeof(internal_hooks));}\n')
    command(['gcc','-I',files,probe,'-lm','-o',out/'layout'],out)
    layout=list(map(int,command([out/'layout'],out).split()))
    require(layout==[64,32,56,0,8,16,24,32,0,24],'private ABI differs; adapt explicitly')
    with binary.open('rb') as f:
        elf=ELFFile(f)
        syms={s.name:[s['st_value'],s['st_size']] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name in NAMES}
        require(set(syms)==set(NAMES),'missing configured symbols')
        segments=[dict(address=s['p_vaddr'],size=s['p_memsz'],flags=s['p_flags'],data=s.data().hex()) for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
        # Verify actual ELF DWARF members used by the native collector, not header alone.
        required={'cJSON':{'valuestring':32},'parse_buffer':{'content':0,'length':8,'offset':16,'depth':24,'hooks':32}}
        verified=set();typedefs={}
        for cu in elf.get_dwarf_info().iter_CUs():
            for die in cu.iter_DIEs():
                n=die.attributes.get('DW_AT_name')
                if die.tag=='DW_TAG_typedef' and n and n.value.decode() in required:
                    typedefs[n.value.decode()]=die.get_DIE_from_attribute('DW_AT_type')
        for name,die in typedefs.items():
            actual={c.attributes['DW_AT_name'].value.decode():c.attributes['DW_AT_data_member_location'].value
                    for c in die.iter_children() if c.tag=='DW_TAG_member'}
            require(all(actual.get(k)==v for k,v in required[name].items()),'ELF DWARF layout')
            verified.add(name)
        require(verified==set(required),'missing ELF ABI types')
    plan=dict(symbols=syms,segments=segments,binary_sha256=sha(binary),upstream_sha256=manifest,
              private_layout=layout,elf_dwarf_layout_checked=True,compiler_flags=FLAGS)
    save(out/'plan.json',plan)
    return binary,plan


def collect(binary,plan,text,offset):
    """Only source bytes and configured entry offset; no expected tags or values."""
    uc=Uc(UC_ARCH_X86,UC_MODE_64)
    pages=set()
    for seg in plan['segments']:
        a,n=seg['address'],seg['size'];pages.update(range(a&~4095,(a+n+4095)&~4095,4096))
    for a in pages:uc.mem_map(a,4096)
    for seg in plan['segments']:uc.mem_write(seg['address'],bytes.fromhex(seg['data']))
    src,item,buf,stack,alloc,heap,tls,stop=0x100000,0x101000,0x102000,0x200000,0x300000,0x400000,0x500000,0x600000
    for a,n in ((src,0x3000),(stack,0x10000),(alloc,4096),(heap,4096),(tls,4096),(stop,4096)):uc.mem_map(a,n)
    data=text.encode()+b'\0';require(len(data)<=256,'input bound')
    uc.mem_write(src,data)
    uc.mem_write(buf,struct.pack('<7Q',src,len(data),offset,0,alloc,alloc+16,0))
    uc.mem_write(tls+40,struct.pack('<Q',0x123456789abcdef0))
    sp=stack+0xff00;uc.mem_write(sp,struct.pack('<Q',stop))
    for r,v in dict(rdi=item,rsi=buf,rsp=sp).items():uc.reg_write(UREGS[r],v)
    uc.reg_write(ux.UC_X86_REG_FS_BASE,tls)
    ranges=[(a,a+n) for a,n in (plan['symbols'][k] for k in NAMES[:3])]
    records=[];state={}
    def hook(machine,pc,size,_):
        if pc==alloc:
            require(not state,'repeated allocation')
            n=machine.reg_read(UREGS['rdi']);require(0<n<=32,'allocation bound')
            stackptr=machine.reg_read(UREGS['rsp'])
            ret=struct.unpack('<Q',bytes(machine.mem_read(stackptr,8)))[0]
            machine.reg_write(UREGS['rax'],heap);machine.reg_write(UREGS['rsp'],stackptr+8)
            machine.reg_write(ux.UC_X86_REG_RIP,ret)
            state.update(address=src,data=data.hex(),offset=offset,item=item,buffer=buf,
                         allocation=heap,allocation_size=n,entry_pc=ret,root_sp=sp,return_pc=stop)
            state['snapshots']=[dict(address=a,data=bytes(machine.mem_read(a,n)).hex())
                                for a,n in ((sp-512,520),(item,64),(buf,56),(tls+40,8))]
            return
        require(any(a<=pc<b for a,b in ranges),'call outside configured decoder')
        if state:
            require(len(records)<8192,'instruction budget')
            records.append(dict(step=len(records)+1,pc=pc,bytes=bytes(machine.mem_read(pc,size)).hex(),
                                registers={r:machine.reg_read(i) for r,i in UREGS.items()},
                                fs_base=machine.reg_read(ux.UC_X86_REG_FS_BASE)))
    uc.hook_add(UC_HOOK_CODE,hook)
    uc.emu_start(plan['symbols']['parse_string'][0],stop,count=20000)
    require(uc.reg_read(ux.UC_X86_REG_RIP)==stop and uc.reg_read(UREGS['rax'])==1,'decoder completion')
    require(bytes(uc.mem_read(src,len(data)))==data,'source mutated')
    pointer=struct.unpack('<Q',bytes(uc.mem_read(item+32,8)))[0]
    require(pointer==heap,'output object binding')
    output=bytes(uc.mem_read(heap,state['allocation_size']));require(b'\0' in output,'terminator')
    return dict(schema='cjson-parser-trace-v1',transport='Unicorn original parse_string ELF',
                native_capture=False,complete=True,source=state,ranges=ranges,instructions=records,
                load_bias=0,
                sink=dict(data=output.split(b'\0',1)[0].hex(),item=item,address=heap))


def main(a):
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',native_capture=False,native_core_calibration=False,
                our_provenance_run=False,performance_eligible=False,queries=[])
    try:
        binary,plan=fixture(a.source.resolve(),out)
        exe,extraction=build(a.libdft.resolve(),out/'core')
        hist=collections.Counter()
        for case_index,case in enumerate(CASES,1):
            truth=oracle(case)
            for query_index,expected in enumerate(truth['queries']):
                path=expected['path'];result=dict(case=case['name'],path=path)
                report['queries'].append(result)
                if expected['status']=='no_sink':result['status']='native_no_sink';continue
                if expected['format_field_origin']=='replacement':
                    result.update(status='not_in_parser_scope',reason='replacement occurs after parsing');continue
                span=truth['input_string_spans'][path]
                trace=collect(binary,plan,case['text'],span['begin']-1)
                inference=replay(exe,trace)
                from parser_ours import infer
                ours=infer(plan,trace)
                require(trace['sink']['data']==expected['value_hex'],'emulated value mismatch')
                # Field-level diagnostic only: control-produced constants have no explicit content tag.
                labels=sorted({x for b in inference['byte_labels'] for x in b})
                require(all(span['begin']<=n-1<span['end'] for n in labels),'unexpected other-field source')
                constant=case.get('semantics')=='control_diagnostic' or expected['empty_content']
                require(bool(labels)==(not constant),'explicit field-presence diagnostic')
                q=out/f'case-{case_index:02d}-query-{query_index:02d}';q.mkdir()
                save(q/'trace.json',trace);save(q/'replay.json',inference)
                save(q/'ours.json',ours)
                for row in trace['instructions']:hist[decode(row).mnemonic]+=1
                result.update(status='emulated_replay_completed',steps=len(trace['instructions']),
                              byte_labels=inference['byte_labels'],source_offsets=[x-1 for x in labels],
                              ours_source_offsets=ours['source_offsets'],
                              field_presence_diagnostic_matched=True)
                require(all(span['begin']<=n<span['end'] for n in ours['source_offsets']), 'ours unexpected field')
                require(bool(ours['source_offsets'])==(not constant),'ours explicit field presence')
        # These checks address new evidence/transport risks, not repeat old C tests.
        bad=[]
        def reject(name,change,engines):
            damaged=copy.deepcopy(trace);change(damaged)
            for engine in engines:
                try:
                    replay(exe,damaged) if engine=='libdft_offline' else infer(plan,damaged)
                except ValueError:bad.append(dict(name=name,engine=engine,rejected=True))
                else:raise AssertionError('accepted damaged evidence: '+name)
        both=['libdft_offline','ours']
        reject('missing_completion',lambda t:t.update(complete=False),both)
        reject('sequence_gap',lambda t:t['instructions'][1].update(step=999),both)
        reject('outside_decoder',lambda t:t['instructions'][0].update(pc=1),both)
        reject('missing_root_return',lambda t:t['instructions'][-1].update(bytes='90'),both)
        reject('wrong_concrete_register',lambda t:t['instructions'][1]['registers'].update(
            rax=t['instructions'][1]['registers']['rax']^1),['ours'])
        reject('missing_stack_snapshot',lambda t:t['source']['snapshots'].pop(0),['ours'])
        report.update(status='local_parser_replay_pass_native_calibration_pending',
                      our_provenance_run=True,
                      query_requests=len(report['queries']),extracted_callbacks=len(extraction['callbacks']),
                      emulated_queries=sum(q['status']=='emulated_replay_completed' for q in report['queries']),
                      emulated_instructions=sum(q.get('steps',0) for q in report['queries']),
                      mnemonic_counts=dict(hist),binary_sha256=plan['binary_sha256'],
                      upstream_sha256=plan['upstream_sha256'],
                      rejection_checks=bad,
                      implementation_sha256={p.name:sha(p) for p in HERE.iterdir() if p.suffix in ('.py','.cpp','.c')},
                      scope='Post-allocation parse_string decoding; replacement/serialization not analyzed',
                      limitations=['Unicorn allocation return is a concrete runtime stub, not native execution',
                                   'Local byte labels are not proof of equivalence to original Pin dispatcher',
                                   'Field-presence diagnostics are not independent per-byte dependency truth'])
    except Exception as e:report.update(status='failed',error=repr(e));raise
    finally:
        save(out/'validation.json',report)
        print(json.dumps({k:report.get(k) for k in ('status','emulated_queries','emulated_instructions','extracted_callbacks')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--libdft',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
