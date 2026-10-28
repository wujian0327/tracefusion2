#!/usr/bin/env python3
"""Close original Piggy return/sink inventory; independently score saved FIRST runs.

Oracle rules and native decoding are distinct modules. No algorithm/Agent edits.
All first task/capture files are hashed before adding derived evaluation outputs.
"""
import argparse,collections,csv,datetime,json,shutil,subprocess,traceback
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_portability_first import TASK_ROOT,verify,log
import portability_piggy_oracle as oracle
from run_mirror_capability_probe import read_events,native_answer

STATES=('known_correct','known_wrong','unknown','evidence_invalid','target_binding_unsupported','instrumented_business_failure','oracle_unavailable')
def coord(event,field):return[event['call'],event['ordinal'],field['path'],field['owner'],field['field'],field['version']]
def raw_rows(path):return[json.loads(l)for l in path.read_text().splitlines()]

def prepare(root,out):
    verify(root);out.mkdir(parents=True);manifest={}
    for base in [root/'original/piggymetrics/attempt04-approved8',root/'tool-runs']:
        for p in sorted(base.rglob('*')):
            if p.is_file()and ('tool-runs'not in str(p)or '/piggymetrics-'in str(p)):manifest[str(p.relative_to(root))]=sha(p)
    save(out/'first-captures-manifest.json',{'files':manifest,'core':load(root/'protocol-start.json')['TF_commit'],'all_prior_captures_read_only':True})
    source=root/'upstream/piggymetrics';files=[p for role in('account-service','auth-service','notification-service')for p in(source/role/'src/main/java').rglob('*.java')]
    sites=oracle.inventory_entries()
    for q in sites:
        for sink in q['sinks']:
            role={'piggymetrics-1':'piggy-account','piggymetrics-2':'piggy-account','piggymetrics-3':'piggy-auth','piggymetrics-5':'piggy-notification'}[q['api']];m=load(root/'metadata'/role/'model.json')['methods'][sink['method']];i=next(i for i in m['instructions']if i['index']==sink['site']);assert i['owner']+'.'+i['name']+i['desc']==sink['callee']
    save(out/'oracle-and-sink-protocol.json',{'sealed_before_this_scoring':True,'retrospective_review':True,'note':'Original first captures already existed. Do not misrepresent this review as pre-registered before their execution. Core/Agent/models unchanged.','sources_sha256':{str(p.relative_to(root)):sha(p)for p in files},'oracle_code_sha256':sha(HERE/'portability_piggy_oracle.py'),'native_decoder_sha256':sha(HERE/'run_mirror_capability_probe.py'),'inventory':sites,'scope':'Every scalar/null actual original method-return leaf AND actual original persistence argument leaves; empty containers separately audited structurally. Supplementary outbound RPC not mixed with primary counts.','coordinate_rule':'Pair API/case/path tasks across different JVMs. Known answers require their own raw message/object/field/version and source occurrence; never equate object IDs across JVMs or choose by equal values. Missing source/sink coordinates remain explicit.','clock_rule':'Fresh Date is a generation fact outside input/DB/RPC-read boundary, not an input-derived source. Do not mix selection/control into data operands.'})
    return manifest

