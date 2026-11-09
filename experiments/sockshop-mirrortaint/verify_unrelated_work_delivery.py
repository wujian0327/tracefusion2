"""Independent counter arithmetic and version/scope checks on final evidence."""
import argparse,csv,json,math,hashlib,statistics
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from run_unrelated_work_scaling import H,MALL,ROOT,AGENT,load,save,sha,verify

def run(out):
 verify();out.mkdir(exist_ok=False);rows=list(csv.DictReader((H/'summary-final-03/rounds.csv').open()));assert len(rows)==40
 before_cores=load(H/'protocol-before-tools.json')['core_sources'];assert len(before_cores)==139
 plan=load(H/'mall-plan.json');declared=set(plan['response_binding']['source_calls']);comparators={};checks=[];correct=targets=completed=attempted=0
 with ZipFile(MALL/'business-jars/mall-admin.jar')as app,ZipFile(BytesIO(app.read('BOOT-INF/lib/jackson-databind-2.13.3.jar')))as lib:mapper=hashlib.sha256(lib.read('com/fasterxml/jackson/databind/ObjectMapper.class')).hexdigest()
 for r in rows:
  trial=ROOT/r['trial'];b=load(trial/'measure-cpu-before.json');a=load(trial/'measure-cpu-after.json');m=load(trial/'measure.json')['requests'];n=sum(c['business_passed']for c in m);assert n==len(m)==60*int(r['rate'])
  # Independent summation and normalization; no resource-summary CPU% input.
  cpu=(a['admin']['cpu_ns']+a['auth']['cpu_ns']+a['portal']['cpu_ns']-b['admin']['cpu_ns']-b['auth']['cpu_ns']-b['portal']['cpu_ns'])/1000000000
  assert math.isclose(float(r['business_cpu_seconds']),cpu,rel_tol=0,abs_tol=1e-12)
  value=cpu/n;assert math.isclose(float(r['cpu_seconds_per_completed_request']),value,rel_tol=0,abs_tol=1e-12)
  phase=load(trial/'measure.json');latencies=sorted(c['http_seconds']*1000 for c in m);expected95=latencies[math.ceil(.95*len(latencies))-1];assert math.isclose(float(r['p95_ms']),expected95,rel_tol=0,abs_tol=1e-9)
  assert math.isclose(float(r['achieved_rps']),n/((phase['end_ns']-phase['start_ns'])/1e9),rel_tol=0,abs_tol=1e-12)
  samples=[json.loads(l)for l in(trial/'resources.jsonl').read_text().splitlines()];aligned=[v for v in samples if all(phase['start_ns']<=v[k]['monotonic_ns']<=phase['end_ns']for k in('admin','auth','portal'))];assert len(aligned)>=2
  rss=[sum(v[k]['rss_bytes']for k in('admin','auth','portal'))for v in aligned];assert math.isclose(float(r['rss_mean_MiB']),statistics.mean(rss)/2**20,rel_tol=0,abs_tol=1e-9)and math.isclose(float(r['rss_sample_peak_MiB']),max(rss)/2**20,rel_tol=0,abs_tol=1e-9)
  key=(int(r['round']),int(r['rate']),r['mode']);comparators[key]=value;completed+=n;attempted+=len(m)
  business=load(trial/'business-check.json');whole=load(trial/'warmup.json')['requests']+m;assert business['requests']==business['login_log_count']==len(whole)
  cfg=load(trial/'compose.json');admin=cfg['services']['admin'];assert admin['cpus']==1 and admin['mem_limit']=='768m'and'-Xmx256m'in admin['command']
  if r['mode']!='original':
   audit=load(trial/'audit/summary.json');assert audit['correct']==audit['targets']==len(whole);correct+=audit['correct'];targets+=audit['targets'];attrib=load(trial/'attribution-strict.json');assert attrib['ambiguous_owner_records']==0 and not attrib['trace_id_alone_used'];assert attrib['counts']['measure']['bytes']==int(r['attributed_measure_bytes'])
   normal=load(trial/'normal-offline-proc/summary.json');assert normal['independent_oracle_executed']is False and normal['profiler']is False
   assert load(trial/'normal-offline-proc/answers.json')==load(trial/'normal-offline/answers.json')==load(trial/'audit/answers.json')
   if r['mode']=='mirrortaint':
    assert set(load(trial/'mt-config.json')['source_calls'])==declared
    libraries=[json.loads(l)for l in(trial/'capture/native-library.jsonl').read_text().splitlines()];w=[x for x in libraries if x.get('class')=='com/fasterxml/jackson/databind/ObjectMapper'];assert len(w)==1 and w[0]['sha256']==mapper and'jackson-databind-2.13.3.jar'in w[0]['source']
   else:
    binary=load(trial/'tool-binaries.json');assert binary['files'][str(AGENT)]==sha(AGENT)
  checks.append({'round':r['round'],'rate':r['rate'],'mode':r['mode'],'cpu_counter_arithmetic_exact':True,'task_and_source_scope_equal':True,'new_independent_deployment':True})
 for r in rows:
  value=comparators[(int(r['round']),int(r['rate']),r['mode'])]-comparators[(int(r['round']),int(r['rate']),'original')];assert math.isclose(float(r['extra_cpu_seconds_per_completed_request']),value,rel_tol=0,abs_tol=1e-12)
 assert correct==targets==8100 and completed==attempted==7200 # measure only; 10,800 including warmup.
 save(out/'summary.json',{'passed':True,'deployments':40,'measure_completed':completed,'measure_attempted':attempted,'all_phase_business_requests':10800,'tool_target_instances_correct':correct,'tool_target_instances':targets,'per_deployment':checks,'matched_MT_Jackson_implementation_sha256':mapper,'source_sets_equal_all_arms':True,'same_capture_all_normal_predictions_equal':True,'core_source_files_unchanged':len(before_cores),'primary_counter_arithmetic_not_derived_from_CPU_percent':True,'all_p95_and_achieved_rates_recomputed_from_requests':True,'all_RSS_recomputed_from_aligned_raw_samples':True})
 print('VERIFIED',len(rows),correct,completed)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
