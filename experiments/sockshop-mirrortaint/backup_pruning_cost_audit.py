"""Back up completed audit data and mounted dependencies; verify reused runtimes."""
import argparse,json,os,subprocess,tarfile
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from backup_shared_work_revision import regular_files

def run(home,out,receipt):
 assert load(home/'pipeline-complete.json')['complete']and load(home/'delivery-audit/summary.json')['passed']
 out.mkdir(parents=True,exist_ok=False);prior=load(ROOT/'experiments/sockshop-mirrortaint/shared-work-backup-20261106.json');verified=[]
 refs=[prior['batch'],prior['external_mounted_inputs'],*prior['reused_verified_archives']];seen=set()
 for record in refs:
  p=ROOT/record['path']
  if str(p)in seen:continue
  seen.add(str(p));assert sha(p)==record['sha256'];subprocess.run(['gzip','-t',str(p)],check=True);verified.append(record)
 images=set();inputs={};runtime=set();inspected={}
 image_manifest=ROOT/'artifacts/backups/ruoyi-zlt-refinement-20261103/actual-images.json'
 # The original image list records exact IDs in a JSON list; keep its original
 # filename from the verified predecessor rather than assuming a tag is fixed.
 previous=load(ROOT/'experiments/sockshop-mirrortaint/ruoyi-tolist-backup-20261105.json');image_manifest=ROOT/previous['image_archive_list'];available=set(load(image_manifest))|set(prior['actual_image_ids'])
 for p in regular_files(home):
  if p.name!='compose.json'or'reference-core-4cb5943'in p.parts:continue
  for s in load(p).get('services',{}).values():
   name=s.get('image')
   if name:
    if name not in inspected:inspected[name]=name if name.startswith('sha256:')else json.loads(subprocess.check_output(['docker','image','inspect',name],text=True))[0]['Id']
    images.add(inspected[name])
   for v in s.get('volumes',[]):
    if not isinstance(v,str)or not v.startswith('/'):continue
    src,target=v.split(':')[:2];f=Path(src)
    if f==home or home in f.parents:continue
    if target.startswith(('/opt/task-jdk','/opt/jdk','/usr/lib/jvm')):runtime.add(src);continue
    assert f.exists(),src
    files=[f]if f.is_file()else regular_files(f)
    for item in files:
     if str(item)not in inputs:inputs[str(item)]={'sha256':sha(item),'bytes':item.stat().st_size}
 missing=images-available
 if missing:
  p=out/'additional-images.tar.gz'
  with p.open('wb')as stream:
   process=subprocess.Popen(['docker','save',*sorted(missing)],stdout=subprocess.PIPE);subprocess.run(['gzip','-c'],stdin=process.stdout,stdout=stream,check=True);process.stdout.close();assert process.wait()==0
  subprocess.run(['gzip','-t',str(p)],check=True);verified.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'gzip_CRC_passed':True})
 save(out/'mounted-inputs-manifest.json',inputs);mounted=out/'mounted-inputs.tar.gz'
 with tarfile.open(mounted,'w:gz',dereference=False)as tar:
  for name in sorted(inputs):tar.add(name,arcname=name.lstrip('/'),recursive=False)
 subprocess.run(['gzip','-t',str(mounted)],check=True)
 save(home/'backup-dependency-coverage.json',{'actual_image_ids':sorted(images),'additional_image_ids':sorted(missing),'runtime_mounts_in_verified_predecessor':sorted(runtime),'external_files':len(inputs),'image_archive_manifest':str(image_manifest)})
 files={str(p.relative_to(home)):sha(p)for p in regular_files(home)};save(out/'files-manifest.json',files);archive=out/'batch-artifacts.tar.gz'
 with archive.open('wb')as stream:subprocess.run(['tar','-czf','-','-C',str(home.parent),home.name],stdout=stream,check=True)
 subprocess.run(['gzip','-t',str(archive)],check=True)
 def fact(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'gzip_CRC_passed':True}
 result={'core_reference':'4cb5943','core_candidate':'bcdf059','independent_score_reference':'df977b7','batch':fact(archive),'external_mounted_inputs':fact(mounted),'files_manifest_sha256':sha(out/'files-manifest.json'),'regular_files':len(files),'reused_verified_archives':verified,'actual_image_ids':sorted(images),'symlinks_dereferenced':False,'all_failures_retained':True,'local_backup_not_off_machine':True}
 save(out/'receipt.json',result);save(receipt,result);print(result['batch'])

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--receipt',required=True,type=Path);a=p.parse_args();run(a.home.resolve(),a.out.resolve(),a.receipt.resolve())
