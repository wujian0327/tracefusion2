"""Archive this batch without following references into historical frozen data."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from run_planned_service import ROOT,save,sha,load

def run(home,out,receipt):
 out.mkdir(parents=True,exist_ok=False);assert load(home/'audit-delivery-01/summary.json')['algorithm']==load(home/'final-offline-freeze.json')['commit']
 observed=set();image_files=[]
 def visit(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in('Id','Image')and isinstance(v,str)and v.startswith('sha256:'):observed.add(v)
    visit(v)
  elif isinstance(x,list):
   for v in x:visit(v)
 for p in home.rglob('*image*.json'):
  try:visit(load(p));image_files.append(str(p))
  except (ValueError,OSError):pass
 image_manifest=ROOT/'artifacts/backups/ruoyi-zlt-refinement-20261103/actual-image-ids.json';assert observed<=set(load(image_manifest)),observed-set(load(image_manifest))
 verified=load(home/'prior-backup-verification.json')
 for entry in verified:assert sha(Path(entry['path']))==entry['sha256']
 save(home/'backup-input-image-coverage.json',{'observed_actual_image_ids':sorted(observed),'image_inspect_files':image_files,'reused_image_manifest':str(image_manifest),'all_observed_images_covered':True})
 files={str(p.relative_to(home)):sha(p)for p in home.rglob('*')if p.is_file()and not p.is_symlink()}
 save(out/'files-manifest.json',files)
 archive=out/'batch-artifacts.tar.gz'
 with archive.open('wb')as f:subprocess.run(['tar','-czf','-','-C',str(home.parent),home.name],stdout=f,check=True)
 subprocess.run(['gzip','-t',str(archive)],check=True)
 data={'algorithm':load(home/'final-offline-freeze.json')['commit'],'online_algorithm':load(home/'final-freeze.json')['commit'],'batch':{'path':str(archive.relative_to(ROOT)),'bytes':archive.stat().st_size,'sha256':sha(archive),'gzip_CRC_passed':True},'files_manifest':str((out/'files-manifest.json').relative_to(ROOT)),'files_manifest_sha256':sha(out/'files-manifest.json'),'regular_files':len(files),'reused_verified_images_and_JDK':verified,'actual_image_ids_observed':sorted(observed),'image_archive_list':str(image_manifest.relative_to(ROOT)),'symlinks_dereferenced':False,'failures_and_both_semantic_versions_included':True,'local_backup_not_off_machine':True,'no_push':True}
 save(out/'receipt.json',data);save(receipt,data);print(data['batch'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve(),a.receipt.resolve())
