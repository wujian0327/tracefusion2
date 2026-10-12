#!/usr/bin/env python3
"""Pinned upstream/native workload check and conservative offline-adapter audit.

This does NOT collect a native instruction trace or score provenance accuracy.
Coverage uses a separate instrumented build and cannot stand in for Pin evidence.
"""
import argparse
from collections import Counter
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_IMM
from elftools.elf.elffile import ELFFile
from cases import CASES, oracle

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'libdft-offline'))
from replay import translate, REGS

REVISION='c859b25da02955fef659d658b8f324b5cde87be3'
TAG='v1.7.19'
URL='https://github.com/DaveGamble/cJSON.git'
FLAGS=['-O1','-g','-fno-inline','-fno-lto','-fno-ipa-icf','-fcf-protection=none']


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')


def command(args,out,cwd=None):
    args=list(map(str,args))
    p=subprocess.run(args,cwd=cwd or out,text=True,capture_output=True,timeout=180)
    with (out/'commands.jsonl').open('a') as f:
        f.write(json.dumps(dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))+'\n')
    if p.returncode: raise RuntimeError(p.stderr or p.stdout)
    return p.stdout


def prepare(source,out):
    if not source.exists():
        source.parent.mkdir(parents=True,exist_ok=True)
        command(['git','clone','--depth','1','--branch',TAG,URL,source],out)
    actual=command(['git','-C',source,'rev-parse','HEAD'],out).strip()
    if actual!=REVISION: raise ValueError('Wrong cJSON revision')
    if command(['git','-C',source,'status','--porcelain','--untracked-files=no'],out).strip():
        raise ValueError('Changed cJSON tracked source')
    target=out/'source';target.mkdir()
    manifest={}
    for name in ('cJSON.c','cJSON.h','LICENSE'):
        data=subprocess.check_output(['git','-C',str(source),'show',REVISION+':'+name])
        if (source/name).read_bytes()!=data: raise ValueError('Source mismatch')
        (target/name).write_bytes(data);manifest[name]=sha(target/name)
    shutil.copyfile(HERE/'driver.c',target/'driver.c')
    # C driver receives workload inputs and requested paths, never expected answers.
    def literal(x): return 'NULL' if x is None else json.dumps(x,ensure_ascii=True)
    lines=['static const struct test_case cases[] = {']
    for c in CASES:
        args=[literal(c[k]) for k in ('name','text')]
        args += [literal(c.get(k)) for k in ('replace_key','replacement')]
        args += [str(len(c['paths'])),'{'+','.join(literal(x) for x in c['paths'])+'}']
        lines.append('    {'+','.join(args)+'},')
    lines.append('};')
    (target/'cases.h').write_text('\n'.join(lines)+'\n')
    return target,manifest


def validate(rows):
    if len(rows)!=len(CASES): raise ValueError('case count')
    report=[]
    for case,row in zip(CASES,rows):
        expected=oracle(case)
        if row['case']!=case['name'] or row['parsed']!=expected['parsed']:
            raise ValueError('parse outcome')
        public=[{k:q[k] for k in ('path','status','value_hex') if k in q} for q in expected['queries']]
        if row['queries']!=public: raise ValueError('queried value mismatch: '+case['name'])
        serialized=row['serialized_hex']
        if (serialized is None)!=(expected['document'] is None): raise ValueError('serialization presence')
        if serialized is not None and json.loads(bytes.fromhex(serialized))!=expected['document']:
            raise ValueError('serialized document mismatch')
        report.append(dict(name=case['name'],native_value_matched=True,
                           category=case.get('semantics','plain_strings'),oracle=expected,
                           provenance_status='not_run'))
    return report


def audit(binary,coverage):
    data=binary.read_bytes();elf=ELFFile(io.BytesIO(data))
    if elf['e_machine']!='EM_X86_64' or not elf.little_endian: raise ValueError('unsupported audit ABI')
    names={s.name:dict(address=s['st_value'],size=s['st_size'])
           for s in elf.get_section_by_name('.symtab').iter_symbols()
           if s['st_info']['type']=='STT_FUNC' and s['st_size']}
    byaddr={s['address']:n for n,s in names.items()}
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    functions={};histogram=Counter();reasons=Counter()
    for name,count in sorted(coverage.items()):
        if count<=0: continue
        sym=names.get(name)
        if not sym:
            functions[name]=dict(coverage_entry_count=count,static_audit='symbol_missing');continue
        a,size=sym['address'],sym['size']
        seg=next(s for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and
                 s['p_vaddr']<=a and a+size<=s['p_vaddr']+s['p_filesz'])
        offset=seg['p_offset']+a-seg['p_vaddr']
        instructions=list(md.disasm(data[offset:offset+size],a))
        if sum(i.size for i in instructions)!=size: raise ValueError('incomplete disassembly')
        rejected=[];calls=[];counts=Counter()
        for ins in instructions:
            counts[ins.mnemonic]+=1
            row=dict(pc=ins.address,bytes=ins.bytes.hex(),registers={r:0x100000 for r in REGS})
            try: translate(row)
            except ValueError as e:
                rejected.append(dict(pc=ins.address,op=ins.mnemonic,args=ins.op_str,reason=str(e)))
                reasons[str(e)]+=1
            if ins.mnemonic=='call':
                direct=len(ins.operands)==1 and ins.operands[0].type==X86_OP_IMM
                target=ins.operands[0].imm if direct else None
                calls.append(dict(pc=ins.address,kind='direct' if direct else 'indirect',
                                  target=target,name=byaddr.get(target),operands=ins.op_str))
        histogram.update(counts)
        functions[name]=dict(coverage_entry_count=count,static_instructions=len(instructions),
                             mnemonic_counts=dict(counts),rejected_forms=rejected,calls=calls)
    return dict(scope='All static instructions in original-build functions reached by separate gcov build; '
                      'overapproximation, not a per-query executed-instruction trace',
                adapter='experiments/libdft-offline/replay.py',
                adapter_sha256=sha(HERE.parent/'libdft-offline/replay.py'),
                functions=functions,static_mnemonic_counts=dict(histogram),
                rejected_form_counts=dict(reasons),
                external_calls_and_allocator_hooks_qualified=False,
                warnings=['Translator acceptance alone does not qualify calls, SIMD, memory or taint semantics',
                          'Coverage counts are from a separate instrumented ELF and not performance evidence'])


