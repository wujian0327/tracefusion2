#!/usr/bin/env python3
"""Independent unchanged logical oracle; no labels/TF graph decide truth."""
import argparse,collections,json,shutil,sys,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.append(str(ROOT/'scripts'))
import external_transfer_oracle as oracle
from infer_distributed_fields import Reconstruction
from analysis_status import AnalysisLimit
FIRST=ROOT/'artifacts/external-frozen-transfer-20261029'
def load(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

def evaluate(home,api,mode,index,out):
    out.mkdir(parents=True,exist_ok=False);receipt=load(home/'planning-first'/api/('%03d.json'%index));q=receipt['query'];role=q['role'];h=home/'tool-runs'/api/mode/('query-%03d'%index)
    run=load(h/'results.json');assert run.get('cleanup_returncode')==0,'Capture not closed'
    (out/'build'/role).mkdir(parents=True);(out/'capture'/role).mkdir(parents=True)
    shutil.copyfile(home/'planning-first'/api/('%03d-plan.json'%index),out/'build'/role/'plan.json')
    (out/'capture'/role/'events.jsonl').symlink_to((h/'capture/events.jsonl').resolve())
    rows=oracle.raw(h/'capture/events.jsonl');graph=None;error=None
    try:graph=Reconstruction(out/'build',out/'capture',[role])
    except Exception as e:error=e
    task=next(x for x in load(FIRST/'task-seal.json')['entries']if x['id']==api)
    original=load(FIRST/'ae7fe8d/original'/task['application']/('sealed-'+api)/'results.json')
    protocol=load(FIRST/'oracle-before-tools.json');scored=[]
    for before in original['cases']:
        if not oracle.original_root_returns(before):continue
        current=next((c for c in run['cases']if c['case']==before['case']),None)
        for path,value in oracle.targets(before['response']):
            if oracle.wildcard(path)!=q['path']:continue
            record={'api':api,'mode':mode,'query_index':index,'case':before['case'],'path':path,'oracle_adequate':False,'state':'unknown'};want=None
            try:
                oracle.require_complete_raw_capture(rows)
                returns=[r for r in rows if r['kind']=='binding-return'and current and r.get('message')==current['message']]
                if len(returns)!=1:raise ValueError('Actual root return absent/ambiguous')
                want=oracle.tf_expected(rows,returns[0],oracle.rule(protocol,api,path),path)
                record.update(expected=want,oracle_adequate=True,positive=bool(want))
            except ValueError as e:record['oracle_gap']=str(e)
            if current is None:record.update(state='environment_failure',error=run.get('error'))
            elif current['http_status']!=before['http_status']:record['state']='instrumented_business_failure'
            elif error:record.update(state='analysis_limited'if isinstance(error,AnalysisLimit)else'evidence_invalid',error=str(error))
            else:
                try:
                    answer=graph.query(current['message'],path,role,boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}])
                    record['answer']=answer
                    if answer['known']:
                        actual={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in answer['sources']}
                        expected={tuple(v)for v in want}if want is not None else None
                        record['state']='known_unchecked'if expected is None else'known_correct'if actual==expected else'known_wrong'
                        if expected is not None:record.update(TP=len(actual&expected),FP=len(actual-expected),FN=len(expected-actual))
                except Exception as e:record.update(state='analysis_limited'if isinstance(e,AnalysisLimit)else'evidence_invalid',error=str(e))
            scored.append(record)
    summary={'api':api,'mode':mode,'query_index':index,'states':dict(collections.Counter(x['state']for x in scored)),'positive_correct':sum(x['state']=='known_correct'and x.get('positive',False)for x in scored),'sources':sum(r['kind']=='binding-source'for r in rows),'direct_dispatch_facts':sum(r['kind']=='execution-direct-dispatch'for r in rows),'problems':[r for r in rows if r['kind']=='problem'],'first_and_C1_unchanged':True}
    save(out/'instances.json',scored);save(out/'summary.json',summary);print(summary,flush=True);return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--api',required=True);p.add_argument('--mode',required=True);p.add_argument('--index',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();evaluate(a.home.resolve(),a.api,a.mode,a.index,a.out.resolve())
