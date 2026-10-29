#!/usr/bin/env python3
"""Keep baseline export, truth adequacy, TF state and API completeness separate."""
import argparse,collections,csv,json,sys,hashlib,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
import external_transfer_oracle as oracle
from run_mirror_capability_probe import read_events,native_answer
HOME=ROOT/'artifacts/external-frozen-transfer-20261029'
SOURCE_CALIBRATED=False

def tool_name(r):
 return r['tool'] if r['tool']=='MT-B0' else r['version']+'-'+r['tool']

def diagnostic_category(r):
 error=str(r.get('error') or r.get('oracle_gap') or '')
 reason=str(r.get('answer',{}).get('reason',''))
 if r['tool']=='MT-B0' and 'serialized field instance absent' in reason:return 'baseline_wire_target_export_gap'
 if 'Query target absent or duplicated' in error:return 'response_target_binding_gap_not_proof_of_log_corruption'
 if 'Collector problem' in error or 'capture_invalid' in error:return 'monitor_failure_capture_rejected'
 if 'serializer' in error.lower():return 'serializer_contract_or_projection_limit'
 if 'runtime' in error.lower():return 'runtime_contract_limit'
 if r['state'].startswith('not_executed'):return 'official_request_not_executed_see_preparation_diagnostic'
 if r['state']=='instrumented_business_failure':return 'business_behavior_changed'
 return r['state']

def capture_diagnostics(source):
 paths=list((source/'capture').glob('*.jsonl'));problems=[];footers=[];kinds=collections.Counter()
 for p in paths:
  for line in p.open():
   try:r=json.loads(line)
   except ValueError:continue
   kinds[r.get('kind')]+=1
   if r.get('kind')=='problem':problems.append(r)
   if r.get('kind') in ('closed','capture-footer'):footers.append(r)
 prep=source/'ready-portal-admin-path.json'
 preparation=None
 if prep.exists():
  observed=load(prep)
  if observed.get('http_status',0)>=400:preparation={'http_status':observed['http_status'],'response':observed.get('response')}
 return {'event_kinds':dict(kinds),'problems':problems,'footers':footers,'preparation_business_failure':preparation}

def original(q):
 p=HOME/'ae7fe8d/original'/q['application']/('sealed-'+q['id'])/'results.json'
 return (load(p),p.parent)if p.exists()else(None,None)
def missing_run_state(api,version,mode,index=None):
 p=HOME/('progress.json'if SOURCE_CALIBRATED else'matrix-progress.json')
 if not p.exists():return {'state':'pending'}
 matrix=load(p)
 matches=[r for r in matrix['results']if r.get('api')==api and r.get('version',version)==version and r.get('mode')==mode and r.get('index')==index]
 if matches:return {'state':'deployment_driver_failure_without_closed_receipt','error':str(matches[-1])}
 return {'state':'not_executed_matrix_closed'if matrix.get('complete')else'pending'}
def score_native(q,out):
 source=HOME/'ae7fe8d/tool-runs'/q['id']/'mirrortaint/fixed-adapter'
 if not(source/'results.json').exists():return [],missing_run_state(q['id'],'ae7fe8d','mirrortaint')
 result=load(source/'results.json');work=out/'native-view'/q['id'];work.mkdir(parents=True);(work/'role').symlink_to(source/'capture',target_is_directory=True)
 try:rows=read_events(work,'role');error=None
 except Exception as e:rows=[];error=str(e)
 proto=load(HOME/'oracle-before-tools.json');records=[];control,_=original(q)
 for c in(control or{}).get('cases',[]):
  if c['api']!=q['id']or not oracle.original_root_returns(c):continue
  other=next((r for r in result['cases']if r['case']==c['case']),None)
  for path,value in oracle.targets(c['response']):
   if q['id']=='apollo-4':continue # Empty body is NOT a JSON-null target.
   r=oracle.rule(proto,q['id'],path);expected=None;gap=None;answer={};status='pending'
   if other is None:status='not_executed_after_environment_failure'
   elif other['http_status']!=c['http_status']:status='instrumented_business_failure'
   elif error:status='evidence_invalid'
   else:
    answer=native_answer(rows,other['message'],path);status=answer['state'];ts=[v for v in rows if v['kind']=='target'and v['context'].get('message')==other['message']]
    try:
     if len(ts)!=1:raise ValueError('Actual root return absent/ambiguous')
     expected=oracle.native_expected(rows,ts[0]['root'],r,path)
    except ValueError as e:gap=str(e)
    if status=='known':status='known_unchecked'if expected is None else'known_correct'if {tuple(x)for x in answer['sources']}=={tuple(x)for x in expected}else'known_wrong'
   got={tuple(x)for x in answer.get('sources',[])};want=None if expected is None else {tuple(x)for x in expected}
   records.append({'api':q['id'],'case':c['case'],'path':path,'tool':'MT-B0','version':'native54fcbfc','state':status,'oracle_adequate':expected is not None,'oracle_gap':gap or error,'expected':expected,'answer':answer,
    'TP':len(got&want)if status.startswith('known_')and want is not None else 0 if want is not None else None,
    'FP':len(got-want)if status.startswith('known_')and want is not None else 0 if want is not None else None,
    'FN':len(want-got)if status.startswith('known_')and want is not None else len(want)if want is not None else None})
 return records,{'state':'captured','capture':str(source),'export_error':error,'actual_source_calls':dict(collections.Counter(r['call']for r in rows if r['kind']=='source')),'known_api_complete':False,'sink_interface':'B0 has no persistence argument export','diagnostics':capture_diagnostics(source)}

