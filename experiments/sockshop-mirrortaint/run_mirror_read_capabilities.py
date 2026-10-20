#!/usr/bin/env python3
"""Matched original-JAR read-entry capabilities on the sealed 62-family set.

Same seeded documents and requests in each tool's fresh deployment. Native
predictions never read the independently reviewed expected-source projections.
Unimplemented entry adapters stay pending in the full inventory, not excluded.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import traceback
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
from build_mirror_capability import configure
from run_mirror_capability_probe import read_events,native_answer

SEED=20261020


def independently_expected(q,c,path,rows,target):
    repo=[r for r in rows if r['kind']=='source' and r['root']==target['root'] and not r['call'].startswith('@argument')]
    if q['role']=='station' and '.queryById(' in q['entry']:
        if not c['database_documents']:
            assert c['response']['status']==0 and c['response']['data']==c['request_path'].rsplit('/',1)[-1]
            candidates=[r for r in rows if r['kind']=='source' and r['root']==target['root'] and r['call']=='@argument:0']
            relative=''
        else:candidates=repo;relative='/name'
    else:
        relative=path.removeprefix('/data');candidates=repo
        if q['role']=='train' and '.retrieve(' in q['entry']:
            assert len(repo)==2,'Original Train.retrieve must perform two reads'
            candidates=repo[1:]
    assert len(candidates)==1,'Independent source invocation absent/ambiguous'
    r=candidates[0];fs=[f for f in r['fields'] if f['path']==relative];assert len(fs)==1,'Independent literal source projection absent/ambiguous'
    f=fs[0]
    if c['database_documents'] and relative:
        declared=q['target'].rsplit('.',1);declared=declared[0].replace('.','/')+'.'+declared[1]
        if q['role']=='station' and '.queryById(' in q['entry']:declared='fdse/microservice/entity/Station.name'
        assert f.get('field')==declared or f.get('field','').startswith(('@list:','@element:')) and q['target'].endswith(('.distances','.stations')),'Source declaration differs from original query field'
    return {(r['call'],r['ordinal'],relative,f.get('owner'),f.get('field'),f.get('version'))}


def native_evaluate(dest,qs):
    capture=dest/'capture';rows=read_events(capture,qs[0]['role']);run=load(capture/'run.json');result=[]
    for q in qs:
        targets=[];na=0
        for c in run['cases']:
            leaves=old.leaves(c['response'],q['path']) if c['http_status']==200 else []
            if not leaves:na+=1
            for path,value in leaves:
                p={'query':q['id'],'case':c['case'],'path':path,'client_value':value,'message':c['message']}
                a=native_answer(rows,c['message'],path);p['answer']=a
                candidates=[r for r in rows if r['kind']=='target' and r['context'].get('message')==c['message']]
                try:
                    assert len(candidates)==1,'Actual returned object witness absent/ambiguous'
                    expected=independently_expected(q,c,path,rows,candidates[0]);p['expected']=[list(v) for v in expected]
                    serialized=[f for f in candidates[0].get('wire_fields',[]) if f['path']==path]
                    assert len(serialized)==1 and serialized[0]['observed'].get('value')==value,'Serialized field/client JSON mismatch'
                    actual={tuple(v) for v in a.get('sources',[])}
                    if a['state']=='known':p['state']='known_correct' if actual==expected else 'known_wrong'
                    else:p['state']=a['state']
                    p.update(tp=len(actual&expected) if a['state']=='known' else 0,fp=len(actual-expected) if a['state']=='known' else 0,fn=len(expected-actual) if a['state']=='known' else len(expected))
                except (AssertionError,ValueError) as e:p.update(state=a['state'] if a['state']!='known' else 'oracle_unavailable',oracle_error=str(e))
                targets.append(p)
        result.append({'id':q['id'],'requests':len(run['cases']),'N/A_requests':na,'targets':targets})
    save(dest/'native-evaluation.json',result);return result


def run(out,base,bundle,inventory,tf_too,port_offset=0):
    out.mkdir(parents=True,exist_ok=True);seal=load(HERE/'capability-comparison-62-20261020.json');groups=defaultdict(list)
    for q in seal['queries']:groups[q['entry']].append(q)
    original_observed=old.observed
    request_method=old.Client.request
    if port_offset:
        def request(self,method,url,*args,**kwargs):
            for port in range(18720,18725):url=url.replace('127.0.0.1:'+str(port)+'/','127.0.0.1:'+str(port+port_offset)+'/')
            return request_method(self,method,url,*args,**kwargs)
        old.Client.request=request
    entries=[]
    for entry,qs in groups.items():
        q=qs[0]
        # This driver implements existing single-read/list fixtures. Every other
        # family remains explicitly pending in the complete 62-family inventory.
        eligible=q['role'] in ('station','train','route','price') and not any(x in q['http'] for x in ('{start}','namelist','idlist'))
        state={'entry':entry,'queries':[q['id'] for q in qs],'status':'not_yet_run' if not eligible else 'pending'};entries.append(state)
        if not eligible:continue
        dest=out/q['id']
        if not dest.exists():
            dest.mkdir();capture=dest/'capture';capture.mkdir();save(dest/'protocol.json',{'queries':qs,'seed':SEED,'native_bundle_sha256':sha(bundle/'build.json'),'original_jar_sha256':sha(base/q['role']/'original.jar'),'scope':'Original repository read entry; six fixed fixture structures; no source answer in prediction.'})
            def observed(spec,name,role,capt,bld):
                original_observed(spec,name,role,capt,bld)
                if role==q['role']:configure(spec,capt,base,bundle,q)
                if port_offset:
                    spec['services'][name]['ports']=[v.replace('127.0.0.1:'+str(18720+i)+':','127.0.0.1:'+str(18720+i+port_offset)+':') for v in spec['services'][name].get('ports',[]) for i in [list(old.ROLES).index(role) if q['role']=='basic' else 0]]
            old.observed=observed
            try:old.capture_train(capture,base,q,SEED)
            except Exception as e:save(dest/'execution-error.json',{'error':str(e),'traceback':traceback.format_exc()})
            finally:old.observed=original_observed
        try:
            assert load(dest/'capture/run.json')['status']=='business-completed'
            evaluations=native_evaluate(dest,qs);state.update(status='native_evaluated',targets=sum(len(e['targets']) for e in evaluations),known_correct=sum(t['state']=='known_correct' for e in evaluations for t in e['targets']),known_wrong=sum(t['state']=='known_wrong' for e in evaluations for t in e['targets']))
        except Exception as e:state.update(status='execution_or_evidence_invalid',error=str(e));save(dest/'evaluation-error.json',{'error':str(e),'traceback':traceback.format_exc()})
        save(out/'progress.json',{'entries':entries,'complete_scope':False,'remaining_families_are_pending_not_excluded':True})
        print(json.dumps(state,ensure_ascii=False),flush=True)
        if tf_too and state['status']=='native_evaluated':
            for query in qs:
                planpath=inventory/query['id']/'plan.json'
                if not planpath.exists():continue
                tf=out/('tf-'+query['id'])
                if not tf.exists():
                    tf.mkdir();old.query_build(tf/'build',base,query,load(planpath));capt=tf/'capture';capt.mkdir()
                    try:old.capture_train(capt,tf/'build',query,SEED)
                    except Exception as e:save(tf/'execution-error.json',{'error':str(e),'traceback':traceback.format_exc()})
                try:
                    result=old.evaluate(tf/'capture',tf/'build',query)
                    native_run=load(dest/'capture/run.json');tf_run=load(tf/'capture/run.json')
                    assert len(native_run['cases'])==len(tf_run['cases'])
                    for a,b in zip(native_run['cases'],tf_run['cases']):
                        assert all(a[k]==b[k] for k in ('case','request_path','database_documents','response','http_status')),'Matched input/business response differs'
                    save(tf/'matched-input-audit.json',{'passed':True,'baseline_capture':str(dest/'capture'),'matching':['case','request_path','database_documents','response','http_status'],'tf_query_plan_sha256':sha(tf/'build'/query['role']/'plan.json'),'same_original_jar':sha(tf/'build'/query['role']/'original.jar')==sha(base/query['role']/'original.jar')})
                    print(json.dumps({'tf':query['id'],'known':result['known'],'targets':result['target_instances'],'matched_input':True}),flush=True)
                except Exception as e:save(tf/'evaluation-error.json',{'error':str(e),'traceback':traceback.format_exc()})
    save(out/'progress.json',{'entries':entries,'complete_scope':False,'remaining_families_are_pending_not_excluded':True})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('out','base','bundle','inventory'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--with-tf',action='store_true');p.add_argument('--port-offset',type=int,default=0);a=p.parse_args();run(a.out.resolve(),a.base.resolve(),a.bundle.resolve(),a.inventory.resolve(),a.with_tf,a.port_offset)
