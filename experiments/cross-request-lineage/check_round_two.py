#!/usr/bin/env python3
"""Known-positive evidence degradation and independent same-value mislabel audit."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from run import HERE,load,save,sha
from analyze import rows


def run(home,predictions,score_dir,out):
    out.mkdir(parents=True,exist_ok=False);positive=load(score_dir/'score.json')
    assert all(r['source_status']=='correct'and r['version_status']in ('correct','N/A')for r in positive['rows'])
    reports=[]
    for cap in sorted((home/'captures/tracefusion').glob('*/*')):
        original=rows(cap/'B/events.jsonl');before=load(predictions/'tracefusion'/cap.parent.name/cap.name/'prediction.json');assert before['state']=='analyzed'
        answers=before['result']['answers'];assert all(a['known']for a in answers)
        history=before['result']['session_history'];by_seq={r['seq']:r for r in original}
        final=answers[-1]
        # Constant clearing has no necessary external data source after the kill;
        # its pre-kill known checkpoint is the source-deletion target instead.
        sourced=next(a for a in reversed(answers)if a['origins'])
        def establishing(answer):
            matches=[r for r in history['reads']if r['root_frame']==answer['root_frame']and r['coordinate'][1]=='lineage/business/Cache$Cell.text']
            if matches:return by_seq[matches[-1]['write_seq']]
            return next(by_seq[v['write_seq']]for v in history['versions']if v['coordinate']==[answer['owner'],answer['field'],answer['version']])
        necessary=establishing(final);source_write=establishing(sourced)
        origin=sourced['origins'][0];assert origin[0]=='http'
        source_row=by_seq[origin[1]];source_field=next(f for f in source_row['fields']if f['path']==origin[2])
        bound=[r for r in original if r['kind']=='binding-input'and r['frame']==source_write['frame'] and any((f['owner'],f['field'],f['version'])==(source_field['owner'],source_field['field'],source_field['version'])for f in r['fields'])]
        assert len(bound)==1,'Necessary source/write binding ambiguous'
        versions=[r for r in original if r['kind']=='read'and r['frame']==final['root_frame']and r.get('field')=='lineage/business/Cache$Cell.text']
        variants=[]
        for regenerate in (False,True):
            variants.append(('delete-required-write',regenerate,[copy.deepcopy(r)for r in original if r['seq']!=necessary['seq']],final))
            variants.append(('delete-required-binding',regenerate,[copy.deepcopy(r)for r in original if r['seq']!=bound[0]['seq']],sourced))
        missing_source=copy.deepcopy(original)
        for r in missing_source:
            if r['seq']==source_row['seq']:r['fields']=[f for f in r['fields']if f['path']!=origin[2]]
        variants.append(('delete-required-external-source-field',True,missing_source,sourced))
        if versions:
            wrong_version=copy.deepcopy(original);read=next(r for r in wrong_version if r['seq']==versions[-1]['seq']);read['version']=max(r.get('version',0)for r in original)+100
            variants.append(('unproved-read-version',True,wrong_version,final))
            donors=[p for p in (home/'captures/tracefusion').glob('*/'+cap.name)if p!=cap]
            assert donors,'Cross-capture identity controls require two independent repetitions'
            donor=donors[0];foreign_rows=rows(donor/'B/events.jsonl')
            matching=[r for r in foreign_rows if r['kind']=='read'and all(r.get(k)==versions[-1].get(k)for k in ('owner','field','version','site'))]
            assert matching,'No real foreign same-number object read available'
            foreign_read=matching[-1]
            save(out/('foreign-donor-'+cap.parent.name+'-'+cap.name+'.json'),{'capture':str(donor),'sha256':sha(donor/'B/events.jsonl'),'actual_foreign_read':foreign_read,'current_read':versions[-1]})
            for component in ('capture_session','process_instance'):
                foreign=copy.deepcopy(original);read=next(r for r in foreign if r['seq']==versions[-1]['seq'])
                read[component]=foreign_read[component]
                variants.append(('foreign-'+component+'-same-object',True,foreign,final))
        for label,regenerate,synthetic,target in variants:
            dest=out/cap.parent.name/cap.name/(label+('-renumbered'if regenerate else'-original-sequence'));dest.mkdir(parents=True)
            if regenerate:
                for i,r in enumerate(synthetic,1):r['seq']=i
                synthetic[-1]['session_history_event_count']=len(synthetic)
            event_file=dest/'synthetic-events.jsonl';event_file.write_text(''.join(json.dumps(r)+'\n'for r in synthetic))
            save(dest/'synthetic-receipt.json',{'synthetic_evidence':True,'original_capture':str(cap),'original_sha256':sha(cap/'B/events.jsonl'),'mutation':label,'sequence_and_event_count_regenerated':regenerate,'original_target':target,'object_identity_preserved':True})
            cmd=[sys.executable,str(HERE/'replay_round_two.py'),'--plan',str(home/'build/tf/B/plan.json'),'--events',str(event_file),'--out',str(dest/'prediction')]
            p=subprocess.run(cmd,capture_output=True,text=True);(dest/'process.log').write_text(p.stdout+p.stderr);assert p.returncode==0
            answer=load(dest/'prediction/prediction.json')
            if answer['state']=='rejected':state='rejected';reason=answer['error']
            else:
                candidates=[a for a in answer['result']['answers']if a['root_frame']==target['root_frame']and a['path']==target['path']]
                assert len(candidates)==1 and not candidates[0]['known'],(label,cap,candidates)
                state='unknown';reason='Exact necessary write/source version is not proved'
            transport=not regenerate and label in ('delete-required-write','delete-required-binding')
            if transport:assert answer['state']=='rejected'and ('sequence'in reason or 'count'in reason)
            reports.append({'repeat':cap.parent.name,'case':cap.name,'mutation':label,'regenerated':regenerate,'positive_before':'known_correct','state':state,'reason':reason,'classification':'evidence_invalid'if transport else'semantic_missing_evidence','derived':str(dest)})
    # The wrapping mistake is in a saved prediction copy; the real run and
    # original native/TF labels remain untouched. Version correctness cannot hide it.
    wrong=out/'wrong-source-wrapper';shutil.copytree(predictions,wrong,copy_function=lambda a,b:Path(b).symlink_to(Path(a).resolve()))
    replacements=0
    for path in sorted(wrong.glob('tracefusion/*/same-object-overwrite/prediction.json')):
        result=load(path);old=result['result']['answers'][0]['origins'];target=result['result']['answers'][-1]
        assert target['known']and target['origins']!=old
        target['origins']=copy.deepcopy(old);path.unlink();save(path,result);replacements+=1
    cmd=[sys.executable,str(HERE/'score_round_two.py'),'--run',str(home),'--predictions',str(wrong),'--out',str(out/'wrong-source-score')]
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'wrong-source-score.log').write_text(p.stdout+p.stderr);assert p.returncode!=0
    wrong_rows=[r for r in load(out/'wrong-source-score/score.json')['rows']if r['source_status']=='wrong']
    assert len(wrong_rows)==replacements and all(r['version_status']=='correct'for r in wrong_rows)
    # Re-evaluate the untouched original files after all derived mutations.
    cmd=[sys.executable,str(HERE/'score_round_two.py'),'--run',str(home),'--predictions',str(predictions),'--out',str(out/'original-positive-recheck')]
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'original-positive-recheck.log').write_text(p.stdout+p.stderr);assert p.returncode==0
    save(out/'results.json',{'known_positive_required':True,'negative_checks':reports,'wrong_wrapper_rejected':wrong_rows,'original_positive_still_correct':True,'strict_MT_version_and_offline_negative':'N/A'})
    print(json.dumps({'degradation_checks':len(reports),'states':{k:sum(r['state']==k for r in reports)for k in ('unknown','rejected')},'wrong_source_wrappers_detected':len(wrong_rows),'original_positive_still_correct':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--scores',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.run.resolve(),a.predictions.resolve(),a.scores.resolve(),a.out.resolve())
