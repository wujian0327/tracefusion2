#!/usr/bin/env python3
"""Native original-cJSON parser capture, libdft core calibration, and our replay.

Fresh Pin process per decoder invocation. Source/target identity is bound by
objects and offsets; source tags from original libdft are verification-only.
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import sys
import traceback

from parser_local import fixture, NAMES
from parser_core import build, replay, require, decode
from parser_ours import infer
from preflight import HERE, ROOT, CASES, oracle, command, save, sha
sys.path.insert(0,str(HERE.parent/'checkout-payment-path'))
import external_compare as shared


def records(path):return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def check_completion(rows,target):
    require(rows and rows[-1]['kind']=='finish','missing finish')
    f=rows[-1]
    require(sum(r['kind']=='finish' for r in rows)==1 and not any(r['kind']=='error' for r in rows),'native error')
    require(f['exit_code']==0 and not f['bad'] and not f['active'] and
            f['threads']==1 and f['contexts']==0 and f['cases']==len(CASES),'native completion contract')
    require(f['starts']==f['sinks']==(1 if target else 0),'query boundaries')
    require([r['case'] for r in rows if r['kind']=='case']==list(range(1,len(CASES)+1)),'case order')
    for r,c in zip([r for r in rows if r['kind']=='case'],CASES):
        require(r['data']==(c['text'].encode()+b'\0').hex(),'actual source input')
    ended=[r for r in rows if r['kind']=='parser_end']
    require([r['root'] for r in ended]==list(range(1,f['roots']+1)),'root coverage')
    fields=[r for r in rows if r['kind']=='field']
    require([(r['case'],r['query']) for r in fields]==
            [(i,q) for i,c in enumerate(CASES,1) for q in range(len(c['paths']))],'field coverage')
    return f


def convert(rows,plan,root):
    f=check_completion(rows,root)
    syms=[r for r in rows if r['kind']=='symbol']
    require(len(syms)==5 and [s['name'] for s in syms]==list(NAMES),'symbols')
    biases=set()
    for s in syms:
        a,n=plan['symbols'][s['name']]
        require(s['end']-s['begin']==n,'symbol length');biases.add(s['begin']-a)
    require(len(biases)==1,'load bias');bias=biases.pop()
    sources=[r for r in rows if r['kind']=='source'];sinks=[r for r in rows if r['kind']=='sink']
    states=[r for r in rows if r['kind']=='state']
    require(len(sources)==len(sinks)==1 and len(states)==f['steps'],'record count')
    source,sink=sources[0],sinks[0]
    require(source['root']==root and source['item']==sink['item'] and
            source['allocation']==sink['address'],'object identity')
    require(states[0]['pc']==source['entry_pc'],'entry PC')
    require(rows.index(source)<rows.index(states[0])<rows.index(sink),'boundary order')
    instructions=[]
    for i,state in enumerate(states,1):
        require(state['step']==i,'steps')
        pc=state['pc']-bias;raw=bytes.fromhex(state['bytes'])
        segs=[s for s in plan['segments'] if s['address']<=pc and
              pc+len(raw)<=s['address']+len(bytes.fromhex(s['data']))]
        require(len(segs)==1,'instruction ELF address')
        s=segs[0];off=pc-s['address']
        require(raw==bytes.fromhex(s['data'])[off:off+len(raw)],'instruction ELF bytes')
        instructions.append({k:state[k] for k in ('step','pc','bytes','registers','fs_base')})
    source={k:v for k,v in source.items() if k not in ('kind','case','root')}
    sink={k:v for k,v in sink.items() if k!='kind' and k!='allocation_tags'}
    trace=dict(schema='cjson-parser-trace-v1',transport='native Pin read-only decoder observer',
               native_capture=True,complete=True,source=source,sink=sink,instructions=instructions,
               load_bias=bias,ranges=[(s['begin'],s['end']) for s in syms[:3]])
    require(decode(instructions[-1]).mnemonic=='ret' and syms[0]['begin']<=instructions[-1]['pc']<syms[0]['end'],'root return')
    return trace,states,sinks[0]


def main(a):
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',performance_eligible=False,queries=[],native_core_calibration=False)
    try:
        binary,plan=fixture(a.source.resolve(),out)
        native=(out/'native.jsonl').read_text()
        report['environment']=shared.hardware()
        pin,lib=shared.dependencies(a,out)
        exe,report['extraction']=build(lib,out/'offline-core')
        tools=shared.build_tools(pin,lib,out,HERE/'parser_capture.cpp','cjson_parser_capture')
        for rel,digest in report['extraction']['upstream_sha256'].items():
            require(sha(out/'libdft-build'/rel)==digest,'reference upstream source differs')
        if a.build_only:
            report['status']='built_native_parser_tools_not_run';return
        null=shared.command([pin/'pin','-t',tools['nullpin'],'--',binary],out)
        require(null==native,'nullpin business output')
        index=out/'index';index.mkdir()
        text=shared.command([pin/'pin','-t',tools['cjson_parser_capture'],'-root','0',
                             '-origin_log',index/'observations.jsonl','--',binary],index)
        require(text==native,'index business output')
        (index/'stdout.jsonl').write_text(text)
        index_rows=records(index/'observations.jsonl');check_completion(index_rows,0)
        fields={(r['case'],r['query']):r for r in index_rows if r['kind']=='field'}
        roots=[r for r in index_rows if r['kind']=='parser_end']
        for ci,case in enumerate(CASES,1):
            expected=oracle(case)
            for qi,truth in enumerate(expected['queries']):
                field=fields[ci,qi];q=dict(case=case['name'],path=truth['path'],status='unknown')
                report['queries'].append(q)
                if truth['status']=='no_sink':
                    require(field['item']==field['address']==0,'unexpected field target')
                    q['status']='native_no_sink';continue
                require(field['address'] and field['data']==truth['value_hex'],'field target value')
                # This explicit scope is fixed in advance, not chosen after seeing accuracy.
                if truth['format_field_origin']=='replacement':
                    q.update(status='not_in_parser_scope',reason='post-parse replacement');continue
                matches=[r for r in roots if r['case']==ci and r['item']==field['item'] and
                         r['address']==field['address'] and r['success']]
                require(len(matches)==1,'ambiguous object/decoder binding')
                match=matches[0];span=expected['input_string_spans'][truth['path']]
                require(match['offset']==span['begin']-1,'source token binding')
                q['root']=match['root'];directory=out/f'case-{ci:02d}-query-{qi:02d}';directory.mkdir()
                try:
                    text=shared.command([pin/'pin','-t',tools['cjson_parser_capture'],'-root',str(q['root']),
                        '-origin_log',directory/'observations.jsonl','--',binary],directory,timeout=180)
                    (directory/'stdout.jsonl').write_text(text);require(text==native,'business output changed')
                    rows=records(directory/'observations.jsonl');trace,states,sink=convert(rows,plan,q['root'])
                    require(trace['source']['offset']==span['begin']-1 and trace['source']['data']==
                            (case['text'].encode()+b'\0').hex(),'repeated source binding')
                    native_fields=[r for r in rows if r['kind']=='field' and r['case']==ci and r['query']==qi]
                    require(len(native_fields)==1 and native_fields[0]['item']==sink['item'] and
                            native_fields[0]['address']==sink['address'],'repeated target object binding')
                    save(directory/'trace.json',trace)
                    libresult=replay(exe,trace);save(directory/'libdft-offline.json',libresult)
                    ours=infer(plan,trace);save(directory/'ours.json',ours)
                    require(libresult['allocation_labels']==sink['allocation_tags'],'final original/offline tags differ')
                    for i,state in enumerate(states):
                        actual=libresult['intermediate_tags_before'][i*17:(i+1)*17]
                        require([x['bytes'] for x in actual]==state['tag_bytes']+[state['allocation_tags']],
                                'original/offline intermediate tags differ at step '+str(i+1))
                    require(sink['data']==truth['value_hex'],'value oracle')
                    lib_offsets=sorted({x-1 for b in libresult['byte_labels'] for x in b})
                    empty=case.get('semantics')=='control_diagnostic' or truth['empty_content']
                    diagnostics={name:all(span['begin']<=x<span['end'] for x in offsets) and
                                 bool(offsets)==(not empty)
                                 for name,offsets in [('ours',ours['source_offsets']),('libdft',lib_offsets)]}
                    q.update(status='native_calibrated',steps=len(states),
                             intermediate_byte_checks=len(states)*(128+trace['source']['allocation_size']),
                             ours_source_offsets=ours['source_offsets'],libdft_source_offsets=lib_offsets,
                             field_presence_diagnostics=diagnostics)
                except Exception as exc:
                    q['reason']=str(exc);(directory/'failure.txt').write_text(traceback.format_exc())
        eligible=[q for q in report['queries'] if q['status'] not in ('native_no_sink','not_in_parser_scope')]
        report['native_core_calibration']=len(eligible)==18 and all(q['status']=='native_calibrated' for q in eligible)
        report['status']='native_parser_calibrated' if report['native_core_calibration'] else 'failed'
        if not report['native_core_calibration']:raise RuntimeError('See preserved query failures')
    except Exception as exc:report.update(status='failed',error=repr(exc));raise
    finally:
        save(out/'validation.json',report)
        shutil.copytree(HERE,out/'adapter-source',ignore=shutil.ignore_patterns('__pycache__'))
        support=out/'support-source';support.mkdir()
        for path in (ROOT/'scripts/c_bit_machine.py',ROOT/'scripts/interproc_model.py',
                     ROOT/'scripts/hybrid_model.py',ROOT/'scripts/language_adapters.py',
                     HERE.parent/'libdft-offline/build_core.py',HERE.parent/'libdft-offline/core.cpp',
                     HERE.parent/'libdft-offline/pin.H',HERE.parent/'libdft-offline/replay.py',
                     HERE.parent/'checkout-payment-path/external_compare.py'):
            shutil.copyfile(path,support/path.name)
        save(out/'support-source-sha256.json',{p.name:sha(p) for p in support.iterdir()})
        archive=shutil.make_archive(str(out),'zip',out.parent,out.name)
        print(json.dumps(dict(status=report['status'],directory=str(out),archive=archive)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'artifacts/external-tools/cjson-v1.7.19')
    p.add_argument('--libdft',type=Path);p.add_argument('--pin-root',type=Path)
    p.add_argument('--build-only',action='store_true')
    p.add_argument('--output',type=Path,default=ROOT/'artifacts'/('cjson-parser-host-'+
                   datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')))
    main(p.parse_args())
