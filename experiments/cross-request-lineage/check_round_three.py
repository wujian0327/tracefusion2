#!/usr/bin/env python3
"""Derived evidence tests ONLY after the corresponding source/version is known."""
import argparse
from collections import Counter
import copy
from pathlib import Path
import shutil
import sys
from run import HERE,load,save,sha,command
from analyze import rows


def check(home,predictions,scores,out):
    out.mkdir(parents=True,exist_ok=False);scored=load(scores/'score.json')['rows'];checks=[];caps=sorted((home/'captures/tracefusion').glob('*/*'))
    for cap in caps:
        if cap.name=='same-trace-no-cache':continue # never count unknown->unknown
        gate=[r for r in scored if r['mode']=='tracefusion'and r['repeat']==cap.parent.name and r['case']==cap.name]
        assert gate and all(r['source_status']==r['version_status']=='correct'for r in gate)
        raw={r:rows(cap/r/'events.jsonl')for r in ('A','B')};p=load(predictions/'tracefusion'/cap.parent.name/cap.name/'prediction.json');q=p['queries'][-1];sourced=q if q['sources']else next(v for v in p['queries']if v['known']and v['sources'])
        origin=sourced['sources'][0];amessage=origin['message'];arpc=next(r for r in raw['A']if r['kind']=='http-json'and r['direction']=='request'and r['phase']=='write'and r['parent_message']==amessage);bmessage=arpc['message']
        bs=next(r for r in raw['B']if r['kind']=='http-json'and r['direction']=='request'and r['message']==bmessage)
        local=p['local_results']['B'];answer=local['answers'][-1];hist=local['session_history'];reads=[r for r in hist['reads']if r['root_frame']==answer['root_frame']and r['coordinate'][1]=='lineage/business/Cache$Cell.text']
        if reads:write=next(r for r in raw['B']if r['seq']==reads[0]['write_seq'])
        else:write=next(r for r in raw['B']if r['kind']=='write'and(r['owner'],r['field'],r['version'])==(answer['owner'],answer['field'],answer['version']))
        bindings=[r for r in raw['B']if r['kind']=='binding-input'and r.get('message')==bmessage];assert bindings
        required_binding=bindings[0]
        variants=[('delete-history-write','B',{write['seq']},q),('delete-actual-send','A',{next(r['seq']for r in raw['A']if r['kind']=='http-exchange'and r['message']==bmessage and r['direction']=='request'and r['phase']=='write')},sourced),('delete-actual-receive','B',{next(r['seq']for r in raw['B']if r['kind']=='http-exchange'and r['message']==bmessage and r['direction']=='request')},sourced),('delete-sent-field-map','A',{arpc['seq']},sourced),('delete-history-input-binding','B',{required_binding['seq']},sourced),('delete-external-input','A',{r['seq']for r in raw['A']if r['kind']in ('http-json','http-exchange')and r.get('message')==amessage and r.get('direction')=='request'},sourced)]
        def evaluate(name,decoded,target,regenerated=True,extra=None):
            dest=out/cap.parent.name/cap.name/name;dest.mkdir(parents=True)
            if regenerated:
                for rs in decoded.values():
                    for i,r in enumerate(rs,1):r['seq']=i
                    for r in rs:
                        if r['kind']=='metrics':
                            for k in ('session_history_event_count','http_exchange_event_count'):
                                if k in r:r[k]=len(rs)
            for role,rs in decoded.items():(dest/(role+'.jsonl')).write_text(''.join(__import__('json').dumps(r)+'\n'for r in rs))
            save(dest/'synthetic.json',{'synthetic_evidence':True,'mutation':name,'regenerated_sequence_and_counts':regenerated,'original_sha256':{r:sha(cap/r/'events.jsonl')for r in raw},'positive_before':'known_correct','target_message':target['target']['message'],'details':extra})
            command([sys.executable,HERE/'replay_round_three.py','--run',home,'--capture',cap,'--events',dest,'--out',dest/'prediction'],dest/'analysis.log')
            result=load(dest/'prediction/prediction.json');qs=[v for v in result.get('queries',[])if v['target']['message']==target['target']['message']]
            state='rejected'if result['state']=='rejected'else'unknown'if len(qs)==1 and not qs[0]['known']else'wrong_known_or_missing'
            checks.append({'repeat':cap.parent.name,'case':cap.name,'mutation':name,'positive_before':'known_correct','state':state,'reason':result.get('error','Unbound necessary communication/source dependency'),'derived':str(dest),'regenerated':regenerated});save(out/'progress.json',checks)
            assert state in ('unknown','rejected'),checks[-1]
        for name,role,removed,target in variants:
            for regenerate in (False,True):
                bad=copy.deepcopy(raw);bad[role]=[r for r in bad[role]if r['seq']not in removed];evaluate(name+('-regenerated'if regenerate else'-original-sequence'),bad,target,regenerate)
        bad=copy.deepcopy(raw);row=next(r for r in bad['B']if r['seq']==bs['seq']);fields={f['path']:f for f in row['fields']};assert fields['/value']['observed']['value']==fields['/fallback']['observed']['value'];fields['/value']['path'],fields['/fallback']['path']='/fallback','/value';evaluate('equal-value-swapped-field-mapping',bad,sourced)
        bad=copy.deepcopy(raw);previous=next(r for r in raw['B']if r['kind']=='http-json'and r['direction']=='request'and r.get('message')!=bmessage)
        for r in bad['B']:
            if r['kind']in ('http-exchange','http-json')and r.get('message')==bmessage and r.get('direction')=='request':r['connection']=previous['connection']
        evaluate('foreign-message-connection',bad,sourced,extra={'donor_actual_event':previous})
        bad=copy.deepcopy(raw);bad['B'][1]['process_instance']='synthetic-foreign-process';evaluate('foreign-process-event',bad,q)
        donors=[c for c in caps if c.name==cap.name and c.parent.name!=cap.parent.name]
        if donors:
            donor=donors[0];bad=copy.deepcopy(raw);bad['B']=rows(donor/'B/events.jsonl');collision={r['owner']for r in raw['B']if r['kind']=='write'}&{r['owner']for r in bad['B']if r['kind']=='write'};assert collision
            evaluate('foreign-capture-same-object-numbers',bad,q,extra={'donor':str(donor),'donor_sha256':sha(donor/'B/events.jsonl'),'actual_colliding_object_ids':sorted(collision)})
    # A malicious reporting wrapper can lie without altering evidence: truth must
    # detect the wrong field even when value and physical versions are correct.
    wrong=out/'wrong-field-wrapper';shutil.copytree(predictions,wrong)
    for p in wrong.glob('tracefusion/*/same-object-overwrite/prediction.json'):
        d=load(p);target=d['queries'][-1];assert target['known']and target['sources'][0]['path']=='/value';target['sources'][0]['path']='/fallback';save(p,d)
    command([sys.executable,HERE/'score_round_three.py','--run',home,'--predictions',wrong,'--out',out/'wrong-wrapper-score','--allow-wrong'],out/'wrong-wrapper-score.log')
    wrong_rows=[r for r in load(out/'wrong-wrapper-score/score.json')['rows']if r['source_status']=='wrong'];assert len(wrong_rows)==len(list(wrong.glob('tracefusion/*/same-object-overwrite/prediction.json')))
    command([sys.executable,HERE/'score_round_three.py','--run',home,'--predictions',predictions,'--out',out/'original-positive-recheck'],out/'positive-recheck.log')
    save(out/'results.json',{'checks':checks,'states':dict(Counter(r['state']for r in checks)),'wrong_wrappers_detected':wrong_rows,'original_positive_still_correct':True,'unseeded_unknown_not_counted':True,'mirror_strict_version_and_offline_deletion':'N/A'});print(Counter(r['state']for r in checks))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--scores',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();check(a.run.resolve(),a.predictions.resolve(),a.scores.resolve(),a.out.resolve())
