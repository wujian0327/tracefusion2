"""Frozen-core experiment: presealed synthetic scaling and matched Mall load.
No core, Agent, public contracts or propagation adapters are built here.
"""
import argparse,copy,hashlib,json,os,random,secrets,subprocess,sys,time,traceback
from pathlib import Path
from zipfile import ZipFile,ZIP_STORED
from concurrent.futures import ThreadPoolExecutor
from run_planned_service import ROOT,HERE,load,save,sha
H=ROOT/'artifacts/unrelated-work-scaling-20261109'
F=ROOT/'artifacts/pruning-contribution-audit-20261106/final-candidate/historical'
AGENT=F/'frozen-base/distributed-observer.jar'
MALL=ROOT/'artifacts/shared-transfer-optimization-20261106/final-candidate/mall'
BUNDLE=ROOT/'artifacts/heldout29-first-20261023/native-bundle'
NATIVE=ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'
JAVA='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
MODES=['original','full','selective','mirrortaint']
TIERS={'low':8,'medium':64,'high':256,'related-high':256}

def verify():
 f=load(F/'algorithm-freeze.json')
 for p,h in f['sources'].items():assert sha(Path(p))==h,p
 if(H/'protocol-before-tools.json').exists():
  for p,h in load(H/'protocol-before-tools.json')['binary_and_environment_files'].items():assert sha(Path(p))==h,p
 if(H/'formal-code-seal-before-timing.json').exists():
  for p,h in load(H/'formal-code-seal-before-timing.json')['files'].items():assert sha(Path(p))==h,p
 return f

def seal():
 assert not(H/'protocol-before-tools.json').exists();f=verify()
 cfg=load(MALL/'tool-runs/mall-swarm-3/full/query-002/compose.json')
 refs=sorted({s['image']for s in cfg['services'].values()});images=json.loads(subprocess.check_output(['docker','image','inspect',*refs],text=True))
 files=[AGENT,NATIVE,*[BUNDLE/x for x in('adapter/integration-adapter.jar','capability.jar','runtime-witness.jar')],MALL/'planning-first/mall-swarm-3/002-plan.json',*sorted((MALL/'business-jars').glob('*.jar')),Path(JAVA),Path(JAVA).parent.parent/'jre/lib/rt.jar',Path(JAVA).parent.parent/'jre/lib/amd64/server/libjvm.so']
 for s in cfg['services'].values():
  for v in s.get('volumes',[]):
   p=Path(v.split(':')[0])
   if p.is_file():files.append(p)
 save(H/'images-before.json',images)
 save(H/'environment-before.json',{'docker_ps':subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines(),'cpu':Path('/proc/cpuinfo').read_text(),'memory':Path('/proc/meminfo').read_text(),'JDK':subprocess.run([JAVA,'-version'],capture_output=True,text=True).stderr})
 p={'TF_commit':subprocess.check_output(['git','rev-parse','bcdf059'],text=True).strip(),'repository_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'core_sources':f['sources'],'binary_and_environment_files':{str(p):sha(p)for p in dict.fromkeys(files)},'images':[{k:i.get(k)for k in('Id','RepoTags','RepoDigests')}for i in images],
 'controlled':{'tiers':TIERS,'entry':'bench/Controller.query()Lbench/Payload;','target':'bench/Payload.target@/target','source_calls':['bench/Store.read()Lbench/Payload;'],'input':'GET /query; deterministic original fixture target1009, field f_i=100+(i%7), including repeated values','unrelated_rule':'query returns same Store.read Payload identity; /target depends only on source /target; all f_i are written by source and serialized in full response. Separate jars differ only in fixed number of fields, assignments and getters; tier is intentional business-shape treatment, not an environment difference within tier.','related_rule':'same high DTO; query overwrites target with sum of source target and all256 f_i, using JVM long addition; source set must include all257 unique raw field occurrences and target new version.','target_truth':'Independent raw source invocation pair + actual source object/field/version; unmodified query bytecode copy/add rule. No native tags or TF graph generate truth.','short_requests':6,'formal_tiers':['low','medium','high'],'related_high':'correctness/necessary-observation control only; excluded growth regression predeclared','formal_rate':2},
 'mall':{'entry':'com/macro/mall/controller/UmsAdminController.login(Lcom/macro/mall/dto/UmsAdminLoginParam;)Lcom/macro/mall/common/api/CommonResult;','path':'/data/expiresIn','sources':load(MALL/'planning-first/mall-swarm-3/002-plan.json')['response_binding']['source_calls'],'input':{'username':'admin','password':'macro123'},'source_rule':'actual AuthService.getAccessToken RPC return /data/expiresIn; independent each JVM raw source coordinates, complete response normalization only fresh tokens and bounded TTL, login_log_count equals total requests','rates':[2],'higher_preflight_candidates':[4,8],'higher_selection':'original only short 12s at4 then8; lock highest with100% business completion, achieved scheduledrate>=98%, p95<500ms; if none retain2 only; no tool formal timing before lock','no_controlled_growth_claim':True},
 'modes':MODES,'fixed_MT':'Unchanged native JAR plus pinned B0 capability/integration/runtime adapter. Multi-field source/target export cannot be disabled; all actual native logs/classdump bytes reported separately. Same selected source/target task; no TF multi-field deployment sums.',
 'pilot_gate':'All four business responses match; all selected positive origins exact; TF selective demonstrably elides increasing scalar boundary payloads vs full. Failure stops that group, no task replacement/model/source changes.',
 'formal':{'rounds':5,'warmup_seconds':30,'measure_seconds':60,'concurrency_limit':2,'order_seed':2026110917,'main_metric':'Business container CPU seconds between explicit start/end measurement snapshots / successful completed measure requests minus corresponding same-round same-tier original; primary growth difference delta_extra(high-low) selective vs MT. CPU can be negative after baseline subtraction, retain signs. Five deployment rounds, no request-as-independent-replicate.','business_groups':{'controlled':['app'],'mall':['admin','auth','portal']},'secondary':['p95 HTTP time_total','completion and achieved rate','2s sampled RSS','batch and actual request-attributed bytes','normal provenance offline CPU/wall/VmHWM; independent oracle/scoring separately'],'decision':'slower growth only if all5 paired delta_extra(selective high-low) < delta_extra(MT high-low); otherwise descriptive median/range no stable conclusion. Mall rates separate load check, not unrelated-work manipulation.','no_profiler':True,'no_business_prewarm_extra':True},
 'resources':{'controlled':'same pinned maven image; OpenJDK8u504;1CPU768MiB; JVM -Xms32m -Xmx256m -XX:ParallelGCThreads=1 -XX:CICompilerCount=2; independent isolated Docker network/client','mall':'same original seven-service limits and JARs as prior common task; three business JVMs1CPU768MiB each; original limits preserved; client excluded'},
 'chronology':'Selection/input/truth/tier/metric sealed before generating any new TF plan or running controlled business. Assembly/plan binary hashes added before short pilots; higher Mall rate only from original preflight.',
 'driver_sha256':sha(Path(__file__))}
 save(H/'protocol-before-tools.json',p);print('SEALED',flush=True)

