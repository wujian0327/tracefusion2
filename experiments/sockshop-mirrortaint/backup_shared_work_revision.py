"""Back up completed work and read-only mounted inputs; reuse verified image/JDK archives."""
import argparse,json,os,subprocess,tarfile
from pathlib import Path
from run_planned_service import ROOT,load,save,sha

def regular_files(root):
 for base,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if not(Path(base)/d).is_symlink()]
  for name in files:
   p=Path(base)/name
   if p.is_file()and not p.is_symlink():yield p


def run(home,out,receipt):
 assert load(home/'measurement-complete.json')['complete'];assert load(home/'derived-final/summary.json')['online']['raw_resource_summaries_exact']
 out.mkdir(parents=True,exist_ok=False);reference=load(ROOT/'experiments/sockshop-mirrortaint/ruoyi-tolist-backup-20261105.json');verified=[]
 for item in reference['reused_verified_images_and_JDK']+[reference['batch']]:
  p=ROOT/item['path'];assert sha(p)==item['sha256'];subprocess.run(['gzip','-t',str(p)],check=True);verified.append(item)
 image_manifest=ROOT/reference['image_archive_list'];available=set(load(image_manifest));images=set();inputs={};jdk_mounts=[]
 for p in regular_files(home):
  if p.name!='compose.json'or'old-repository'in p.parts:continue
  cfg=load(p)
  for service in cfg.get('services',{}).values():
   if service.get('image'):
    value=service['image'];actual=value if value.startswith('sha256:')else json.loads(subprocess.check_output(['docker','image','inspect',value],text=True))[0]['Id'];images.add(actual)
   for mount in service.get('volumes',[]):
    if not isinstance(mount,str):continue
    parts=mount.split(':');src=Path(parts[0])
    if not src.is_absolute():continue
    if src==home or home in src.parents:continue
    target=parts[1]if len(parts)>1 else''
    if target.startswith(('/opt/task-jdk','/opt/jdk','/usr/lib/jvm')):jdk_mounts.append(str(src));continue
    if not src.exists():raise ValueError('Required mounted input no longer exists: '+str(src))
    paths=[src]if src.is_file()else list(regular_files(src))
    for f in paths:inputs[str(f)]={'sha256':sha(f),'bytes':f.stat().st_size}
 missing=images-available
 if missing:
  image_out=out/'additional-required-images.tar.gz'
  with image_out.open('wb')as f:
   saved=subprocess.Popen(['docker','save',*sorted(missing)],stdout=subprocess.PIPE);gz=subprocess.run(['gzip','-c'],stdin=saved.stdout,stdout=f,check=True);saved.stdout.close();assert saved.wait()==0
  subprocess.run(['gzip','-t',str(image_out)],check=True);verified.append({'path':str(image_out.relative_to(ROOT)),'sha256':sha(image_out),'bytes':image_out.stat().st_size,'gzip_CRC_passed':True})
 save(out/'mounted-inputs.json',{'files':inputs,'JDK_mounts_covered_by_reused_runtime_archive':sorted(set(jdk_mounts))})
 mounted=out/'mounted-inputs.tar.gz'
 with tarfile.open(mounted,'w:gz',dereference=False)as tar:
  for name in sorted(inputs):tar.add(name,arcname=name.lstrip('/'),recursive=False)
 subprocess.run(['gzip','-t',str(mounted)],check=True)
 save(home/'backup-dependency-coverage.json',{'actual_image_ids':sorted(images),'previous_image_manifest':str(image_manifest),'additional_image_ids':sorted(missing),'read_only_external_files':len(inputs),'JDK_mounts':sorted(set(jdk_mounts))})
 # Do not follow the old-repository/artifacts link or old-capture compatibility links.
 files={str(p.relative_to(home)):sha(p)for p in regular_files(home)};save(out/'files-manifest.json',files)
 archive=out/'batch-artifacts.tar.gz'
 with archive.open('wb')as f:subprocess.run(['tar','-czf','-','-C',str(home.parent),home.name],stdout=f,check=True)
 subprocess.run(['gzip','-t',str(archive)],check=True)
 data={'algorithm':'4cb5943c8b43f3f1eecace85dc462cf75d8294eb','base':'2427c6f','no_push':True,'batch':{'path':str(archive.relative_to(ROOT)),'sha256':sha(archive),'bytes':archive.stat().st_size,'gzip_CRC_passed':True},'external_mounted_inputs':{'path':str(mounted.relative_to(ROOT)),'sha256':sha(mounted),'bytes':mounted.stat().st_size,'gzip_CRC_passed':True},'files_manifest_sha256':sha(out/'files-manifest.json'),'regular_files':len(files),'reused_verified_archives':verified,'actual_image_ids':sorted(images),'failures_preserved':True,'symlinks_dereferenced':False,'local_backup_not_off_machine':True}
 save(out/'receipt.json',data);save(receipt,data);print(data['batch'])

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve(),a.receipt.resolve())
