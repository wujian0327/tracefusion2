#!/usr/bin/env python3
"""Back up this batch, exact mounted inputs, strict counterexample and images."""
import argparse,gzip,hashlib,json,shutil,subprocess,tarfile,time
from pathlib import Path
from run_frozen_zlt_reuse import ROOT,load,save,sha
from run_frozen_locality_cost import verify

def sha(path):
 digest=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
 return digest.hexdigest()

def run(out):
 verify();out.mkdir(parents=True,exist_ok=False);stage=out/'reference-inputs';stage.mkdir();mapping={};images=set();roots=[ROOT/'artifacts/frozen-zlt-reuse-20261030',ROOT/'artifacts/frozen-locality-cost-20261030'];old=ROOT/'artifacts/source-locality-effects-20261030'
 for root in roots:
  for p in root.rglob('tool-binaries.json'):
   for name in load(p)['files']:mapping[name]=None
  for p in root.rglob('compose.json'):
   data=load(p)
   if not isinstance(data,dict)or'services'not in data:continue
   for service in data['services'].values():
    images.add(service['image'])
    for volume in service.get('volumes',[]):
     name=volume.split(':')[0];f=Path(name)
     if f.is_file():mapping[name]=None
 for role in('zlt-user','zlt-uaa'):
  for name in('model.json','receipt.json'):mapping[str(ROOT/'artifacts/portability-first-20261028/metadata'/role/name)]=None
 mapping[str(old/'final-mall-03/metadata/mall-admin/model.json')]=None
 mapping[str(ROOT/'artifacts/external-frozen-transfer-20261029/oracle-before-tools.json')]=None
 for directory in('zlt-uaa/src/main','zlt-business/user-center/src/main','zlt-doc/sql'):
  base=ROOT/'artifacts/portability-first-20261028/upstream/ZLT-MP'/directory
  for p in base.rglob('*'):
   if p.is_file()and p.suffix in('.java','.xml','.sql'):mapping[str(p)]=None
 # Store mounted files outside the two new roots once, by digest. Never follow
 # arbitrary directory mounts or copy unrelated credentials/configuration.
 for name in sorted(mapping):
  p=Path(name).resolve()
  if not p.is_file():raise ValueError('Referenced input missing: '+name)
  if any(p.is_relative_to(root)for root in roots):mapping[name]={'inside_batch':str(p.relative_to(ROOT)),'sha256':sha(p)};continue
  digest=sha(p);target=stage/digest
  if not target.exists():shutil.copyfile(p,target)
  mapping[name]={'archived_as':str(target.relative_to(out)),'sha256':digest,'basename':p.name}
 save(out/'reference-input-index.json',mapping)
 # Git base plus explicit experiment overlay; frozen core remains the base's
 # 96 byte-identical sources, checked against c1a4e5c above.
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();subprocess.run(['git','archive','--format=tar','--output='+str(out/'repository-base.tar'),commit],cwd=ROOT,check=True)
 overlay=[p for p in(ROOT/'experiments/sockshop-mirrortaint').iterdir()if p.is_file()and(p.name.startswith(('run_frozen_','audit_frozen_','review_frozen_','measure_frozen_','summarize_frozen_','archive_frozen_','FROZEN-','frozen-')))]
 with tarfile.open(out/'experiment-overlay.tar','w')as tar:
  for p in overlay:tar.add(p,arcname=str(p.relative_to(ROOT)))
 runtime=Path('/usr/lib/jvm/java-8-openjdk-amd64')
 with tarfile.open(out/'jdk8-runtime.tar.gz','w:gz',compresslevel=1)as tar:
  tar.add(runtime,arcname=str(runtime).lstrip('/'))
  for name in('jvm.cfg','java.security','java.policy','net.properties','logging.properties','sound.properties','accessibility.properties','swing.properties','security/java.security','security/java.policy','security/cacerts'):
   p=Path('/etc/java-8-openjdk')/name
   if p.is_file():tar.add(p,arcname=str(p).lstrip('/'))
 archive=out/'complete-batch-and-counterexample.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=1)as tar:
  for root in roots:tar.add(root,arcname=str(root.relative_to(ROOT)))
  for name in('controls-22-adversarial-confirmed','controls-25-sealed-metadata','controls-28-mixin-scope','context-escape-reproducer'):
   tar.add(old/name,arcname=str((old/name).relative_to(ROOT)))
  tar.add(stage,arcname='reference-inputs');tar.add(out/'reference-input-index.json',arcname='reference-input-index.json')
  for name in('repository-base.tar','experiment-overlay.tar','jdk8-runtime.tar.gz'):tar.add(out/name,arcname=name)
 inspected=json.loads(subprocess.check_output(['docker','image','inspect',*sorted(images)],text=True));ids=sorted({i['Id']for i in inspected});save(out/'images.json',inspected)
 with(out/'docker-images.tar.gz').open('wb')as dest:
  source=subprocess.Popen(['docker','image','save',*ids],stdout=subprocess.PIPE)
  zipproc=subprocess.Popen(['gzip','-1'],stdin=source.stdout,stdout=dest);source.stdout.close();zipcode=zipproc.wait();code=source.wait()
  assert code==zipcode==0,(code,zipcode)
 archives={}
 for p in(archive,out/'docker-images.tar.gz',out/'jdk8-runtime.tar.gz'):
  # Read to EOF to verify gzip CRC, without extracting or executing anything.
  with gzip.open(p,'rb')as f:
   while f.read(8*1024*1024):pass
  archives[p.name]={'sha256':sha(p),'bytes':p.stat().st_size,'gzip_crc_verified':True}
 manifest={'algorithm':'c1a4e5ceb60a276cc3651e4cdb413aa29d7f8d5d','repository_base_commit':commit,'archives':archives,'image_ids':ids,'reference_files':len(mapping),'source_overlay_files':{str(p.relative_to(ROOT)):sha(p)for p in overlay},'scope':'Complete NEW reuse/cost batch and strict confirmed counterexample/final guards; previous unrelated historical capture batches remain in their preserved directories, not repackaged. Runtime container writable layers are not exported; public dependency images plus original jars/SQL/request/DB/capture facts are included.','note':'Absolute symlinks in captures correspond to reference-input-index.json. Restore referenced files under the chosen workspace before using archived drivers.'}
 save(out/'manifest.json',manifest);verify();print({'archives':archives,'image_ids':len(ids),'reference_files':len(mapping)},flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