def build():
 verify();p=load(H/'protocol-before-tools.json');dest=H/'controlled-build-04';dest.mkdir(exist_ok=False);libs=dest/'libs';libs.mkdir()
 original=MALL/'business-jars/mall-admin.jar'
 with ZipFile(original)as z:
  for n in z.namelist():
   if n.startswith('BOOT-INF/lib/')and not Path(n).name.startswith('spring-cloud-')and Path(n).name.startswith(('spring-','tomcat-embed-','jackson-','logback-','slf4j-','jul-to-','log4j-','snakeyaml-')):(libs/Path(n).name).write_bytes(z.read(n))
 cp=':'.join(str(x)for x in sorted(libs.glob('*.jar')))
 from run_query_planner import JARS,command
 from contract_applicability import library_inventory
 from plan_distributed_fields import augment
 from plan_capability_policy import choose
 env=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json')
 for tier,n in TIERS.items():
  d=dest/tier;src=d/'src/bench';src.mkdir(parents=True);classes=d/'classes';classes.mkdir()
  (src/'Application.java').write_text('package bench; @org.springframework.boot.autoconfigure.SpringBootApplication public class Application {public static void main(String[] args){org.springframework.boot.SpringApplication.run(Application.class,args);}}')
  (src/'Payload.java').write_text('package bench; public class Payload {public long target; public long getTarget(){return target;}'+''.join('public long f%d;public long getF%d(){return f%d;}'%(i,i,i)for i in range(n))+'}')
  (src/'Store.java').write_text('package bench; public class Store {public static Payload read(){Payload r=new Payload();r.target=1009L;'+''.join('r.f%d=%dL;'%(i,100+i%7)for i in range(n))+'return r;}}')
  related='r.target=r.target'+''.join('+r.f%d'%i for i in range(n))+';'if tier=='related-high'else''
  (src/'Controller.java').write_text('package bench; @org.springframework.web.bind.annotation.RestController public class Controller {@org.springframework.web.bind.annotation.GetMapping("/query") public Payload query(){Payload r=Store.read();'+related+'return r;}}')
  command([JAVA[:-4]+'javac','-cp',cp,'-d',str(classes),*[str(f)for f in sorted(src.glob('*.java'))]],d/'compile.log')
  jar=d/'business.jar'
  with ZipFile(jar,'w',ZIP_STORED)as out,ZipFile(original)as z:
   out.writestr('BOOT-INF/classes/',b'');out.writestr('BOOT-INF/classes/bench/',b'');out.writestr('BOOT-INF/lib/',b'')
   out.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nMain-Class: org.springframework.boot.loader.JarLauncher\nStart-Class: bench.Application\nSpring-Boot-Version: 2.7.0\n\n')
   for name in z.namelist():
    if name.startswith('org/springframework/boot/loader/')and not name.endswith('/'):out.writestr(name,z.read(name))
   for f in sorted(classes.rglob('*.class')):out.write(f,'BOOT-INF/classes/'+str(f.relative_to(classes)))
   for f in sorted(libs.glob('*.jar')):out.write(f,'BOOT-INF/lib/'+f.name)
  command([JAVA,'-cp',':'.join(map(str,[F/'frozen-base/tools',*JARS])),'QueryBytecodeModel',str(classes),str(d/'model.json')],d/'model.log')
  model=load(d/'model.json');model['library_inventory']=library_inventory(jar);save(d/'model.json',model)
  schema=augment(model,None);save(d/'schema.json',{'json_schema':schema['json_schema'],'rejected_properties':schema.get('rejected_properties',[])})
  q=p['controlled'];target,path=q['target'].split('@');
  try:
   plan,route=choose(model,{'entry':q['entry'],'target':target,'path':path,'source_calls':q['source_calls']},deployment=env);save(d/'plan.json',plan);save(d/'route.json',route);save(d/'planning.json',{'state':'planned','profile':plan['profile']})
  except Exception as e:save(d/'planning.json',{'state':'planning_rejected','error':str(e)})
  save(d/'mt-config.json',{'entry':q['entry'],'prefix':'bench/','source_calls':q['source_calls']})
 save(H/'controlled-build-receipt.json',{'files':{str(f):sha(f)for f in dest.rglob('*')if f.is_file()},'all_plans_generated_before_pilot':True});verify();print('BUILT',flush=True)

