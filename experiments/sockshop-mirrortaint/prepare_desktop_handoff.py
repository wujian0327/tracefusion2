#!/usr/bin/env python3
"""Package committed code and explicit W3C experiment inputs; Docker images separate."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
from run_planned_service import ROOT, load, save, sha
from run_query_planner import JARS


def prepare(out):
    subprocess.run(['git','diff','--quiet','HEAD'],cwd=ROOT,check=True)
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if not branch:raise ValueError('A named branch is required for the clone command')
    out.mkdir(parents=True,exist_ok=False)
    build=ROOT/'artifacts/distributed-plans-w3c-final-build-20261015'
    capture=ROOT/'artifacts/distributed-paths-w3c-20261015'
    baseline=ROOT/'artifacts/distributed-paths-final-20261015'
    baseline_build=ROOT/'artifacts/distributed-plans-final-build-20261015'
    files=set(JARS)
    for directory in (build,capture):files.update(p for p in directory.rglob('*') if p.is_file())
    files.update([baseline/'cases.json',baseline/'results.md',baseline/'main-table.csv',baseline_build/'build.json',
                  ROOT/'artifacts/real-path-expansion-preflight-20261015/images.json'])
    for app in ('sockshop','trainticket'):files.add(baseline/app/'field-results.json')
    for role in load(build/'build.json')['inputs']:files.add(baseline_build/role/'plan.json')
    queries={role:{**record['query_config'],'jar':str((build/role/'original.jar').relative_to(ROOT))}
             for role,record in load(build/'build.json')['inputs'].items()}
    generated=out/'generated';generated.mkdir()
    save(generated/'queries-portable.json',queries)
    images={}
    for app in ('sockshop','trainticket'):
        observed=load(capture/app/'images.json');index={}
        for ref,record in observed.items():
            for name in [ref,*record['digests']]:index[name]=record
        for service,cfg in load(capture/app/'compose.lock.json')['services'].items():
            ref=cfg['image'];record=index[ref]
            item=images.setdefault(ref,{'image_id':record['id'],'services':[]});item['services'].append(app+'/'+service)
    save(generated/'images-lock.json',images)
    content={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}
    for p in generated.iterdir():content['artifacts/desktop-inputs/'+p.name]=sha(p)
    save(generated/'input-files.json',content)
    archive=out/'experiment-inputs.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
        for p in sorted(files):tar.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
        for p in sorted(generated.iterdir()):tar.add(p,arcname='artifacts/desktop-inputs/'+p.name,recursive=False)
    bundle=out/'tracefusion2.bundle'
    subprocess.run(['git','bundle','create',str(bundle),branch],cwd=ROOT,check=True)
    subprocess.run(['git','bundle','verify',str(bundle)],cwd=ROOT,check=True,capture_output=True)
    save(out/'handoff.json',{'commit':commit,'branch':branch,'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in (archive,bundle)},
        'artifact_files':len(content),'docker_images':len(images),'docker_images_included':False,
        'historical_baseline_build':'Manifest and local plans only; enough for answer comparison, not a complete old executable build.',
        'next':'Clone bundle, extract inputs, verify hashes, pull pinned image digests, rebuild for the new absolute workspace path. See experiments/sockshop-mirrortaint/DESKTOP-HANDOFF.md.'})
    (out/'START-HERE.txt').write_text('Commit: '+commit+'\n\ngit clone -b '+branch+' tracefusion2.bundle tracefusion2\ncd tracefusion2\ntar -xzf ../experiment-inputs.tar.gz\n\nRead experiments/sockshop-mirrortaint/DESKTOP-HANDOFF.md.\nDocker images are separate; image digests are in artifacts/desktop-inputs/images-lock.json.\n')
    print(json.dumps(load(out/'handoff.json'),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();prepare(args.out.resolve())
