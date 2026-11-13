#!/usr/bin/env python3
"""Prediction side: reads only plans and captures. No oracle/workload imports."""
import argparse
import copy
import json
from pathlib import Path
import sys
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'experiments/sockshop-mirrortaint'))
from infer_distributed_fields import Reconstruction


def save(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def rows(p):return [json.loads(line) for line in p.read_text().splitlines()]


def tf(build,capture,dest,decoded=None):
    try:
        g=Reconstruction(build,capture,['A','B'],decoded_rows=decoded)
        save(dest/'graph.json',g.export())
        queries=[]
        for role in ('A','B'):
            for row in g.rows[role]:
                if row['kind']!='http-json' or row['direction']!='response' or row['phase']!='write':continue
                if not any(f['path']=='/text' for f in row['fields']):continue
                a=g.query(row['message'],'/text',role,boundary=[{'kind':'http-json','service':'A','direction':'request','phase':'read'}])
                local=g.query(row['message'],'/text',role)
                a['path_edges']=g.path_edges(a['target_key'])
                # This is diagnostic only: a B-local boundary is not an external source.
                a['unrestricted_leaf_diagnostic']=local
                blocked=[{'key':n['key'],'reason':n.get('unknown')} for n in g.export()['nodes'] if n.get('unknown')]
                queries.append({'role':role,'message':row['message'],'answer':a,'unknown_nodes':blocked})
        result={'status':'analyzed','queries':queries,'oracle_consumed':False}
    except Exception as e:
        result={'status':'analysis_error','error':str(e),'error_type':type(e).__name__,'traceback':traceback.format_exc(),'oracle_consumed':False}
    save(dest/'prediction.json',result)


def main(run):
    def oracle_guard(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)) and Path(args[0]).name in ('expected.json','workload.json'):
            raise RuntimeError('Analyzer attempted to read oracle/workload')
    sys.addaudithook(oracle_guard)
    output=run/'predictions';output.mkdir(exist_ok=False)
    for cap in sorted((run/'captures/tracefusion').glob('*/*')):
        dest=output/'tracefusion'/cap.parent.name/cap.name;dest.mkdir(parents=True)
        tf(run/'build/tf',cap,dest)
        # Evidence deletion is a derived control, never a replacement capture.
        decoded={r:rows(cap/r/'events.jsonl') for r in ('A','B')}
        writes=[r for r in decoded['B'] if r['kind']=='write' and r.get('field')=='lineage/business/Cache$Cell.text']
        if len(writes)>=2:
            bad=copy.deepcopy(decoded);removed=writes[1]
            bad['B']=[r for r in bad['B'] if r['seq']!=removed['seq']]
            for index,r in enumerate(bad['B'],1):r['seq']=index
            negative=dest/'drop-second-field-write';negative.mkdir()
            save(negative/'deletion.json',{'removed_original_event':removed,'seq_renumbered':True,'raw_capture_untouched':True})
            for role,rs in bad.items():(negative/(role+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rs))
            tf(run/'build/tf',cap,negative,decoded=bad)
    for cap in sorted((run/'captures/mirrortaint').glob('*/*')):
        dest=output/'mirrortaint'/cap.parent.name/cap.name;dest.mkdir(parents=True)
        native={r:rows(cap/r/'native.jsonl') if (cap/r/'native.jsonl').exists() else [] for r in ('A','B')}
        save(dest/'prediction.json',{'status':'native_export','native':native,'oracle_consumed':False,
                                  'source_configuration':'tagManually only on A external /value and /fallback',
                                  'strict_field_version_query':'unavailable in exported public native tag API',
                                  'missing_write_evidence_control':'not applicable to online native labels; no field-write event input'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);main(p.parse_args().run.resolve())