def controlled_spec(out,tier,mode,diagnostic=False):
 p=load(H/'protocol-before-tools.json');image=next(i['Id']for i in p['images']if any(x.startswith('maven:')for x in i['RepoTags']));d=H/'controlled-build-04'/tier
 cap=out/'capture';cap.mkdir();cap.chmod(0o777)
 volumes=[str(d/'business.jar')+':/app.jar:ro','/usr/lib/jvm/java-8-openjdk-amd64:/approved-jdk:ro','/etc/java-8-openjdk:/etc/java-8-openjdk:ro',str(cap)+':/tf2/capture:rw']
 opts=[];mounts={}
 if mode in('full','selective'):
  mounts={AGENT:'/tf2/observer.jar',d/'plan.json':'/tf2/plan.json'};opts=['-javaagent:/tf2/observer.jar','-Dservice.plan=/tf2/plan.json','-Dservice.events=/tf2/capture/events.jsonl','-Dservice.mode='+mode]
 elif mode=='mirrortaint':
  mounts={NATIVE:'/tf2/mirrorTaint.jar',BUNDLE/'adapter/integration-adapter.jar':'/tf2/adapter.jar',BUNDLE/'capability.jar':'/tf2/capability.jar',BUNDLE/'runtime-witness.jar':'/tf2/runtime-witness.jar',d/'schema.json':'/tf2/schema.json',d/'mt-config.json':'/tf2/mt-config.json'}
  opts=['-javaagent:/tf2/runtime-witness.jar','-Dnative.library.events=/tf2/capture/native-library.jsonl','-Dtaint.env=remote','-Dtaint.app=bench','-Dtaint.version=capability','-Duser.home=/tf2/capture','-javaagent:/tf2/adapter.jar=strings','-javaagent:/tf2/adapter.jar=streams','-javaagent:/tf2/mirrorTaint.jar',*['-javaagent:/tf2/adapter.jar='+x for x in('returns','sources','fields','threads','logging')],'-javaagent:/tf2/capability.jar','-Dcapability.config=/tf2/mt-config.json','-Dcapability.events=/tf2/capture/native-capability.jsonl','-javaagent:/tf2/capability.jar=transport','-Dinstance.schema=/tf2/schema.json','-Dinstance.events=/tf2/capture/instances.jsonl']
 if diagnostic:
  probe=ROOT/'artifacts/pruning-contribution-audit-20261106/probe/probe-v2.jar';assert sha(probe)==load(H/'diagnostic-protocol-before-runs.json')['probe_sha256'];mounts[probe]='/tf2/cost-probe.jar';opts.insert(0,'-javaagent:/tf2/cost-probe.jar=/tf2/capture/monitor-cost.json')
 volumes += [str(f)+':'+name+':ro'for f,name in mounts.items()]
 command=['/approved-jdk/bin/java','-Xms32m','-Xmx256m','-XX:ParallelGCThreads=1','-XX:CICompilerCount=2',*opts,'-jar','/app.jar','--server.port=8080','--spring.main.banner-mode=off']
 return {'services':{'app':{'image':image,'command':command,'volumes':volumes,'cpus':1,'mem_limit':'768m'},'load-client':{'image':image,'entrypoint':['sleep','infinity'],'cpus':1,'mem_limit':'128m'}},'networks':{'default':{'internal':True}}}