def main(a):
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',native_instruction_trace_collected=False,
                libdft_original_run=False,libdft_offline_run=False,our_provenance_run=False,
                provenance_accuracy=None,performance_eligible=False)
    try:
        source,manifest=prepare(a.source.resolve(),out)
        report.update(upstream=dict(url=URL,tag=TAG,revision=REVISION,sha256=manifest),
                      environment=dict(platform=platform.platform(),machine=platform.machine(),
                                       gcc=command(['gcc','--version'],out).splitlines()[0],python=sys.version),
                      compiler_flags=FLAGS)
        binary=out/'cjson-workload'
        command(['gcc',*FLAGS,'-I',source,source/'driver.c',source/'cJSON.c','-lm','-o',binary],out)
        native=command([binary],out);(out/'native.jsonl').write_text(native)
        case_results=validate([json.loads(x) for x in native.splitlines()])
        save(out/'cases-and-oracle.json',dict(inputs=CASES,results=case_results))
        cov=out/'coverage';cov.mkdir()
        covbin=cov/'program'
        command(['gcc',*FLAGS,'--coverage','-I',source,source/'driver.c',source/'cJSON.c','-lm','-o',covbin],out)
        covtext=command([covbin],out)
        if covtext!=native: raise ValueError('coverage build changed outputs')
        command(['gcov','--json-format',cov/'program-cJSON.gcno'],out,cwd=cov)
        documents=[json.loads(gzip.decompress(p.read_bytes())) for p in cov.glob('*.gcov.json.gz')]
        if len(documents)!=1: raise ValueError('coverage record count')
        file=next(f for f in documents[0]['files'] if Path(f['file']).name=='cJSON.c')
        hits={f['name']:f['execution_count'] for f in file['functions']}
        required=['parse_string','parse_object','parse_array','get_object_item','print_string_ptr',
                  'parse_hex4','utf16_literal_to_utf8','cJSON_ReplaceItemViaPointer']
        if not all(hits.get(n,0)>0 for n in required): raise ValueError('required original path not exercised')
        static=audit(binary,hits);save(out/'instruction-audit.json',static)
        report.update(status='native_preflight_pass_provenance_pending',
                      cases=len(CASES),query_requests=sum(len(c['paths']) for c in CASES),
                      string_targets=sum(q['status']=='string' for c in case_results for q in c['oracle']['queries']),
                      no_sink_targets=sum(q['status']=='no_sink' for c in case_results for q in c['oracle']['queries']),
                      native_value_checks_passed=True,serialized_documents=sum(c['oracle']['parsed'] for c in case_results),
                      source_semantics='Input lexical field identities vs explicit data/control origins kept separate',
                      required_function_hits={n:hits[n] for n in required},
                      reached_upstream_functions=sum(c>0 for c in hits.values()),
                      static_rejected_forms=sum(static['rejected_form_counts'].values()),
                      static_rejected_form_reasons=static['rejected_form_counts'],
                      binary_sha256=sha(binary),coverage_binary_sha256=sha(covbin),
                      files_sha256={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},
                      implementation_sha256={p.name:sha(p) for p in HERE.iterdir() if p.suffix in ('.py','.c')},
                      next_step='Add a native observation contract for allocation/copy/calls and extend '
                                'amd64 adapter with same-trace original-core calibration; no claimed full comparison')
    except Exception as exc:
        report.update(status='failed',error=repr(exc));raise
    finally:
        save(out/'validation.json',report)
        print(json.dumps({k:report.get(k) for k in ('status','cases','query_requests','string_targets',
                         'no_sink_targets','static_rejected_forms','provenance_accuracy')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'artifacts/external-tools/cjson-v1.7.19')
    p.add_argument('--output',type=Path,default=ROOT/'artifacts'/('cjson-preflight-'+
                   datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')))
    main(p.parse_args())