def verify_passwords(root,out,control):
    jar=next((root/'metadata/piggy-auth/libs').glob('spring-security-crypto-*.jar'));classes=out/'password-oracle-classes';classes.mkdir()
    p=subprocess.run(['javac','-cp',str(jar),'-d',str(classes),str(HERE/'PortabilityPasswordOracle.java')],capture_output=True,text=True);assert p.returncode==0,p.stderr
    items=[];lines=[]
    for c in control['cases']:
        if c['api']not in('piggymetrics-2','piggymetrics-3')or c['http_status']!=200:continue
        file=root/'original/piggymetrics/attempt04-approved8'/(c['api']+'-'+c['case']+'-database-after.jsonl');docs=oracle.database(file)[('piggy-auth','users')];doc=[d for d in docs if d['_id']==c['body']['username']];assert len(doc)==1
        lines.append(c['body']['password']+'\t'+doc[0]['password']);items.append({'api':c['api'],'case':c['case'],'database_fact_sha256':sha(file)})
    p=subprocess.run(['java','-cp',str(classes)+':'+str(jar),'PortabilityPasswordOracle'],input='\n'.join(lines)+'\n',capture_output=True,text=True);assert p.returncode==0,p.stderr;assert p.stdout.splitlines()==['true']*len(lines)
    save(out/'password-database-checks.json',{'checks':[dict(i,original_BCrypt_matches_fixture=True)for i in items],'library_sha256':sha(jar),'probe_sha256':sha(HERE/'PortabilityPasswordOracle.java'),'no_TF_or_MT_loaded':True})

def native_context(root,out,api):
    home=root/'tool-runs'/api/'mirrortaint/fixed-adapter';work=out/'native-decoding'/api;work.mkdir(parents=True);(work/'role').symlink_to(home/'capture',target_is_directory=True)
    try:return read_events(work,'role'),None
    except Exception as e:return None,str(e)

def queried_state(home,case):
    db=oracle.database(home/(case['api']+'-'+case['case']+'-database-before.jsonl'));name=case['body']['username']
    return {k:len([d for d in db.get(k,[])if d['_id']==name])for k in [('piggy-account','accounts'),('piggy-auth','users')]}

