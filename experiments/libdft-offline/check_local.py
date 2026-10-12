#!/usr/bin/env python3
"""Execute original C machine code in Unicorn, then replay unmodified libdft callbacks.

Emulated collection is explicitly NOT native Pin/BPF evidence. The native driver
is executed separately only for its values and independent oracle.
"""
import argparse
import collections
import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
import unicorn.x86_const as ux
from build_core import build, sha
from replay import REGS, replay, require, run_core, translate

ROOT=Path(__file__).resolve().parents[2]
NAMES=('loop_call_overwrite','loop_call_accumulate','loop_call_transform')
FUNCTIONS=(*NAMES,'read_iteration','transform_iteration')
UC_REGS={r:getattr(ux,'UC_X86_REG_'+r.upper()) for r in REGS}


def collect(binary, name, values, count):
    """Collector has no source-answer input and never calls the taint core."""
    uc=Uc(UC_ARCH_X86,UC_MODE_64)
    with binary.open('rb') as f:
        elf=ELFFile(f)
        loads=[(s['p_vaddr'],s['p_memsz'],s.data()) for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
        syms={s.name:(s['st_value'],s['st_size']) for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name in FUNCTIONS}
    pages=set()
    for addr,size,data in loads:
        pages.update(range(addr&~4095,(addr+size+4095)&~4095,4096))
    for addr in pages: uc.mem_map(addr,4096)
    for addr,size,data in loads: uc.mem_write(addr,data)
    src,dst,stack,stop=0x100000,0x100100,0x200000,0x300000
    uc.mem_map(src,4096); uc.mem_map(stack,0x10000); uc.mem_map(stop,4096)
    uc.mem_write(src,struct.pack('<III',*values)); uc.mem_write(dst,struct.pack('<II',0xdeadbeef,0))
    sp=stack+0xff00; uc.mem_write(sp,struct.pack('<Q',stop))
    for r,v in {'rdi':dst,'rsi':src,'rdx':count,'rsp':sp}.items(): uc.reg_write(UC_REGS[r],v)
    ranges=[(a,a+n) for a,n in syms.values()]; rows=[]
    def on_code(machine,pc,size,user):
        require(any(a<=pc<b for a,b in ranges),'emulated call outside declared functions')
        require(len(rows)<4096,'instruction budget')
        rows.append({'step':len(rows)+1,'pc':pc,'bytes':bytes(machine.mem_read(pc,size)).hex(),
                     'registers':{r:machine.reg_read(k) for r,k in UC_REGS.items()},
                     'eflags':machine.reg_read(ux.UC_X86_REG_EFLAGS)})
    uc.hook_add(UC_HOOK_CODE,on_code)
    uc.emu_start(syms[name][0],stop,count=4097)
    require(uc.reg_read(ux.UC_X86_REG_RIP)==stop,'incomplete emulated return')
    require(bytes(uc.mem_read(src,12))==struct.pack('<III',*values),'source mutation')
    return {'schema':'libdft-offline-trace-v1','transport':'Unicorn original ELF instructions',
            'native_capture':False,'complete':True,'function':name,'steps':len(rows),'ranges':ranges,
            'sources':[{'address':src+i*4,'width':4,'label':i+1} for i in range(3)],
            'sink':{'address':dst,'value':struct.unpack('<I',bytes(uc.mem_read(dst,4)))[0]},
            'inputs':{'values':values,'count':count},'instructions':rows}


def checks(exe):
    # Independently specified transport checks, including alias overwrite and upper-byte retention.
    cases=[
        ('copy', ['seed 4096 4 1','call m2r_xfer_opl 10 4096','call r2m_xfer_opl 8192 10','memory 8192 4'], [[1]]*4),
        ('union', ['seed 4096 4 1','seed 8192 4 2','call m2r_xfer_opl 10 4096','call m2r_binary_opl 10 8192','register 10 4'], [[1,2]]*4),
        ('overwrite', ['seed 4096 4 1','seed 8192 4 2','call m2r_xfer_opl 10 4096','call m2r_xfer_opl 10 8192','register 10 4'], [[2]]*4),
        ('clear', ['seed 4096 4 1','call m2r_xfer_opl 10 4096','call r_clrl 10','register 10 4'], [[]]*4),
        ('upstream_32bit_upper_retention', ['seed 4096 8 1','call m2r_xfer_opq 10 4096','call r_clrl 10','register 10 8'], [[]]*4+[[1]]*4),
        ('memory_alias', ['seed 4096 4 1','seed 8192 4 2','call m2r_xfer_opl 10 8192','call r2m_xfer_opl 4096 10','memory 4096 4'], [[2]]*4),
    ]
    report=[]
    for name,commands,expected in cases:
        got=run_core(exe,commands)[-1]['bytes']; require(got==expected,name)
        report.append({'name':name,'passed':True,'byte_labels':got})
    bad=[['call absent 1'],['call r2r_xfer_opq 999 10'],['seed 18446744073709551615 4 1']]
    for cmd in bad:
        try: run_core(exe,cmd)
        except ValueError: report.append({'name':cmd[0],'rejected':True})
        else: raise AssertionError('invalid transport accepted')
    # Preserve unsupported operations as unknown rather than claiming a full dispatcher.
    try: translate({'pc':4096,'bytes':'0f05','registers':{}})
    except ValueError: report.append({'name':'syscall','rejected':True})
    else: raise AssertionError('unsupported opcode accepted')
    return report


def main(a):
    out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    report={'schema':'libdft-offline-local-v1','status':'running','pin_executed':False,
            'bpf_executed':False,'native_trace_collected':False,'native_pin_equivalence':False,
            'performance_eligible':False,'cases':[]}
    try:
        exe,extraction=build(a.libdft,out/'core')
        report['extraction']=extraction
        report['transport_checks']=checks(exe)
        fixture=out/'fixture'; fixture.mkdir()
        files={}
        for name in ('main.c','operations.c','model.h'):
            src=ROOT/'scenarios/loop-calls-provenance'/name
            shutil.copyfile(src,fixture/name); files[name]=sha(src.read_bytes())
        binary=fixture/'program'
        flags=['-O1','-g','-fPIE','-pie','-fno-if-conversion','-fno-if-conversion2',
               '-fno-inline','-fno-lto','-fno-ipa-icf','-fno-stack-protector','-fcf-protection=none']
        cmd=['gcc',*flags,'-o',str(binary),str(fixture/'main.c'),str(fixture/'operations.c')]
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=60); require(p.returncode==0,p.stderr)
        native=subprocess.run([str(binary)],text=True,capture_output=True,timeout=30)
        require(native.returncode==0,native.stderr)
        (out/'native.jsonl').write_text(native.stdout)
        truth=[json.loads(s) for s in native.stdout.splitlines()]
        require(len(truth)==24,'native query count')
        report['fixture']={'source_sha256':files,'command':cmd,'elf_sha256':sha(binary.read_bytes()),
                           'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]}
        report['dependencies']={n:importlib.metadata.version(n) for n in ('capstone','unicorn','pyelftools')}
        histogram=collections.Counter()
        for seq in range(1,25):
            round_id,within=divmod(seq-1,12); fid,ci=divmod(within,4)
            count=(0,1,2,4)[ci]; value=424242+round_id
            trace=collect(binary,NAMES[fid],[value,value,99],count)
            result=replay(exe,trace)
            # Truth is only consulted after both collection and replay complete.
            expected=[] if count==0 else ([1] if count<=2 else [2] if fid==0 else [1,2])
            expected_value=(42 if count==0 else value) if fid==0 else count*(value if fid==1 else value^0x55)
            require(truth[seq-1]['output']==truth[seq-1]['expected_value']==expected_value,'native value oracle')
            require(truth[seq-1]['expected_sources']==[{1:'input.secret',2:'input.public_value'}[n] for n in expected],'native source oracle')
            require(trace['sink']['value']==expected_value,'emulated value')
            require(result['labels']==expected,'callback source mismatch')
            directory=out/f'query-{seq:02d}'; directory.mkdir()
            for name,doc in [('trace.json',trace),('replay.json',result)]:
                (directory/name).write_text(json.dumps(doc,indent=2)+'\n')
            for step in result['dispatch']:
                for call in step['callbacks']: histogram[call.split()[1] if call.startswith('call ') else call.split()[0]]+=1
            report['cases'].append({'sequence':seq,'function':NAMES[fid],'count':count,'steps':trace['steps'],
                                    'value':trace['sink']['value'],'labels':result['labels'],'expected':expected,
                                    'matched':True,'trace_sha256':sha((directory/'trace.json').read_bytes()),
                                    'replay_sha256':sha((directory/'replay.json').read_bytes())})
        report.update(status='local_pass_native_pin_calibration_pending',correct_queries=24,
                      raw_instruction_records=sum(r['steps'] for r in report['cases']),
                      callback_counts=dict(histogram),source_relations=sum(len(r['labels']) for r in report['cases']),
                      missing_host_archive='c-libdft-20261010-032159-226808.zip',
                      limitations=['Emulated collection, not a native Pin replacement validation',
                                   'Handwritten bounded instruction dispatcher; callback bodies and BDD/tagmap unchanged',
                                   'Single thread, five existing C functions; no Go/Rust/C++/Java support claim',
                                   'New local ELF; old host summary agreement is not same-trace calibration'])
    except Exception as e:
        report.update(status='failed',error=repr(e)); raise
    finally:
        report['adapter_sha256']={p.name:sha(p.read_bytes()) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.cpp','.H')}
        (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'status':report['status'],'directory':str(out),'correct_queries':report.get('correct_queries')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--libdft',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
