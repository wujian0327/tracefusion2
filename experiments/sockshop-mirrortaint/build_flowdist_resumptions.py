#!/usr/bin/env python3
"""Copy monitored Boot apps and add normal call-return observations only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile


def build(apps,out):
    out.mkdir(parents=True,exist_ok=False);here=Path(__file__).parent
    manifest=json.loads((apps/'manifest.json').read_text());classes=out/'tool';classes.mkdir()
    asm=[Path('artifacts/java-collection-deps')/(name+'-9.7.1.jar') for name in ('asm','asm-tree')]
    subprocess.run(['javac','--release','8','-cp',':'.join(map(str,asm)),'-d',str(classes),str(here/'FlowDistResumeCalls.java')],check=True,capture_output=True)
    counts={}
    for role,package in (('orders','orders'),('carts','cart'),('shipping','shipping')):
        source=apps/(role+'-flowdist.jar')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=manifest['apps'][role]['adapted_sha256']:raise ValueError('App changed')
        output=out/source.name;logs=[];changed=[]
        with ZipFile(source) as original,ZipFile(output,'w') as target:
            for entry in original.infolist():
                before=original.read(entry.filename);after=before
                if entry.filename.startswith('BOOT-INF/classes/works/weave/socks/'+package+'/') and entry.filename.endswith('.class'):
                    file=out/'class-input';result=out/'class-output';file.write_bytes(before)
                    run=subprocess.run(['java','-cp',':'.join(map(str,[classes,*asm])),'FlowDistResumeCalls',str(file),str(result)],capture_output=True,text=True,check=True,timeout=20)
                    logs.append(run.stdout+run.stderr);after=result.read_bytes()
                    if after!=before:changed.append(entry.filename)
                target.writestr(entry,after)
        (out/(role+'-resume.log')).write_text(''.join(logs));counts[role]=changed
        manifest['apps'][role]['adapted_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    manifest.update(normal_call_resumption_probes=True,resumption_source_build=str(apps),resumption_changed_entries=counts,
        resumption_tool_sha256=hashlib.sha256((here/'FlowDistResumeCalls.java').read_bytes()).hexdigest(),
        resumption_policy='Original monitor returnInto only after actual successful invokes, within methods after their existing enter probe; inverse canonical class comparison passed')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('apps','out'):parser.add_argument('--'+flag,type=Path,required=True)
    a=parser.parse_args();build(a.apps.resolve(),a.out.resolve())