def run(out,partial=False):
 out.mkdir(parents=True,exist_ok=False);entries=load(HOME/'task-seal.json')['entries'];rows=[];apis=[]
 for q in entries:
  native,receipt=score_native(q,out);rows.extend(native)
  versions={}
  control,_=original(q)
  targets=[(c,path,value)for c in(control or{}).get('cases',[])if oracle.original_root_returns(c) for path,value in oracle.targets(c['response'])if q['id']!='apollo-4']
  for version in ('ae7fe8d','78a9534'):
   plans=[load(p)for p in sorted((HOME/version/'planning-first'/q['id']).glob('[0-9][0-9][0-9].json'))]
   versions[version]={'planning':dict(collections.Counter(p['status']for p in plans)),'runtime_configurations':{}}
   for mode in ('full','selective'):
    for p in plans:
     home=HOME/version/'tool-runs'/q['id']/mode/('query-%03d'%p['index'])
     if p['status']=='accepted'and(home/'results.json').exists():
      analysis=home/'evaluation-frozen-v3/graph-construction.json'
      if not analysis.exists():
       log=out/(q['id']+'-'+version+'-'+mode+'-'+str(p['index'])+'.log')
       with log.open('w')as f:subprocess.run([sys.executable,str(HERE/'external_frozen_entry.py'),'--stage','evaluate','--version',version,'--api',q['id'],'--mode',mode,'--index',str(p['index']),*(['--source-calibrated']if SOURCE_CALIBRATED else[])],stdout=f,stderr=subprocess.STDOUT)
      state=load(analysis)if analysis.exists()else{'state':'evaluation_driver_failed'}
     else:state={'state':p['status']}if p['status']!='accepted'else missing_run_state(q['id'],version,mode,p['index'])
     scored=load(home/'evaluation-frozen-v3/instances.json')if(home/'evaluation-frozen-v3/instances.json').exists()else[]
     for c,path,value in targets:
      if oracle.wildcard(path)!=p['query']['path']:continue
      complete=next((r for r in scored if r['case']==c['case']and r['path']==path),None)
      if complete is not None:rows.append(complete);continue
      record={'api':q['id'],'case':c['case'],'path':path,'version':version,'tool':mode,'state':state['state'],'oracle_adequate':False,'oracle_gap':'Raw source/target instance evaluation pending'if state['state']=='constructed'else state.get('error'),'TP':None,'FP':None,'FN':None}
      rows.append(record)
     versions[version]['runtime_configurations'][mode+'-'+str(p['index'])]={'state':state['state'],'error':state.get('error'),'diagnostics':capture_diagnostics(home) if (home/'results.json').exists() else None}
  apis.append({'api':q['id'],'original':None if control is None else{**{k:v for k,v in control.items()if k!='cases'},'cases':len(control['cases'])},'MT':receipt,'TF':versions,'sink_sites':q['effect_sink_candidates'],'method_null_or_unbound_root':q['id']in('apollo-3','apollo-4'),'all_task_obligations_answered':False})
 save(out/'instances.json',rows);save(out/'apis.json',apis)
 summary={'partial':partial,'APIs_retained':40,'selected_batch_APIs':10,'no_core_agent_contract_changes':True,'no_performance':True,'api_complete_success_not_claimed':True,'states':{v:dict(collections.Counter(r['state']for r in rows if tool_name(r)==v))for v in ['MT-B0','ae7fe8d-full','ae7fe8d-selective','78a9534-full','78a9534-selective']},'oracle_adequate':dict(collections.Counter(tool_name(r)for r in rows if r['oracle_adequate']))}
 export_tables(out,entries,rows,apis,summary)
 save(out/'summary.json',summary);print(summary,flush=True)

