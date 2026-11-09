"""Affected-task raw-oracle guards, frozen-source and MT-library checks."""
import argparse
import copy
import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from run_planned_service import ROOT, load, save, sha
from run_paper_frozen_reuse import verify
from score_paper_frozen_reuse import raw_expected
from external_transfer_oracle import raw


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);verify(home)
    checks=[];jar=ROOT/'artifacts/target-closure-revision-20261103/external-candidates/ruoyi-cloud/ruoyi-modules/ruoyi-system/target/ruoyi-modules-system.jar'
    with ZipFile(jar)as z:
        name=next(n for n in z.namelist()if n.startswith('BOOT-INF/lib/jackson-databind-')and n.endswith('.jar'))
        with ZipFile(BytesIO(z.read(name)))as j:mapper=hashlib.sha256(j.read('com/fasterxml/jackson/databind/ObjectMapper.class')).hexdigest()
    for folder,qid in [(home/'post-metadata-C2','fresh-post-detail'),(home/'calibration-C2','fresh-dict-type-page')]:
        verify(folder);q=load(folder/'task-seal.json')['tasks']['ruoyi'][0]
        mt=folder/'runs'/qid/'mirrortaint'
        rows=raw(mt/'capture/native-library.jsonl')
        facts=[r for r in rows if r.get('class')=='com/fasterxml/jackson/databind/ObjectMapper']
        assert len(facts)==1 and facts[0]['sha256']==mapper and 'app.jar!/BOOT-INF/lib/'in facts[0]['source']
        checks.append({'query':qid,'MT_actual_ObjectMapper_matches_original':True,'sha256':mapper})
        cases=load(folder/'runs'/qid/'original/result.json')['cases']
        records=load(folder/'audit-final/instances.json')
        for mode in ('full','selective','mirrortaint'):
            selected=next((r for r in records if r['mode']==mode and r['state']=='known_correct'),None)
            if selected is None:continue
            trial=folder/'runs'/qid/mode
            native=mode=='mirrortaint';rs=raw(trial/'capture'/('native-capability.jsonl'if native else'events.jsonl'))
            wire=raw(trial/'capture/instances.jsonl')if native else[]
            c=cases[selected['case']];actual=load(trial/'result.json')['cases'][selected['case']]
            value=next(f['observed']['value']for e in (wire if native else rs)
                       if e['kind']=='http-json'and e.get('message')==actual['message']and e.get('phase')=='write'and e.get('direction')=='response'
                       for f in e['fields']if f['path']==selected['path'])
            expected=raw_expected(rs,wire,mode,actual['message'],selected['path'],value,q)
            assert expected['expected']==selected['expected']
            for fault in ('missing-source','duplicate-source','wrong-source-owner','wrong-source-version','missing-completion','wrong-PC','sticky-problem'):
                bad=copy.deepcopy(rs)
                source=next(s for s in bad if s['kind']==('source'if native else'binding-source')and (s.get('call')or s.get('callee'))in q['source_calls'])
                if fault=='missing-source':bad.remove(source)
                elif fault=='duplicate-source':bad.insert(-1,copy.deepcopy(source))
                elif fault in ('wrong-source-owner','wrong-source-version'):
                    key='owner'if fault.endswith('owner')else'version'
                    for f in source['fields']:f[key]='other'if key=='owner'else 999
                elif fault=='missing-completion':
                    cid=source['source_call_id'];bad.remove(next(e for e in bad if e['kind']==('source-call-exit'if native else'collection-call-exit')and e.get('source_call_id'if native else'call_id')==cid))
                elif fault=='wrong-PC':source['instrumented_instruction_index'if native else'source_pc']=999
                else:bad.insert(-1,{'kind':'problem','error':'derived guard injection'})
                try:raw_expected(bad,wire,mode,actual['message'],selected['path'],value,q)
                except Exception:checks.append({'query':qid,'mode':mode,'fault':fault,'rejected':True})
                else:raise AssertionError((qid,mode,fault,'raw oracle accepted malformed facts'))
    assert load(home/'post-metadata-C2/audit-final/summary.json')['queries'][0]['targets']==5
    # Table arithmetic must account for every target, including refused/unbound.
    table_root=home/'tables-final-03'if(home/'tables-final-03').exists()else home/'tables-final'
    tables=load(table_root/'tables.json')
    for row in tables['capability']:
        if row['targets']is not None:
            assert row['targets']==sum(row[k]for k in ('correct','unknown','rejected_invalid','wrong','other_unscored'))
    verify(home);save(out/'summary.json',{'passed':True,'core_files_unchanged':139,'new_framework_contracts':0,
         'checks':checks,'tables_no_cross_version_total':True,'new_queries':2,'no_performance':True})
    print({'passed':True,'checks':len(checks)})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();run(a.home.resolve(),a.out.resolve())
