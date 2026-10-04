#!/usr/bin/env python3
"""Host runner for instruction-derived provenance in a Go byte loop."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback
import zipfile
import byte_capture
from byte_provenance import infer
from go_byte_adapter import plan_binary
from hybrid_provenance import ROOT, save
from string_capture import collect

SCENARIO=ROOT/'scenarios/go-byte-provenance'
SUITES={'instruction':('forward','reverse'),'assignment':('assign','overwrite')}


def build(out,variant):
    out.mkdir(parents=True,exist_ok=True)
    go=os.environ.get('TRACEFUSION_GO') or shutil.which('go')
    if not go:raise RuntimeError('Go not visible; preserve PATH when using sudo')
    env=dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GO111MODULE='off',
             GOTOOLCHAIN='local',GOTELEMETRY='off',GOFLAGS='',GOEXPERIMENT='',GOAMD64='v1')
    version=subprocess.check_output([go,'version'],env=env,text=True).strip()
    if not any((' '+v+' ') in version for v in ('go1.25.4','go1.25.5')):
        raise RuntimeError('Byte ABI pilot accepts Go 1.25.4/1.25.5; got '+version)
    shutil.copyfile(SCENARIO/'main.go',out/'main.go')
    shutil.copyfile(SCENARIO/(variant+'.go'),out/'operations.go')
    binary=out/'byte-target'
    command=[go,'build','-buildvcs=false','-buildmode=exe','-gcflags=-l','-o',str(binary),str(out/'main.go'),str(out/'operations.go')]
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=180)
    save(out/'build.json',{'command':command,'go':version,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
         'source_sha256':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('main.go','operations.go')}})
    result.check_returncode()
    # The planner receives only the binary and toolchain, not the variant/oracle.
    plan=plan_binary(binary,go,env,out);save(out/'plan.json',plan)
    return plan


def fixtures(out,suite='instruction'):
    folder=out/'inputs';folder.mkdir()
    for field in ('A','B','C'):(folder/(field+'.txt')).write_bytes(b'SAME')
    entries=[]
    for variant in SUITES[suite]:
        indices=[3,2,1,0] if variant=='reverse' else [0,1,2,3]
        for selected in ('a','c'):
            name=variant+'_'+selected;request={f:str(folder/(f+'.txt')) for f in ('A','B','C')}
            request['UseC']=selected=='c';save(folder/(name+'.json'),request)
            initial='source:3' if selected=='c' else 'source:1'
            source='source:2' if variant=='overwrite' else initial
            expected={'case':name,'variant':variant,'sources':[source],
                'excluded':[s for s in ('source:1','source:2','source:3') if s!=source],
                'output':{'result':bytes(b'SAME'[i]^(0x20 if suite=='instruction' else 0) for i in indices).decode()}}
            if suite=='instruction':
                expected['byte_sources']=[{'output_byte':i,'origins':[{'source':source,'byte':j}]} for i,j in enumerate(indices)]
            else:
                expected.update(source_versions=[[initial],sorted([initial,'source:2']),['source:2']] if variant=='overwrite' else [[initial]],
                    overwritten_sources=[initial] if variant=='overwrite' else [],total_writes=8 if variant=='overwrite' else 4)
            entries.append(expected)
    save(out/'oracle.json',entries)
    return [(o['case'],o['variant']) for o in entries]


def score(result,expected):
    if result['status']!='resolved_under_instruction_model':return {'passed':False,'reason':result}
    actual=set(result['sources']);wanted=set(expected['sources'])
    tp,fp,fn=len(actual&wanted),len(actual-wanted),len(wanted-actual)
    metrics={'source_relations':{'tp':tp,'fp':fp,'fn':fn,'precision':tp/max(1,tp+fp),'recall':tp/max(1,tp+fn)}}
    checks={'sources_match':result['sources']==expected['sources'],
            'excluded_match':result['noncontributing_reads']==expected['excluded'],
            'output_matches':result['output']==expected['output']}
    if 'byte_sources' in expected:
        actual={(r['output_byte'],o['source'],o['byte']) for r in result['byte_sources'] for o in r['origins']}
        wanted={(r['output_byte'],o['source'],o['byte']) for r in expected['byte_sources'] for o in r['origins']}
        tp,fp,fn=len(actual&wanted),len(actual-wanted),len(wanted-actual)
        checks['byte_mapping_matches']=result['byte_sources']==expected['byte_sources']
        metrics['byte_origin_relations']={'tp':tp,'fp':fp,'fn':fn,'precision':tp/max(1,tp+fp),'recall':tp/max(1,tp+fn)}
    if 'source_versions' in expected:
        checks.update(source_versions_match=[v['sources'] for v in result['source_versions']]==expected['source_versions'],
            old_origins_removed=result['overwritten_sources']==expected['overwritten_sources'],
            writes_match=result['total_writes']==expected['total_writes'],
            same_value_versions=all(v['output_hex']==b'SAME'.hex() for v in result['source_versions']))
    return {'passed':all(checks.values()),**checks,**metrics,
            'replayed_instructions':len(result['instruction_steps'])}


def negative_checks(document,plan,include_overwrite=False):
    if infer(document,plan)['status']!='resolved_under_instruction_model':
        return [{'case':'baseline','passed':False}]
    results=[]
    loads={n['site'] for n in plan['instructions'] if n['op']=='movzx'}
    names=['capture_loss','missing_instruction','wrong_register','wrong_load','unbound_input','wrong_json']
    if include_overwrite:names.append('missing_final_store')
    for name in names:
        bad=deepcopy(document)
        ordered=sorted(bad['events'],key=lambda e:(e['timestamp'],e['sequence']))
        if name=='capture_loss':bad['capture_errors']=['injected loss']
        elif name=='missing_instruction':
            victim=next(e for e in ordered if e['site'] in loads)
            bad['events'].remove(victim)
        elif name=='wrong_register':
            victim=next(e for e in ordered if e['site'] in loads);victim['registers']['rax']^=1
        elif name=='wrong_load':
            victim=next(e for e in ordered if e['site'] in loads)
            value=victim['values']['load'];value['hex']=bytes([bytes.fromhex(value['hex'])[0]^1]).hex()
        elif name=='unbound_input':
            value=next(e for e in ordered if e['op']=='work' and e['phase']=='pre')['values']['src']
            value['pointer']=123;value['key']='7b:4'
        elif name=='missing_final_store':
            stores={n['site'] for n in plan['instructions'] if n['op']=='mov' and n['args'][1]['kind']=='mem'}
            victim=next(e for e in reversed(ordered) if e['site'] in stores)
            bad['events'].remove(victim)
        else:
            value=next(e for e in ordered if e['op']=='json' and e['phase']=='post')['values']['json']
            data=b'{"result":"NOPE"}';value['hex']=data.hex();value['key']=f'{value["pointer"]:x}:{len(data)}'
        bad['stats']['submitted']=len(bad['events'])
        result=infer(bad,plan);results.append({'case':name,'passed':result['status']=='unknown','actual':result})
    return results


def evaluate_pairs(results,documents,outputs):
    checks={}
    for variant in ('forward','reverse'):
        a,c=variant+'_a',variant+'_c'
        checks[variant]={
            'same_binary':documents[a]['binary_sha256']==documents[c]['binary_sha256'],
            'same_output':outputs[a]==outputs[c],
            'origins_switch':results[a].get('sources')==['source:1'] and results[c].get('sources')==['source:3'],
        }
    for selected in ('a','c'):
        f,r=results['forward_'+selected],results['reverse_'+selected]
        checks['index_order_'+selected]={
            'forward':[o['byte'] for row in f.get('byte_sources',[]) for o in row['origins']]==[0,1,2,3],
            'reverse':[o['byte'] for row in r.get('byte_sources',[]) for o in row['origins']]==[3,2,1,0],
            'different_output':outputs['forward_'+selected]!=outputs['reverse_'+selected],
        }
    return {'passed':all(all(c.values()) for c in checks.values()),'checks':checks}


def evaluate_assignment(results,documents,outputs):
    checks={}
    for variant in ('assign','overwrite'):
        a,c=variant+'_a',variant+'_c'
        checks[variant]={'same_binary':documents[a]['binary_sha256']==documents[c]['binary_sha256'],
                        'same_output':outputs[a]==outputs[c]}
    for selected in ('a','c'):
        before,after='assign_'+selected,'overwrite_'+selected
        source='source:3' if selected=='c' else 'source:1'
        checks[selected]={
            'initial_origin':results[before].get('sources')==[source],
            'final_origin':results[after].get('sources')==['source:2'],
            'old_origin_removed':results[after].get('overwritten_sources')==[source],
            'unchanged_output':outputs[before]==outputs[after],
        }
    return {'passed':all(all(c.values()) for c in checks.values()),'checks':checks}


def run(out,suite='instruction'):
    ok=False
    try:
        save(out/'environment.json',{'platform':platform.platform(),'python':sys.executable,'root':os.geteuid()==0})
        plans={v:build(out/v,v) for v in SUITES[suite]}
        cases=fixtures(out,suite);documents={};inferred={};outputs={}
        for name,variant in cases:
            print('Collecting '+name,flush=True)
            with (out/(name+'.log')).open('w') as log:
                result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'collect','--plan',str(out/variant/'plan.json'),
                    '--input',str(out/'inputs'/(name+'.json')),'--output',str(out/name)],stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                print((out/(name+'.log')).read_text()[-12000:],file=sys.stderr)
                raise RuntimeError('Capture failed: '+name)
            documents[name]=json.loads((out/name/'events.json').read_text())
            inferred[name]=infer(documents[name],plans[variant]);save(out/name/'inference.json',inferred[name])
            outputs[name]=json.loads((out/name/'target.stdout').read_text())
        # Oracle and variant-specific expected index order enter only evaluation.
        oracle=json.loads((out/'oracle.json').read_text())
        scored=[dict(case=o['case'],**score(inferred[o['case']],o),program_output_matches=outputs[o['case']]==o['output']) for o in oracle]
        negative_variant=SUITES[suite][-1]
        negatives=negative_checks(documents[negative_variant+'_c'],plans[negative_variant],include_overwrite=suite=='assignment')
        pairs=(evaluate_assignment if suite=='assignment' else evaluate_pairs)(inferred,documents,outputs)
        ok=all(r['passed'] and r['program_output_matches'] for r in scored) and all(n['passed'] for n in negatives) and pairs['passed']
        report={'all_passed':ok,'suite':suite,'cases':scored,'negative_checks':negatives,'pairs':pairs,
                'scope':('Source-set propagation and full overwrite on four controlled runs; byte cells are internal evidence'
                         if suite=='assignment' else 'Controlled leaf instruction replay; byte-origin accuracy on four runs; no arbitrary Go/library coverage claim')}
        save(out/'evaluation.json',report);print(json.dumps(report),flush=True)
    except Exception:
        error=traceback.format_exc();(out/'runner-error.txt').write_text(error);print(error,file=sys.stderr)
    finally:
        save(out/'run-status.json',{'completed':ok})
        archive=out.with_name(out.name+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(out.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(out.parent))
        if os.geteuid()==0 and os.environ.get('SUDO_UID','').isdigit() and os.environ.get('SUDO_GID','').isdigit():
            os.chown(archive,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
        print('Return this archive: '+str(archive),flush=True)
    return 0 if ok else 1


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    for name in ('build','run'):
        s=sub.add_parser(name);s.add_argument('--output',type=Path);s.add_argument('--suite',choices=SUITES,default='instruction')
    s=sub.add_parser('collect');s.add_argument('--plan',type=Path,required=True);s.add_argument('--input',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('analyze');s.add_argument('--plan',type=Path,required=True);s.add_argument('--events',type=Path,required=True)
    args=p.parse_args()
    if args.command=='collect':
        plan=json.loads(args.plan.read_text());doc=collect(Path(plan['binary']),plan,args.input.read_bytes(),args.output,transport=byte_capture)
        return int(bool(doc['capture_errors']) or doc['returncode']!=0)
    if args.command=='analyze':
        print(json.dumps(infer(json.loads(args.events.read_text()),json.loads(args.plan.read_text())),indent=2));return 0
    out=(args.output or ROOT/'artifacts'/('go-byte-provenance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    if args.command=='build':
        for variant in SUITES[args.suite]:
            plan=build(out/variant,variant);print(json.dumps({'variant':variant,'sites':len(plan['sites']),'instructions':len(plan['instructions'])}))
        print('Build output: '+str(out));return 0
    return run(out,args.suite)

if __name__=='__main__':raise SystemExit(main())