def evaluate_account(root,out,controls):
    home=root/'tool-runs/piggymetrics-2/mirrortaint/fixed-adapter';run=load(home/'results.json');nr,error=native_context(root,out,'piggymetrics-2');assert not error,error
    nativecases={c['case']:c for c in run['cases']};records=[];evidencechecks=[]
    plans=load(root/'planning-first/piggymetrics-2/summary.json')['rows'];query_by_path={r['query']['path']:r for r in plans};assert len(query_by_path)==len(plans)
    for original in controls:
        if original['api']!='piggymetrics-2' or original['http_status']!=200:continue
        c=nativecases[original['case']];assert c['body']==original['body']and c['http_status']==original['http_status'];checks=oracle.account_return_checks(c,home);original_state=queried_state(root/'original/piggymetrics/attempt04-approved8',original);assert queried_state(home,c)==original_state;assert all(v==0 for v in original_state.values());evidencechecks.append({'case':c['case'],'checks':checks,'same_original_code_queried_record_absence':True,'initial_whole_database_byte_identity':False,'nonidentical_fixture_fields':'Unqueried tf2-current record, BCrypt-generated hashes, OAuth tokens and clocks differ; not claimed identical full DB. Read predicates are source-reviewed by requested username.'})
        message=c['message'];target=next(r for r in nr if r['kind']=='target'and r['context'].get('message')==message)
        for path,value in oracle.flatten(c['response']):
            rule=oracle.return_rule('piggymetrics-2',path);assert rule.get('source')!='unresolved';expected=[]
            if rule['source']:
                sources=[r for r in nr if r['kind']=='source' and r['root']==target['root']and r['call']=='@argument:0'];assert len(sources)==1
                fields=[f for f in sources[0]['fields']if f['path']=='/username'];assert len(fields)==1;expected=[coord(sources[0],fields[0])]
                assert fields[0]['value']==c['body']['username'] # ONLY consistency, never source choice.
            wire=[f for f in target['wire_fields']if f['path']==path];assert len(wire)==1
            answer=native_answer(nr,message,path);actual=answer.get('sources',[]);known=answer['state']=='known';correct=known and{tuple(v)for v in actual}=={tuple(v)for v in expected}
            mt={'state':('known_correct'if correct else'known_wrong')if known else answer['state'],'expected':expected,'actual':actual,'answer':answer,'target_coordinate':{k:wire[0][k]for k in('owner','field','version')},'message':message,'oracle_adequate':True,'TP':len({tuple(v)for v in actual}&{tuple(v)for v in expected})if known else 0,'FP':len({tuple(v)for v in actual}-{tuple(v)for v in expected})if known else 0,'FN':len({tuple(v)for v in expected}-{tuple(v)for v in actual})if known else len(expected)}
            tf={}
            for mode in('full','selective'):
                planned=query_by_path.get(path)
                if planned is None:
                    tf[mode]={'state':'target_binding_unsupported','reason':'Frozen task listed only collection element paths; actual null collection field was not bound. Actual original target stays in denominator.','expected':[],'oracle_adequate':True,'TP':0,'FP':0,'FN':0};assert rule['source']is None;continue
                index=planned['index'];dep=root/'tool-runs/piggymetrics-2'/mode/('query-%03d'%index);tc=next(c for c in load(dep/'results.json')['cases']if c['case']==original['case']);assert tc['body']==original['body']and tc['http_status']==original['http_status'];oracle.account_return_checks(tc,dep);assert queried_state(dep,tc)==original_state
                raw=raw_rows(dep/'capture/events.jsonl');expected_tf=[]
                if rule['source']:
                    returns=[r for r in raw if r['kind']=='binding-return'and r.get('message')==tc['message']];assert len(returns)==1
                    args=[r for r in raw if r['kind']=='binding-input'and r.get('frame')==returns[0]['frame']and r['argument']==0];assert len(args)==1
                    fs=[f for f in args[0]['fields']if f['path']=='/username'];assert len(fs)==1
                    expected_tf=[{'service':'piggy-account','seq':args[0]['seq'],'path':'/username','owner':fs[0]['owner'],'field':fs[0]['field'],'version':fs[0]['version'],'argument':0,'frame':args[0]['frame'],'message':tc['message']}]
                prior=load(root/'checkpoint-audit-03/piggymetrics-2'/mode/('query-%03d'%index)/'evaluation.json');prediction=next(p for p in prior['predictions']if p['case']==original['case']and p['path']==path);state=prediction['status'];assert state in('unknown','evidence_invalid')
                tf[mode]={'state':state,'expected':expected_tf,'oracle_adequate':True,'message':tc['message'],'tool_prediction':prediction,'TP':0,'FP':0,'FN':len(expected_tf)}
            records.append({'api':'piggymetrics-2','case':original['case'],'kind':'method-return','path':path,'independent_rule':rule,'data_relation_count':len(expected),'baseline':mt,'TF':tf,'gap':{mode:'baseline_correct_TF_unanswered'if mt['state']=='known_correct'and tf[mode]['state']!='known_correct'else'both_unanswered'for mode in('full','selective')}})
    save(out/'account-return-independent-checks.json',evidencechecks);return records

