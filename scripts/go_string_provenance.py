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
    for name,phone,prefix,other,use_other,copy_value in [('ordinary','13800138000','+86','UNUSED',False,False),
                                    ('equal_values','SAME','SAME','SAME',False,False),
                                    ('json_escaping','user"\\id','地区:','user"\\id',False,False),
                                    ('branch_phone','SAME','+86','SAME',False,False),
                                    ('branch_other','SAME','+86','SAME',True,False),
                                    ('copy_phone','SAME','+86','SAME',False,True),
                                    ('copy_other','SAME','+86','SAME',True,True)]:
        folder=out/'inputs'/name;folder.mkdir(parents=True)
        # Paired runs use the same files; only the request selector changes.
        data_folder=out/'inputs'/'branch_data' if name.startswith(('branch_','copy_')) else folder
        data_folder.mkdir(exist_ok=True)
        request={'UseOther':use_other,'CopyValue':copy_value}
        for field,text in [('Phone',phone),('Prefix',prefix),('Other',other)]:
            path=data_folder/(field.lower()+'.txt');path.write_text(text)
            request[field]=str(path)
        save(folder/'request.json',request)
        chosen='source:3' if use_other else 'source:1'
        operand='copy:1' if copy_value else chosen
        entries.append({'case':name,'sources':sorted(['source:2',chosen]),
                        'excluded':['source:1' if use_other else 'source:3'],
                        'result':prefix+(other if use_other else phone),
                        'edges':([[chosen,'copy:1','input']] if copy_value else [])+
                                [['source:2','concat:1','left'],[operand,'concat:1','right'],
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


def copy_negative_checks(doc,plan):
    if infer(doc,plan)['status']!='resolved_under_configured_summaries':
        return [{'case':'copy_baseline','passed':False,'reason':'Valid copy baseline required'}]
    results=[]
    for name in ('missing_copy_pair','changed_copy_bytes','reused_copy_identity'):
        bad=deepcopy(doc)
        if name=='missing_copy_pair':
            bad['events']=[e for e in bad['events'] if e['op']!='copy']
        else:
            before=next(e for e in bad['events'] if e['op']=='copy' and e['phase']=='pre')['values']['value']
            after=next(e for e in bad['events'] if e['op']=='copy' and e['phase']=='post')['values']['value']
            if name=='changed_copy_bytes':after['hex']=b'WRONG'.hex()
            else:after['key']=before['key']
        bad['stats']['submitted']=len(bad['events'])
        result=infer(bad,plan)
        results.append({'case':name,'passed':result['status']=='unknown','actual':result})
    return results


def branch_pair_checks(inferred,documents,requests,outputs,prefix='branch'):
    a,b=prefix+'_phone',prefix+'_other'
    ra,rb=requests[a],requests[b]
    checks={
        'same_input_paths':all(ra[k]==rb[k] for k in ('Phone','Prefix','Other')),
        'different_selector':ra['UseOther'] is False and rb['UseOther'] is True,
        'same_binary':documents[a]['binary_sha256']==documents[b]['binary_sha256'],
        'same_output':outputs[a]==outputs[b],
        'same_observed_sites':[e['site'] for e in sorted(documents[a]['events'],key=lambda e:(e['timestamp'],e['sequence']))]
                              ==[e['site'] for e in sorted(documents[b]['events'],key=lambda e:(e['timestamp'],e['sequence']))],
        'sources_follow_selection':inferred[a].get('sources')==['source:1','source:2']
                                    and inferred[b].get('sources')==['source:2','source:3'],
    }
    return {'passed':all(checks.values()),'checks':checks,
            'scope':'Observed value dependencies; selector/control dependence is not included'}


def copy_checks(inferred,documents,requests,outputs):
    pair=branch_pair_checks(inferred,documents,requests,outputs,prefix='copy')
    checks={}
    for suffix in ('phone','other'):
        name='copy_'+suffix;baseline='branch_'+suffix
        nodes=inferred[name].get('graph',{}).get('nodes',[])
        copies=[n for n in nodes if n['kind']=='copy']
        checks[name]={
            'new_storage':len(copies)==1 and copies[0]['input_identity']!=copies[0]['output_identity'],
            'same_sources':bool(inferred[name].get('sources')) and inferred[name].get('sources')==inferred[baseline].get('sources'),
            'same_output':outputs[name]==outputs[baseline],
            'same_binary':documents[name]['binary_sha256']==documents[baseline]['binary_sha256'],
            'same_read_inputs':all(requests[name][k]==requests[baseline][k] for k in ('Phone','Prefix','Other','UseOther')),
            'copy_requested':requests[name]['CopyValue'] is True and requests[baseline]['CopyValue'] is False,
        }
    return {'passed':pair['passed'] and all(all(c.values()) for c in checks.values()),'pair':pair,'comparisons':checks}


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
        outputs={};requests={}
        for o in oracle:
            output=json.loads((out/o['case']/'target.stdout').read_text())
            outputs[o['case']]=output
            requests[o['case']]=json.loads((out/'inputs'/o['case']/'request.json').read_text())
            comparisons[cases.index(o['case'])]['program_output_matches']=output=={'result':o['result']}
        pair=branch_pair_checks(inferred,documents,requests,outputs)
        copies=copy_checks(inferred,documents,requests,outputs)
        negatives=negative_checks(documents['equal_values'],plan)+copy_negative_checks(documents['copy_other'],plan)
        ok=all(x['passed'] and x['program_output_matches'] for x in comparisons) and all(x['passed'] for x in negatives) and pair['passed'] and copies['passed']
        save(out/'evaluation.json',{'all_passed':ok,'cases':comparisons,'negative_checks':negatives,'branch_pair':pair,'copy_checks':copies,
             'scope':'Seven controlled cases; modeled API operation edges, not complete instruction/byte lineage accuracy'})
        print(json.dumps({'all_passed':ok,'cases':comparisons,'negative_checks':len(negatives),'branch_pair':pair,'copy_checks':copies}),flush=True)
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
