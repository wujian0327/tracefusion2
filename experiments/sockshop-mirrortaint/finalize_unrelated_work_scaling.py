"""Final read-only integrity and local backup, no image export or old overwrite."""
import gzip,hashlib,json,shutil,tarfile,subprocess
from datetime import datetime,timezone
from pathlib import Path
from run_unrelated_work_scaling import H,HERE,ROOT,load,save,sha,verify

def run():
 freeze=verify();out=H/'integrity-final-02';out.mkdir(exist_ok=False);initial=load(H/'protocol-before-tools.json');allowed={r['Id']for r in initial['images']};refs={ref:r['Id']for r in initial['images']for ref in [r['Id'],*(r.get('RepoTags')or[]),*(r.get('RepoDigests')or[])]};receipts=[]
 for trial in sorted(H.rglob('result.json')):
  base=trial.parent;r=load(trial)
  if r.get('state')!='captured':continue
  if (base/'compose.json').exists():
   c=load(base/'compose.json');assert all(refs.get(s['image'])in allowed for s in c['services'].values()),str(base)
  cases=load(base/'warmup.json')['requests']+load(base/'measure.json')['requests']
  # Failed environment attempt with404 is intentionally retained, not a gate success.
  receipts.append({'trial':str(base.relative_to(ROOT)),'requests':len(cases),'business_passed':sum(x['business_passed']for x in cases),'cleanup_returncode':r.get('cleanup_returncode'),'raw_capture_sha256':{str(p.relative_to(base)):sha(p)for p in(base/'capture').rglob('*')if p.is_file()and p.name.endswith('.jsonl')}})
  assert r.get('cleanup_returncode')==0,str(base)
 for job in load(H/'formal-order-before-timing.json')['jobs']:
  trial=H/'formal'/('%02d-%s-%s-%s'%(job['round'],job['task'],job['tier'],job['mode']));assert load(trial/'formal-job.json')['passed'];r=load(trial/'result.json');assert r['requests']==r['business_passed']
  if job['mode']!='original':assert load(trial/'normal-offline/prediction-equivalence.json')['exact_all_answers']
 original=set(load(H/'environment-before.json')['docker_ps']);current=set(subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines());assert original==current,(original,current)
 save(out/'summary.json',{'passed':True,'core_sources':len(freeze['sources']),'initial_nonexperiment_containers_unchanged':True,'successful_and_failed_business_attempts':receipts,'formal_deployments':len(load(H/'formal-order-before-timing.json')['jobs']),'sources':{str(p):sha(p)for p in HERE.glob('*unrelated_work*.py')},'no_core_Agent_public_contract_change':True})
 # Keep every build attempt/failed log. Existing archives are referenced only
 # after digest and full gzip CRC verification, never overwritten.
 archive_images=load(ROOT/'artifacts/backups/frozen-reuse-common-cost-20261030/images.json');assert allowed<={i['Id']for i in archive_images},'Pinned actual image missing from prior archive'
 backup=ROOT/'artifacts/backups/unrelated-work-scaling-20261109';backup.mkdir(exist_ok=False,parents=True);deps=[]
 for p in (ROOT/'artifacts/backups/frozen-reuse-common-cost-20261030/docker-images.tar.gz',ROOT/'artifacts/backups/ruoyi-request-scope-20261104/jdk8-runtime.tar.gz'):
  with gzip.open(p,'rb')as f:
   while f.read(8*1024*1024):pass
  deps.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'gzip_CRC':True,'reused_not_new_export':True})
 # Mounted small binary inputs are included, so archives do not depend solely
 # on external absolute mount paths. JDK/images use the verified prior archive.
 mounted=H/'backup-mounted-inputs';mounted.mkdir();files={}
 for i,(name,digest)in enumerate(initial['binary_and_environment_files'].items()):
  p=Path(name)
  dest=mounted/('%03d-'%i+p.name);shutil.copyfile(p,dest);assert sha(dest)==digest;files[name]={'archive_member':str(dest.relative_to(ROOT)),'sha256':digest}
 save(mounted/'manifest.json',files)
 archive=backup/'complete-round.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=1)as t:
  t.add(H,arcname=str(H.relative_to(ROOT)))
  for p in HERE.glob('*unrelated_work*.py'):t.add(p,arcname=str(p.relative_to(ROOT)))
  for p in HERE.glob('*unrelated-work*20261109*'):
   if p.is_file():t.add(p,arcname=str(p.relative_to(ROOT)))
  p=HERE/'UNRELATED-WORK-SCALING-20261109.md';t.add(p,arcname=str(p.relative_to(ROOT)))
 with gzip.open(archive,'rb')as f:
  while f.read(8*1024*1024):pass
 receipt={'archive':str(archive.relative_to(ROOT)),'sha256':sha(archive),'bytes':archive.stat().st_size,'gzip_CRC':True,'prior_archives':deps,'local_backup_only':True,'created_utc':datetime.now(timezone.utc).isoformat(),'no_old_capture_or_report_modified':True,'core_sources_unchanged':len(freeze['sources'])}
 save(backup/'receipt.json',receipt);save(HERE/'unrelated-work-scaling-backup-20261109.json',receipt);verify();print(receipt)

if __name__=='__main__':run()
