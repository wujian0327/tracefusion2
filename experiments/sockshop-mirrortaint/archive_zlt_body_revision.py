"""Back up this batch and exact referenced inputs; never delete originals."""
import argparse,gzip,hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
from run_planned_service import ROOT,load,save
from run_zlt_body_cost import verify,COMMIT


def sha(path):
    d=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):d.update(b)
    return d.hexdigest()


def run(out):
    verify();out.mkdir(parents=True,exist_ok=False);refs=out/'reference-inputs';refs.mkdir()
    roots=[ROOT/'artifacts/zlt-completion-slice-20261031',ROOT/'artifacts/zlt-body-cost-20261031']
    mapping={};images=set()
    for root in roots:
        for p in root.rglob('compose.json'):
            cfg=load(p)
            if not isinstance(cfg,dict)or'services'not in cfg:continue
            for s in cfg['services'].values():
                images.add(s['image'])
                for v in s.get('volumes',[]):
                    name=v.split(':')[0];f=Path(name)
                    if f.is_file()and f.is_relative_to(ROOT/'artifacts'):mapping[name]=None
                    elif f.is_dir()and f.is_relative_to(ROOT/'artifacts')and not any(f.resolve().is_relative_to(r)for r in roots):
                        # Explicit public experiment mounts only, not arbitrary
                        # home/cache/credential trees or container data volumes.
                        for child in f.rglob('*'):
                            if child.is_file()and child.suffix in('.sql','.json','.yaml','.yml','.xml','.properties','.jar'):
                                mapping[str(child)]=None
        for p in root.rglob('tool-binaries.json'):
            for name in load(p).get('files',{}):
                f=Path(name)
                if f.is_file()and f.is_relative_to(ROOT/'artifacts'):mapping[name]=None
    # Explicitly include reused original/MT runs, not just their absolute links.
    reused=[]
    zlt=roots[0]/'final-candidate-01/zlt/runs'
    for api in('ZLT-MP-1','ZLT-MP-4'):
        for mode in('original','mirrortaint'):
            p=(zlt/api/mode).resolve();assert p.is_relative_to(ROOT/'artifacts');reused.append(p)
    public=ROOT/'artifacts/portability-first-20261028/upstream/ZLT-MP'
    for folder in('zlt-uaa/src/main','zlt-business/user-center/src/main','zlt-common','zlt-doc/sql'):
        for p in(public/folder).rglob('*'):
            if p.is_file()and p.suffix in('.java','.xml','.sql'):mapping[str(p)]=None
    for name in sorted(mapping):
        p=Path(name).resolve();digest=sha(p)
        if any(p.is_relative_to(r)for r in roots):mapping[name]={'inside_batch':str(p.relative_to(ROOT)),'sha256':digest}
        else:
            target=refs/digest
            if not target.exists():shutil.copyfile(p,target)
            mapping[name]={'stored_as':str(target.relative_to(out)),'basename':p.name,'sha256':digest}
    save(out/'reference-input-index.json',mapping)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    subprocess.run(['git','archive','--format=tar','--output='+str(out/'repository.tar'),commit],check=True)
    prior=ROOT/'artifacts/source-locality-effects-20261030'
    strict=[prior/name for name in('controls-22-adversarial-confirmed','controls-25-sealed-metadata','controls-28-mixin-scope','context-escape-reproducer')]
    archive=out/'complete-current-batch.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=1)as tar:
        for p in [*roots,*reused,*strict]:tar.add(p,arcname=str(p.relative_to(ROOT)))
        for name in('reference-input-index.json','reference-inputs','repository.tar'):tar.add(out/name,arcname=name)
    inspected=json.loads(subprocess.check_output(['docker','image','inspect',*sorted(images)],text=True));ids=sorted({i['Id']for i in inspected});save(out/'images.json',inspected)
    with(out/'docker-images.tar.gz').open('wb')as dest:
        source=subprocess.Popen(['docker','image','save',*ids],stdout=subprocess.PIPE)
        zipped=subprocess.Popen(['gzip','-1'],stdin=source.stdout,stdout=dest);source.stdout.close()
        assert zipped.wait()==source.wait()==0
    archives={}
    for p in(archive,out/'docker-images.tar.gz'):
        with gzip.open(p,'rb')as f:
            while f.read(8*1024*1024):pass
        archives[p.name]={'bytes':p.stat().st_size,'sha256':sha(p),'gzip_crc_verified':True}
    # The host JDK package was independently archived in the preceding batch.
    runtime=ROOT/'artifacts/backups/frozen-reuse-common-cost-20261030/jdk8-runtime.tar.gz'
    assert runtime.is_file()
    shutil.copyfile(runtime,out/'jdk8-runtime.tar.gz')
    with gzip.open(out/'jdk8-runtime.tar.gz','rb')as f:
        while f.read(8*1024*1024):pass
    archives['jdk8-runtime.tar.gz']={'bytes':runtime.stat().st_size,'sha256':sha(runtime),'gzip_crc_verified':True}
    receipt={'algorithm':COMMIT,'repository_commit':commit,'archives':archives,'actual_image_ids':ids,'reference_files':len(mapping),
        'reused_original_MT_runs':[str(p.relative_to(ROOT))for p in reused],
        'scope':'Complete NEW batch, exact mounted artifact files, reused ZLT original/MT runs and permanent strict locality counterexamples. Prior unrelated historical batches remain separately preserved/backed up; no deletion or overwrite.',
        'restore':'Absolute experiment links can be restored under the original workspace or remapped using reference-input-index.json. No arbitrary private home or credential trees copied.'}
    save(out/'manifest.json',receipt);verify();print({'archives':archives,'image_count':len(ids),'reference_files':len(mapping)},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