def export_tables(out,entries,rows,apis,summary):
 def write(name,data,fields):
  with(out/name).open('w',newline='')as f:
   w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(data)
 write('instances.csv',[{**r,'oracle_gap':r.get('oracle_gap') or r.get('error'),'diagnostic_category':diagnostic_category(r)}for r in rows],['api','case','path','version','tool','state','diagnostic_category','oracle_adequate','oracle_gap','TP','FP','FN'])
 keys=sorted({(r['api'],r['case'],r['path'])for r in rows});paired=[]
 for key in keys:
  matching={tool_name(r):r for r in rows if(r['api'],r['case'],r['path'])==key}
  assert len(matching)==len([r for r in rows if(r['api'],r['case'],r['path'])==key]),'Duplicate tool target'
  mt=matching.get('MT-B0',{});record=dict(zip(['api','case','path'],key))
  for tool,r in matching.items():record[tool]=r['state']
  for version in ('ae7fe8d','78a9534'):
   full=matching.get(version+'-full',{});sel=matching.get(version+'-selective',{})
   record[version+'_MT_correct_TF_not_correct']=mt.get('state')=='known_correct' and sel.get('state')!='known_correct'
   record[version+'_TF_correct_MT_not_correct']=sel.get('state')=='known_correct' and mt.get('state')!='known_correct'
   record[version+'_full_selective_state_equal']=full.get('state')==sel.get('state') if full and sel else None
  paired.append(record)
 write('paired-gaps.csv',paired,['api','case','path','MT-B0','ae7fe8d-full','ae7fe8d-selective','78a9534-full','78a9534-selective',*[v+s for v in ('ae7fe8d','78a9534')for s in('_MT_correct_TF_not_correct','_TF_correct_MT_not_correct','_full_selective_state_equal')]])
 per_api=[]
 for a in apis:
  q=next(q for q in entries if q['id']==a['api']);selected=[r for r in rows if r['api']==a['api']]
  per_api.append({'api':a['api'],'entry':q['entry'],'queries':len(q['return_targets']),'original':a['original'],'MT':dict(collections.Counter(r['state']for r in selected if r['tool']=='MT-B0')),'TF':{v:dict(collections.Counter(r['state']for r in selected if tool_name(r)==v))for v in('ae7fe8d-full','ae7fe8d-selective','78a9534-full','78a9534-selective')},'sink_sites':len(q['effect_sink_candidates']),'source_sites':len(q['read_source_candidates']),'complete_API_verified':False})
 save(out/'per-api.json',per_api)
 special=[]
 for q in entries:
  control,_=original(q)
  for c in(control or{}).get('cases',[]):
   response=c.get('response')
   if c['http_status']==200 and not oracle.original_root_returns(c):special.append({'api':q['id'],'case':c['case'],'kind':'original-root-exception-handler-response','handler_wire_fields':oracle.targets(response),'declared_entry_return_target':False,'API_kept':True,'answered_source_claim':False})
   if q['id']=='apollo-4':special.append({'api':q['id'],'case':c['case'],'kind':'method-null/empty-HTTP-body','wire_field_target':False,'original_http':c['http_status'],'answered_source_claim':False})
   def empty(v,p=''):
    if isinstance(v,(dict,list)) and not v:special.append({'api':q['id'],'case':c['case'],'kind':'empty-container','path':p or'/','wire_field_target':False,'answered_source_claim':False})
    elif isinstance(v,dict):
     for k,x in v.items():empty(x,p+'/'+k)
    elif isinstance(v,list):
     for i,x in enumerate(v):empty(x,p+'/'+str(i))
   if c['http_status']==200:empty(response)
  for sink in q['effect_sink_candidates']:special.append({'api':q['id'],'kind':'sink-obligation','site':sink,'scored_return_answer_substituted':False,'frozen_TF_sink_query':'unsupported','B0_sink_export':'unsupported'})
  current={t['path']for t in q['return_targets']}
  for legacy in q['legacy_return_targets']:
   if legacy.get('path')not in current:special.append({'api':q['id'],'kind':'legacy-static-candidate-not-in-observed-wire-query-set','target':legacy,'answered_source_claim':False})
 save(out/'non-return-and-structural-obligations.json',special)
 ledger=[]
 reviewed={q['id']:q for q in load(ROOT/'artifacts/portability-first-20261028/task-seal.json')['entries']}
 for q in load(HOME/'task-seal.json')['all40_retained']:
  api=q['id'];current=next((a for a in per_api if a['api']==api),None)
  state='current_matrix' if current else'prior_Piggy_first_and_development_results_separate' if api.startswith('piggymetrics') else'original_roles_started_entry_unverified' if api.startswith('ZLT-') else'original_environment_blocked' if api.startswith(('FEBS-','goodsKill-','SuperMarket-')) else'this_API_common_task_pending'
  ledger.append({**q,'locked_actual_entry':reviewed[api]['entry'],'batch_state':state,'current_batch_result':current})
 assert len(ledger)==40;save(out/'all40-ledger.json',ledger)
 summary['paired_target_rows']=len(paired)
 summary['paired_confirmed_MT_correct_TF_not_correct']={v:sum(r[v+'_MT_correct_TF_not_correct']for r in paired) for v in('ae7fe8d','78a9534')}
 summary['paired_confirmed_TF_correct_MT_not_correct']={v:sum(r[v+'_TF_correct_MT_not_correct']for r in paired) for v in('ae7fe8d','78a9534')}
 summary['paired_limit']='Counts only independently certified answers. Zero identified baseline-leading pairs is not equivalence when baseline target export or truth is incomplete.'
 summary['diagnoses']={v:dict(collections.Counter(diagnostic_category(r)for r in rows if tool_name(r)==v))for v in summary['states']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--partial',action='store_true');p.add_argument('--source-calibrated',action='store_true');a=p.parse_args();SOURCE_CALIBRATED=a.source_calibrated
 if SOURCE_CALIBRATED:HOME=HOME/'source-config-C1'
 run(a.out.resolve(),a.partial)
