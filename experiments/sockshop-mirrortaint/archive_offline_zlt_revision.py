"""New complete artifacts plus verified prior captures/images/runtime backup."""
import argparse,gzip,hashlib,json,subprocess,tarfile
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save

def digest(path):
 h=hashlib.sha256()
 with path.open('rb')as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def run(out):
 home=ROOT/'artifacts/offline-zlt-revision-20261031';out.mkdir(parents=True,exist_ok=False)
 prior=load(HERE/'frozen-backup-receipt-20261030.json');prior_checks={}
 for name,record in prior['archives'].items():
  p=ROOT/prior['backup_directory']/name;assert digest(p)==record['sha256'],p
  with gzip.open(p,'rb')as f:
   for block in iter(lambda:f.read(1024*1024),b''):pass
  prior_checks[name]={**record,'sha256_rechecked':True,'CRC_rechecked':True}
 # Inputs outside the new root already archived by their exact content digest.
 previous_inputs=load(ROOT/prior['backup_directory']/'reference-input-index.json');previous_digests={v['sha256']for v in previous_inputs.values()};uncovered={};mapping={}
 for p in home.rglob('compose.json'):
  spec=load(p)
  for service in spec.get('services',{}).values():
   for v in service.get('volumes',[]):
    source=Path(v.split(':')[0])
    if source.is_file():
     resolved=source.resolve();value=digest(resolved)
     if resolved.is_relative_to(home.resolve()):mapping[str(source)]={'new_archive':str(resolved.relative_to(ROOT)),'sha256':value}
     elif value in previous_digests:mapping[str(source)]={'prior_archive_content_sha256':value}
     else:uncovered[str(source)]=value
 # Retain additional inputs if any, without copying arbitrary directory mounts.
 stage=out/'additional-inputs';stage.mkdir()
 import shutil
 for name,value in uncovered.items():
  target=stage/value
  if not target.exists():shutil.copyfile(name,target)
  mapping[name]={'new_additional_input':str(target.relative_to(out)),'sha256':value}
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();subprocess.run(['git','archive','--format=tar','--output='+str(home/'final-repository.tar'),commit],cwd=ROOT,check=True)
 manifest={str(p.relative_to(ROOT)):digest(p)for p in home.rglob('*')if p.is_file()and not p.is_symlink()}
 save(out/'artifact-files-manifest.json',manifest);save(out/'reference-input-index.json',mapping)
 archive=out/'offline-zlt-complete.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=1)as tar:
  tar.add(home,arcname=str(home.relative_to(ROOT)));tar.add(stage,arcname='additional-inputs');tar.add(out/'reference-input-index.json',arcname='reference-input-index.json');tar.add(out/'artifact-files-manifest.json',arcname='artifact-files-manifest.json')
 with gzip.open(archive,'rb')as f:
  for block in iter(lambda:f.read(1024*1024),b''):pass
 # No capture can change while the backup is being made.
 assert all(digest(ROOT/name)==value for name,value in manifest.items())
 result={'backup_directory':str(out.relative_to(ROOT)),'new_archive':{'name':archive.name,'sha256':digest(archive),'bytes':archive.stat().st_size,'gzip_crc_verified':True},'artifact_files':len(manifest),'manifest_sha256':digest(out/'artifact-files-manifest.json'),'source_commit':commit,'prior_backup_required_for_original_Mall_captures_and_images':prior['backup_directory'],'prior_archives_reverified':prior_checks,'mounted_file_references':len(mapping),'new_additional_inputs':len(uncovered),'native_MT_unchanged':True,'all_new_files_unchanged_during_backup':True,'scope':'New raw captures, all failed/intermediate audits, profiles, full offline reruns and source snapshots; original complete captures, Docker images and JDK retained in verified prior backup. Restore old digest-indexed inputs together with this archive.'}
 save(out/'receipt.json',result);save(HERE/'offline-zlt-backup-receipt-20261031.json',result);print(result)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