def sinks(root,control):
    inv={q['api']:q for q in oracle.inventory_entries()};home=root/'original/piggymetrics/attempt04-approved8';records=[];structural=[]
    for c in control['cases']:
        if c['http_status']!=200:continue
        api=c['api'];db=oracle.database(home/(api+'-'+c['case']+'-database-after.jsonl'))
        if api in('piggymetrics-1','piggymetrics-2'):
            name='tf2-current'if api.endswith('-1')else c['body']['username'];docs=[d for d in db[('piggy-account','accounts')]if d['_id']==name];assert len(docs)==1;doc=docs[0];v={('name'if k=='_id'else k):value for k,value in doc.items()if k!='_class'}
            # Missing persisted nullable fields are present in original entity
            # getters; include these save-argument obligations explicitly.
            for k in('incomes','expenses','note'):v.setdefault(k,None)
            if api.endswith('-1'):
                assert v['note']==c['body']['note']and v['incomes']==c['body']['incomes']and v['expenses']==c['body']['expenses'];assert v['saving']['currency']==c['body']['saving']['currency']
                for field in('amount','interest'):assert str(v['saving'][field])==str(c['body']['saving'][field])
            groups=[('account-save'if api.endswith('-1')else'account-create-save',v)]
            if api.endswith('-2'):
                u=[d for d in db[('piggy-auth','users')]if d['_id']==name];assert len(u)==1;groups.append(('remote-auth-user-save',{'username':u[0]['_id'],'password':u[0]['password']}))
        elif api=='piggymetrics-3':
            u=[d for d in db[('piggy-auth','users')]if d['_id']==c['body']['username']];assert len(u)==1;groups=[('user-save',{'username':u[0]['_id'],'password':u[0]['password']})]
        elif api=='piggymetrics-5':
            ds=[d for d in db[('piggy-notification','recipients')]if d['_id']=='tf2-current'];assert len(ds)==1;v={('accountName'if k=='_id'else k):value for k,value in ds[0].items()if k!='_class'};assert v['email']==c['body']['email'];groups=[('recipient-save',v)]
        else:groups=[]
        for sink,value in groups:
            for path,_ in oracle.flatten(value):records.append({'api':api,'case':c['case'],'kind':'persistence','sink':sink,'path':path,'original_database_fact_available':True,'independent_logical_rule':'See oracle-and-sink-protocol.json; DB facts verify values but do NOT supply Java object/version/call sink coordinates','oracle_adequate':False,'oracle_gap':'Actual persistence argument object/field/write version and its call occurrence are not present in the frozen first exporter. Do not substitute DB storage values for Java heap instances.','baseline_state':'target_binding_unsupported','TF_full_state':'target_binding_unsupported','TF_selective_state':'target_binding_unsupported','TP_FP_FN':None})
            for k,x in value.items():
                if isinstance(x,(list,dict))and not x:structural.append({'api':api,'case':c['case'],'sink':sink,'path':'/'+k,'empty_container':type(x).__name__})
    return records,structural

def diagnose(root,out):
    rows=[]
    for api in('piggymetrics-2','piggymetrics-5'):
        controls={c['case']:c for c in load(root/'original/piggymetrics/attempt04-approved8/results.json')['cases']if c['api']==api}
        for result in sorted((root/'tool-runs'/api).glob('*/*/results.json')):
            run=load(result);mode=run['mode']
            if mode=='mirrortaint':continue
            home=result.parent;raw=raw_rows(home/'capture/events.jsonl');problems=[r for r in raw if r['kind']=='problem'];logs=(home/'compose.log').read_text();failed=[{'case':c['case'],'message':c['message'],'original_http':controls[c['case']]['http_status'],'instrumented_http':c['http_status']}for c in run['cases']if controls[c['case']]['http_status']==200 and c['http_status']!=200]
            if not failed and not problems:continue
            messages=collections.Counter(p['message']for p in problems);cause=''
            if failed:
                if 'Unmodeled JDK read-effect runtime'in logs:cause='Runtime contract throws in ReadEffectHooks.enter → ResponseBindingHooks.enter → Recorder.enter rethrows → Spring500 before user method body'
                elif 'enter:java.lang.IllegalStateException: Only String map keys admitted'in logs:cause='Root input snapshot in ResponseBindingHooks.enter walks enum-key Map → throws → Recorder.enter rethrows → Spring500 before user method body'
                else:cause='Needs separate exception-chain review'
            else:cause='Non-throwing capture/validation failure; business completion not changed'
            rows.append({'api':api,'mode':mode,'query':home.name,'capture':str(home.relative_to(root)),'failed_requests':failed,'problem_messages':dict(messages),'direct_failure_chain':cause,'raw_log_sha256':sha(home/'compose.log'),'raw_events_sha256':sha(home/'capture/events.jsonl'),'source_rethrow_sites':['PlannedServiceAgent.java Recorder.enter catch(Throwable) records problem then throws IllegalStateException','ReadEffectHooks.enter runtime whitelist verification','ResponseBindingHooks.enter sourceSnapshot(args) and Map type guard'],'scope_note':'Do not conflate nonthrowing source-read/json-read diagnostics with the exception that changes business response.'})
    save(out/'business-preservation-root-causes.json',rows);return rows

