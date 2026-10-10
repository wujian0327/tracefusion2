#!/usr/bin/env python3
"""Native ngiflib boundary-replay vs unmodified libdft64, correctness diagnostics.

Only the patched revision and ordinary images. Never a performance benchmark.
Both modes use Pin for transport; our mode does not initialize libdft propagation.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

from PIL import Image,__version__ as pillow_version
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'checkout-payment-path'))
import external_compare as shared
import query
from host_records import read_log
from gif_reference import parse,decode
from validate_normal import REVISION,FIX,tga_rgb

check=query.check;save=shared.save
SOURCE_HASHES={'ngiflib.c':'de2df465173a8acf6f376d6b264c0e1d74903901d683368c8cd2a7f2bf499b33',
              'ngiflib.h':'3f585dc029479541ff1ac1dde749c4f346170ea06b9d99731a81e7086e7f05cd',
              'gif2tga.c':'4f2a8468ce708bc4436077b4d90af69c457835125b2f3f756f6c6d520530794a'}
CASES=('single_pixel','stripes','checker','blocks')


def fixture(args,out):
    target=out/'fixture';target.mkdir();source=target/'source';source.mkdir()
    if args.validation:
        prior=json.loads((args.validation/'summary.json').read_text())
        check(prior['revision']==REVISION and prior['source_sha256']==SOURCE_HASHES,'Wrong validation revision/source')
        for name in SOURCE_HASHES:shutil.copy2(args.validation/'source'/name,source/name)
        binary=target/'gif2tga';shutil.copy2(args.validation/'gif2tga-native',binary)
        check(shared.sha(binary)==prior['binary_sha256']['native'],'Validation ELF changed')
        for name in CASES:
            folder=target/name;folder.mkdir();shutil.copy2(args.validation/name/'normal.gif',folder/'normal.gif')
            old=[r for r in prior['cases'] if r['input']==name and r['build']=='native']
            check(old and all(r['input_sha256']==shared.sha(folder/'normal.gif') for r in old),'Validation input changed')
    else:
        repo=(args.source or ROOT/'artifacts/external-tools/ngiflib-patched').resolve()
        if not repo.exists():
            check(args.source is None,'Supplied upstream source directory absent')
            repo.parent.mkdir(parents=True,exist_ok=True)
            shared.command(['git','clone','https://github.com/miniupnp/ngiflib.git',repo],out)
        shared.command(['git','merge-base','--is-ancestor',FIX,REVISION],out,cwd=repo)
        for name in SOURCE_HASHES:
            block=subprocess.check_output(['git','-C',str(repo),'show',REVISION+':'+name])
            (source/name).write_bytes(block)
        binary=target/'gif2tga'
        shared.command(['gcc','-O1','-g','-Wall','-Wextra','-o',binary,source/'gif2tga.c',source/'ngiflib.c'],out)
        palette=[0,0,0,255,0,0,0,255,0,0,0,255]+[0]*(768-12)
        patterns=[('single_pixel',1,1,lambda x,y:1),('stripes',8,4,lambda x,y:x%4),
                  ('checker',31,17,lambda x,y:(x+y)%4),('blocks',64,64,lambda x,y:((x//8)+(y//8))%4)]
        for name,w,h,fn in patterns:
            folder=target/name;folder.mkdir();im=Image.new('P',(w,h));im.putpalette(palette)
            im.putdata([fn(x,y) for y in range(h) for x in range(w)])
            im.save(folder/'normal.gif',format='GIF',optimize=False,interlace=False)
    check(all(shared.sha(source/n)==h for n,h in SOURCE_HASHES.items()),'Upstream source modified')
    save(out/'fixture-identity.json',dict(revision=REVISION,fix=FIX,source_sha256=SOURCE_HASHES,
         binary_sha256=shared.sha(binary),pillow_version=pillow_version,input_sha256={n:shared.sha(target/n/'normal.gif') for n in CASES},
         source_modified=False,ordinary_inputs_only=True))
    shared.command(['objdump','-d','-M','intel',binary],out)
    return binary,source,target


def expand_adapter(plan,out):
    l=plan['layout'];c=l['ngiflib_decode_context'];g=l['ngiflib_gif'];i=l['ngiflib_img']
    fields=dict(CTX_SIZE=c['size'],CTX_BUFFER=c['byte_buffer'],CTX_NBBIT=c['nbbit'],CTX_MAX=c['max'],
                CTX_RESTBITS=c['restbits'],CTX_RESTBYTE=c['restbyte'],IMG_PARENT=i['parent'],GIF_INPUT=g['input'],GIF_MODE=g['mode'])
    body=(HERE/'libdft_ngif.cpp').read_text();marker='// ABI_CONTRACT -- replaced by header offsets verified against target ELF DWARF.'
    check(body.count(marker)==1,'ABI insertion marker changed')
    body=body.replace(marker,'\n'.join(f'static const unsigned {k}={v};' for k,v in fields.items()))
    dest=out/'libdft_ngif.cpp';dest.write_text(body)
    save(out/'adapter-layout.json',fields)
    return dest


def audit(lib,out):
    core=(lib/'src/libdft_core.cpp').read_text()
    ignored=[]
    for name in ('SHL','SHR','SAR'):
        tail=core.split('case XED_ICLASS_'+name+':',1)[1].split('break;',1)[0]
        lines=[l.strip() for l in tail.splitlines() if l.strip()]
        check(all(re.fullmatch(r'case XED_ICLASS_\w+:',line) for line in lines),'Upstream shift dispatcher changed; re-audit')
        ignored.append(name)
    result=dict(revision=shared.LIBDFT_REV,core_sha256=shared.sha(lib/'src/libdft_core.cpp'),
                ignored_scalar_shift_opcodes=ignored,propagation_modified=False,
                qualification='Raw upstream behavior; dispatcher case membership is not semantic coverage',
                scoring='GIF format source coverage/extras, not a common instruction-taint oracle')
    save(out/'upstream-semantics.json',result)
    return result


def compare_reference(observed,expected):
    check(len(observed)==len(expected),'Query count differs from independent reference')
    rows=[]
    for a,b in zip(observed,expected):
        check(a['sequence']==b['sequence'],'Invocation sequence differs')
        actual,required=set(a['source_file_offsets']),set(b['source_file_offsets'])
        rows.append(dict(sequence=b['sequence'],value_match=a['value']==b['value'],
                         exact_format_sources=actual==required,covered_required_bytes=len(actual&required),
                         missing_required_bytes=sorted(required-actual),additional_source_bytes=sorted(actual-required)))
    return dict(queries=len(rows),value_matches=sum(r['value_match'] for r in rows),
                exact_format_sources=sum(r['exact_format_sources'] for r in rows),
                covered_required_bytes=sum(r['covered_required_bytes'] for r in rows),
                missing_required_bytes=sum(len(r['missing_required_bytes']) for r in rows),
                additional_source_bytes=sum(len(r['additional_source_bytes']) for r in rows),rows=rows)


def run_image(prefix,binary,path,folder,indexed,out,timeout):
    folder.mkdir()
    stdout=shared.command([*prefix,binary,*(['--indexed'] if indexed else []),'--outbase','image',path],out,cwd=folder,timeout=timeout)
    (folder/'stdout.txt').write_text(stdout)
    check('LoadGif() returned -' not in stdout,'Business decoder rejected image')
    outputs=list(folder.glob('*.tga'));check(len(outputs)==1,'Expected exactly one converted image')
    size,pixels=tga_rgb(outputs[0])
    with Image.open(path) as im:check(size==im.size and pixels==im.convert('RGB').tobytes(),'Converted pixels differ from input')
    return stdout,shared.sha(outputs[0])


def execute(args,out,report):
    report['stage']='prepare_patched_native_target'
    binary,source,inputs=fixture(args,out)
    plan=query.plan(binary,source,out);save(out/'plan.json',plan)
    report['binary_sha256']=plan['binary_sha256']
    pin,lib=shared.dependencies(args,out)
    report['semantics']=audit(lib,out)
    report['stage']='build_boundary_tools'
    built=shared.build_tools(pin,lib,out,expand_adapter(plan,out),'libdft_ngif')
    manifest={}
    for original in sorted((lib/'src').rglob('*')):
        if original.is_file() and original.suffix in ('.c','.cpp','.h'):
            rel=original.relative_to(lib);check(shared.sha(original)==shared.sha(out/'libdft-build'/rel),'Upstream propagation source changed')
            manifest[str(rel)]=shared.sha(original)
    save(out/'upstream-source-manifest.json',manifest)
    report['compiled']=True
    if args.mode=='build-tools':report['stage']='compiled_not_executed';return
    report['stage']='pin_startup'
    shared.command([pin/'pin','-t',built['nullpin'],'--','/bin/true'],out,timeout=args.timeout)
    report['pin_startup_passed']=True
    for name in CASES:
        path=inputs/name/'normal.gif';data=path.read_bytes()
        for indexed in (False,True):
            case=out/(name+('-indexed' if indexed else '-truecolor'));case.mkdir()
            result=dict(input=name,indexed=indexed,methods={});report['cases'].append(result)
            report['stage']='native_comparison'
            native_stdout,native_hash=run_image([],binary,path,case/'native',indexed,out,args.timeout)
            null_stdout,null_hash=run_image([pin/'pin','-t',built['nullpin'],'--'],binary,path,case/'nullpin',indexed,out,args.timeout)
            check((native_stdout,native_hash)==(null_stdout,null_hash),'Nullpin changed business output')
            for method,enabled in (('boundary_replay',False),('libdft64',True)):
                folder=case/method;raw=folder/'raw.jsonl';item=dict(status='unknown');result['methods'][method]=item
                try:
                    stdout,output_hash=run_image([pin/'pin','-t',built['libdft_ngif'],'-enable_taint',str(int(enabled)),
                        '-input_file',path,'-origin_log',raw,'--'],binary,path,folder,indexed,out,args.timeout)
                    check((stdout,output_hash)==(native_stdout,native_hash),'Instrumented run changed business output')
                    trace,external,detail=read_log(raw,plan,data,enabled)
                    save(folder/'transport.json',trace);save(folder/'diagnostics.json',detail)
                    if enabled:
                        observed=external
                        save(folder/'inference.json',dict(method=method,queries=external,original_propagation=True,
                            semantics_qualified=False,ignored_shift_executions=detail['ignored_shift_executions']))
                    else:
                        replay=query.infer(plan,trace,data);save(folder/'inference.json',replay);observed=replay['queries']
                        check(len(observed)==len(detail['instruction_paths']),'Diagnostic path count mismatch')
                        for actual,pcs in zip(observed,detail['instruction_paths']):
                            check(actual['instruction_path_sha256']==hashlib.sha256(json.dumps(pcs).encode()).hexdigest(),'Replayed path differs from native execution')
                    # Independent truth is generated ONLY after this tool's
                    # inference. Neither native adapter nor replay reads it.
                    reference,pixels=decode(parse(data))
                    with Image.open(path) as im:check(im.tobytes()==pixels,'Reference LZW differs from Pillow')
                    save(case/'reference.json',reference)
                    evaluation=compare_reference(observed,reference);save(folder/'evaluation.json',evaluation)
                    item.update(status='observed',**{k:v for k,v in evaluation.items() if k!='rows'},
                                ignored_shift_executions=detail['ignored_shift_executions'],native_pixels_match=True)
                except Exception as exc:
                    item['reason']=str(exc);folder.mkdir(exist_ok=True);(folder/'failure.txt').write_text(traceback.format_exc())
                save(out/'summary.json',report)
    report['stage']='comparison_complete'
    report['observed_method_runs']=sum(m['status']=='observed' for c in report['cases'] for m in c['methods'].values())
    report['unknown_method_runs']=16-report['observed_method_runs']
    report['all_runs_observed']=report['observed_method_runs']==16


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('build-tools','run'));p.add_argument('--source',type=Path)
    p.add_argument('--validation',type=Path);p.add_argument('--pin-root',type=Path);p.add_argument('--libdft',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--timeout',type=int,default=180)
    args=p.parse_args()
    for key in ('source','validation','pin_root','libdft'):
        if getattr(args,key):setattr(args,key,getattr(args,key).resolve())
    out=(args.output or ROOT/'artifacts'/('ngiflib-comparison-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    report=dict(mode=args.mode,stage='initialization',compiled=False,pin_startup_passed=False,cases=[],
                bpf_executed=False,performance_eligible=False,external_baseline_qualified=False,
                scope='Patched original converter; ordinary images; GetByteStr source bytes to GetGifWord AX',
                our_method='boundary_replay with bit routing, not selected',transport='Separate Pin observation-only and original-libdft runs')
    evidence=out/'adapter-sources';evidence.mkdir()
    paths=[HERE/n for n in ('compare_host.py','host_records.py','libdft_ngif.cpp','query.py','gif_reference.py','validate_normal.py')]
    paths += [ROOT/'scripts'/n for n in ('c_bit_machine.py','interproc_model.py','hybrid_model.py','language_adapters.py')]
    paths += [HERE.parent/'checkout-payment-path/external_compare.py']
    for path in paths:
        dest=evidence/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    save(out/'adapter-identity.json',dict(repository_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         files={str(p.relative_to(ROOT)):shared.sha(p) for p in paths}))
    try:execute(args,out,report)
    except Exception as exc:
        report['failure']=str(exc);(out/'failure.txt').write_text(traceback.format_exc())
        raise
    finally:
        save(out/'summary.json',report)
        print('Return this result archive: '+shutil.make_archive(str(out),'zip',root_dir=out.parent,base_dir=out.name),flush=True)
    if args.mode=='run' and not report.get('all_runs_observed'):raise SystemExit(2)


if __name__=='__main__':main()