def controlled_trial(out,tier,mode,warm,measure,rate,diagnostic=False):
 from sockshop import Deployment
 from run_sockshop_cost import Sampler,resource_snapshot
 verify();out.mkdir(parents=True,exist_ok=False);save(out/'compose.json',controlled_spec(out,tier,mode,diagnostic));dep=Deployment(argparse.Namespace(project='tf2-scaling-'+secrets.token_hex(5)),out,out/'compose.json');result={'state':'failed','task':'controlled','tier':tier,'mode':mode,'rate':rate}
 def phase(label,seconds,count=None):
  start=time.monotonic_ns();jobs=[]
  def request(i):
   h=hashlib.sha256((str(out)+label+str(i)).encode()).hexdigest();t=time.monotonic_ns();r=dep.compose('exec','-T','load-client','curl','--noproxy','*','-sS','--max-time','20','-w','\n%{http_code}\n%{time_total}','-H','traceparent: 00-'+h[:32]+'-'+h[32:48]+'-01','http://app:8080/query',check=False)
   try:body,status,latency=r.stdout.rsplit('\n',2);body=json.loads(body);status=int(status);latency=float(latency)
   except Exception:body=r.stdout;status=0;latency=None
   n=TIERS[tier];expected={**{'target':1009+(sum(100+i%7 for i in range(n))if tier=='related-high'else 0)},**{'f%d'%i:100+i%7 for i in range(n)}}
   return {'case':label+'-%d'%i,'message':h[:32]+'/'+h[32:48],'response':body,'http_status':status,'http_seconds':latency,'start_ns':t,'end_ns':time.monotonic_ns(),'business_passed':status==200 and body==expected,'error':r.stderr}
  with ThreadPoolExecutor(max_workers=2)as pool:
   for i in range(count if count is not None else round(seconds*rate)):
    wait=start/1e9+i/rate-time.monotonic()
    if wait>0:time.sleep(wait)
    jobs.append(pool.submit(request,i))
   wait=start/1e9+seconds-time.monotonic()
   if wait>0:time.sleep(wait)
   rows=[j.result()for j in jobs]
  return {'start_ns':start,'end_ns':time.monotonic_ns(),'requests':rows}
 try:
  dep.compose('up','-d','--pull','never',timeout=180)
  # TCP readiness only: do not execute business query as extra warm-up.
  for i in range(100):
   logs=dep.compose('logs','--no-color','app',check=False).stdout
   if 'Started Application'in logs:break
   if 'Application run failed'in logs or 'APPLICATION FAILED'in logs or 'FATAL ERROR'in logs or 'Exception in thread'in logs:raise RuntimeError('startup failure')
   time.sleep(1)
  else:raise RuntimeError('startup timeout')
  containers={'app':dep.compose('ps','-q','app').stdout.strip()}
  with Sampler(containers,2,out/'resources.jsonl',observed_roles=('app',))as sampler:
   a=phase('warmup',warm);save(out/'warmup.json',a)
   before=resource_snapshot(containers);save(out/'measure-cpu-before.json',before)
   b=phase('measure',measure);save(out/'measure.json',b)
   after=resource_snapshot(containers);save(out/'measure-cpu-after.json',after)
  if measure>=5:save(out/'resource-summary.json',sampler.summary(b['start_ns'],b['end_ns']))
  result.update(state='captured',requests=len(a['requests'])+len(b['requests']),business_passed=sum(x['business_passed']for x in a['requests']+b['requests']))
 except Exception as e:result['error']=str(e);(out/'failure.log').write_text(traceback.format_exc())
 finally:
  dep.compose('stop','-t','30','app',check=False,timeout=90);dep.diagnostics();r=dep.compose('down','--volumes','--remove-orphans',check=False,timeout=90);result['cleanup_returncode']=r.returncode;save(out/'result.json',result)
 verify();print(out.name,result,flush=True);return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['seal','build','controlled-trial']);p.add_argument('--out',type=Path);p.add_argument('--tier',choices=list(TIERS));p.add_argument('--mode',choices=MODES);p.add_argument('--warm',type=int,default=0);p.add_argument('--seconds',type=int,default=3);p.add_argument('--rate',type=int,default=2);a=p.parse_args()
 if a.stage=='seal':seal()
 elif a.stage=='build':build()
 else:controlled_trial(a.out.resolve(),a.tier,a.mode,a.warm,a.seconds,a.rate)