def main(root,out):
    manifest=prepare(root,out);control=load(root/'original/piggymetrics/attempt04-approved8/results.json');verify_passwords(root,out,control)
    returns=evaluate_account(root,out,control['cases']);persist,structural=sinks(root,control);causes=diagnose(root,out)
    other=[];native_failures={}
    for api in('piggymetrics-1','piggymetrics-3','piggymetrics-4','piggymetrics-5'):
        nr,error=native_context(root,out,api);native_failures[api]=error
        for c in control['cases']:
            if c['api']!=api or c['http_status']!=200 or api in('piggymetrics-1','piggymetrics-3'):continue
            for path,_ in oracle.flatten(c['response']):other.append({'api':api,'case':c['case'],'kind':'method-return','path':path,'independent_logical_rule':oracle.return_rule(api,path),'oracle_adequate':False,'oracle_gap':'Frozen complete source-instance projection unavailable for runtime Principal or enum Map; no expected source coordinates guessed','baseline_state':'evidence_invalid'if error else'pending','TF_full_state':'instrumented_business_failure'if api.endswith('-5')else'target_binding_unsupported','TF_selective_state':'instrumented_business_failure'if api.endswith('-5')else'target_binding_unsupported','status_note':'API5 failures retain original target obligations; API4 TF had no expressible target plan. Global native exporter errors retain batch invalidity; no silent per-root salvage.'})
    summary={'core':load(root/'protocol-start.json')['TF_commit'],'first_capture_manifest_sha256':sha(out/'first-captures-manifest.json'),'oracle_protocol_sha256':sha(out/'oracle-and-sink-protocol.json'),'account_return_targets':len(returns),'per_tool':{},'remaining_return_targets':len(other),'persistence_targets':len(persist),'empty_container_checkpoints':len(structural),'native_export_failures':native_failures,'all40APIs_retained':True,'no_new_cost_or_contracts':True,'primary_task_complete':False,'reason':'All five APIs are inventoried and per-task rows retained, but frozen first captures lack required void-sink, Principal and enum Map source coordinates. Complete fine-grained task accuracy/Recall is therefore not asserted.'}
    for mode in('baseline','full','selective'):
        rs=[r['baseline']if mode=='baseline'else r['TF'][mode]for r in returns];summary['per_tool'][mode]={'states':dict(collections.Counter(r['state']for r in rs)),'TP':sum(r['TP']for r in rs),'FP':sum(r['FP']for r in rs),'FN':sum(r['FN']for r in rs)}
    summary['paired_gap_counts']={m:dict(collections.Counter(r['gap'][m]for r in returns))for m in('full','selective')}
    save(out/'account-return-paired-instances.json',returns);save(out/'remaining-task-instances.json',other+persist);save(out/'empty-container-structural-checkpoints.json',structural);save(out/'summary.json',summary)
    with(out/'paired-account-return.csv').open('w',newline='')as f:
        w=csv.writer(f);w.writerow(['api','case','path','expected_data_relations','MirrorTaint','TF_full','TF_selective','gap_full','gap_selective'])
        for r in returns:w.writerow([r['api'],r['case'],r['path'],r['data_relation_count'],r['baseline']['state'],r['TF']['full']['state'],r['TF']['selective']['state'],r['gap']['full'],r['gap']['selective']])
    for p,h in manifest.items():assert sha(root/p)==h,p
    verify(root);log(root,'07-piggy-first-capability-scoring',{'summary':str(out/'summary.json'),'summary_sha256':sha(out/'summary.json'),'first_captures_unchanged':True,'algorithm_contracts_unchanged':True});print(summary)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.root.resolve(),a.out.resolve())
