#!/usr/bin/env python3
"""Native same-trace calibration: original Pin dispatcher vs offline extracted callbacks.

Adds read-only concrete-register/tag snapshots to the existing C adapter.
Original propagation source is not edited. Replay never receives reference tags.
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

from build_core import build, sha
from replay import REGS, replay, require

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'experiments/c-libdft')]
import compare as original


def adapter(out):
    src=ROOT/'experiments/c-libdft/libdft_c.cpp'
    text=src.read_text()
    marker='        if (entry && fid >= 3) ++helpers;'
    require(text.count(marker)==1,'adapter anchor changed')
    names=list(REGS)
    insertion='''
        // Read-only calibration evidence BEFORE upstream instruction propagation.
        out << "{\\"kind\\":\\"state\\",\\"step\\":" << steps << ",\\"pc\\":" << pc << ",\\"registers\\":{";
'''
    for i,name in enumerate(names):
        insertion+=f'        out << "{"," if i else ""}\\"{name}\\":" << PIN_GetContextReg(ctx, REG_{name.upper()});\n'
    insertion+='        out << "},\\"tag_bytes\\":[";\n'
    for i,name in enumerate(names):
        insertion+=f'        out << "{"," if i else ""}[";\n'
        insertion+=f'        for (unsigned b=0;b<8;++b) {{ if(b) out << ","; tags(tagmap_getb_reg(tid, DFT_REG_{name.upper()}, b)); }}\n'
        insertion+='        out << "]";\n'
    insertion+='        out << "],\\"sink_bytes\\":"; bytes(dst); out << "}" << std::endl;\n'
    path=out/'libdft_offline_capture.cpp'
    path.write_text(text.replace(marker,insertion+'\n'+marker))
    return path,{'base_sha256':sha(src.read_bytes()),'generated_sha256':sha(path.read_bytes())}


def convert(rows,evidence,sequence):
    finish=[x for x in rows if x['kind']=='finish']
    require(len(finish)==1 and rows[-1]==finish[0],'completion')
    f=finish[0]
    require(f['exit_code']==0 and not f['bad'] and not f['active'] and
            f['starts']==f['sinks']==f['threads']==1 and f['contexts']==0,'native capture contract')
    require(not any(x['kind']=='error' for x in rows),'native error')
    symbols=[x for x in rows if x['kind']=='symbol']
    require(len(symbols)==5 and len({x['id'] for x in symbols})==5,'symbols')
    bases=set()
    for s in symbols:
        begin,size=evidence['symbols'][s['name']]
        require(s['end']-s['begin']==size,'symbol size')
        bases.add(s['begin']-begin)
    require(len(bases)==1,'PIE load bias'); bias=bases.pop()
    sources=[x for x in rows if x['kind']=='source']; sinks=[x for x in rows if x['kind']=='sink']
    require(len(sources)==len(sinks)==1,'boundaries')
    source,sink=sources[0],sinks[0]
    require(source['sequence']==sink['sequence']==sequence,'query identity')
    require(source['byte_labels']==[[[i]]*4 for i in (1,2,3)],'source tags')
    states=[x for x in rows if x['kind']=='state']; ins=[x for x in rows if x['kind']=='instruction']
    require(len(states)==len(ins)==f['steps'] and 0<len(ins)<=4096,'step count')
    records=[]
    for i,(state,instruction) in enumerate(zip(states,ins),1):
        require(state['step']==instruction['step']==i and state['pc']==instruction['pc'],'state pairing')
        require(instruction['covered'] and instruction['tid']==source['tid'],'instruction coverage/context')
        require(set(state['registers'])==set(REGS),'register coverage')
        code=evidence['instructions'][state['pc']-bias]['bytes']
        records.append({'step':i,'pc':state['pc'],'bytes':''.join(code),'registers':state['registers']})
    trace={'schema':'libdft-offline-trace-v1','transport':'read-only Pin concrete-state callback',
           'native_capture':True,'complete':True,'function':source['function'],'steps':len(records),
           'ranges':[(s['begin'],s['end']) for s in symbols],
           'sources':[{'address':source['src']+i*4,'width':4,'label':i+1} for i in range(3)],
           'sink':{'address':source['dst'],'value':sink['value']},
           'inputs':{'values':source['values'],'count':source['count']},'instructions':records}
    return trace,states,sink


def main(a):
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    report={'status':'running','native_pin_equivalence':False,'performance_eligible':False,'queries':[]}
    try:
        pin,lib=original.shared.dependencies(a,out)
        exe,report['extraction']=build(lib,out/'offline-core')
        path,report['capture_adapter']=adapter(out)
        tools=original.shared.build_tools(pin,lib,out,path,'libdft_offline_capture')
        # Compare files actually built into the original Pin reference with offline provenance.
        for rel,digest in report['extraction']['upstream_sha256'].items():
            require(sha((out/'libdft-build'/rel).read_bytes())==digest,'Pin upstream source mismatch: '+rel)
        fixture=out/'fixture';fixture.mkdir()
        for name in ('main.c','operations.c','model.h'):
            shutil.copyfile(ROOT/'scenarios/loop-calls-provenance'/name,fixture/name)
        binary=fixture/'program'
        original.shared.command(['gcc','-O1','-g','-fPIE','-pie','-fno-if-conversion','-fno-if-conversion2',
            '-fno-inline','-fno-lto','-fno-ipa-icf','-fno-stack-protector','-fcf-protection=none',
            '-o',binary,fixture/'main.c',fixture/'operations.c'],out)
        evidence=original.binary_evidence(binary,out)
        native=original.shared.command([binary],out);(out/'native.jsonl').write_text(native)
        truth=original.truth_rows(native)
        if a.build_only:
            report['status']='built_native_pin_calibration_not_run'
            return
        null=original.shared.command([pin/'pin','-t',tools['nullpin'],'--',binary],out)
        require(original.truth_rows(null)==truth,'nullpin output')
        for seq in range(1,25):
            directory=out/f'query-{seq:02d}';directory.mkdir()
            q={'sequence':seq,'status':'unknown'};report['queries'].append(q)
            try:
                stdout=original.shared.command([pin/'pin','-t',tools['libdft_offline_capture'],
                    '-sequence',str(seq),'-origin_log',directory/'observations.jsonl','--',binary],directory,timeout=180)
                (directory/'stdout.jsonl').write_text(stdout)
                require(original.truth_rows(stdout)==truth,'business output changed')
                rows=[json.loads(s) for s in (directory/'observations.jsonl').read_text().splitlines()]
                trace,states,sink=convert(rows,evidence,seq)
                # The replay input deliberately excludes every native taint/tag field.
                (directory/'trace.json').write_text(json.dumps(trace,indent=2)+'\n')
                result=replay(exe,trace)
                (directory/'replay.json').write_text(json.dumps(result,indent=2)+'\n')
                require(result['byte_labels']==sink['byte_labels'] and result['labels']==sink['labels'],'sink tags differ')
                cursor=0
                for state in states:
                    expected=state['tag_bytes']+[state['sink_bytes']]
                    require(len(expected)==len(REGS)+1,'native shadow snapshot shape')
                    actual=result['intermediate_tags_before'][cursor:cursor+len(expected)]
                    require([r['bytes'] for r in actual]==expected,'intermediate tags differ at step '+str(state['step']))
                    cursor+=len(expected)
                expected_labels=[original.FIELDS.index(s)+1 for s in truth[seq-1]['expected_sources']]
                require(result['labels']==expected_labels and sink['value']==truth[seq-1]['expected_value'],'independent oracle mismatch')
                q.update(status='matched',steps=trace['steps'],labels=result['labels'],
                         intermediate_byte_checks=trace['steps']*(8*len(REGS)+4))
            except Exception as exc:
                q['reason']=str(exc);(directory/'failure.txt').write_text(traceback.format_exc())
        report['native_pin_equivalence']=all(q['status']=='matched' for q in report['queries']) and len(report['queries'])==24
        report['status']='pass_bounded_native_calibration' if report['native_pin_equivalence'] else 'failed'
        if not report['native_pin_equivalence']: raise RuntimeError('Inspect preserved per-query failures')
    except Exception as exc:
        report.update(status='failed',error=repr(exc));raise
    finally:
        original.save(out/'validation.json',report)
        shutil.copytree(Path(__file__).parent,out/'adapter-source',ignore=shutil.ignore_patterns('__pycache__'))
        archive=shutil.make_archive(str(out),'zip',out.parent,out.name)
        print(json.dumps({'status':report['status'],'directory':str(out),'archive':archive}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pin-root',type=Path)
    p.add_argument('--libdft',type=Path)
    p.add_argument('--build-only',action='store_true')
    p.add_argument('--output',type=Path,default=ROOT/'artifacts'/('libdft-offline-host-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')))
    main(p.parse_args())
