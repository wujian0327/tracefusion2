"""Back up this revision, retaining failed attempts and external references."""
import argparse,gzip,json,shutil,subprocess,tarfile
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha


def run(home,final,out):
    assert load(final.parent/'capability-pass-01/summary.json')['complete']
    freeze=load(final/'historical/algorithm-freeze.json')
    assert all(sha(Path(p))==v for p,v in freeze['sources'].items())
    out.mkdir(parents=True,exist_ok=False)
    refs=[{'path':str(p.relative_to(ROOT)),'target':str(p.resolve()),'exists':p.exists()}
          for p in home.rglob('*')if p.is_symlink()]
    save(out/'external-references.json',refs)
    source=home/'final-source-bundle';source.mkdir(exist_ok=False)
    for p in freeze['sources']:
        path=Path(p);shutil.copyfile(path,source/path.name)
    for p in HERE.iterdir():
        if p.is_file()and p.suffix in('.py','.java','.json','.md','.csv'):
            shutil.copyfile(p,source/p.name)
    save(source/'manifest.json',{p.name:sha(p)for p in source.iterdir()if p.is_file()})
    data=out/'batch-artifacts.tar.gz'
    with tarfile.open(data,'w:gz',dereference=False,compresslevel=2)as archive:
        archive.add(home,arcname=str(home.relative_to(ROOT)),recursive=True)
    import yaml
    references=set()
    for p in home.rglob('*'):
        if not p.is_file()or p.name not in('compose.json','compose.yml','compose.yaml'):continue
        config=load(p)if p.suffix=='.json'else yaml.safe_load(p.read_text())
        references.update(v['image']for v in config.get('services',{}).values()if 'image'in v)
    images=set();unavailable=[]
    for name in sorted(references):
        r=subprocess.run(['docker','image','inspect',name],capture_output=True,text=True)
        if r.returncode:unavailable.append({'reference':name,'error':r.stderr.strip()})
        else:images.add(json.loads(r.stdout)[0]['Id'])
    save(out/'actual-image-ids.json',sorted(images));save(out/'unavailable-attempt-images.json',unavailable)
    packed=out/'actual-images.tar.gz'
    with gzip.open(packed,'wb',compresslevel=2)as target:
        process=subprocess.Popen(['docker','image','save',*sorted(images)],stdout=subprocess.PIPE)
        shutil.copyfileobj(process.stdout,target,1024*1024);assert process.wait()==0
    for p in(data,packed):subprocess.run(['gzip','-t',str(p)],check=True)
    receipt={'candidate':freeze['commit'],'files':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)}for p in(data,packed)},
        'gzip_CRC_passed':True,'unique_images':len(images),'unique_image_references':len(references),'unavailable_attempt_references':unavailable,
        'symlinks_dereferenced':False,'external_reference_list':str(out/'external-references.json'),
        'previous_dependency_and_capture_backup':'artifacts/backups/target-closure-20261103; earlier JDK/native/dependency backups remain separate.',
        'scope':'Complete current revision including failed and superseded captures, final fresh captures, old-capture replay and source bundle. Local backup, not off-machine replication.',
        'no_push':True}
    save(out/'receipt.json',receipt);save(HERE/'ruoyi-zlt-refinement-backup-20261103.json',receipt)
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--final',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.final.resolve(),a.out.resolve())
