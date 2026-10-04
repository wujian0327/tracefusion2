#!/usr/bin/env python3
"""Build/run the three-read, two-input string lineage pilot."""
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
from hybrid_provenance import ROOT, save
from go_string_adapter import plan_binary
from string_capture import collect
from value_lineage import infer

SCENARIO=ROOT/'scenarios/go-string-provenance'


def build(out):
    out.mkdir(parents=True,exist_ok=True)
    go=os.environ.get('TRACEFUSION_GO') or shutil.which('go')
    if not go:raise RuntimeError('Go is not visible; preserve PATH when using sudo')
    env=dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GO111MODULE='off',
             GOTOOLCHAIN='local',GOTELEMETRY='off',GOFLAGS='',GOEXPERIMENT='',GOAMD64='v1')
    version=subprocess.check_output([go,'version'],env=env,text=True).strip()
    if not any((' '+v+' ') in version for v in ('go1.25.4','go1.25.5')):
        raise RuntimeError('String ABI pilot accepts Go 1.25.4/1.25.5; got '+version)
    source=out/'main.go';shutil.copyfile(SCENARIO/'main.go',source)
    binary=out/'string-target'
    command=[go,'build','-buildvcs=false','-buildmode=exe','-gcflags=-l','-o',str(binary),str(source)]
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=180)
    save(out/'build.json',{'command':command,'go':version,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
                           'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    result.check_returncode()
    plan=plan_binary(binary,go,env,out)
    save(out/'plan.json',plan)
    return binary,plan


def fixtures(out):
    entries=[]
    for name,phone,prefix,other in [('ordinary','13800138000','+86','UNUSED'),
                                    ('equal_values','SAME','SAME','SAME'),
                                    ('json_escaping','user"\\id','地区:','user"\\id')]:
        folder=out/'inputs'/name;folder.mkdir(parents=True)
        request={}
        for field,text in [('Phone',phone),('Prefix',prefix),('Other',other)]:
            path=folder/(field.lower()+'.txt');path.write_text(text)
            request[field]=str(path)
        save(folder/'request.json',request)
        entries.append({'case':name,'sources':['source:1','source:2'],'excluded':['source:3'],
                        'result':prefix+phone,
                        'edges':[['source:2','concat:1','left'],['source:1','concat:1','right'],
                                 ['concat:1','json:1','value'],['json:1','output:result','result']]})
    save(out/'oracle.json',entries)
    return [e['case'] for e in entries]


def negative_checks(doc,plan):
    if infer(doc,plan)['status']!='resolved_under_configured_summaries':
        return [{'case':'all','passed':False,'reason':'Valid baseline required'}]
    results=[]
    for name in ['capture_error','missing_source_pair','missing_concat_return','unknown_operand','corrupt_json']:
        bad=deepcopy(doc)
        if name=='capture_error':bad['capture_errors']=['injected loss']
        elif name=='missing_source_pair':
            ids=[s['id'] for s in plan['sites'] if s['op']=='source'][2:4]
            bad['events']=[e for e in bad['events'] if e['site'] not in ids]
        elif name=='missing_concat_return':
            bad['events']=[e for e in bad['events'] if not(e['op']=='concat' and e['phase']=='post')]
        elif name=='unknown_operand':
            next(e for e in bad['events'] if e['op']=='concat' and e['phase']=='pre')['values']['right']['key']='not-observed'
        else:
            next(e for e in bad['events'] if e['op']=='json' and e['phase']=='post')['values']['json']['hex']=b'{"result":"WRONG"}'.hex()
        bad['stats']['submitted']=len(bad['events'])
        result=infer(bad,plan)
        results.append({'case':name,'passed':result['status']=='unknown','actual':result})
    return results


def score(inferred,expected):
    if inferred['status']!='resolved_under_configured_summaries':return {'passed':False,'reason':inferred}
    actual=set(inferred['sources']);wanted=set(expected['sources'])
    aedges={(e['source'],e['target'],e['role']) for e in inferred['graph']['edges']}
    wedges={tuple(e) for e in expected['edges']}
    output=next(n['value'] for n in inferred['graph']['nodes'] if n['id']=='output:result')
    tp,fp,fn=len(actual&wanted),len(actual-wanted),len(wanted-actual)
    etp,efp,efn=len(aedges&wedges),len(aedges-wedges),len(wedges-aedges)
    return {'passed':not(fp or fn or efp or efn) and output==expected['result'] and set(inferred['noncontributing_reads'])==set(expected['excluded']),
            'source_relations':{'tp':tp,'fp':fp,'fn':fn,'precision':tp/max(1,tp+fp),'recall':tp/max(1,tp+fn)},
            'modeled_graph_edges':{'tp':etp,'fp':efp,'fn':efn},'output_matches':output==expected['result']}


def run(out):
    ok=False
    try:
        save(out/'environment.json',{'platform':platform.platform(),'python':sys.executable,'root':os.geteuid()==0})
        binary,plan=build(out)
        cases=fixtures(out)
        inferred={};documents={}
        for case in cases:
            print('Collecting '+case,flush=True)
            with (out/(case+'.log')).open('w') as log:
                result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'collect','--plan',str(out/'plan.json'),
                    '--input',str(out/'inputs'/case/'request.json'),'--output',str(out/case)],stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                print((out/(case+'.log')).read_text()[-10000:],file=sys.stderr)
                raise RuntimeError('Capture failed: '+case)
            doc=json.loads((out/case/'events.json').read_text());documents[case]=doc
            inferred[case]=infer(doc,plan);save(out/case/'inference.json',inferred[case])
        # Inference above neither receives nor opens the independent oracle.
        oracle=json.loads((out/'oracle.json').read_text())
        comparisons=[dict(case=o['case'],**score(inferred[o['case']],o)) for o in oracle]
        for o in oracle:
            output=json.loads((out/o['case']/'target.stdout').read_text())
            comparisons[cases.index(o['case'])]['program_output_matches']=output=={'result':o['result']}
        negatives=negative_checks(documents['equal_values'],plan)
        ok=all(x['passed'] and x['program_output_matches'] for x in comparisons) and all(x['passed'] for x in negatives)
        save(out/'evaluation.json',{'all_passed':ok,'cases':comparisons,'negative_checks':negatives,
             'scope':'Three controlled cases; modeled API operation edges, not complete instruction/byte lineage accuracy'})
        print(json.dumps({'all_passed':ok,'cases':comparisons,'negative_checks':len(negatives)}),flush=True)
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
        s=sub.add_parser(name);s.add_argument('--output',type=Path)
    s=sub.add_parser('collect');s.add_argument('--plan',type=Path,required=True);s.add_argument('--input',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('analyze');s.add_argument('--plan',type=Path,required=True);s.add_argument('--events',type=Path,required=True)
    args=p.parse_args()
    if args.command=='collect':
        plan=json.loads(args.plan.read_text());doc=collect(Path(plan['binary']),plan,args.input.read_bytes(),args.output)
        return int(bool(doc['capture_errors']) or doc['returncode']!=0)
    if args.command=='analyze':
        print(json.dumps(infer(json.loads(args.events.read_text()),json.loads(args.plan.read_text())),indent=2));return 0
    out=(args.output or ROOT/'artifacts'/('go-string-provenance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    if args.command=='build':
        binary,plan=build(out);print(json.dumps({'output':str(out),'sites':len(plan['sites'])}));return 0
    return run(out)

if __name__=='__main__':raise SystemExit(main())
