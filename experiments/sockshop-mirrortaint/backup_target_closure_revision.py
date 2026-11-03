"""Archive this batch without following source/capture reuse symlinks.

All old dependency references remain explicit. This is not a claim that the
entire historical repository is copied into a self-contained new archive.
"""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from run_planned_service import ROOT,HERE,load,save,sha


def run(home,out):
    assert load(home/'common-cost-01/formal-complete.json')['complete'],'Backup only after timed deployments'
    out.mkdir(parents=True,exist_ok=False)
    refs=[]
    for p in home.rglob('*'):
        if p.is_symlink():refs.append({'path':str(p.relative_to(ROOT)),'target':str(p.resolve()),'exists':p.exists()})
    save(out/'external-reference-list.json',refs)
    data=out/'batch-artifacts.tar.gz'
    with tarfile.open(data,'w:gz',dereference=False,compresslevel=2)as archive:archive.add(home,arcname=str(home.relative_to(ROOT)),recursive=True)
    # Only images actually specified by experiment compose files. Upstream
    # example deployment files and isolated source snapshots are not executions.
    images=set();unavailable=[]
    import yaml
    for p in home.rglob('*'):
        if not p.is_file()or p.name not in('compose.json','compose.yml'):continue
        if any(s in p.parts for s in('external-candidates','prefix-variant-source')):continue
        cfg=load(p)if p.suffix=='.json'else yaml.safe_load(p.read_text())
        for service in cfg.get('services',{}).values():
            if 'image'not in service:continue
            result=subprocess.run(['docker','image','inspect',service['image']],text=True,capture_output=True)
            if result.returncode:
                unavailable.append({'compose':str(p.relative_to(ROOT)),'image':service['image'],
                                    'inspect_error':result.stderr.strip()})
                continue
            row=json.loads(result.stdout)[0]
            images.add(row['Id'])
    save(out/'actual-image-ids.json',sorted(images))
    save(out/'unavailable-attempt-image-references.json',unavailable)
    image_archive=out/'actual-images.tar.gz'
    with gzip.open(image_archive,'wb',compresslevel=2)as target:
        process=subprocess.Popen(['docker','image','save',*sorted(images)],stdout=subprocess.PIPE)
        shutil.copyfileobj(process.stdout,target,1024*1024);assert process.wait()==0
    for p in(data,image_archive):subprocess.run(['gzip','-t',str(p)],check=True)
    core=load(home/'final-candidate-02/historical/algorithm-freeze.json')
    assert all(sha(Path(p))==h for p,h in core['sources'].items())
    files={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)}for p in(data,image_archive)}
    receipt={'algorithm':core['commit'],'core_unchanged':True,'files':files,'gzip_CRC_passed':True,'images':len(images),
        'symlinks_not_dereferenced':True,'external_references':str(out/'external-reference-list.json'),
        'unavailable_image_references':unavailable,
        'old_dependency_backup':'artifacts/backups/zlt-body-completion-20261031; original JDK/native/dependencies and earlier first captures remain separate immutable references.',
        'scope':'Full current batch tree including failures, source clones, original JAR/WAR, complete first/cost captures, protocols and derived audits. Not all historical artifacts and not an external off-machine backup.',
        'push':False}
    save(out/'receipt.json',receipt);save(HERE/'target-observation-backup-receipt-20261103.json',receipt)
    print({'backup':str(out),'images':len(images),'files':files},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
